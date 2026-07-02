from __future__ import annotations

from sqlalchemy import BigInteger, Column, DateTime, Identity, Index, JSON, Table, Text, func

from domain.schema import METADATA


OPERATION_LOG_TABLE = Table(
    "operation_logs",
    METADATA,
    Column("id", BigInteger, Identity(always=False), primary_key=True),
    Column("module", Text, nullable=False),
    Column("action", Text, nullable=False),
    Column("entity_type", Text, nullable=False),
    Column("entity_id", Text, nullable=True),
    Column("entity_label", Text, nullable=True),
    Column("summary", Text, nullable=False),
    Column("changed_fields", JSON, nullable=True),
    Column("before_data", JSON, nullable=True),
    Column("after_data", JSON, nullable=True),
    Column("user_id", BigInteger, nullable=True),
    Column("username", Text, nullable=True),
    Column("display_name", Text, nullable=True),
    Column("department_name", Text, nullable=True),
    Column("created_at", DateTime(timezone=True), server_default=func.now()),
)

Index("idx_operation_logs_module_created_at", OPERATION_LOG_TABLE.c.module, OPERATION_LOG_TABLE.c.created_at)
Index("idx_operation_logs_entity", OPERATION_LOG_TABLE.c.module, OPERATION_LOG_TABLE.c.entity_type, OPERATION_LOG_TABLE.c.entity_id)
Index("idx_operation_logs_user", OPERATION_LOG_TABLE.c.username)
