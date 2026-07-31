from __future__ import annotations

from sqlalchemy import BigInteger, Column, Date, DateTime, Identity, Index, Integer, JSON, Numeric, Table, Text, UniqueConstraint, func

from domain.legacy_partitioning import LegacyPartitionTarget, attach_partition_if_parent_exists
from domain.schema import METADATA


def _table_for_year(prefix: str, year: int, columns: list[Column], unique_columns: list[str]) -> Table:
    if year < 2000 or year > 2100:
        raise ValueError(f"Unsupported sales year: {year}")
    table_name = f"{prefix}_{year:04d}"
    if table_name in METADATA.tables:
        return METADATA.tables[table_name]
    table = Table(
        table_name,
        METADATA,
        Column("id", BigInteger, Identity(always=False), primary_key=True),
        Column("sales_date", Date, nullable=False),
        *columns,
        Column("source_workbook", Text, nullable=False),
        Column("source_sheet", Text, nullable=False),
        Column("source_row_number", Integer, nullable=False),
        Column("raw_payload", JSON, nullable=False),
        Column("created_at", DateTime(timezone=True), server_default=func.date_trunc("minute", func.now())),
        Column("updated_at", DateTime(timezone=True), server_default=func.date_trunc("minute", func.now()), onupdate=func.date_trunc("minute", func.now())),
        UniqueConstraint("sales_date", *unique_columns, name=f"uq_{table_name}_business_key"),
    )
    Index(f"idx_{table_name}_sales_date", table.c.sales_date)
    if prefix == "jst_daily_sales":
        Index(
            f"idx_{table_name}_product_code_pattern",
            table.c.product_code,
            postgresql_ops={"product_code": "text_pattern_ops"},
        )
        Index(f"idx_{table_name}_style_code", table.c.style_code)
    elif prefix == "vip_daily_sales":
        Index(
            f"idx_{table_name}_goods_code_pattern",
            table.c.goods_code,
            postgresql_ops={"goods_code": "text_pattern_ops"},
        )
        Index(f"idx_{table_name}_style_code", table.c.style_code)
    return table


def jst_daily_sales_table_for_year(year: int) -> Table:
    columns = [
        Column("channel", Text, nullable=False, server_default=""),
        Column("product_code", Text, nullable=False, server_default=""),
        Column("style_code", Text, nullable=False, server_default=""),
        Column("color_spec", Text, nullable=False, server_default=""),
        Column("channel_code", Text, nullable=False, server_default=""),
        Column("barcode", Text, nullable=False, server_default=""),
        Column("order_type", Text, nullable=True),
        Column("supplier", Text, nullable=True),
        Column("supplier_style_code", Text, nullable=True),
        Column("product_name", Text, nullable=True),
        Column("product_category", Text, nullable=True),
        Column("brand", Text, nullable=True),
        Column("cost_price", Numeric(18, 4), nullable=True),
        Column("shipped_order_count", Integer, nullable=True),
        Column("sales_order_count", Integer, nullable=True),
        Column("return_order_count", Integer, nullable=True),
        Column("sales_quantity", Integer, nullable=True),
        Column("shipped_quantity", Integer, nullable=True),
        Column("return_quantity", Integer, nullable=True),
        Column("net_sales_quantity", Integer, nullable=True),
        Column("sales_amount", Numeric(18, 2), nullable=True),
        Column("net_sales_amount", Numeric(18, 2), nullable=True),
        Column("cost_amount", Numeric(18, 2), nullable=True),
        Column("gross_profit", Numeric(18, 2), nullable=True),
    ]
    return _table_for_year(
        "jst_daily_sales",
        year,
        columns,
        ["channel", "product_code", "style_code", "color_spec", "channel_code", "barcode"],
    )


def vip_daily_sales_table_for_year(year: int) -> Table:
    columns = [
        Column("barcode", Text, nullable=True),
        Column("size_id", Text, nullable=False, server_default=""),
        Column("goods_id", Text, nullable=False, server_default=""),
        Column("product_name", Text, nullable=True),
        Column("goods_code", Text, nullable=True),
        Column("style_code", Text, nullable=True),
        Column("spu_id", Text, nullable=True),
        Column("size_name", Text, nullable=True),
        Column("product_image", Text, nullable=True),
        Column("product_type", Text, nullable=True),
        Column("brand_sn", Text, nullable=True),
        Column("brand_name", Text, nullable=True),
        Column("sales_amount", Numeric(18, 2), nullable=True),
        Column("sales_quantity", Integer, nullable=True),
        Column("customer_count", Integer, nullable=True),
        Column("on_sale_stock", Integer, nullable=True),
        Column("product_link", Text, nullable=True),
    ]
    return _table_for_year("vip_daily_sales", year, columns, ["goods_id", "size_id"])


def ensure_jst_daily_sales_table(engine, year: int) -> Table:
    table = jst_daily_sales_table_for_year(year)
    table.create(engine, checkfirst=True)
    _attach_year_partition_if_enabled(engine, "jst_daily_sales", table.name, year)
    return table


def ensure_vip_daily_sales_table(engine, year: int) -> Table:
    table = vip_daily_sales_table_for_year(year)
    table.create(engine, checkfirst=True)
    _attach_year_partition_if_enabled(engine, "vip_daily_sales", table.name, year)
    return table


def _attach_year_partition_if_enabled(engine, parent_name: str, child_name: str, year: int) -> None:
    attach_partition_if_parent_exists(
        engine,
        LegacyPartitionTarget(
            parent_name=parent_name,
            child_name=child_name,
            partition_key="sales_date",
            lower_bound=f"{year:04d}-01-01",
            upper_bound=f"{year + 1:04d}-01-01",
        ),
    )
