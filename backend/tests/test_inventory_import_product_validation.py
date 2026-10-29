from dataclasses import replace
from datetime import datetime
from io import BytesIO
from types import SimpleNamespace
from unittest.mock import Mock, patch

import pytest
from fastapi import HTTPException
from openpyxl import Workbook
from sqlalchemy import create_engine, event
from sqlalchemy.pool import StaticPool
from sqlalchemy.schema import CreateTable

from api.routes import inventory as routes
from domain.color_barcode_schema import COLOR_BARCODE_TABLE
from domain.gj_schema import GJ_MERGED_PRODUCT_INFO_TABLE
from domain.inventory_template_import import TEMPLATE_HEADERS, read_template_documents
from domain.product_archive_identity_schema import PRODUCT_ARCHIVE_IDENTITY_TABLE
from domain.schema import PRODUCT_ARCHIVE_TABLES
from domain.size_group_schema import SIZE_GROUP_ITEMS_TABLE, SIZE_GROUPS_TABLE
from domain.vip_schema import JST_PRICE_TABLE
from storage.inventory_repository import InventoryRepository


SKU = "NI24Q1A020201"


def workbook(headers, rows):
    book = Workbook()
    sheet = book.active
    sheet.append(headers)
    for row in rows:
        sheet.append(row)
    buffer = BytesIO()
    book.save(buffer)
    book.close()
    return buffer.getvalue()


def template(kind="purchase", codes=(SKU,)):
    document_type = {
        "purchase": "进货单", "purchase_return": "进货退货单",
        "sale": "批发销售单", "sale_return": "批发销售退货单",
        "stock_loss": "报损单", "stock_gain": "报溢单", "transfer": "同价调拨单",
    }[kind]
    values = {
        "日期": "2026-10-29", "单据类型": document_type,
        "单位全名": "单位A", "仓库全名": "NI仓库", "出货仓库": "NI仓库",
        "入货仓库": "NI入货仓库", "经手人": "测试", "摘要": "测试导入",
        "数量": 1, "单价": 10,
    }
    return workbook(TEMPLATE_HEADERS[kind], [
        [code if header == "商品编码" else values[header] for header in TEMPLATE_HEADERS[kind]]
        for code in codes
    ])


