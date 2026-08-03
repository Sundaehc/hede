from __future__ import annotations

from datetime import date
import re

from sqlalchemy import BigInteger, Column, Date, DateTime, ForeignKey, Identity, Index, Integer, JSON, Table, Text, UniqueConstraint, func, inspect, text
from sqlalchemy.dialects.postgresql import JSONB

from domain.legacy_partitioning import LegacyPartitionTarget, attach_partition_if_parent_exists, partition_parent_exists
from domain.schema import METADATA


FINE_TABLE_SNAPSHOT_BATCH_TABLE = Table(
    "fine_table_snapshot_batches",
    METADATA,
    Column("id", BigInteger, Identity(always=False), primary_key=True),
    Column("brand", Text, nullable=False),
    Column("snapshot_date", Date, nullable=False),
    Column("total_rows", Integer, nullable=False, default=0),
    Column("latest_order_date", Date, nullable=True),
    Column("created_at", DateTime(timezone=True), server_default=func.date_trunc("minute", func.now())),
    Column(
        "updated_at",
        DateTime(timezone=True),
        server_default=func.date_trunc("minute", func.now()),
        onupdate=func.date_trunc("minute", func.now()),
    ),
    UniqueConstraint("brand", "snapshot_date", name="uq_fine_table_snapshot_batches_brand_date"),
)
_FINE_TABLE_SNAPSHOT_YEAR_TABLE_PATTERN = re.compile(r"^fine_table_snapshot_rows_(\d{4})$")
_FINE_TABLE_SNAPSHOT_REF_YEAR_TABLE_PATTERN = re.compile(r"^fine_table_snapshot_refs_(\d{4})$")
FINE_TABLE_SNAPSHOT_PARENT_NAME = "fine_table_snapshot_rows"
FINE_TABLE_SNAPSHOT_PAYLOADS_TABLE = Table(
    "fine_table_snapshot_payloads",
    METADATA,
    Column("id", BigInteger, Identity(always=False), primary_key=True),
    Column("brand", Text, nullable=False),
    Column("content_hash", Text, nullable=False),
    Column("payload", JSONB, nullable=False),
    Column("created_at", DateTime(timezone=True), server_default=func.date_trunc("minute", func.now())),
    UniqueConstraint("brand", "content_hash", name="uq_fine_table_snapshot_payloads_brand_hash"),
)
FINE_TABLE_SNAPSHOT_METRICS_TABLE = Table(
    "fine_table_snapshot_metrics",
    METADATA,
    Column("id", BigInteger, Identity(always=False), primary_key=True),
    Column("brand", Text, nullable=False),
    Column("content_hash", Text, nullable=False),
    Column("payload", JSONB, nullable=False),
    Column("created_at", DateTime(timezone=True), server_default=func.date_trunc("minute", func.now())),
    UniqueConstraint("brand", "content_hash", name="uq_fine_table_snapshot_metrics_brand_hash"),
)


def fine_table_snapshot_row_table_name(snapshot_date: date) -> str:
    return f"fine_table_snapshot_rows_{snapshot_date.year:04d}"


def fine_table_snapshot_ref_table_name(snapshot_date: date) -> str:
    return f"fine_table_snapshot_refs_{snapshot_date.year:04d}"


def fine_table_snapshot_ref_table_for_date(snapshot_date: date) -> Table:
    table_name = fine_table_snapshot_ref_table_name(snapshot_date)
    if table_name in METADATA.tables:
        return METADATA.tables[table_name]

    table = Table(
        table_name,
        METADATA,
        Column("id", BigInteger, Identity(always=False), primary_key=True),
        Column(
            "batch_id",
            BigInteger,
            ForeignKey("fine_table_snapshot_batches.id", ondelete="CASCADE"),
            nullable=False,
        ),
        Column("snapshot_date", Date, nullable=False),
        Column("sku", Text, nullable=True),
        Column("original_sku", Text, nullable=True),
        Column("row_index", Integer, nullable=False),
        Column("payload_id", BigInteger, ForeignKey("fine_table_snapshot_payloads.id"), nullable=False),
        Column("metrics_id", BigInteger, ForeignKey("fine_table_snapshot_metrics.id"), nullable=False),
        Column("created_at", DateTime(timezone=True), server_default=func.date_trunc("minute", func.now())),
        UniqueConstraint("batch_id", "row_index", name=f"uq_{table_name}_batch_row_index"),
    )
    Index(f"idx_{table_name}_batch_row_index", table.c.batch_id, table.c.row_index)
    Index(f"idx_{table_name}_batch_sku", table.c.batch_id, table.c.sku)
    Index(f"idx_{table_name}_batch_original_sku", table.c.batch_id, table.c.original_sku)
    Index(f"idx_{table_name}_payload_id", table.c.payload_id)
    Index(f"idx_{table_name}_metrics_id", table.c.metrics_id)
    Index(
        f"idx_{table_name}_sku_trgm",
        table.c.sku,
        postgresql_using="gin",
        postgresql_ops={"sku": "gin_trgm_ops"},
    )
    Index(
        f"idx_{table_name}_original_sku_trgm",
        table.c.original_sku,
        postgresql_using="gin",
        postgresql_ops={"original_sku": "gin_trgm_ops"},
    )
    return table


