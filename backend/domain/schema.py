from __future__ import annotations

from sqlalchemy import JSON, BigInteger, Column, DateTime, Identity, Index, MetaData, Numeric, Table, Text, UniqueConstraint, func

from domain.fields import FieldSpec, PRODUCT_FIELDS
from domain.sources import TABLE_NAMES


METADATA = MetaData()



def _column_type(field: FieldSpec):
    if field.type_key == "numeric":
        return Numeric(10, 2)
    return Text()



def build_product_tables() -> dict[str, Table]:
    tables: dict[str, Table] = {}
    for brand_group, table_name in TABLE_NAMES.items():
        columns: list = [
            Column("id", BigInteger, Identity(always=False), primary_key=True),
            Column("source_workbook", Text, nullable=False),
            Column("source_sheet", Text, nullable=False),
            Column("source_row_number", Text, nullable=False),
            Column("raw_payload", JSON, nullable=False),
        ]
        columns.extend(Column(field.name, _column_type(field)) for field in PRODUCT_FIELDS)
        columns.append(Column("extra_fields", JSON, nullable=True))
        columns.append(Column("created_at", DateTime(timezone=True), server_default=func.date_trunc('minute', func.now())))
        columns.append(Column("updated_at", DateTime(timezone=True), server_default=func.date_trunc('minute', func.now()), onupdate=func.date_trunc('minute', func.now())))
        columns.append(UniqueConstraint("sku", name=f"uq_{table_name}_sku"))
        table = Table(table_name, METADATA, *columns)
        Index(f"idx_{table_name}_year", table.c.year)
        tables[brand_group] = table
    return tables


PRODUCT_TABLES = build_product_tables()
