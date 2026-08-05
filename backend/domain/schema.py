from __future__ import annotations

from sqlalchemy import JSON, BigInteger, Column, DateTime, Identity, Index, MetaData, Numeric, Table, Text, UniqueConstraint, func

from domain.fields import FieldSpec, PRODUCT_FIELDS
from domain.sources import TABLE_NAMES


METADATA = MetaData()



def _column_type(field: FieldSpec):
    if field.type_key == "numeric":
        return Numeric(10, 2)
    return Text()



def _build_product_table(table_name: str) -> Table:
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
    columns.append(Column("last_imported_at", DateTime(timezone=True), nullable=True))
    columns.append(UniqueConstraint("sku", name=f"uq_{table_name}_sku"))
    table = Table(table_name, METADATA, *columns)
    Index(f"idx_{table_name}_year", table.c.year)
    Index(f"idx_{table_name}_original_sku", table.c.original_sku)
    Index(f"idx_{table_name}_last_imported_at", table.c.last_imported_at)
    return table


def build_product_tables() -> dict[str, Table]:
    return {
        brand_group: _build_product_table(table_name)
        for brand_group, table_name in TABLE_NAMES.items()
    }


PRODUCT_TABLES = build_product_tables()

# Smiley and NI use the editable product-archive shape, but intentionally stay
# outside TABLE_NAMES so they do not enter fine-table or product-goods jobs.
SMILEY_PRODUCT_TABLE = _build_product_table("smiley_products")
NI_PRODUCT_TABLE = _build_product_table("ni_products")
PRODUCT_ARCHIVE_TABLES = {
    **PRODUCT_TABLES,
    "smiley": SMILEY_PRODUCT_TABLE,
    "ni": NI_PRODUCT_TABLE,
}
