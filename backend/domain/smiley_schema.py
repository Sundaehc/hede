from __future__ import annotations

from sqlalchemy import BigInteger, Column, Date, DateTime, Identity, Index, Integer, JSON, Numeric, Table, Text, UniqueConstraint, func

from domain.schema import METADATA


SMILEY_FINE_TABLE = Table(
    "smiley_fine_table",
    METADATA,
    Column("id", BigInteger, Identity(always=False), primary_key=True),
    Column("snapshot_date", Date, nullable=False),
    Column("source_workbook", Text, nullable=False),
    Column("source_sheet", Text, nullable=False),
    Column("source_row_number", Integer, nullable=False),
    Column("image_path", Text, nullable=True),
    Column("sku", Text, nullable=False),
    Column("original_sku", Text, nullable=True),
    Column("factory_code", Text, nullable=True),
    Column("factory_sku", Text, nullable=True),
    Column("market_price", Numeric(10, 2), nullable=True),
    Column("cost", Numeric(10, 2), nullable=True),
    Column("product_name", Text, nullable=True),
    Column("barcode", Text, nullable=True),
    Column("execution_standard", Text, nullable=True),
    Column("insole_material", Text, nullable=True),
    Column("outsole_material", Text, nullable=True),
    Column("lining_material", Text, nullable=True),
    Column("upper_material", Text, nullable=True),
    Column("shoe_box_spec", Text, nullable=True),
    Column("accessories", Text, nullable=True),
    Column("first_order_date", Date, nullable=True),
    Column("season_category", Text, nullable=True),
    Column("stock_qty", Integer, nullable=False, server_default="0"),
    Column("inbound_qty", Integer, nullable=False, server_default="0"),
    Column("warehouse_stock", Integer, nullable=False, server_default="0"),
    Column("available_stock", Integer, nullable=False, server_default="0"),
    Column("daily_sales_total", Integer, nullable=False, server_default="0"),
    Column("total_3d_sales", Integer, nullable=False, server_default="0"),
    Column("total_7d_sales", Integer, nullable=False, server_default="0"),
    Column("total_15d_sales", Integer, nullable=False, server_default="0"),
    Column("total_30d_sales", Integer, nullable=False, server_default="0"),
    Column("shop_sales", JSON, nullable=False),
    Column("size_stock", JSON, nullable=False),
    Column("return_rates", JSON, nullable=False),
    Column("remark", Text, nullable=True),
    Column("raw_payload", JSON, nullable=False),
    Column("created_at", DateTime(timezone=True), server_default=func.date_trunc("minute", func.now())),
    Column(
        "updated_at",
        DateTime(timezone=True),
        server_default=func.date_trunc("minute", func.now()),
        onupdate=func.date_trunc("minute", func.now()),
    ),
    UniqueConstraint("snapshot_date", "sku", name="uq_smiley_fine_table_date_sku"),
)

Index("idx_smiley_fine_table_snapshot_date", SMILEY_FINE_TABLE.c.snapshot_date)
Index("idx_smiley_fine_table_sku", SMILEY_FINE_TABLE.c.sku)
Index("idx_smiley_fine_table_original_sku", SMILEY_FINE_TABLE.c.original_sku)
