from __future__ import annotations

import asyncio
import io
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from fastapi import BackgroundTasks, UploadFile
from openpyxl import Workbook
from sqlalchemy import Column, MetaData, Table, Text, create_engine

from api.routes import import_export, products
from domain.product_archive_features import has_womens_product_style_fields


HEJIN_BRAND = "supplier_brand_33aa8a0c3b6a"


@pytest.mark.parametrize("brand, expected", [
    ("cbanner_womens", True), (HEJIN_BRAND, True), ("cbanner_mens", False),
    ("supplier_brand_new", False), (None, False),
])
def test_womens_style_capability_is_scoped_to_configured_brands(brand, expected):
    assert has_womens_product_style_fields(brand) is expected


@pytest.mark.parametrize("brand, expected_scope", [
    (HEJIN_BRAND, "cbanner_womens"), ("cbanner_womens", "cbanner_womens"), ("supplier_brand_new", "other"),
])
def test_hejin_uses_womens_auxiliary_options(brand, expected_scope):
    engine = create_engine("sqlite://")
    table = Table(
        "product_auxiliary_attributes", MetaData(),
        Column("brand_scope", Text), Column("attribute_type", Text), Column("attribute_name", Text),
    )
    table.create(engine)
    with engine.begin() as connection:
        connection.execute(table.insert(), [
            {"brand_scope": "cbanner_womens", "attribute_type": "品名", "attribute_name": "女休闲鞋"},
            {"brand_scope": "other", "attribute_type": "品名", "attribute_name": "男休闲鞋"},
        ])
    request = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(
        repository=SimpleNamespace(engine=engine, is_product_archive_brand=lambda _: True),
    )))
    try:
        result = products.list_product_auxiliary_options(request, brand)
        assert result["brand_scope"] == expected_scope
        assert result["items"][0]["options"] == (["女休闲鞋"] if expected_scope == "cbanner_womens" else ["男休闲鞋"])
    finally:
        engine.dispose()


@pytest.mark.parametrize("brand", [HEJIN_BRAND, "cbanner_womens", "supplier_brand_new"])
def test_excel_import_retains_hejin_style_fields_and_separate_heel_heights(monkeypatch, brand):
    values = {
        "sole_style": "厚底", "fashion_elements": "蝴蝶结", "upper_height": "低帮", "opening_depth": "浅口",
        "boot_shaft": "短筒", "closure_type": "搭扣", "mesh_upper_type": "网面", "toe_shape": "方头",
        "heel_height": "高跟", "rear_heel_height": "5cm",
    }
    workbook = Workbook()
    workbook.active.append(["货号", "条码构成逻辑", *[import_export._export_label(field, brand) for field in values]])
    workbook.active.append(["HJ-001", "货号+颜色代码+尺码", *values.values()])
    buffer = io.BytesIO()
    workbook.save(buffer)
    workbook.close()
    buffer.seek(0)
    engine = create_engine("sqlite://")
    repository = SimpleNamespace(
        engine=engine, is_product_archive_brand=lambda _: True, find_by_sku=Mock(return_value=None),
        create_product=Mock(return_value={"id": 1, "sku": "HJ-001"}), mark_products_imported=Mock(),
    )
    request = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(repository=repository)))
    monkeypatch.setattr(import_export, "get_image_matcher", lambda *_: None)
    try:
        result = asyncio.run(import_export.import_products(
            request, BackgroundTasks(), brand, UploadFile(filename="style.xlsx", file=buffer),
        ))
        assert result["created"] == 1
        record = repository.create_product.call_args.args[1]
        for field, value in values.items():
            if field == "rear_heel_height" and not has_womens_product_style_fields(brand):
                assert record.get(field) is None
            else:
                assert record[field] == value
    finally:
        engine.dispose()
