from __future__ import annotations

from sqlalchemy import BigInteger, Column, DateTime, Identity, Index, Table, Text, UniqueConstraint, func

from domain.schema import METADATA


PRODUCT_GOODS_SHOP_CHANNEL_MAPPINGS_TABLE = Table(
    "product_goods_shop_channel_mappings",
    METADATA,
    Column("id", BigInteger, Identity(always=False), primary_key=True),
    Column("brand", Text, nullable=False),
    Column("shop_name", Text, nullable=False),
    Column("channel", Text, nullable=False),
    Column("source_workbook", Text, nullable=False),
    Column("source_sheet", Text, nullable=False),
    Column("created_at", DateTime(timezone=True), server_default=func.date_trunc("minute", func.now())),
    Column("updated_at", DateTime(timezone=True), server_default=func.date_trunc("minute", func.now()), onupdate=func.date_trunc("minute", func.now())),
    UniqueConstraint("brand", "shop_name", name="uq_product_goods_shop_channel_brand_shop"),
)

Index("idx_product_goods_shop_channel_brand", PRODUCT_GOODS_SHOP_CHANNEL_MAPPINGS_TABLE.c.brand)
