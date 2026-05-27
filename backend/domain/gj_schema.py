from __future__ import annotations

from sqlalchemy import BigInteger, Column, Date, DateTime, Identity, Index, Integer, JSON, Table, Text, UniqueConstraint, func

from domain.fields import GJ_MERGED_PRODUCT_INFO_FIELDS, FieldSpec
from domain.schema import METADATA


GJ_MERGED_PRODUCT_INFO_TABLE_NAME = "gj_merged_product_info"


def _column_type(field: FieldSpec):
    if field.type_key == "integer":
        return Integer()
    return Text()


def build_gj_merged_product_info_table() -> Table:
    columns: list = [
        Column("id", BigInteger, Identity(always=False), primary_key=True),
        Column("source_date", Text, nullable=False),
        Column("source_date_value", Date, nullable=True),
        Column("source_workbook", Text, nullable=False, default=""),
        Column("source_sheet", Text, nullable=False, default=""),
        Column("source_row_number", Text, nullable=False, default=""),
        Column("raw_payload", JSON, nullable=False, default=dict),
    ]
    columns.extend(Column(field.name, _column_type(field)) for field in GJ_MERGED_PRODUCT_INFO_FIELDS)
    columns.append(Column("extra_fields", JSON, nullable=True))
    columns.append(Column("created_at", DateTime(timezone=True), server_default=func.date_trunc("minute", func.now())))
    columns.append(Column("updated_at", DateTime(timezone=True), server_default=func.date_trunc("minute", func.now()), onupdate=func.date_trunc("minute", func.now())))
    table = Table(
        GJ_MERGED_PRODUCT_INFO_TABLE_NAME,
        METADATA,
        *columns,
        UniqueConstraint("source_date", "goods_code", name="uq_gj_merged_product_info_date_code"),
    )
    Index("idx_gj_merged_product_info_goods_code", table.c.goods_code)
    Index("idx_gj_merged_product_info_original_code", table.c.original_goods_code)
    Index("idx_gj_merged_product_info_source_date", table.c.source_date_value)
    return table


GJ_MERGED_PRODUCT_INFO_TABLE = build_gj_merged_product_info_table()