@pytest.fixture
def context(monkeypatch):
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    event.listen(engine, "connect", lambda connection, _record: connection.create_function(
        "date_trunc", 2, lambda _unit, value: value,
    ))
    for table in (
        PRODUCT_ARCHIVE_TABLES["ni"], PRODUCT_ARCHIVE_TABLES["yandou"],
        PRODUCT_ARCHIVE_IDENTITY_TABLE, GJ_MERGED_PRODUCT_INFO_TABLE, JST_PRICE_TABLE,
        COLOR_BARCODE_TABLE, SIZE_GROUPS_TABLE, SIZE_GROUP_ITEMS_TABLE,
    ):
        with engine.begin() as connection:
            connection.execute(CreateTable(table))
    with engine.begin() as connection:
        for brand, product_id, code, deleted_at in (
            ("ni", 1, SKU, None), ("ni", 2, "DELETED", datetime(2026, 10, 28)),
            ("yandou", 3, "OTHERBRAND", None),
        ):
            connection.execute(PRODUCT_ARCHIVE_TABLES[brand].insert().values(
                id=product_id, sku=code, original_sku=code,
                source_workbook="test.xlsx", source_sheet="商品", source_row_number="2", raw_payload={},
                color="黑色", color_code="01", barcode_build_rule="货号+尺码",
                size_range="测试尺码", deleted_at=deleted_at,
            ))
            connection.execute(PRODUCT_ARCHIVE_IDENTITY_TABLE.insert().values(
                id=product_id, brand=brand, source_table=PRODUCT_ARCHIVE_TABLES[brand].name,
                source_product_id=product_id, sku=code, original_sku=code,
                is_active=deleted_at is None,
                created_at=datetime(2026, 10, 29), updated_at=datetime(2026, 10, 29),
            ))
        connection.execute(SIZE_GROUPS_TABLE.insert().values(id=1, name="测试尺码"))
        connection.execute(SIZE_GROUP_ITEMS_TABLE.insert(), [
            {"id": index, "size_group_id": 1, "size_name": size, "barcode": size}
            for index, size in enumerate(("35-36", "39", "45-46"), 1)
        ])
        connection.execute(GJ_MERGED_PRODUCT_INFO_TABLE.insert().values(
            id=1, source_date="2026-10-29", goods_code="ERPONLY", product_name="只有ERP资料",
        ))
        connection.execute(JST_PRICE_TABLE.insert().values(
            id=1, goods_code="PRICEONLY", goods_full_name="只有物价资料", preset_price="10",
        ))
    repository = Mock(spec=InventoryRepository)
    repository.engine = engine
    repository.get_supplier_by_name.return_value = {"name": "单位A", "brand": "ni"}
    repository.get_warehouse_by_name.return_value = {"name": "NI仓库", "brand": "ni"}
    repository.list_suppliers.return_value = [{"name": "单位A"}]
    repository.list_warehouses.return_value = [{"name": "NI仓库"}, {"name": "NI入货仓库"}]
    repository.list_general_customer_shops.return_value = [{"shop_name": "单位A"}]
    repository.list_general_customer_units.return_value = []
    repository.list_account_subjects.return_value = [{"name": "包装费"}]
    repository.preview_template_documents.return_value = {"total": 1, "conflicts": []}
    repository.get_record_for_append.return_value = None
    repository.latest_document_costs.return_value = {}
    repository.latest_wholesale_sales_prices.return_value = {}
    repository.get_record.return_value = {
        "id": 1, "document_type": "进货单", "supplier": "单位A", "warehouse": "NI仓库",
        "date": "2026-10-29", "raw_payload": {"brand": "ni"},
    }
    repository.list_details.return_value = []
    repository.import_template_documents.return_value = {"created": 1, "replaced": 0, "skipped": 0, "details": 1}
    monkeypatch.setattr(routes, "_product_archive_brand_codes", lambda _connection: ["ni", "yandou"])
    monkeypatch.setattr(routes, "write_operation_log", Mock())
    request = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(inventory_repository=repository)))
    try:
        yield repository, request
    finally:
        engine.dispose()


def assert_no_writes(repository):
    for method in (
        "import_template_documents", "create_record", "create_details", "merge_imported_details",
        "overwrite_imported_document", "create_supplier", "update_record",
    ):
        getattr(repository, method).assert_not_called()


@pytest.mark.parametrize("code", ["UNKNOWN", "ERPONLY", "PRICEONLY", "DELETED", "OTHERBRAND", SKU + "99", SKU + "JUNK"])
def test_unmatched_product_blocks_whole_template_and_names_product_department(context, code):
    repository, request = context
    with pytest.raises(HTTPException) as error:
        routes._import_inventory_template(request, "导入.xlsx", {}, template(codes=(SKU, code)))
    assert error.value.status_code == 400
    assert code in error.value.detail
    assert "请联系商品部" in error.value.detail
    assert "本次未导入任何数据" in error.value.detail
    assert_no_writes(repository)


@pytest.mark.parametrize("kind", ["purchase", "purchase_return", "sale", "sale_return", "stock_loss", "stock_gain", "transfer"])
def test_all_goods_templates_validate_on_preview_and_submit(context, kind):
    repository, request = context
    content = template(kind, codes=("UNKNOWN",))
    for run in (
        lambda: routes._preview_inventory_template(request, content),
        lambda: routes._import_inventory_template(request, "导入.xlsx", {}, content),
    ):
        with pytest.raises(HTTPException, match="请联系商品部"):
            run()
        assert_no_writes(repository)


