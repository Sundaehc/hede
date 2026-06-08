from __future__ import annotations

from datetime import date

from sqlalchemy import BigInteger, Column, Date, DateTime, ForeignKey, Identity, Index, Integer, JSON, Table, Text, UniqueConstraint, func, inspect

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


def fine_table_snapshot_row_table_name(snapshot_date: date) -> str:
    return f"fine_table_snapshot_rows_{snapshot_date.year:04d}"


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


def ensure_fine_table_snapshot_row_table(engine, snapshot_date: date) -> Table:
    table = fine_table_snapshot_row_table_for_date(snapshot_date)
    table.create(engine, checkfirst=True)
    return table
