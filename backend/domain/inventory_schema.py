from __future__ import annotations

from sqlalchemy import (
    BigInteger,
    Column,
    DateTime,
    ForeignKey,
    Identity,
    Integer,
    JSON,
    Numeric,
    Table,
    Text,
    UniqueConstraint,
    func,
)

from domain.inventory_sources import (
    INVENTORY_CANONICAL_COLUMNS,
    INVENTORY_DETAIL_COLUMNS,
    INVENTORY_DETAIL_TABLE_NAME,
    INVENTORY_TABLE_NAME,
    JST_STOCK_COLUMNS,
    JST_STOCK_TABLE_NAME,
    SUPPLIER_TABLE_NAME,
    WAREHOUSE_TABLE_NAME,
)
from domain.schema import METADATA


def _column_type(column_name: str):
    if column_name in ("total_count", "amount", "quantity", "unit_price"):
        return Numeric(10, 2)
    return Text()


def build_inventory_table() -> Table:
    columns: list = [
        Column("id", BigInteger, Identity(always=False), primary_key=True),
        Column("source_workbook", Text, nullable=False, default=""),
        Column("source_sheet", Text, nullable=False, default=""),
        Column("source_row_number", Text, nullable=False, default=""),
        Column("raw_payload", JSON, nullable=False, default=dict),
    ]
    columns.extend(Column(name, _column_type(name)) for name in INVENTORY_CANONICAL_COLUMNS)
    columns.append(Column("extra_fields", JSON, nullable=True))
    columns.append(Column("created_at", DateTime(timezone=True), server_default=func.date_trunc('minute', func.now())))
    columns.append(Column("updated_at", DateTime(timezone=True), server_default=func.date_trunc('minute', func.now()), onupdate=func.date_trunc('minute', func.now())))
    return Table(INVENTORY_TABLE_NAME, METADATA, *columns)


def build_inventory_detail_table() -> Table:
    columns: list = [
        Column("id", BigInteger, Identity(always=False), primary_key=True),
        Column("document_id", BigInteger, ForeignKey(f"{INVENTORY_TABLE_NAME}.id", ondelete="CASCADE"), nullable=False),
    ]
    columns.extend(Column(name, _column_type(name)) for name in INVENTORY_DETAIL_COLUMNS)
    columns.append(Column("created_at", DateTime(timezone=True), server_default=func.date_trunc('minute', func.now())))
    columns.append(Column("updated_at", DateTime(timezone=True), server_default=func.date_trunc('minute', func.now()), onupdate=func.date_trunc('minute', func.now())))
    return Table(INVENTORY_DETAIL_TABLE_NAME, METADATA, *columns)


def build_supplier_table() -> Table:
    columns: list = [
        Column("id", BigInteger, Identity(always=False), primary_key=True),
        Column("name", Text, nullable=False),
        Column("contact", Text, nullable=True),
        Column("address", Text, nullable=True),
        Column("notes", Text, nullable=True),
        Column("created_at", DateTime(timezone=True), server_default=func.date_trunc('minute', func.now())),
        Column("updated_at", DateTime(timezone=True), server_default=func.date_trunc('minute', func.now()), onupdate=func.date_trunc('minute', func.now())),
        UniqueConstraint("name", name="uq_supplier_name"),
    ]
    return Table(SUPPLIER_TABLE_NAME, METADATA, *columns)


def build_warehouse_table() -> Table:
    columns: list = [
        Column("id", BigInteger, Identity(always=False), primary_key=True),
        Column("name", Text, nullable=False),
        Column("address", Text, nullable=True),
        Column("notes", Text, nullable=True),
        Column("created_at", DateTime(timezone=True), server_default=func.date_trunc('minute', func.now())),
        Column("updated_at", DateTime(timezone=True), server_default=func.date_trunc('minute', func.now()), onupdate=func.date_trunc('minute', func.now())),
        UniqueConstraint("name", name="uq_warehouse_name"),
    ]
    return Table(WAREHOUSE_TABLE_NAME, METADATA, *columns)


INVENTORY_TABLE = build_inventory_table()
INVENTORY_DETAIL_TABLE = build_inventory_detail_table()
SUPPLIER_TABLE = build_supplier_table()
WAREHOUSE_TABLE = build_warehouse_table()


def build_jst_stock_table() -> Table:
    columns: list = [
        Column("id", BigInteger, Identity(always=False), primary_key=True),
        Column("stock_date", Text, nullable=False),
        Column("product_code", Text, nullable=False),
        Column("available_qty", Integer),
        Column("created_at", DateTime(timezone=True), server_default=func.date_trunc('minute', func.now())),
        UniqueConstraint("stock_date", "product_code", name="uq_jst_stock_date_code"),
    ]
    return Table(JST_STOCK_TABLE_NAME, METADATA, *columns)


JST_STOCK_TABLE = build_jst_stock_table()
