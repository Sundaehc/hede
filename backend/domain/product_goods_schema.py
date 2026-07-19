from __future__ import annotations

from sqlalchemy import BigInteger, Column, DateTime, Identity, JSON, Table, Text, UniqueConstraint, func

from domain.schema import METADATA


PRODUCT_GOODS_OVERRIDES_TABLE = Table(
    "product_goods_overrides",
    METADATA,
    Column("id", BigInteger, Identity(always=False), primary_key=True),
    Column("brand", Text, nullable=False),
    Column("product_id", BigInteger, nullable=False),
    Column("platform", Text, nullable=True),
    Column("category_l4", Text, nullable=True),
    Column("product_role", Text, nullable=True),
    Column("product_type", Text, nullable=True),
    Column("douyin_hot", Text, nullable=True),
    Column("clearance", Text, nullable=True),
    Column("remark", Text, nullable=True),
    Column("extra_fields", JSON, nullable=True),
    Column("created_at", DateTime(timezone=True), server_default=func.date_trunc("minute", func.now())),
    Column("updated_at", DateTime(timezone=True), server_default=func.date_trunc("minute", func.now()), onupdate=func.date_trunc("minute", func.now())),
    UniqueConstraint("brand", "product_id", name="uq_product_goods_overrides_brand_product"),
)
