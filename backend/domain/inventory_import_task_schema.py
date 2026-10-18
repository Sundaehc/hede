from sqlalchemy import BigInteger, Column, DateTime, Integer, JSON, Table, Text, func

from domain.schema import METADATA


INVENTORY_IMPORT_TASK_TABLE = Table(
    "inventory_import_tasks",
    METADATA,
    Column("id", Text, primary_key=True),
    Column("request_hash", Text, nullable=False),
    Column("user_id", BigInteger, nullable=True),
    Column("filename", Text, nullable=False),
    Column("status", Text, nullable=False),
    Column("result", JSON, nullable=True),
    Column("error", Text, nullable=True),
    Column("error_status", Integer, nullable=True),
    Column("created_at", DateTime(timezone=True), server_default=func.now(), nullable=False),
    Column("heartbeat_at", DateTime(timezone=True), server_default=func.now(), nullable=False),
    Column("finished_at", DateTime(timezone=True), nullable=True),
)
