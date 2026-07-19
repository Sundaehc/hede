from __future__ import annotations

from sqlalchemy import BigInteger, Column, Date, DateTime, Identity, Index, Integer, Table, Text, UniqueConstraint, func

from domain.schema import METADATA


PRODUCT_GOODS_SALES_PERIODS_TABLE = Table(
    "product_goods_sales_periods",
    METADATA,
    Column("id", BigInteger, Identity(always=False), primary_key=True),
    Column("brand", Text, nullable=False),
    Column("product_code", Text, nullable=False),
    Column("style_code", Text, nullable=True),
    Column("period_type", Text, nullable=False),
    Column("period_start", Date, nullable=False),
    Column("sales_quantity", Integer, nullable=False),
    Column("source_as_of_date", Date, nullable=True),
    Column("source_workbook", Text, nullable=False),
    Column("source_sheet", Text, nullable=False),
    Column("source_row_number", Integer, nullable=False),
    Column("created_at", DateTime(timezone=True), server_default=func.date_trunc("minute", func.now())),
    UniqueConstraint(
        "source_workbook",
        "source_sheet",
        "source_row_number",
        "period_type",
        "period_start",
        name="uq_product_goods_sales_period_source",
    ),
)

Index("idx_product_goods_sales_period_brand_product", PRODUCT_GOODS_SALES_PERIODS_TABLE.c.brand, PRODUCT_GOODS_SALES_PERIODS_TABLE.c.product_code)
Index("idx_product_goods_sales_period_brand_style", PRODUCT_GOODS_SALES_PERIODS_TABLE.c.brand, PRODUCT_GOODS_SALES_PERIODS_TABLE.c.style_code)
Index("idx_product_goods_sales_period_period", PRODUCT_GOODS_SALES_PERIODS_TABLE.c.period_type, PRODUCT_GOODS_SALES_PERIODS_TABLE.c.period_start)


def ensure_product_goods_sales_periods_table(engine) -> None:
    PRODUCT_GOODS_SALES_PERIODS_TABLE.create(engine, checkfirst=True)
