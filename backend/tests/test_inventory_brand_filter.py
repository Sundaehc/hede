from __future__ import annotations

import asyncio
from datetime import date, datetime
from io import BytesIO
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from openpyxl import load_workbook
from sqlalchemy import create_engine, event

from api.routes.inventory import export_inventory, list_inventory_brands
from domain.inventory_brands import inventory_brand_filter_aliases, inventory_brand_options
from domain.inventory_schema import (
    GENERAL_CUSTOMER_BRAND_TABLE, GENERAL_CUSTOMER_SHOP_TABLE, GENERAL_CUSTOMER_UNIT_TABLE,
    INVENTORY_TABLE, SUPPLIER_BRAND_TABLE, SUPPLIER_TABLE, WAREHOUSE_BRAND_TABLE, WAREHOUSE_TABLE,
)
from storage.inventory_repository import InventoryRepository


@pytest.fixture
def brand_repository():
    engine = create_engine("sqlite://")
    event.listen(engine, "connect", lambda connection, record: connection.create_function(
        "date_trunc", 2, lambda unit, value: value,
    ))
    for table in (
        INVENTORY_TABLE, SUPPLIER_BRAND_TABLE, SUPPLIER_TABLE, WAREHOUSE_BRAND_TABLE,
        WAREHOUSE_TABLE, GENERAL_CUSTOMER_BRAND_TABLE, GENERAL_CUSTOMER_SHOP_TABLE, GENERAL_CUSTOMER_UNIT_TABLE,
    ):
        table.create(engine)
    with engine.begin() as connection:
        connection.execute(SUPPLIER_BRAND_TABLE.insert(), [
            {"id": 1, "code": "yandou", "name": "烟斗"},
            {"id": 2, "code": "cbanner_mens", "name": "千百度男鞋"},
            {"id": 3, "code": "cbanner_womens", "name": "千百度女鞋"},
            {"id": 4, "code": "eblan", "name": "伊伴男鞋"},
            {"id": 5, "code": "eblan_womens", "name": "伊伴女鞋"},
            {"id": 6, "code": "custom", "name": "自定义品牌"},
        ])
        connection.execute(SUPPLIER_TABLE.insert(), [
            {"id": 1, "brand": "yandou", "name": "烟斗供应商"},
            {"id": 2, "brand": "cbanner_mens", "name": "男鞋供应商"},
            {"id": 3, "brand": "cbanner_womens", "name": "女鞋供应商"},
            {"id": 4, "brand": "eblan", "name": "伊伴男供应商"},
            {"id": 5, "brand": "eblan_womens", "name": "伊伴女供应商"},
            {"id": 6, "brand": "custom", "name": "自定义供应商"},
        ])
        connection.execute(WAREHOUSE_BRAND_TABLE.insert(), [
            {"id": 1, "name": "烟斗仓库"}, {"id": 2, "name": "NI仓库"},
        ])
        connection.execute(WAREHOUSE_TABLE.insert(), [
            {"id": 1, "brand": "烟斗仓库", "name": "烟斗总仓"},
            {"id": 2, "brand": "NI仓库", "name": "NI总仓"},
        ])
        connection.execute(GENERAL_CUSTOMER_BRAND_TABLE.insert(), [
            {"id": 1, "name": "烟斗"}, {"id": 2, "name": "千百度"}, {"id": 3, "name": "自定义品牌"},
        ])
        connection.execute(GENERAL_CUSTOMER_SHOP_TABLE.insert(), [
            {"id": 1, "customer_name": "烟斗", "shop_name": "烟斗店铺", "is_active": False},
            {"id": 2, "customer_name": "千百度", "shop_name": "千百度店铺", "is_active": True},
            {"id": 3, "customer_name": "自定义品牌", "shop_name": "自定义店铺", "is_active": True},
            {"id": 4, "customer_name": "烟斗", "shop_name": "烟斗其他店铺", "is_active": True},
        ])
        connection.execute(GENERAL_CUSTOMER_UNIT_TABLE.insert(), [
            {"id": 1, "shop_id": 1, "unit_name": "烟斗单位"},
            {"id": 2, "shop_id": 4, "unit_name": "烟斗单位"},
            {"id": 3, "shop_id": 3, "unit_name": "自定义单位"},
        ])
        records = [
            (1, "进货单", "未知", "烟斗总仓"),
            (2, "应付款增加", "烟斗供应商", None),
            (3, "应收款减少", "烟斗店铺", None),
            (4, "应收款增加", "烟斗单位", None),
            (5, "批发销售单", "烟斗店铺", "NI总仓"),
            (6, "进货单", "未知", "NI总仓"),
            (7, "进货单", "烟斗供应商", "烟斗总仓"),
            (8, "同价调拨单", "烟斗总仓", "NI总仓"),
            (9, "进货单", "烟斗总仓", "NI总仓"),
            (10, "应付款增加", "烟斗供应商", None),
            (11, "应付款增加", "女鞋供应商", None),
            (12, "应收款增加", "千百度店铺", None),
            (13, "应付款增加", "伊伴女供应商", None),
            (14, "应付款增加", "伊伴男供应商", None),
            (15, "应收款增加", "自定义单位", None),
            (16, "应付款增加", "自定义供应商", None),
            (17, "应付款减少", " 烟斗供应商 ", None),
        ]
        connection.execute(INVENTORY_TABLE.insert(), [
            {
                "id": record_id, "document_number": f"DOC-{record_id}", "document_type": document_type,
                "supplier": supplier, "warehouse": warehouse, "date": "2026-10-01",
                "date_value": date(2026, 10, 1), "summary": "烟斗", "total_count": 1, "amount": 10,
                "deleted_at": datetime.now() if record_id == 10 else None,
            }
            for record_id, document_type, supplier, warehouse in records
        ])
    repository = object.__new__(InventoryRepository)
    repository.engine = engine
    repository.purge_expired_deleted_records = lambda: 0
    try:
        yield repository
    finally:
        engine.dispose()


