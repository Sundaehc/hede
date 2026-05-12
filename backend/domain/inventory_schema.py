from __future__ import annotations

from sqlalchemy import (
    BigInteger,
    Column,
    DateTime,
    Identity,
    JSON,
    Numeric,
    Table,
    Text,
    UniqueConstraint,
    func,
)

from domain.inventory_sources import (
    INVENTORY_CANONICAL_COLUMNS,
    INVENTORY_TABLE_NAME,
    SUPPLIER_TABLE_NAME,
    WAREHOUSE_TABLE_NAME,
)
from domain.schema import METADATA


def _column_type(column_name: str):
    if column_name in ("quantity", "unit_price"):
        return Numeric(10, 2)
    return Text()


def build_inventory_table() -> Table:
    columns = [
        Column("id", BigInteger, Identity(always=False), primary_key=True),
        Column("source_workbook", Text, nullable=False, default=""),
        Column("source_sheet", Text, nullable=False, default=""),
        Column("source_row_number", Text, nullable=False, default=""),
        Column("raw_payload", JSON, nullable=False, default=dict),
    ]
    columns.extend(Column(name, _column_type(name)) for name in INVENTORY_CANONICAL_COLUMNS)
    columns.append(Column("extra_fields", JSON, nullable=True))
    columns.append(Column("created_at", DateTime(timezone=True), server_default=func.now()))
    columns.append(Column("updated_at", DateTime(timezone=True), server_default=func.now(), onupdate=func.now()))
    table = Table(INVENTORY_TABLE_NAME, METADATA, *columns)
    table.append_constraint(UniqueConstraint("summary", name="uq_inventory_summary"))
    return table


def build_supplier_table() -> Table:
    columns = [
        Column("id", BigInteger, Identity(always=False), primary_key=True),
        Column("name", Text, nullable=False),
        Column("contact", Text, nullable=True),
        Column("address", Text, nullable=True),
        Column("notes", Text, nullable=True),
        Column("created_at", DateTime(timezone=True), server_default=func.now()),
        Column("updated_at", DateTime(timezone=True), server_default=func.now(), onupdate=func.now()),
        UniqueConstraint("name", name="uq_supplier_name"),
    ]
    return Table(SUPPLIER_TABLE_NAME, METADATA, *columns)


def build_warehouse_table() -> Table:
    columns = [
        Column("id", BigInteger, Identity(always=False), primary_key=True),
        Column("name", Text, nullable=False),
        Column("address", Text, nullable=True),
        Column("notes", Text, nullable=True),
        Column("created_at", DateTime(timezone=True), server_default=func.now()),
        Column("updated_at", DateTime(timezone=True), server_default=func.now(), onupdate=func.now()),
        UniqueConstraint("name", name="uq_warehouse_name"),
    ]
    return Table(WAREHOUSE_TABLE_NAME, METADATA, *columns)


INVENTORY_TABLE = build_inventory_table()
SUPPLIER_TABLE = build_supplier_table()
WAREHOUSE_TABLE = build_warehouse_table()
