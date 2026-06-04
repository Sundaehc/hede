from __future__ import annotations

from sqlalchemy import (
    BigInteger,
    Column,
    DateTime,
    Date,
    ForeignKey,
    Identity,
    Index,
    Integer,
    JSON,
    Numeric,
    Table,
    Text,
    UniqueConstraint,
    func,
)

from domain.inventory_sources import (
    INVENTORY_DETAIL_TABLE_NAME,
    INVENTORY_TABLE_NAME,
    JST_STOCK_TABLE_NAME,
    SUPPLIER_TABLE_NAME,
    WAREHOUSE_TABLE_NAME,
)
from domain.fields import (
    FieldSpec,
    INVENTORY_DETAIL_FIELDS,
    INVENTORY_FIELDS,
    JST_STOCK_FIELDS,
    SUPPLIER_FIELDS,
    WAREHOUSE_FIELDS,
)
from domain.schema import METADATA


def _column_type(field: FieldSpec):
    if field.type_key == "numeric":
        return Numeric(10, 2)
    if field.type_key == "integer":
        return Integer()
    return Text()


def build_inventory_table() -> Table:
    columns: list = [
        Column("id", BigInteger, Identity(always=False), primary_key=True),
        Column("source_workbook", Text, nullable=False, default=""),
        Column("source_sheet", Text, nullable=False, default=""),
        Column("source_row_number", Text, nullable=False, default=""),
        Column("raw_payload", JSON, nullable=False, default=dict),
    ]
    columns.extend(Column(field.name, _column_type(field)) for field in INVENTORY_FIELDS)
    columns.append(Column("date_value", Date, nullable=True))
    columns.append(Column("extra_fields", JSON, nullable=True))
    columns.append(Column("created_at", DateTime(timezone=True), server_default=func.date_trunc('minute', func.now())))
    columns.append(Column("updated_at", DateTime(timezone=True), server_default=func.date_trunc('minute', func.now()), onupdate=func.date_trunc('minute', func.now())))
    table = Table(INVENTORY_TABLE_NAME, METADATA, *columns)
    Index("idx_inventory_records_date", table.c.date)
    Index("idx_inventory_records_supplier", table.c.supplier)
    Index("idx_inventory_records_warehouse", table.c.warehouse)
    Index("idx_inventory_records_document_type", table.c.document_type)
    return table


def build_inventory_detail_table() -> Table:
    columns: list = [
        Column("id", BigInteger, Identity(always=False), primary_key=True),
        Column("document_id", BigInteger, ForeignKey(f"{INVENTORY_TABLE_NAME}.id", ondelete="CASCADE"), nullable=False),
    ]
    columns.extend(Column(field.name, _column_type(field)) for field in INVENTORY_DETAIL_FIELDS)
    columns.append(Column("created_at", DateTime(timezone=True), server_default=func.date_trunc('minute', func.now())))
    columns.append(Column("updated_at", DateTime(timezone=True), server_default=func.date_trunc('minute', func.now()), onupdate=func.date_trunc('minute', func.now())))
    table = Table(INVENTORY_DETAIL_TABLE_NAME, METADATA, *columns)
    Index("idx_inventory_details_document_id", table.c.document_id)
    return table


def build_supplier_table() -> Table:
    columns: list = [
        Column("id", BigInteger, Identity(always=False), primary_key=True),
        *[
            Column(field.name, _column_type(field), nullable=field.name != "name")
            for field in SUPPLIER_FIELDS
        ],
        Column("created_at", DateTime(timezone=True), server_default=func.date_trunc('minute', func.now())),
        Column("updated_at", DateTime(timezone=True), server_default=func.date_trunc('minute', func.now()), onupdate=func.date_trunc('minute', func.now())),
        UniqueConstraint("name", name="uq_supplier_name"),
    ]
    table = Table(SUPPLIER_TABLE_NAME, METADATA, *columns)
    Index("idx_suppliers_factory_code", table.c.factory_code)
    return table


def build_warehouse_table() -> Table:
    columns: list = [
        Column("id", BigInteger, Identity(always=False), primary_key=True),
        *[
            Column(field.name, _column_type(field), nullable=field.name != "name")
            for field in WAREHOUSE_FIELDS
        ],
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
        Column(JST_STOCK_FIELDS[0].name, _column_type(JST_STOCK_FIELDS[0]), nullable=False),
        Column("stock_date_value", Date, nullable=True),
        Column(JST_STOCK_FIELDS[1].name, _column_type(JST_STOCK_FIELDS[1]), nullable=False),
        Column(JST_STOCK_FIELDS[2].name, _column_type(JST_STOCK_FIELDS[2])),
        Column("created_at", DateTime(timezone=True), server_default=func.date_trunc('minute', func.now())),
        UniqueConstraint("stock_date", "product_code", name="uq_jst_stock_date_code"),
    ]
    return Table(JST_STOCK_TABLE_NAME, METADATA, *columns)


JST_STOCK_TABLE = build_jst_stock_table()