@pytest.mark.parametrize("brand", ["yandou", "烟斗", "烟斗仓库", " YANDOU "])
def test_brand_matches_warehouse_supplier_shop_and_disabled_shop_units(brand_repository, brand):
    result = brand_repository.list_records(brands=[brand], page=1, page_size=100)
    assert {item["id"] for item in result["items"]} == {1, 2, 3, 4, 5, 7, 8, 17}
    assert result["total"] == 8
    assert result["totals"]["all"]["amount"] == "80"


def test_overlapping_brand_matches_do_not_duplicate_records_or_totals(brand_repository):
    result = brand_repository.list_records(brands=["yandou", "烟斗", "烟斗仓库"], page=1, page_size=3)
    assert result["total"] == 8
    assert len(result["items"]) == 3
    assert result["totals"]["all"]["amount"] == "80"
    assert result["totals"]["current_page"]["amount"] == "30"


@pytest.mark.parametrize("brand,expected_ids", [
    ("千百度仓库", {12}), ("cbanner_mens", {12}), ("千百度男鞋", {12}),
    ("千百度女鞋仓库", {11}), ("伊伴男鞋仓库", {14}), ("eblan_womens", {13}),
    ("自定义品牌", {15, 16}), ("custom", {15, 16}), ("自定义品牌仓库", {15, 16}),
])
def test_gender_and_custom_brand_names_remain_distinct(brand_repository, brand, expected_ids):
    result = brand_repository.list_records(brands=[brand], page=1, page_size=100)
    assert {item["id"] for item in result["items"]} == expected_ids


def test_brand_filter_still_intersects_explicit_warehouse_and_document_filters(brand_repository):
    result = brand_repository.list_records(
        brands=["烟斗"], warehouses=["NI总仓"], document_types=["批发销售单"], page=1, page_size=100,
    )
    assert [item["id"] for item in result["items"]] == [5]
    multiple = brand_repository.list_records(brands=["烟斗", "custom"], page=1, page_size=100)
    assert {item["id"] for item in multiple["items"]} == {1, 2, 3, 4, 5, 7, 8, 15, 16, 17}


def test_brand_options_merge_all_master_data_without_duplicate_aliases(brand_repository):
    options = brand_repository.list_inventory_brand_options()
    assert {item["value"] for item in options} == {
        "yandou", "ni", "cbanner_mens", "cbanner_womens", "eblan", "eblan_womens", "custom",
    }
    assert options.count({"value": "yandou", "label": "烟斗"}) == 1
    assert {"value": "custom", "label": "自定义品牌"} in options
    request = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(inventory_repository=brand_repository)))
    assert list_inventory_brands(request) == {"items": options}


def test_brand_options_include_unconfigured_custom_supplier_and_customer_brands():
    options = inventory_brand_options([], [{"code": "new_code", "name": "新品牌"}], ["新品牌", "其他品牌"])
    assert options == [{"value": "new_code", "label": "新品牌"}, {"value": "其他品牌", "label": "其他品牌"}]
    assert "新品牌仓库" in inventory_brand_filter_aliases(["new_code"], [{"code": "new_code", "name": "新品牌"}])


def test_export_uses_the_same_brand_scope_including_warehouse_free_accounting_records(brand_repository):
    brand_repository.list_details_for_documents = Mock(return_value=[])
    request = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(inventory_repository=brand_repository)))
    response = export_inventory(request, brands=["烟斗仓库"])

    async def read_content():
        return b"".join([chunk async for chunk in response.body_iterator])

    workbook = load_workbook(BytesIO(asyncio.run(read_content())), data_only=True)
    try:
        rows = list(workbook["经营历程"].iter_rows(values_only=True))
        headers = rows[0]
        numbers = {row[headers.index("单据编号")] for row in rows[1:]}
        assert numbers == {f"DOC-{record_id}" for record_id in (1, 2, 3, 4, 5, 7, 8, 17)}
    finally:
        workbook.close()
