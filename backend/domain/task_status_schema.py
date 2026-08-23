from __future__ import annotations

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    Column,
    Date,
    DateTime,
    Identity,
    Index,
    Integer,
    JSON,
    Table,
    Text,
    UniqueConstraint,
    func,
)

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


SCHEDULED_TASK_RUN_TABLE = Table(
    "scheduled_task_runs",
    METADATA,
    Column("id", BigInteger, Identity(always=False), primary_key=True),
    Column("task_name", Text, nullable=False),
    Column("status", Text, nullable=False, default="running"),
    Column("started_at", DateTime(timezone=True), nullable=False, server_default=func.now()),
    Column("finished_at", DateTime(timezone=True), nullable=True),
    Column("duration_ms", BigInteger, nullable=True),
    Column("exit_code", Integer, nullable=True),
    Column("host_name", Text, nullable=True),
    Column("process_id", Integer, nullable=True),
    Column("command", Text, nullable=True),
    Column("log_path", Text, nullable=True),
    Column("error_summary", Text, nullable=True),
    Column("created_at", DateTime(timezone=True), nullable=False, server_default=func.now()),
    CheckConstraint(
        "status IN ('running', 'success', 'failed')",
        name="ck_scheduled_task_runs_status",
    ),
    CheckConstraint(
        "duration_ms IS NULL OR duration_ms >= 0",
        name="ck_scheduled_task_runs_duration_ms",
    ),
)

Index(
    "idx_scheduled_task_runs_task_started",
    SCHEDULED_TASK_RUN_TABLE.c.task_name,
    SCHEDULED_TASK_RUN_TABLE.c.started_at.desc(),
)
Index(
    "idx_scheduled_task_runs_status_started",
    SCHEDULED_TASK_RUN_TABLE.c.status,
    SCHEDULED_TASK_RUN_TABLE.c.started_at.desc(),
)
