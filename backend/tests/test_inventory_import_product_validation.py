from dataclasses import replace
from datetime import date, datetime
from decimal import Decimal
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
from domain.smiley_schema import SMILEY_FINE_TABLE
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
    repository.create_record.side_effect = lambda payload: {"id": 1, **payload}
    repository.merge_imported_details.return_value = {"added": 2, "updated": 0}
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
def test_unmatched_product_no_longer_blocks_template_import(context, code):
    repository, request = context
    result = routes._import_inventory_template(request, "导入.xlsx", {}, template(codes=(SKU, code)))
    assert result["created"] == 1
    details = repository.import_template_documents.call_args.args[0][0]["details"]
    assert sum(Decimal(detail["quantity"]) for detail in details) == 2
    if code in {"UNKNOWN", "ERPONLY", "PRICEONLY", "DELETED", "OTHERBRAND"}:
        unmatched = next(detail for detail in details if detail["product_code"] == code)
        assert unmatched["product_identity_id"] is None


@pytest.mark.parametrize("kind", ["purchase", "purchase_return", "sale", "sale_return", "stock_loss", "stock_gain", "transfer"])
def test_all_goods_templates_allow_unmatched_products_on_preview_and_submit(context, kind):
    repository, request = context
    content = template(kind, codes=("UNKNOWN",))
    # Preview still checks master data and brands, but needs no product queries.
    with patch.object(repository.engine, "connect", side_effect=AssertionError("preview queried products")):
        assert routes._preview_inventory_template(request, content)["total"] == 1
    assert_no_writes(repository)
    assert routes._import_inventory_template(request, "导入.xlsx", {}, content)["created"] == 1
    detail = repository.import_template_documents.call_args.args[0][0]["details"][0]
    assert detail["product_code"] == "UNKNOWN"
    assert detail["product_identity_id"] is None


@pytest.mark.parametrize("code", [SKU, SKU + "39", SKU + "35-36", SKU + "45-46"])
def test_archive_sku_and_valid_size_codes_import_with_product_link(context, code):
    repository, request = context
    content = template(codes=(code,))
    assert routes._preview_inventory_template(request, content)["total"] == 1
    assert routes._import_inventory_template(request, "导入.xlsx", {}, content)["created"] == 1
    detail = repository.import_template_documents.call_args.args[0][0]["details"][0]
    assert detail["product_identity_id"] == 1
    assert detail["product_code"] == SKU


def test_unmatched_product_imports_when_fallback_brand_is_submitted(context):
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
        assert routes._import_inventory_template(request, "导入.xlsx", {"brand": "ni"}, content)["created"] == 1
    detail = repository.import_template_documents.call_args.args[0][0]["details"][0]
    assert detail["product_code"] == "UNKNOWN"
    assert detail["product_identity_id"] is None


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
def test_other_inventory_import_entries_allow_unmatched_products(context, entry):
    repository, request = context
    content = workbook(["商品编码", "数量"], [[SKU + "39", 1], ["UNKNOWN", 1]])
    form = {
        "document_type": "进货单", "supplier": "单位A", "warehouse": "NI仓库",
        "handler": "测试", "summary": "测试", "brand": "ni", "date": "2026-10-29",
    }
    if entry.startswith("existing"):
        if entry == "existing-preview":
            form["preview"] = "true"
        result = routes._import_purchase_inventory(request, "导入.xlsx", form, content)
        if entry == "existing-preview":
            assert result["total"] == 1
            assert_no_writes(repository)
            return
        assert result["created"] == 1
        details = repository.create_details.call_args.args[0]
    elif entry == "reimport":
        result = routes._reimport_inventory_details_from_excel(request, 1, "导入.xlsx", {}, content)
        assert result["details"] == 2
        details = repository.merge_imported_details.call_args.args[1]
    else:
        content = workbook(
            ["date", "document_type", "supplier", "warehouse", "summary", "product_code", "quantity"],
            [["2026-10-29", "进货单", "单位A", "NI仓库", "测试", SKU, 1],
             ["2026-10-29", "进货单", "单位A", "NI仓库", "测试", "UNKNOWN", 1]],
        )
        result = routes._import_inventory(request, "导入.xlsx", content)
        assert result["created"] == 1
        assert result["details"] == 2
        details = repository.create_details.call_args.args[0]
    assert len(details) == 2
    assert any(detail["product_code"] == "UNKNOWN" for detail in details)


def test_purchase_order_keeps_existing_archive_code_validation(context):
    repository, _request = context
    with pytest.raises(HTTPException, match="不是由商品信息档案中的已有商品构成"):
        routes._build_purchase_details_from_rows(
            repository, [{"product_code": "UNKNOWN", "quantity": "1"}],
            brand="ni", fallback_unit_price=Decimal("0"), require_archive_product_code=True,
        )
    assert_no_writes(repository)


def test_large_product_lookup_bounds_expanded_query_parameters(context):
    repository, _request = context
    product_codes = {f"BULK{index:05d}END39" for index in range(12500)} | {SKU + "39"}
    expanded_codes = {
        candidate
        for code in product_codes
        for candidate in routes._purchase_product_lookup_candidates(code, "ni")
    }
    # The previous two-column IN query exceeded PostgreSQL's parameter limit.
    assert len(expanded_codes) * 2 > 65535
    queries = []

    def capture_query(_connection, _cursor, statement, parameters, _context, _executemany):
        queries.append((statement, len(parameters)))

    with repository.engine.connect() as connection:
        event.listen(connection, "before_cursor_execute", capture_query)
        lookup = routes._load_purchase_product_lookup(connection, "ni", product_codes)
    assert set(lookup) == expanded_codes
    assert lookup[SKU]["_archive_identity_id"] == 1
    assert max(count for _statement, count in queries) <= 2 * routes.PURCHASE_PRODUCT_LOOKUP_BATCH_SIZE
    batch_size = routes.PURCHASE_PRODUCT_LOOKUP_BATCH_SIZE
    expected_batches = (len(expanded_codes) + batch_size - 1) // batch_size
    for table in (
        GJ_MERGED_PRODUCT_INFO_TABLE, JST_PRICE_TABLE,
        PRODUCT_ARCHIVE_TABLES["ni"], PRODUCT_ARCHIVE_IDENTITY_TABLE,
    ):
        assert sum(f"FROM {table.name} " in statement for statement, _count in queries) == expected_batches
    assert not lookup["BULK00000END39"].get("_archive_matched")
    assert_no_writes(repository)


