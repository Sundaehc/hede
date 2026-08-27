from __future__ import annotations

from sqlalchemy import BigInteger, Column, DateTime, Identity, Index, Table, Text, UniqueConstraint, func

from domain.schema import METADATA


PRODUCT_AUXILIARY_ATTRIBUTE_FIELDS = {
    "品名": "product_name",
    "产品型号": "product_model",
    "鞋面材质": "upper_material",
    "内里材质": "lining_material",
    "大底材质": "outsole_material",
    "鞋垫材质": "insole_material",
    "执行标准": "execution_standard",
}


PRODUCT_AUXILIARY_ATTRIBUTE_TABLE = Table(
    "product_auxiliary_attributes",
    METADATA,
    Column("id", BigInteger, Identity(always=False), primary_key=True),
    Column("brand_scope", Text, nullable=False),
    Column("attribute_type", Text, nullable=False),
    Column("attribute_name", Text, nullable=False),
    Column("source_workbook", Text, nullable=False, default=""),
    Column("source_sheet", Text, nullable=False, default=""),
    Column("source_row_number", Text, nullable=False, default=""),
    Column("created_at", DateTime(timezone=True), server_default=func.date_trunc("minute", func.now())),
    Column(
        "updated_at",
        DateTime(timezone=True),
        server_default=func.date_trunc("minute", func.now()),
        onupdate=func.date_trunc("minute", func.now()),
    ),
    UniqueConstraint(
        "brand_scope",
        "attribute_type",
        "attribute_name",
        name="uq_product_auxiliary_attributes_scope_type_name",
    ),
)

Index("idx_product_auxiliary_attributes_scope_type", PRODUCT_AUXILIARY_ATTRIBUTE_TABLE.c.brand_scope, PRODUCT_AUXILIARY_ATTRIBUTE_TABLE.c.attribute_type)
Index("idx_product_auxiliary_attributes_name", PRODUCT_AUXILIARY_ATTRIBUTE_TABLE.c.attribute_name)