def fine_table_snapshot_row_table_for_date(snapshot_date: date) -> Table:
    table_name = fine_table_snapshot_row_table_name(snapshot_date)
    if table_name in METADATA.tables:
        return METADATA.tables[table_name]

    table = Table(
        table_name,
        METADATA,
        Column("id", BigInteger, Identity(always=False), primary_key=True),
        Column(
            "batch_id",
            BigInteger,
            ForeignKey("fine_table_snapshot_batches.id", ondelete="CASCADE"),
            nullable=False,
        ),
        Column("snapshot_date", Date, nullable=False),
        Column("sku", Text, nullable=True),
        Column("original_sku", Text, nullable=True),
        Column("row_index", Integer, nullable=False),
        Column("payload", JSON, nullable=False),
        Column("created_at", DateTime(timezone=True), server_default=func.date_trunc("minute", func.now())),
        UniqueConstraint("batch_id", "row_index", name=f"uq_{table_name}_batch_row_index"),
    )
    Index(f"idx_{table_name}_batch_sku", table.c.batch_id, table.c.sku)
    Index(f"idx_{table_name}_batch_original_sku", table.c.batch_id, table.c.original_sku)
    Index(
        f"idx_{table_name}_sku_trgm",
        table.c.sku,
        postgresql_using="gin",
        postgresql_ops={"sku": "gin_trgm_ops"},
    )
    Index(
        f"idx_{table_name}_original_sku_trgm",
        table.c.original_sku,
        postgresql_using="gin",
        postgresql_ops={"original_sku": "gin_trgm_ops"},
    )
    return table


def fine_table_snapshot_year_table_exists(engine, snapshot_date: date) -> bool:
    return inspect(engine).has_table(fine_table_snapshot_row_table_name(snapshot_date))


def fine_table_snapshot_ref_table_exists(engine, snapshot_date: date) -> bool:
    return inspect(engine).has_table(fine_table_snapshot_ref_table_name(snapshot_date))


def list_fine_table_snapshot_ref_tables(engine) -> list[Table]:
    years = sorted(
        int(matched.group(1))
        for table_name in inspect(engine).get_table_names()
        if (matched := _FINE_TABLE_SNAPSHOT_REF_YEAR_TABLE_PATTERN.fullmatch(table_name))
    )
    return [fine_table_snapshot_ref_table_for_date(date(year, 1, 1)) for year in years]


def ensure_fine_table_snapshot_row_table(engine, snapshot_date: date) -> Table:
    table = fine_table_snapshot_row_table_for_date(snapshot_date)
    table.create(engine, checkfirst=True)
    attach_partition_if_parent_exists(
        engine,
        LegacyPartitionTarget(
            parent_name=FINE_TABLE_SNAPSHOT_PARENT_NAME,
            child_name=table.name,
            partition_key="snapshot_date",
            lower_bound=f"{snapshot_date.year:04d}-01-01",
            upper_bound=f"{snapshot_date.year + 1:04d}-01-01",
        ),
    )
    refresh_fine_table_snapshot_compatibility_view(engine)
    return table


def ensure_fine_table_snapshot_ref_table(engine, snapshot_date: date) -> Table:
    table = fine_table_snapshot_ref_table_for_date(snapshot_date)
    table.create(engine, checkfirst=True)
    for index in table.indexes:
        index.create(engine, checkfirst=True)
    return table


def refresh_fine_table_snapshot_compatibility_view(engine) -> None:
    table_names: list[tuple[int, str]] = []
    for table_name in inspect(engine).get_table_names():
        matched = _FINE_TABLE_SNAPSHOT_REF_YEAR_TABLE_PATTERN.fullmatch(table_name)
        if matched:
            table_names.append((int(matched.group(1)), table_name))
    if not table_names:
        return

    selects = []
    for year, table_name in sorted(table_names):
        selects.append(
            f"""
            SELECT
                batches.brand,
                batches.snapshot_date,
                refs.id,
                refs.batch_id,
                refs.sku,
                refs.original_sku,
                refs.row_index,
                (payloads.payload || metrics.payload)::json AS payload,
                refs.created_at
            FROM public.{table_name} AS refs
            JOIN public.fine_table_snapshot_batches AS batches ON batches.id = refs.batch_id
            JOIN public.fine_table_snapshot_payloads AS payloads ON payloads.id = refs.payload_id
            JOIN public.fine_table_snapshot_metrics AS metrics ON metrics.id = refs.metrics_id
            WHERE batches.snapshot_date >= DATE '{year:04d}-01-01'
              AND batches.snapshot_date < DATE '{year + 1:04d}-01-01'
            """
        )
    view_sql = "\nUNION ALL\n".join(selects)
    _replace_fine_snapshot_view(engine, view_sql)


def _replace_fine_snapshot_view(engine, view_sql: str) -> None:
    with engine.begin() as connection:
        connection.execute(text(f"CREATE OR REPLACE VIEW public.v_fine_table_snapshot_rows AS {view_sql}"))
