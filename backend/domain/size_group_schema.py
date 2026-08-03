from __future__ import annotations

from sqlalchemy import BigInteger, Column, DateTime, ForeignKey, Identity, Index, Integer, Table, Text, UniqueConstraint, func

from domain.schema import METADATA


IDENTITY_TYPE = BigInteger().with_variant(Integer, "sqlite")


SIZE_GROUPS_TABLE = Table(
    "size_groups",
    METADATA,
    Column("id", IDENTITY_TYPE, Identity(always=False), primary_key=True),
    Column("name", Text, nullable=False),
    Column("created_at", DateTime(timezone=True), server_default=func.date_trunc("minute", func.now())),
    Column(
        "updated_at",
        DateTime(timezone=True),
        server_default=func.date_trunc("minute", func.now()),
        onupdate=func.date_trunc("minute", func.now()),
    ),
    UniqueConstraint("name", name="uq_size_groups_name"),
)


SIZE_GROUP_ITEMS_TABLE = Table(
    "size_group_items",
    METADATA,
    Column("id", IDENTITY_TYPE, Identity(always=False), primary_key=True),
    Column("size_group_id", IDENTITY_TYPE, ForeignKey("size_groups.id", ondelete="CASCADE"), nullable=False),
    Column("size_name", Text, nullable=False),
    Column("barcode", Text, nullable=False),
    Column("sort_order", Integer, nullable=False, server_default="0"),
    Column("created_at", DateTime(timezone=True), server_default=func.date_trunc("minute", func.now())),
    Column(
        "updated_at",
        DateTime(timezone=True),
        server_default=func.date_trunc("minute", func.now()),
        onupdate=func.date_trunc("minute", func.now()),
    ),
    UniqueConstraint("size_group_id", "size_name", name="uq_size_group_items_group_size"),
    UniqueConstraint("size_group_id", "barcode", name="uq_size_group_items_group_barcode"),
)

Index("idx_size_group_items_group_sort", SIZE_GROUP_ITEMS_TABLE.c.size_group_id, SIZE_GROUP_ITEMS_TABLE.c.sort_order)
