from datetime import datetime, timedelta, timezone

from sqlalchemy import insert, select, update
from sqlalchemy.exc import IntegrityError

from domain.inventory_import_task_schema import INVENTORY_IMPORT_TASK_TABLE


class InventoryImportTasks:
    def __init__(self, engine):
        self.engine = engine

    def get(self, task_id, user_id):
        table = INVENTORY_IMPORT_TASK_TABLE
        with self.engine.begin() as connection:
            connection.execute(update(table).where(
                table.c.id == task_id,
                table.c.user_id == user_id,
                table.c.status.in_(["queued", "running"]),
                table.c.heartbeat_at < datetime.now(timezone.utc) - timedelta(minutes=2),
            ).values(
                status="failed", error="导入任务已中断，本批次未提交，请重新预检查后导入。",
                error_status=503, finished_at=datetime.now(timezone.utc),
            ))
            row = connection.execute(select(table).where(
                table.c.id == task_id, table.c.user_id == user_id,
            )).mappings().first()
        return dict(row) if row else None

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
            connection.execute(update(table).where(
                table.c.id == task_id, table.c.status == "running",
            ).values(heartbeat_at=datetime.now(timezone.utc)))

    def fail(self, task_id, message, status_code):
        table = INVENTORY_IMPORT_TASK_TABLE
        with self.engine.begin() as connection:
            connection.execute(update(table).where(
                table.c.id == task_id, table.c.status.in_(["queued", "running"]),
            ).values(status="failed", error=message, error_status=status_code, finished_at=datetime.now(timezone.utc)))


def complete_inventory_import(connection, task_id, result):
    table = INVENTORY_IMPORT_TASK_TABLE
    updated = connection.execute(update(table).where(
        table.c.id == task_id, table.c.status == "running",
    ).values(status="succeeded", result=result, finished_at=datetime.now(timezone.utc)))
    if updated.rowcount != 1:
        raise ValueError("导入任务已中断，本批次未提交，请重新预检查后导入")
