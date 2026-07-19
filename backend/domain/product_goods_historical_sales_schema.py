from __future__ import annotations

from sqlalchemy import BigInteger, Column, Date, DateTime, Identity, Index, Integer, Numeric, Table, Text, UniqueConstraint, func

from domain.schema import METADATA


HISTORICAL_SALES_YEARS = (2024, 2025)


def product_goods_historical_sales_table_for_year(year: int) -> Table:
    if year < 2000 or year > 2100:
        raise ValueError(f"Unsupported historical sales year: {year}")
    table_name = f"product_goods_historical_sales_{year:04d}"
    if table_name in METADATA.tables:
        return METADATA.tables[table_name]
    table = Table(
        table_name,
        METADATA,
        Column("id", BigInteger, Identity(always=False), primary_key=True),
        Column("brand", Text, nullable=False),
        Column("sales_year", Integer, nullable=False),
        Column("sales_date", Date, nullable=False),
        Column("channel", Text, nullable=True),
        Column("style_code", Text, nullable=True),
        Column("product_code", Text, nullable=True),
        Column("original_sku", Text, nullable=True),
        Column("size", Text, nullable=True),
        Column("color", Text, nullable=True),
        Column("sales_quantity", Integer, nullable=False),
        Column("sales_amount", Numeric(18, 2), nullable=True),
        Column("source_workbook", Text, nullable=False),
        Column("source_sheet", Text, nullable=False),
        Column("source_row_number", Integer, nullable=False),
        Column("created_at", DateTime(timezone=True), server_default=func.date_trunc("minute", func.now())),
        UniqueConstraint("source_workbook", "source_sheet", "source_row_number", name=f"uq_{table_name}_source_row"),
    )
    Index(f"idx_{table_name}_date", table.c.sales_date)
    Index(f"idx_{table_name}_product", table.c.product_code)
    Index(f"idx_{table_name}_original", table.c.original_sku)
    Index(f"idx_{table_name}_brand_product", table.c.brand, table.c.product_code)
    return table


def ensure_product_goods_historical_sales_table(engine, year: int) -> Table:
    table = product_goods_historical_sales_table_for_year(year)
    table.create(engine, checkfirst=True)
    return table
