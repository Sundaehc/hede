from __future__ import annotations

from sqlalchemy import BigInteger, Column, DateTime, Identity, Index, JSON, Table, Text, UniqueConstraint, func

from domain.schema import METADATA


COLOR_BARCODE_TABLE = Table(
    "color_barcodes",
    METADATA,
    Column("id", BigInteger, Identity(always=False), primary_key=True),
    Column("brand", Text, nullable=False),
    Column("color_barcode", Text, nullable=False),
    Column("color_name", Text, nullable=False),
    Column("source_workbook", Text, nullable=False),
    Column("source_sheet", Text, nullable=False),
    Column("source_row_number", Text, nullable=False),
    Column("raw_payload", JSON, nullable=False),
    Column("created_at", DateTime(timezone=True), server_default=func.date_trunc("minute", func.now())),
    Column("updated_at", DateTime(timezone=True), server_default=func.date_trunc("minute", func.now()), onupdate=func.date_trunc("minute", func.now())),
    UniqueConstraint("brand", "color_barcode", name="uq_color_barcodes_brand_code"),
)

Index("idx_color_barcodes_brand", COLOR_BARCODE_TABLE.c.brand)
Index("idx_color_barcodes_color_barcode", COLOR_BARCODE_TABLE.c.color_barcode)
Index("idx_color_barcodes_color_name", COLOR_BARCODE_TABLE.c.color_name)
