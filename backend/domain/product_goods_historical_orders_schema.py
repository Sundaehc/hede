from __future__ import annotations

from sqlalchemy import BigInteger, Column, Date, DateTime, Identity, Index, Integer, Table, Text, UniqueConstraint, func

from domain.schema import METADATA


HISTORICAL_ORDER_START_YEAR = 2022


def product_goods_historical_orders_table_for_year(year: int) -> Table:
    if year < 2000 or year > 2100:
        raise ValueError(f"Unsupported historical order year: {year}")
    table_name = f"product_goods_historical_orders_{year:04d}"
    if table_name in METADATA.tables:
        return METADATA.tables[table_name]
    table = Table(
        table_name,
        METADATA,
        Column("id", BigInteger, Identity(always=False), primary_key=True),
        Column("brand", Text, nullable=False),
        Column("order_date", Date, nullable=False),
        Column("original_sku", Text, nullable=False),
        Column("channel", Text, nullable=True),
        Column("order_quantity", Integer, nullable=False),
        Column("source_workbook", Text, nullable=False),
        Column("source_sheet", Text, nullable=False),
        Column("source_row_number", Integer, nullable=False),
        Column("created_at", DateTime(timezone=True), server_default=func.date_trunc("minute", func.now())),
        Column("updated_at", DateTime(timezone=True), server_default=func.date_trunc("minute", func.now()), onupdate=func.date_trunc("minute", func.now())),
        UniqueConstraint("source_workbook", "source_sheet", "source_row_number", name=f"uq_{table_name}_source_row"),
    )
    Index(f"idx_{table_name}_brand_original", table.c.brand, table.c.original_sku)
    Index(f"idx_{table_name}_order_date", table.c.order_date)
    return table


def ensure_product_goods_historical_orders_table(engine, year: int) -> Table:
    table = product_goods_historical_orders_table_for_year(year)
    table.create(engine, checkfirst=True)
    return table
