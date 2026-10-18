from datetime import datetime, timedelta, timezone
import logging

from sqlalchemy import insert, select, update
from sqlalchemy.exc import IntegrityError

from domain.inventory_import_task_schema import INVENTORY_IMPORT_TASK_TABLE


logger = logging.getLogger(__name__)
INTERRUPTED_IMPORT_ERROR = "导入任务已失联或中断，本批次未提交，请重新预检查后导入。"


class InventoryImportTasks:
    def __init__(self, engine):
        self.engine = engine

    def get(self, task_id, user_id):
        table = INVENTORY_IMPORT_TASK_TABLE
        self.expire_stale(task_id=task_id, user_id=user_id)
        with self.engine.connect() as connection:
            row = connection.execute(select(table).where(
                table.c.id == task_id, table.c.user_id == user_id,
            )).mappings().first()
        return dict(row) if row else None

    def expire_stale(self, *, task_id=None, user_id=None):
        table = INVENTORY_IMPORT_TASK_TABLE
        now = datetime.now(timezone.utc)
        conditions = [
            table.c.status.in_(["queued", "running"]),
            table.c.heartbeat_at < now - timedelta(minutes=2),
        ]
        if task_id is not None:
            conditions.extend([table.c.id == task_id, table.c.user_id == user_id])
        with self.engine.begin() as connection:
            rows = connection.execute(update(table).where(*conditions).values(
                status="failed", error=INTERRUPTED_IMPORT_ERROR,
                error_status=503, finished_at=now,
            ).returning(table)).mappings().all()
        for row in rows:
            logger.error("Inventory import task %s interrupted: user=%s filename=%s", row["id"], row["user_id"], row["filename"])
        return [dict(row) for row in rows]

    def create(self, task_id, user_id, filename, request_hash):
        table = INVENTORY_IMPORT_TASK_TABLE
        try:
            with self.engine.begin() as connection:
                connection.execute(insert(table).values(
                    id=task_id, user_id=user_id, filename=filename,
                    request_hash=request_hash, status="queued",
                    heartbeat_at=datetime.now(timezone.utc),
                ))
            return True
        except IntegrityError:
            existing = self.get(task_id, user_id)
            if existing is None or existing["request_hash"] != request_hash:
                raise ValueError("导入批次编号已被使用，请重新选择文件后导入") from None
            return False

    def start(self, task_id):
        table = INVENTORY_IMPORT_TASK_TABLE
        with self.engine.begin() as connection:
            return connection.execute(update(table).where(
                table.c.id == task_id, table.c.status == "queued",
            ).values(status="running", heartbeat_at=datetime.now(timezone.utc))).rowcount == 1

    def heartbeat(self, task_id):
        table = INVENTORY_IMPORT_TASK_TABLE
        with self.engine.begin() as connection:
            return connection.execute(update(table).where(
                table.c.id == task_id, table.c.status == "running",
            ).values(heartbeat_at=datetime.now(timezone.utc))).rowcount == 1

    def fail(self, task_id, message, status_code):
        table = INVENTORY_IMPORT_TASK_TABLE
        with self.engine.begin() as connection:
            return connection.execute(update(table).where(
                table.c.id == task_id, table.c.status.in_(["queued", "running"]),
            ).values(status="failed", error=message, error_status=status_code, finished_at=datetime.now(timezone.utc))).rowcount == 1


def complete_inventory_import(connection, task_id, result):
    table = INVENTORY_IMPORT_TASK_TABLE
    updated = connection.execute(update(table).where(
        table.c.id == task_id, table.c.status == "running",
    ).values(status="succeeded", result=result, finished_at=datetime.now(timezone.utc)))
    if updated.rowcount != 1:
        raise ValueError("导入任务已中断，本批次未提交，请重新预检查后导入")
