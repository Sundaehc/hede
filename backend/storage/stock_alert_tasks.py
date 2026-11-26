"""Persist alert follow-up work independently of the live alert calculation."""
from datetime import datetime, time, timedelta, timezone

from sqlalchemy import (JSON, CheckConstraint, Column, Date, DateTime, ForeignKey,
                        Index, Integer, MetaData, Table, Text, case, func, insert,
                        inspect, select, update)
from sqlalchemy.exc import IntegrityError

from storage.stock_operating_rules import CLEARANCE, META as OPERATING_META, lock_stock_decision


METADATA = MetaData()
TASK_KIND_SQL = "kind IN ('zero', 'slow', 'replenish', 'clearance')"
TASK_KIND_CHECK = "ck_stock_alert_tasks_kind"
TASKS = Table(
    "stock_alert_tasks", METADATA,
    Column("id", Integer, primary_key=True),
    Column("brand", Text, nullable=False), Column("product_id", Integer, nullable=False),
    Column("kind", Text, nullable=False), Column("sku", Text, nullable=False),
    Column("original_sku", Text), Column("product_name", Text), Column("color", Text),
    Column("snapshot", JSON, nullable=False),
    # NULL releases the unique slot on completion, on both PostgreSQL and SQLite.
    Column("active_key", Text, unique=True),
    Column("assignee_id", Integer, nullable=False), Column("assignee_name", Text, nullable=False),
    Column("due_date", Date, nullable=False), Column("status", Text, nullable=False),
    Column("measures", Text, nullable=False), Column("result", Text, nullable=False),
    Column("version", Integer, nullable=False),
    Column("created_by", Integer, nullable=False), Column("updated_by", Integer, nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("updated_at", DateTime(timezone=True), nullable=False),
    Column("completed_at", DateTime(timezone=True)),
    CheckConstraint(TASK_KIND_SQL, name=TASK_KIND_CHECK),
    CheckConstraint("status IN ('pending', 'processing', 'completed')"),
    CheckConstraint("(status = 'completed' AND active_key IS NULL) OR (status <> 'completed' AND active_key IS NOT NULL)"),
)
Index("ix_stock_alert_tasks_owner_due", TASKS.c.assignee_id, TASKS.c.status, TASKS.c.due_date)
Index("ix_stock_alert_tasks_brand_due", TASKS.c.brand, TASKS.c.status, TASKS.c.due_date)
EVENTS = Table(
    "stock_alert_task_events", METADATA,
    Column("id", Integer, primary_key=True),
    Column("task_id", Integer, ForeignKey("stock_alert_tasks.id"), nullable=False),
    Column("actor_id", Integer, nullable=False), Column("actor_name", Text, nullable=False),
    Column("action", Text, nullable=False), Column("changes", JSON, nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
)
Index("ix_stock_alert_task_events_task", EVENTS.c.task_id, EVENTS.c.id)


def business_today():
    return datetime.now(timezone(timedelta(hours=8))).date()


class TaskConflict(ValueError):
    pass


def public_task(row, today):
    item = dict(row)
    item.pop("active_key", None)
    item["overdue"] = item["status"] != "completed" and item["due_date"] < today
    for key in ("created_at", "updated_at", "completed_at"):
        if item.get(key) is not None and item[key].tzinfo is None:
            item[key] = item[key].replace(tzinfo=timezone.utc)
    return item


def _changes(values):
    return {key: value.isoformat() if hasattr(value, "isoformat") else value
            for key, value in values.items()
            if key in {"assignee_id", "assignee_name", "due_date", "status", "measures", "result"}}


class StockAlertTaskRepository:
    def __init__(self, engine):
        self.engine = engine

    def create_tables(self):
        METADATA.create_all(self.engine)
        OPERATING_META.create_all(self.engine)
        if self.engine.dialect.name == "postgresql":
            # These tables are provisioned at app startup (not by the Alembic chain).
            with self.engine.begin() as connection:
                checks = inspect(connection).get_check_constraints(TASKS.name)
                if not any(check["name"] == TASK_KIND_CHECK for check in checks):
                    connection.exec_driver_sql("LOCK TABLE stock_alert_tasks IN ACCESS EXCLUSIVE MODE")
                    checks = inspect(connection).get_check_constraints(TASKS.name)
                    if any(check["name"] == TASK_KIND_CHECK for check in checks):
                        return
                    for check in checks:
                        sql = check.get("sqltext") or ""
                        if "kind" in sql and "'zero'" in sql and "'slow'" in sql:
                            name = connection.dialect.identifier_preparer.quote(check["name"])
                            connection.exec_driver_sql(f"ALTER TABLE stock_alert_tasks DROP CONSTRAINT {name}")
                    connection.exec_driver_sql(f"ALTER TABLE stock_alert_tasks ADD CONSTRAINT {TASK_KIND_CHECK} CHECK ({TASK_KIND_SQL})")

    def _event(self, connection, task_id, actor, action, values, now):
        connection.execute(insert(EVENTS).values(
            task_id=task_id, actor_id=actor["id"],
            actor_name=actor.get("display_name") or actor.get("username") or str(actor["id"]),
            action=action, changes=_changes(values), created_at=now))

    def _create_on(self, connection, *, snapshot, kind, assignee, due_date, measures, actor):
        if kind in {"replenish", "clearance"}:
            lock_stock_decision(connection, snapshot["brand"], snapshot["id"])
            if kind == "replenish" and connection.execute(select(CLEARANCE.c.confirmed).where(
                CLEARANCE.c.brand == snapshot["brand"], CLEARANCE.c.product_id == snapshot["id"],
            )).scalar_one_or_none():
                raise TaskConflict("商品组已确认清仓，不能分配补货待办")
            other = "replenish" if kind == "clearance" else "clearance"
            existing = connection.execute(select(TASKS.c.id).where(TASKS.c.active_key ==
                f"{snapshot['brand']}:{snapshot['id']}:{other}")).scalar_one_or_none()
            if existing is not None:
                raise TaskConflict(f"该商品已有相反的未完成待办（#{existing}），请先核对现有待办")
        now = datetime.now(timezone.utc)
        key = f"{snapshot['brand']}:{snapshot['id']}:{kind}"
        values = dict(
            brand=snapshot["brand"], product_id=snapshot["id"], kind=kind,
            sku=snapshot["sku"], original_sku=snapshot.get("original_sku"),
            product_name=snapshot.get("product_name"), color=snapshot.get("color"),
            snapshot=snapshot, active_key=key, assignee_id=assignee["id"],
            assignee_name=assignee.get("display_name") or assignee["username"],
            due_date=due_date, measures=measures, result="", status="pending", version=1,
            created_by=actor["id"], updated_by=actor["id"], created_at=now, updated_at=now,
        )
        row = connection.execute(insert(TASKS).values(**values).returning(TASKS)).mappings().one()
        self._event(connection, row["id"], actor, "created", values, now)
        return public_task(row, business_today())

    def create(self, **kwargs):
        snapshot, kind = kwargs["snapshot"], kwargs["kind"]
        key = f"{snapshot['brand']}:{snapshot['id']}:{kind}"
        try:
            with self.engine.begin() as connection:
                item = self._create_on(connection, **kwargs)
        except IntegrityError:
            with self.engine.connect() as connection:
                existing = connection.execute(select(TASKS.c.id).where(TASKS.c.active_key == key)).scalar_one_or_none()
            if existing is not None:
                raise TaskConflict(f"该商品已有未完成待办（#{existing}），请查看现有待办") from None
            raise
        return item

    def create_many(self, snapshots, *, kind, **kwargs):
        saved, failed = self.create_many_by_kind(((snapshot, kind) for snapshot in snapshots), **kwargs)
        return saved, [{key: value for key, value in item.items() if key != "kind"} for item in failed]

    def create_many_by_kind(self, entries, **kwargs):
        # Consistent lock order avoids deadlocks when operators pick the same rows in different orders.
        ordered = sorted(enumerate(entries), key=lambda entry: (
            entry[1][0]["brand"], entry[1][0]["id"], entry[1][1]))
        if not ordered:
            return [], []
        saved, failed = {}, {}
        with self.engine.begin() as connection:
            # SQLite's legacy driver otherwise releases the first SAVEPOINT as a commit.
            if connection.dialect.name == "sqlite":
                connection.exec_driver_sql("BEGIN")
            for index, (snapshot, kind) in ordered:
                try:
                    with connection.begin_nested():
                        item = self._create_on(connection, snapshot=snapshot, kind=kind, **kwargs)
                except (IntegrityError, TaskConflict) as error:
                    if isinstance(error, TaskConflict):
                        reason = str(error)
                    else:
                        key = f"{snapshot['brand']}:{snapshot['id']}:{kind}"
                        existing = connection.execute(select(TASKS.c.id).where(TASKS.c.active_key == key)).scalar_one_or_none()
                        if existing is None:
                            raise
                        reason = f"已有未完成待办（#{existing}），请查看现有待办"
                    failed[index] = {"id": snapshot["id"], "label": snapshot["sku"], "kind": kind, "reason": reason}
                else:
                    saved[index] = item
        return [saved[i] for i in sorted(saved)], [failed[i] for i in sorted(failed)]

    def get(self, task_id):
        with self.engine.connect() as connection:
            row = connection.execute(select(TASKS).where(TASKS.c.id == task_id)).mappings().first()
        return public_task(row, business_today()) if row else None

    def get_many(self, task_ids):
        with self.engine.connect() as connection:
            rows = connection.execute(select(TASKS).where(TASKS.c.id.in_(task_ids))).mappings()
            return {row["id"]: public_task(row, business_today()) for row in rows}

    def events(self, task_id, *, page=1, page_size=20):
        with self.engine.connect() as connection:
            total = connection.execute(select(func.count()).select_from(EVENTS).where(EVENTS.c.task_id == task_id)).scalar_one()
            rows = list(connection.execute(select(EVENTS).where(EVENTS.c.task_id == task_id)
                        .order_by(EVENTS.c.id.desc()).offset((page - 1) * page_size).limit(page_size)).mappings())
        items = [dict(row) for row in rows]
        for item in items:
            if item["created_at"].tzinfo is None:
                item["created_at"] = item["created_at"].replace(tzinfo=timezone.utc)
        return {"items": items, "total": total, "page": page, "page_size": page_size}

    def _save_on(self, connection, task_id, *, version, values, actor):
        now = datetime.now(timezone.utc)
        changes = dict(values, version=version + 1, updated_by=actor["id"], updated_at=now)
        if values.get("status") == "completed":
            changes.update(active_key=None, completed_at=now)
        row = connection.execute(update(TASKS).where(
            TASKS.c.id == task_id, TASKS.c.version == version, TASKS.c.status != "completed",
        ).values(**changes).returning(TASKS)).mappings().first()
        if row is None:
            raise TaskConflict("待办已被其他页面修改或已完成，请重新打开后处理；当前填写内容尚未保存")
        self._event(connection, task_id, actor, "completed" if values.get("status") == "completed" else "updated", values, now)
        return public_task(row, business_today())

    def save(self, task_id, **kwargs):
        with self.engine.begin() as connection:
            return self._save_on(connection, task_id, **kwargs)

    def save_many(self, entries, *, actor):
        saved, failed = [], []
        with self.engine.begin() as connection:
            for entry in entries:
                try:
                    item = self._save_on(connection, entry["id"], version=entry["version"], values=entry["values"], actor=actor)
                except TaskConflict as error:
                    failed.append({"id": entry["id"], "label": entry["label"], "reason": str(error)})
                else:
                    saved.append(item)
        return saved, failed

    def active_for(self, brand, kind, product_ids):
        if not product_ids:
            return {}
        with self.engine.connect() as connection:
            rows = connection.execute(select(TASKS).where(
                TASKS.c.brand == brand, TASKS.c.kind == kind,
                TASKS.c.product_id.in_(product_ids), TASKS.c.active_key.is_not(None))).mappings()
            return {row["product_id"]: {key: value for key, value in public_task(row, business_today()).items()
                    if key in {"id", "status", "assignee_name", "due_date", "overdue"}} for row in rows}

    def overview_active(self, brand):
        with self.engine.connect() as connection:
            rows = connection.execute(select(TASKS.c.id, TASKS.c.product_id, TASKS.c.kind,
                TASKS.c.status, TASKS.c.assignee_name, TASKS.c.due_date).where(
                TASKS.c.brand == brand, TASKS.c.active_key.is_not(None))).mappings()
            today = business_today()
            return {(row["product_id"], row["kind"]): {"id": row["id"], "status": row["status"],
                "assignee_name": row["assignee_name"], "due_date": row["due_date"],
                "overdue": row["due_date"] < today} for row in rows}

    def overview_week(self, brand, first, last):
        zone = timezone(timedelta(hours=8))
        start, stop = (datetime.combine(day, time.min, zone).astimezone(timezone.utc)
                       for day in (first, last + timedelta(days=1)))
        created = (TASKS.c.created_at >= start) & (TASKS.c.created_at < stop)
        completed = (TASKS.c.completed_at >= start) & (TASKS.c.completed_at < stop)
        overdue = (TASKS.c.created_at < stop) & (TASKS.c.due_date <= last) & (
            TASKS.c.completed_at.is_(None) | (TASKS.c.completed_at >= stop))
        with self.engine.connect() as connection:
            summary = dict(connection.execute(select(*[func.coalesce(func.sum(case((where, 1), else_=0)), 0).label(key)
                for key, where in (("created", created), ("completed", completed), ("overdue", overdue))])
                .where(TASKS.c.brand == brand)).mappings().one())
            rows = list(connection.execute(select(TASKS.c.product_id, TASKS.c.kind).distinct()
                .where(TASKS.c.brand == brand, completed)))
            return summary, {product for product, _ in rows}, {product for product, kind in rows if kind == "clearance"}

    def list(self, *, user_id, scope, status, brand, kind, query, page, page_size):
        today = business_today()
        conditions = []
        if scope == "mine":
            conditions.append(TASKS.c.assignee_id == user_id)
        if brand:
            conditions.append(TASKS.c.brand == brand)
        if kind:
            conditions.append(TASKS.c.kind == kind)
        if query.strip():
            conditions.append(func.coalesce(TASKS.c.sku, "").icontains(query.strip(), autoescape=True)
                | func.coalesce(TASKS.c.original_sku, "").icontains(query.strip(), autoescape=True)
                | func.coalesce(TASKS.c.product_name, "").icontains(query.strip(), autoescape=True)
                | func.coalesce(TASKS.c.color, "").icontains(query.strip(), autoescape=True)
                | TASKS.c.assignee_name.icontains(query.strip(), autoescape=True))
        open_condition = TASKS.c.status != "completed"
        flags = {"open": open_condition, "overdue": open_condition & (TASKS.c.due_date < today),
                 "completed": TASKS.c.status == "completed"}
        with self.engine.connect() as connection:
            counts = dict(connection.execute(select(*[
                func.coalesce(func.sum(case((condition, 1), else_=0)), 0).label(name)
                for name, condition in flags.items()]).where(*conditions)).mappings().one())
            total = sum((counts["open"], counts["completed"])) if status == "all" else counts[status]
            page = min(page, max(1, (total + page_size - 1) // page_size))
            rows = list(connection.execute(select(TASKS).where(*conditions, *([] if status == "all" else [flags[status]]))
                .order_by(case((open_condition, 0), else_=1), TASKS.c.due_date, TASKS.c.id)
                .offset((page - 1) * page_size).limit(page_size)).mappings())
        return {"items": [public_task(row, today) for row in rows], "total": total, "counts": counts,
                "page": page, "page_size": page_size, "today": today}

    def reminders(self, user_id):
        today = business_today()
        with self.engine.connect() as connection:
            row = connection.execute(select(func.count().label("open"),
                func.coalesce(func.sum(case((TASKS.c.due_date < today, 1), else_=0)), 0).label("overdue"))
                .where(TASKS.c.assignee_id == user_id, TASKS.c.status != "completed")).mappings().one()
        return {**dict(row), "today": today}
