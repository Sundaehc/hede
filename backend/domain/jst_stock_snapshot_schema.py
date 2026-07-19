from __future__ import annotations

from sqlalchemy import BigInteger, Column, Date, DateTime, Identity, Index, Integer, JSON, Table, Text, UniqueConstraint, func

from domain.schema import METADATA


JST_SIZE_STOCK_SNAPSHOT_TABLE = Table(
    "jst_size_stock_snapshots",
    METADATA,
    Column("id", BigInteger, Identity(always=False), primary_key=True),
    Column("snapshot_date", Date, nullable=False),
    Column("product_code", Text, nullable=False),
    Column("size", Text, nullable=False),
    Column("stock_qty", Integer, nullable=False, server_default="0"),
    Column("source_workbook", Text, nullable=False),
    Column("source_sheet", Text, nullable=False),
    Column("source_row_number", Text, nullable=False),
    Column("raw_payload", JSON, nullable=False, default=dict),
    Column("created_at", DateTime(timezone=True), server_default=func.date_trunc("minute", func.now())),
    Column("updated_at", DateTime(timezone=True), server_default=func.date_trunc("minute", func.now()), onupdate=func.date_trunc("minute", func.now())),
    UniqueConstraint("snapshot_date", "product_code", "size", name="uq_jst_size_stock_snapshot"),
)
Index("idx_jst_size_stock_snapshots_date_code", JST_SIZE_STOCK_SNAPSHOT_TABLE.c.snapshot_date, JST_SIZE_STOCK_SNAPSHOT_TABLE.c.product_code)


JST_STOCK_SUMMARY_SNAPSHOT_TABLE = Table(
    "jst_stock_summary_snapshots",
    METADATA,
    Column("id", BigInteger, Identity(always=False), primary_key=True),
    Column("snapshot_date", Date, nullable=False),
    Column("product_code", Text, nullable=False),
    Column("defect_stock_qty", Integer, nullable=True),
    Column("purchase_in_transit_qty", Integer, nullable=True),
    Column("off_shelf_qty", Integer, nullable=True),
    Column("order_occupy_qty", Integer, nullable=True),
    Column("source_workbook", Text, nullable=False),
    Column("source_sheet", Text, nullable=False),
    Column("source_row_number", Text, nullable=False),
    Column("raw_payload", JSON, nullable=False, default=dict),
    Column("created_at", DateTime(timezone=True), server_default=func.date_trunc("minute", func.now())),
    Column("updated_at", DateTime(timezone=True), server_default=func.date_trunc("minute", func.now()), onupdate=func.date_trunc("minute", func.now())),
    UniqueConstraint("snapshot_date", "product_code", name="uq_jst_stock_summary_snapshot"),
)
Index("idx_jst_stock_summary_snapshots_date_code", JST_STOCK_SUMMARY_SNAPSHOT_TABLE.c.snapshot_date, JST_STOCK_SUMMARY_SNAPSHOT_TABLE.c.product_code)
