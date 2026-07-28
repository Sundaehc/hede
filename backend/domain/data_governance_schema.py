from __future__ import annotations

from sqlalchemy import BigInteger, Column, DateTime, Identity, Index, JSON, Table, Text, UniqueConstraint, func

from domain.schema import METADATA


DATA_GOVERNANCE_RUNS_TABLE = Table(
    "data_governance_runs",
    METADATA,
    Column("id", BigInteger, Identity(always=False), primary_key=True),
    Column("status", Text, nullable=False),
    Column("result", JSON, nullable=False, default=dict),
    Column("started_at", DateTime(timezone=True), server_default=func.date_trunc("minute", func.now())),
    Column("finished_at", DateTime(timezone=True), nullable=True),
)


DATA_QUALITY_ISSUES_TABLE = Table(
    "data_quality_issues",
    METADATA,
    Column("id", BigInteger, Identity(always=False), primary_key=True),
    Column("table_name", Text, nullable=False),
    Column("column_name", Text, nullable=False),
    Column("record_key", Text, nullable=False),
    Column("issue_type", Text, nullable=False),
    Column("raw_value", Text, nullable=True),
    Column("details", JSON, nullable=True),
    Column("first_seen_at", DateTime(timezone=True), server_default=func.date_trunc("minute", func.now())),
    Column("last_seen_at", DateTime(timezone=True), server_default=func.date_trunc("minute", func.now())),
    Column("resolved_at", DateTime(timezone=True), nullable=True),
    UniqueConstraint(
        "table_name",
        "column_name",
        "record_key",
        "issue_type",
        name="uq_data_quality_issues_record",
    ),
)
Index("idx_data_quality_issues_open", DATA_QUALITY_ISSUES_TABLE.c.resolved_at, DATA_QUALITY_ISSUES_TABLE.c.table_name)
