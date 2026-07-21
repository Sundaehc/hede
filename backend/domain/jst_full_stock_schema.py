from __future__ import annotations

from sqlalchemy import BigInteger, Column, Date, DateTime, Identity, Index, Integer, Numeric, Table, Text, func

from domain.schema import METADATA


JST_FULL_STOCK_TABLE = Table(
    "jst_full_stock",
    METADATA,
    Column("id", BigInteger, Identity(always=False), primary_key=True),
    Column("sync_date", Date, nullable=False),
    Column("source_workbook", Text, nullable=False),
    Column("source_sheet", Text, nullable=False),
    Column("source_row_number", Text, nullable=False),
    Column("image_url", Text, nullable=True),
    Column("style_code", Text, nullable=True),
    Column("product_code", Text, nullable=False),
    Column("product_name", Text, nullable=True),
    Column("color_spec", Text, nullable=True),
    Column("color", Text, nullable=True),
    Column("size", Text, nullable=True),
    Column("product_tag", Text, nullable=True),
    Column("actual_stock_qty", Integer, nullable=True),
    Column("order_occupy_qty", Integer, nullable=True),
    Column("available_qty", Integer, nullable=True),
    Column("stock_sale_days", Numeric(12, 2), nullable=True),
    Column("purchase_feature", Text, nullable=True),
    Column("suggested_purchase_qty", Integer, nullable=True),
    Column("purchase_in_transit_qty", Integer, nullable=True),
    Column("safety_stock_min_qty", Integer, nullable=True),
    Column("safety_stock_max_qty", Integer, nullable=True),
    Column("safety_stock_delivery_days_min", Integer, nullable=True),
    Column("safety_stock_days_max", Integer, nullable=True),
    Column("warehouse_pending_qty", Integer, nullable=True),
    Column("return_warehouse_stock_qty", Integer, nullable=True),
    Column("purchase_warehouse_stock_qty", Integer, nullable=True),
    Column("exception_warehouse_qty", Integer, nullable=True),
    Column("off_shelf_warehouse_qty", Integer, nullable=True),
    Column("worn_warehouse_qty", Integer, nullable=True),
    Column("live_warehouse_qty", Integer, nullable=True),
    Column("off_shelf_inventory_qty", Integer, nullable=True),
    Column("processing_warehouse_qty", Integer, nullable=True),
    Column("temporary_location_qty", Integer, nullable=True),
    Column("transfer_in_transit_qty", Integer, nullable=True),
    Column("return_in_transit_qty", Integer, nullable=True),
    Column("inventory_sync_status", Text, nullable=True),
    Column("main_warehouse_location", Text, nullable=True),
    Column("yesterday_sales_qty", Integer, nullable=True),
    Column("sales_7d_qty", Integer, nullable=True),
    Column("sales_15d_qty", Integer, nullable=True),
    Column("yesterday_return_qty", Integer, nullable=True),
    Column("return_7d_qty", Integer, nullable=True),
    Column("return_15d_qty", Integer, nullable=True),
    Column("inventory_updated_at", Text, nullable=True),
    Column("warehouse_name", Text, nullable=True),
    Column("created_at", DateTime(timezone=True), server_default=func.date_trunc("minute", func.now())),
    Column("updated_at", DateTime(timezone=True), server_default=func.date_trunc("minute", func.now()), onupdate=func.date_trunc("minute", func.now())),
)

Index("idx_jst_full_stock_product_code", JST_FULL_STOCK_TABLE.c.product_code)
Index("idx_jst_full_stock_product_size", JST_FULL_STOCK_TABLE.c.product_code, JST_FULL_STOCK_TABLE.c.size)
Index("idx_jst_full_stock_style_code", JST_FULL_STOCK_TABLE.c.style_code)