@pytest.mark.parametrize("code", [SKU, SKU + "39", SKU + "35-36", SKU + "45-46"])
def test_archive_sku_and_valid_size_codes_import_with_product_link(context, code):
    repository, request = context
    content = template(codes=(code,))
    assert routes._preview_inventory_template(request, content)["total"] == 1
    assert routes._import_inventory_template(request, "导入.xlsx", {}, content)["created"] == 1
    detail = repository.import_template_documents.call_args.args[0][0]["details"][0]
    assert detail["product_identity_id"] == 1
    assert detail["product_code"] == SKU


def test_unresolved_brand_is_validated_when_fallback_brand_is_submitted(context):
    repository, request = context
    repository.get_supplier_by_name.return_value = None
    repository.get_warehouse_by_name.return_value = None
    content = template(codes=("UNKNOWN",))
    # Use a warehouse name that does not imply any brand.
    document = read_template_documents(content)[2][0]
    document.warehouse = "普通仓库"
    repository.list_warehouses.return_value = [{"name": "普通仓库"}]
    with patch.object(routes, "read_template_documents", return_value=("purchase", "data", [document])):
        assert routes._preview_inventory_template(request, content)["unresolved_brand_keys"]
        with pytest.raises(HTTPException, match="请联系商品部"):
            routes._import_inventory_template(request, "导入.xlsx", {"brand": "ni"}, content)
    assert_no_writes(repository)


def test_cancelled_goods_document_does_not_block_valid_document(context):
    repository, request = context
    content = template(codes=("UNKNOWN", SKU))
    documents = read_template_documents(content)[2]
    # Split into two documents, with only the unknown product cancelled.
    documents = [
        replace(documents[0], key="cancel", rows=[documents[0].rows[0]]),
        replace(documents[0], key="keep", rows=[documents[0].rows[1]], summary="保留"),
    ]
    repository.preview_template_documents.return_value = {"conflicts": [{"key": "cancel"}]}
    with patch.object(routes, "read_template_documents", return_value=("purchase", "data", documents)):
        routes._import_inventory_template(request, "导入.xlsx", {"decisions": '{"cancel":{"action":"skip"}}'}, content)
    plans = repository.import_template_documents.call_args.args[0]
    assert plans[0] == {"decision": "skip"}
    assert plans[1]["details"][0]["product_identity_id"] == 1


def test_accounting_template_uses_subjects_without_product_validation(context):
    repository, request = context
    content = workbook(TEMPLATE_HEADERS["accounting"], [
        ["2026-10-29", "应付款增加", "测试", "单位A", "费用", "包装费", 10],
    ])
    assert routes._preview_inventory_template(request, content)["kind"] == "accounting"
    assert routes._import_inventory_template(request, "费用.xlsx", {}, content)["created"] == 1


@pytest.mark.parametrize("entry", ["existing", "existing-preview", "reimport", "generic"])
def test_other_import_entries_cannot_bypass_product_validation(context, entry):
    repository, request = context
    content = workbook(["商品编码", "数量"], [[SKU + "39", 1], ["UNKNOWN", 1]])
    form = {
        "document_type": "进货单", "supplier": "单位A", "warehouse": "NI仓库",
        "handler": "测试", "summary": "测试", "brand": "ni", "date": "2026-10-29",
    }
    with pytest.raises(HTTPException, match="请联系商品部"):
        if entry.startswith("existing"):
            if entry == "existing-preview":
                form["preview"] = "true"
            routes._import_purchase_inventory(request, "导入.xlsx", form, content)
        elif entry == "reimport":
            routes._reimport_inventory_details_from_excel(request, 1, "导入.xlsx", {}, content)
        else:
            content = workbook(
                ["date", "document_type", "supplier", "warehouse", "summary", "product_code", "quantity"],
                [["2026-10-29", "进货单", "单位A", "NI仓库", "有效", SKU, 1],
                 ["2026-10-29", "进货单", "单位A", "NI仓库", "无效", "UNKNOWN", 1]],
            )
            routes._import_inventory(request, "导入.xlsx", content)
    assert_no_writes(repository)
