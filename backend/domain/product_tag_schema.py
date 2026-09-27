from __future__ import annotations

from sqlalchemy import BigInteger, Boolean, CheckConstraint, Column, DateTime, ForeignKey, Identity, Index, Integer, JSON, Table, Text, UniqueConstraint, func

from domain.schema import METADATA


PRODUCT_TAG_DEFINITIONS_TABLE = Table(
    "product_tag_definitions",
    METADATA,
    Column("id", BigInteger, Identity(always=False), primary_key=True),
    Column("tag_code", Text, nullable=False),
    Column("tag_name", Text, nullable=False),
    Column("tag_group", Text, nullable=False),
    Column("value_type", Text, nullable=False, server_default="multiple"),
    Column("source_type", Text, nullable=False, server_default="manual"),
    Column("is_active", Boolean, nullable=False, server_default="true"),
    Column("is_manual_override", Boolean, nullable=False, server_default="false"),
    Column("sort_order", Integer, nullable=False, server_default="0"),
    Column("created_at", DateTime(timezone=True), server_default=func.date_trunc("minute", func.now())),
    Column("updated_at", DateTime(timezone=True), server_default=func.date_trunc("minute", func.now()), onupdate=func.date_trunc("minute", func.now())),
    UniqueConstraint("tag_code", name="uq_product_tag_definitions_code"),
)

Index("idx_product_tag_definitions_group_active", PRODUCT_TAG_DEFINITIONS_TABLE.c.tag_group, PRODUCT_TAG_DEFINITIONS_TABLE.c.is_active)


PRODUCT_STYLE_ENTITIES_TABLE = Table(
    "product_style_entities",
    METADATA,
    Column("id", BigInteger, Identity(always=False), primary_key=True),
    Column("brand", Text, nullable=False),
    Column("style_key", Text, nullable=False),
    Column("style_name", Text, nullable=True),
    Column("source", Text, nullable=False, server_default="derived"),
    Column("created_at", DateTime(timezone=True), server_default=func.date_trunc("minute", func.now())),
    Column("updated_at", DateTime(timezone=True), server_default=func.date_trunc("minute", func.now()), onupdate=func.date_trunc("minute", func.now())),
    UniqueConstraint("brand", "style_key", name="uq_product_style_entities_brand_key"),
)


PRODUCT_TAG_ASSIGNMENTS_TABLE = Table(
    "product_tag_assignments",
    METADATA,
    Column("id", BigInteger, Identity(always=False), primary_key=True),
    Column("tag_id", BigInteger, ForeignKey("product_tag_definitions.id", ondelete="CASCADE"), nullable=False),
    Column("brand", Text, nullable=False),
    Column("style_id", BigInteger, ForeignKey("product_style_entities.id", ondelete="CASCADE"), nullable=True),
    Column("product_id", BigInteger, nullable=True),
    Column("target_type", Text, nullable=False, server_default="sku"),
    Column("source_type", Text, nullable=False, server_default="manual"),
    Column("confidence", Integer, nullable=True),
    Column("evidence", JSON, nullable=True),
    Column("status", Text, nullable=False, server_default="confirmed"),
    Column("is_locked", Boolean, nullable=False, server_default="false"),
    Column("valid_from", DateTime(timezone=True), nullable=True),
    Column("valid_to", DateTime(timezone=True), nullable=True),
    Column("created_by", BigInteger, nullable=True),
    Column("created_at", DateTime(timezone=True), server_default=func.date_trunc("minute", func.now())),
    Column("updated_at", DateTime(timezone=True), server_default=func.date_trunc("minute", func.now()), onupdate=func.date_trunc("minute", func.now())),
    UniqueConstraint("tag_id", "brand", "style_id", "product_id", "target_type", name="uq_product_tag_assignment_target"),
    CheckConstraint(
        "(style_id IS NOT NULL AND product_id IS NULL) OR (style_id IS NULL AND product_id IS NOT NULL)",
        name="ck_product_tag_assignment_one_target",
    ),
)

Index("idx_product_tag_assignments_product", PRODUCT_TAG_ASSIGNMENTS_TABLE.c.brand, PRODUCT_TAG_ASSIGNMENTS_TABLE.c.product_id, PRODUCT_TAG_ASSIGNMENTS_TABLE.c.status)
Index("idx_product_tag_assignments_style", PRODUCT_TAG_ASSIGNMENTS_TABLE.c.brand, PRODUCT_TAG_ASSIGNMENTS_TABLE.c.style_id, PRODUCT_TAG_ASSIGNMENTS_TABLE.c.status)
Index("idx_product_tag_assignments_tag", PRODUCT_TAG_ASSIGNMENTS_TABLE.c.tag_id, PRODUCT_TAG_ASSIGNMENTS_TABLE.c.status)
Index(
    "uq_product_tag_assignment_product",
    PRODUCT_TAG_ASSIGNMENTS_TABLE.c.tag_id,
    PRODUCT_TAG_ASSIGNMENTS_TABLE.c.brand,
    PRODUCT_TAG_ASSIGNMENTS_TABLE.c.product_id,
    PRODUCT_TAG_ASSIGNMENTS_TABLE.c.target_type,
    unique=True,
    postgresql_where=PRODUCT_TAG_ASSIGNMENTS_TABLE.c.product_id.isnot(None),
)
Index(
    "uq_product_tag_assignment_style",
    PRODUCT_TAG_ASSIGNMENTS_TABLE.c.tag_id,
    PRODUCT_TAG_ASSIGNMENTS_TABLE.c.brand,
    PRODUCT_TAG_ASSIGNMENTS_TABLE.c.style_id,
    PRODUCT_TAG_ASSIGNMENTS_TABLE.c.target_type,
    unique=True,
    postgresql_where=PRODUCT_TAG_ASSIGNMENTS_TABLE.c.style_id.isnot(None),
)


def ensure_product_tag_schema(connection) -> None:
    """Create the tag tables for older databases."""
    PRODUCT_TAG_DEFINITIONS_TABLE.create(connection, checkfirst=True)
    connection.exec_driver_sql(
        "ALTER TABLE product_tag_definitions "
        "ADD COLUMN IF NOT EXISTS is_manual_override BOOLEAN NOT NULL DEFAULT FALSE"
    )
    PRODUCT_STYLE_ENTITIES_TABLE.create(connection, checkfirst=True)
    PRODUCT_TAG_ASSIGNMENTS_TABLE.create(connection, checkfirst=True)
