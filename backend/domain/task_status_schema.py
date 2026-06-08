from __future__ import annotations

from sqlalchemy import BigInteger, Column, Date, DateTime, Identity, Index, Integer, JSON, Table, Text, UniqueConstraint, func

from domain.schema import METADATA


SCHEDULED_TASK_STATUS_TABLE = Table(
    "scheduled_task_statuses",
    METADATA,
    Column("id", BigInteger, Identity(always=False), primary_key=True),
    Column("task_name", Text, nullable=False),
    Column("business_date", Date, nullable=False),
    Column("status", Text, nullable=False, default="pending"),
    Column("source_path", Text, nullable=True),
    Column("message", Text, nullable=True),
    Column("result", JSON, nullable=True),
    Column("attempts", Integer, nullable=False, default=0),
    Column("first_started_at", DateTime(timezone=True), nullable=True),
    Column("last_started_at", DateTime(timezone=True), nullable=True),
    Column("finished_at", DateTime(timezone=True), nullable=True),
    Column("created_at", DateTime(timezone=True), server_default=func.date_trunc("minute", func.now())),
    Column(
        "updated_at",
        DateTime(timezone=True),
        server_default=func.date_trunc("minute", func.now()),
        onupdate=func.date_trunc("minute", func.now()),
    ),
    UniqueConstraint("task_name", "business_date", name="uq_scheduled_task_statuses_task_date"),
)

Index(
    "idx_scheduled_task_statuses_task_status_date",
    SCHEDULED_TASK_STATUS_TABLE.c.task_name,
    SCHEDULED_TASK_STATUS_TABLE.c.status,
    SCHEDULED_TASK_STATUS_TABLE.c.business_date,
)
