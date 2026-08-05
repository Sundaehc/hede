from __future__ import annotations

from sqlalchemy import BigInteger, Column, DateTime, Identity, Index, Integer, Table, Text, UniqueConstraint, func

from domain.schema import METADATA


IDENTITY_TYPE = BigInteger().with_variant(Integer, "sqlite")


PRODUCT_SIZE_GROUP_MAPPINGS_TABLE = Table(
    "product_size_group_mappings",
    METADATA,
    Column("id", IDENTITY_TYPE, Identity(always=False), primary_key=True),
    Column("product_code", Text, nullable=False),
    Column("size_group_name", Text, nullable=False),
    Column("source_workbook", Text, nullable=False, default=""),
    Column("source_sheet", Text, nullable=False, default=""),
    Column("source_row_number", Text, nullable=False, default=""),
    Column("created_at", DateTime(timezone=True), server_default=func.date_trunc("minute", func.now())),
    Column("updated_at", DateTime(timezone=True), server_default=func.date_trunc("minute", func.now()), onupdate=func.date_trunc("minute", func.now())),
    UniqueConstraint("product_code", name="uq_product_size_group_mappings_code"),
)

Index("idx_product_size_group_mappings_group", PRODUCT_SIZE_GROUP_MAPPINGS_TABLE.c.size_group_name)
