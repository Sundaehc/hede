"""Persist confirmed clearance and optional brand/type assignment rules."""
from datetime import datetime, timezone

from sqlalchemy import Boolean, CheckConstraint, Column, DateTime, Integer, MetaData, Table, Text, delete, insert, select, text, tuple_, update
from sqlalchemy.exc import IntegrityError

from storage.stock_alert_rules import RuleConflict

META = MetaData()
CLEARANCE = Table("stock_clearance_decisions", META,
    Column("brand", Text, primary_key=True), Column("product_id", Integer, primary_key=True),
    Column("confirmed", Boolean, nullable=False), Column("reason", Text, nullable=False),
    Column("version", Integer, nullable=False), Column("updated_by", Integer, nullable=False),
    Column("updated_at", DateTime(timezone=True), nullable=False),
)
ASSIGNMENT = Table("stock_auto_assignment_rules", META,
    Column("brand", Text, primary_key=True), Column("kind", Text, primary_key=True),
    Column("assignee_id", Integer, nullable=False), Column("enabled", Boolean, nullable=False),
    Column("due_days", Integer, nullable=False), Column("version", Integer, nullable=False),
    Column("updated_by", Integer, nullable=False), Column("updated_at", DateTime(timezone=True), nullable=False),
    CheckConstraint("kind IN ('zero', 'slow', 'replenish', 'clearance')"),
    CheckConstraint("due_days BETWEEN 0 AND 90"),
)


OBSERVATIONS = Table("stock_auto_assignment_observations", META,
    Column("brand", Text, primary_key=True), Column("kind", Text, primary_key=True),
    Column("product_id", Integer, primary_key=True), Column("task_id", Integer, nullable=False),
)


def lock_stock_decision(connection, brand, product_id):
    if connection.dialect.name == "postgresql":
        connection.execute(text("SELECT pg_advisory_xact_lock(hashtextextended(:key, 0))"),
                           {"key": f"stock-overview:{brand}:{product_id}"})


class StockOperatingRepository:
    def __init__(self, engine):
        self.engine = engine

    def decisions(self, brand):
        stmt = select(CLEARANCE).where(CLEARANCE.c.brand == brand)
        with self.engine.connect() as conn:
            return {row["product_id"]: dict(row) for row in conn.execute(stmt).mappings()}

    def assignments(self, brand=None):
        stmt = select(ASSIGNMENT)
        if brand is not None:
            stmt = stmt.where(ASSIGNMENT.c.brand == brand)
        with self.engine.connect() as conn:
            return [dict(row) for row in conn.execute(stmt.order_by(ASSIGNMENT.c.brand, ASSIGNMENT.c.kind)).mappings()]

    def reconcile(self, brand, candidates, *, observable_kinds, tasks, people, rule_versions=None):
        """Retain assigned issues until an aligned calculation shows them absent."""
        from storage.stock_alert_tasks import TASKS, TaskConflict

        with self.engine.begin() as conn:
            if conn.dialect.name == "sqlite":
                conn.exec_driver_sql("BEGIN")
            if conn.dialect.name == "postgresql":
                conn.execute(text("SELECT pg_advisory_xact_lock(hashtextextended(:key, 0))"),
                             {"key": f"stock-auto-assignment:{brand}"})
            if rule_versions is not None:
                versions = {row.kind: row.version for row in conn.execute(select(ASSIGNMENT.c.kind, ASSIGNMENT.c.version)
                    .where(ASSIGNMENT.c.brand == brand, ASSIGNMENT.c.enabled.is_(True)))}
                current = {kind for kind in people if versions.get(kind) == rule_versions.get(kind)}
                people = {kind: people[kind] for kind in current}
                observable_kinds = observable_kinds & current
            seen = {(row.kind, row.product_id): row.task_id for row in conn.execute(
                select(OBSERVATIONS).where(OBSERVATIONS.c.brand == brand))}
            active = {(row.kind, row.product_id): row.id for row in conn.execute(
                select(TASKS.c.kind, TASKS.c.product_id, TASKS.c.id).where(
                    TASKS.c.brand == brand, TASKS.c.active_key.is_not(None)))}
            expired = [key for key in seen if key[0] in observable_kinds and key not in candidates]
            if expired:
                conn.execute(delete(OBSERVATIONS).where(OBSERVATIONS.c.brand == brand,
                    tuple_(OBSERVATIONS.c.kind, OBSERVATIONS.c.product_id).in_(expired)))
            created = []
            for (kind, product_id), entry in sorted(candidates.items(), key=lambda part: (part[0][1], part[0][0])):
                if entry is None or (kind, product_id) in seen or kind not in people:
                    continue
                snapshot, due = entry
                assignee, actor = people[kind]
                task_id = active.get((kind, product_id))
                if task_id is None:
                    try:
                        with conn.begin_nested():
                            task = tasks._create_on(conn, snapshot=snapshot, kind=kind, assignee=assignee,
                                due_date=due, measures="", actor=actor)
                    except (TaskConflict, IntegrityError):
                        task_id = conn.execute(select(TASKS.c.id).where(
                            TASKS.c.active_key == f"{brand}:{product_id}:{kind}")).scalar_one_or_none()
                        if task_id is None:
                            continue
                    else:
                        task_id = task["id"]
                        created.append(task)
                conn.execute(insert(OBSERVATIONS).values(brand=brand, kind=kind, product_id=product_id, task_id=task_id))
            return created

    def save_clearance(self, brand, product_id, version, user_id, *, confirmed, reason):
        with self.engine.begin() as conn:
            lock_stock_decision(conn, brand, product_id)
            return self._save(conn, CLEARANCE, {"brand": brand, "product_id": product_id}, version, user_id,
                              {"confirmed": confirmed, "reason": reason})

    def save_assignment(self, brand, kind, version, user_id, **fields):
        with self.engine.begin() as conn:
            if conn.dialect.name == "postgresql":
                conn.execute(text("SELECT pg_advisory_xact_lock(hashtextextended(:key, 0))"),
                             {"key": f"stock-auto-assignment:{brand}"})
            return self._save(conn, ASSIGNMENT, {"brand": brand, "kind": kind}, version, user_id, fields)

    @staticmethod
    def _save(conn, table, key, version, user_id, fields):
        values = {**fields, "version": version + 1, "updated_by": user_id, "updated_at": datetime.now(timezone.utc)}
        try:
            if version == 0:
                stmt = insert(table).values(**key, **values)
            else:
                stmt = update(table).where(*(table.c[name] == value for name, value in key.items()),
                                           table.c.version == version).values(**values)
            row = conn.execute(stmt.returning(table)).mappings().one_or_none()
        except IntegrityError:
            raise RuleConflict("设置已变化，请重新打开后保存") from None
        if row is None:
            raise RuleConflict("设置已变化，请重新打开后保存")
        return dict(row)

