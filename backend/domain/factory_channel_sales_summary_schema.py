from __future__ import annotations

from sqlalchemy import BigInteger, Column, Date, DateTime, Identity, Index, Table, Text, UniqueConstraint, func

from domain.schema import METADATA


FACTORY_CHANNEL_SALES_DAILY_SUMMARY_TABLE = Table(
    "factory_channel_sales_daily_summaries",
    METADATA,
    Column("id", BigInteger, Identity(always=False), primary_key=True),
    Column("brand", Text, nullable=False),
    Column("sales_date", Date, nullable=False),
    Column("product_code", Text, nullable=False, server_default=""),
    Column("channel_group", Text, nullable=False, server_default=""),
    Column("match_status", Text, nullable=False, server_default="matched"),
    Column("quantity", BigInteger, nullable=False, server_default="0"),
    Column("gross_quantity", BigInteger, nullable=False, server_default="0"),
    Column("return_quantity", BigInteger, nullable=False, server_default="0"),
    Column("created_at", DateTime(timezone=True), server_default=func.date_trunc("minute", func.now())),
    Column(
        "updated_at",
        DateTime(timezone=True),
        server_default=func.date_trunc("minute", func.now()),
        onupdate=func.date_trunc("minute", func.now()),
    ),
    UniqueConstraint(
        "brand",
        "sales_date",
        "product_code",
        "channel_group",
        "match_status",
        name="uq_factory_channel_sales_daily_summary_key",
    ),
)

Index(
    "idx_factory_channel_sales_daily_summary_brand_date",
    FACTORY_CHANNEL_SALES_DAILY_SUMMARY_TABLE.c.brand,
    FACTORY_CHANNEL_SALES_DAILY_SUMMARY_TABLE.c.sales_date,
)
