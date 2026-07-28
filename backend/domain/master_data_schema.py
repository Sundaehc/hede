from __future__ import annotations

from sqlalchemy import BigInteger, Boolean, CheckConstraint, Column, DateTime, ForeignKey, Identity, Index, JSON, Table, Text, UniqueConstraint, func

from domain.schema import METADATA


MASTER_DATA_ENTITY_TYPES = ("supplier", "warehouse", "shop", "channel")
PRODUCT_CODE_TYPES = ("sku", "original_sku", "goods_code", "product_code", "style_code")


MASTER_DATA_ENTITIES_TABLE = Table(
    "master_data_entities",
    METADATA,
    Column("id", BigInteger, Identity(always=False), primary_key=True),
    Column("entity_type", Text, nullable=False),
    Column("canonical_name", Text, nullable=False),
    Column("canonical_code", Text, nullable=True),
    Column("is_active", Boolean, nullable=False, server_default="true"),
    Column("raw_payload", JSON, nullable=True),
    Column("created_at", DateTime(timezone=True), server_default=func.date_trunc("minute", func.now())),
    Column(
        "updated_at",
        DateTime(timezone=True),
        server_default=func.date_trunc("minute", func.now()),
        onupdate=func.date_trunc("minute", func.now()),
    ),
    CheckConstraint(
        "entity_type IN ('supplier', 'warehouse', 'shop', 'channel')",
        name="ck_master_data_entities_type",
    ),
    UniqueConstraint("entity_type", "canonical_name", name="uq_master_data_entities_type_name"),
)
Index("idx_master_data_entities_type_active", MASTER_DATA_ENTITIES_TABLE.c.entity_type, MASTER_DATA_ENTITIES_TABLE.c.is_active)


MASTER_DATA_ALIASES_TABLE = Table(
    "master_data_aliases",
    METADATA,
    Column("id", BigInteger, Identity(always=False), primary_key=True),
    Column("entity_id", BigInteger, ForeignKey("master_data_entities.id", ondelete="CASCADE"), nullable=False),
    Column("entity_type", Text, nullable=False),
    Column("alias_name", Text, nullable=False),
    Column("normalized_name", Text, nullable=False),
    Column("source_system", Text, nullable=False),
    Column("raw_payload", JSON, nullable=True),
    Column("created_at", DateTime(timezone=True), server_default=func.date_trunc("minute", func.now())),
    Column(
        "updated_at",
        DateTime(timezone=True),
        server_default=func.date_trunc("minute", func.now()),
        onupdate=func.date_trunc("minute", func.now()),
    ),
    CheckConstraint(
        "entity_type IN ('supplier', 'warehouse', 'shop', 'channel')",
        name="ck_master_data_aliases_type",
    ),
    UniqueConstraint("entity_type", "normalized_name", name="uq_master_data_aliases_type_normalized"),
)
Index("idx_master_data_aliases_entity", MASTER_DATA_ALIASES_TABLE.c.entity_id)


PRODUCT_CODE_MAPPINGS_TABLE = Table(
    "product_code_mappings",
    METADATA,
    Column("id", BigInteger, Identity(always=False), primary_key=True),
    Column("brand", Text, nullable=False, server_default=""),
    Column("code_type", Text, nullable=False),
    Column("code_value", Text, nullable=False),
    Column("canonical_product_code", Text, nullable=False),
    Column("source_system", Text, nullable=False),
    Column("is_active", Boolean, nullable=False, server_default="true"),
    Column("raw_payload", JSON, nullable=True),
    Column("created_at", DateTime(timezone=True), server_default=func.date_trunc("minute", func.now())),
    Column(
        "updated_at",
        DateTime(timezone=True),
        server_default=func.date_trunc("minute", func.now()),
        onupdate=func.date_trunc("minute", func.now()),
    ),
    CheckConstraint(
        "code_type IN ('sku', 'original_sku', 'goods_code', 'product_code', 'style_code')",
        name="ck_product_code_mappings_type",
    ),
    UniqueConstraint(
        "brand",
        "code_type",
        "code_value",
        "canonical_product_code",
        name="uq_product_code_mappings_brand_type_value_canonical",
    ),
)
Index("idx_product_code_mappings_canonical", PRODUCT_CODE_MAPPINGS_TABLE.c.brand, PRODUCT_CODE_MAPPINGS_TABLE.c.canonical_product_code)
