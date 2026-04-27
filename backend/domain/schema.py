from __future__ import annotations

from sqlalchemy import JSON, BigInteger, Column, Identity, MetaData, Numeric, Table, Text, UniqueConstraint

from domain.sources import CANONICAL_COLUMNS, TABLE_NAMES


METADATA = MetaData()



def _column_type(column_name: str):
    if column_name == "cost":
        return Numeric(10, 2)
    return Text()



def build_product_tables() -> dict[str, Table]:
    tables: dict[str, Table] = {}
    for brand_group, table_name in TABLE_NAMES.items():
        columns = [
            Column("id", BigInteger, Identity(always=False), primary_key=True),
            Column("source_workbook", Text, nullable=False),
            Column("source_sheet", Text, nullable=False),
            Column("source_row_number", Text, nullable=False),
            Column("raw_payload", JSON, nullable=False),
        ]
        columns.extend(Column(name, _column_type(name)) for name in CANONICAL_COLUMNS)
        columns.append(UniqueConstraint("sku", name=f"uq_{table_name}_sku"))
        tables[brand_group] = Table(table_name, METADATA, *columns)
    return tables


PRODUCT_TABLES = build_product_tables()