@pytest.mark.parametrize("brand", ["ni", "smiley"])
def test_product_lookup_batches_preserve_alias_order_prices_and_identity(context, monkeypatch, brand):
    repository, _request = context
    table = PRODUCT_ARCHIVE_TABLES[brand]
    today = datetime(2026, 10, 29)
    with repository.engine.begin() as connection:
        if brand == "smiley":
            connection.execute(CreateTable(table))
            connection.execute(CreateTable(SMILEY_FINE_TABLE))
        for product_id, sku, original_sku in (
            (10, "AA-STYLE", "ZZ-ALIAS"), (11, "MM-SECOND", "MM-SECOND"),
        ):
            connection.execute(table.insert().values(
                id=product_id, sku=sku, original_sku=original_sku,
                source_workbook="test.xlsx", source_sheet="商品", source_row_number=str(product_id), raw_payload={},
                color="黑色", color_code="01", barcode_build_rule="货号+尺码",
                lining_material="档案内里", size_range="测试尺码", updated_at=today,
            ))
            connection.execute(PRODUCT_ARCHIVE_IDENTITY_TABLE.insert().values(
                id=1000 + product_id, brand=brand, source_table=table.name,
                source_product_id=product_id, sku=sku, original_sku=original_sku,
                created_at=today, updated_at=today,
            ))
        for row_id, day, sku, original_sku, name in (
            (10, 27, "ZZ-ALIAS", "AA-STYLE", "旧资料"),
            (11, 28, "AA-STYLE", "ZZ-ALIAS", "货号最新资料"),
            (12, 29, "QQ-ERP-ONLY", "ZZ-ALIAS", "别名最新资料"),
        ):
            connection.execute(GJ_MERGED_PRODUCT_INFO_TABLE.insert().values(
                id=row_id, source_date=f"2026-10-{day}", source_date_value=date(2026, 10, day),
                goods_code=sku, original_goods_code=original_sku, product_name=name,
                updated_at=today,
            ))
        for row_id, sku, day, price in (
            (10, "AA-STYLE", 28, "10"), (11, "AA-STYLE", 29, "20"),
            (12, "ZZ-ALIAS", 28, "11"), (13, "ZZ-ALIAS", 29, "21"),
        ):
            connection.execute(JST_PRICE_TABLE.insert().values(
                id=row_id, source_date=f"2026-10-{day}", source_date_value=date(2026, 10, day),
                goods_code=sku, preset_price=price, updated_at=today,
            ))
        if brand == "smiley":
            for row_id, day, sku, original_sku, material in (
                (10, 27, "ZZ-ALIAS", "AA-STYLE", "旧鞋垫"),
                (11, 28, "AA-STYLE", "ZZ-ALIAS", "货号最新鞋垫"),
                (12, 29, "QQ-FINE-ONLY", "ZZ-ALIAS", "别名最新鞋垫"),
                (13, 29, "MM-SECOND", "MM-SECOND", "第二商品鞋垫"),
            ):
                connection.execute(SMILEY_FINE_TABLE.insert().values(
                    id=row_id, snapshot_date=date(2026, 10, day),
                    source_workbook="test.xlsx", source_sheet="商品", source_row_number=row_id,
                    sku=sku, original_sku=original_sku, insole_material=material, cost=Decimal("33.50"),
                    shop_sales={}, size_stock={}, return_rates={}, raw_payload={}, updated_at=today,
                ))

    product_codes = {"AA-STYLE", "ZZ-ALIAS", "MM-SECOND"}
    with repository.engine.connect() as connection:
        baseline = routes._load_purchase_product_lookup(connection, brand, product_codes)
        monkeypatch.setattr(routes, "PURCHASE_PRODUCT_LOOKUP_BATCH_SIZE", 2)
        queries = []

        def capture_query(_connection, _cursor, statement, parameters, _context, _executemany):
            queries.append((statement, len(parameters)))

        event.listen(connection, "before_cursor_execute", capture_query)
        lookup = routes._load_purchase_product_lookup(connection, brand, product_codes)
    assert lookup == baseline
    assert max(count for _statement, count in queries) <= 4
    assert lookup["AA-STYLE"]["product_name"] == "货号最新资料"
    assert lookup["ZZ-ALIAS"]["product_name"] == "别名最新资料"
    assert lookup["AA-STYLE"]["unit_price"] == Decimal("20")
    assert lookup["ZZ-ALIAS"]["unit_price"] == Decimal("21")
    for code, identity_id in (("AA-STYLE", 1010), ("ZZ-ALIAS", 1010), ("MM-SECOND", 1011)):
        assert lookup[code]["_archive_identity_id"] == identity_id
        assert lookup[code]["lining_material"] == "档案内里"
    if brand == "smiley":
        assert lookup["AA-STYLE"]["insole_material"] == "货号最新鞋垫"
        assert lookup["ZZ-ALIAS"]["insole_material"] == "别名最新鞋垫"
        assert lookup["MM-SECOND"]["unit_price"] == Decimal("33.50")
