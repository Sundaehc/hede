from __future__ import annotations

from sqlalchemy import BigInteger, Column, Date, DateTime, Identity, Index, Integer, JSON, Table, Text, UniqueConstraint, func

from domain.schema import METADATA


PRODUCT_GOODS_DETAIL_SNAPSHOT_BATCHES_TABLE = Table(
    "product_goods_detail_snapshot_batches",
    METADATA,
    Column("id", BigInteger, Identity(always=False), primary_key=True),
    Column("brand", Text, nullable=False),
    Column("snapshot_date", Date, nullable=False),
    Column("source_path", Text, nullable=False),
    Column("source_workbook", Text, nullable=False),
    Column("row_count", Integer, nullable=True),
    Column("status", Text, nullable=False),
    Column("message", Text, nullable=True),
    Column("created_at", DateTime(timezone=True), server_default=func.date_trunc("minute", func.now())),
    Column("updated_at", DateTime(timezone=True), server_default=func.date_trunc("minute", func.now()), onupdate=func.date_trunc("minute", func.now())),
    UniqueConstraint("brand", "snapshot_date", name="uq_product_goods_detail_snapshot_batch"),
)
Index(
    "idx_product_goods_detail_snapshot_batches_brand_date",
    PRODUCT_GOODS_DETAIL_SNAPSHOT_BATCHES_TABLE.c.brand,
    PRODUCT_GOODS_DETAIL_SNAPSHOT_BATCHES_TABLE.c.snapshot_date,
)


def product_goods_detail_snapshots_table_for_year(year: int) -> Table:
    if year < 2000 or year > 2100:
        raise ValueError(f"Unsupported product-goods detail snapshot year: {year}")
    table_name = f"product_goods_detail_snapshots_{year:04d}"
    if table_name in METADATA.tables:
        return METADATA.tables[table_name]
    table = Table(
        table_name,
        METADATA,
        Column("id", BigInteger, Identity(always=False), primary_key=True),
        Column("brand", Text, nullable=False),
        Column("snapshot_date", Date, nullable=False),
        Column("goods_code", Text, nullable=False),
        Column("style_code", Text, nullable=True),
        Column("source_workbook", Text, nullable=False),
        Column("source_sheet", Text, nullable=False),
        Column("source_row_number", Integer, nullable=False),
        Column("data", JSON, nullable=False),
        Column("created_at", DateTime(timezone=True), server_default=func.date_trunc("minute", func.now())),
        Column("updated_at", DateTime(timezone=True), server_default=func.date_trunc("minute", func.now()), onupdate=func.date_trunc("minute", func.now())),
        UniqueConstraint("brand", "snapshot_date", "goods_code", name=f"uq_{table_name}_brand_date_goods"),
    )
    Index(f"idx_{table_name}_brand_date_goods", table.c.brand, table.c.snapshot_date, table.c.goods_code)
    Index(f"idx_{table_name}_brand_style", table.c.brand, table.c.style_code)
    return table


def ensure_product_goods_detail_snapshot_tables(engine, year: int) -> Table:
    PRODUCT_GOODS_DETAIL_SNAPSHOT_BATCHES_TABLE.create(engine, checkfirst=True)
    table = product_goods_detail_snapshots_table_for_year(year)
    table.create(engine, checkfirst=True)
    return table
