from datetime import date, datetime

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.dialects import postgresql
from sqlalchemy.schema import CreateIndex

from domain.inventory_schema import GENERAL_CUSTOMER_SHOP_TABLE, GENERAL_CUSTOMER_UNIT_TABLE, INVENTORY_DETAIL_TABLE, INVENTORY_TABLE
from scripts.optimize_inventory_pagination import INDEX_NAMES, index_statements
from storage.inventory_repository import InventoryRepository


@pytest.fixture
def completion_repository():
    engine = create_engine("sqlite://")
    event.listen(engine, "connect", lambda connection, record: connection.create_function("date_trunc", 2, lambda unit, value: value))
    for table in (INVENTORY_TABLE, INVENTORY_DETAIL_TABLE, GENERAL_CUSTOMER_SHOP_TABLE, GENERAL_CUSTOMER_UNIT_TABLE):
        table.create(engine)
    records = [
        (1, "普通客户", "进货单", None), (2, "普通客户", "进货单", None),
        (3, "普通客户", "进货单", None), (4, "普通客户", "进货单", None),
        (5, "普通客户", "应付款增加", None), (6, "普通客户", "应付款减少", None),
        (7, "普通客户", "应付款增加", None), (8, "测试内销客户", "批发销售单", None),
        (9, "内部单位", "批发销售单", None), (10, " 总部 采购 ", "批发销售单", None),
        (11, " 总部 采购 ", "进货单", None), (12, None, "进货单", None),
        (13, None, "进货单", None), (14, "未知客户", None, None),
        (15, "普通客户", "进货单", datetime(2026, 10, 12)),
        (16, "普通客户", "进货订单", None), (17, "普通客户", "进货退货单", None),
    ]
    with engine.begin() as connection:
        connection.execute(GENERAL_CUSTOMER_SHOP_TABLE.insert(), [{"id": 1, "customer_name": "测试品牌", "shop_name": "测试内销客户"}, {"id": 2, "customer_name": "测试品牌", "shop_name": "普通客户"}])
        connection.execute(GENERAL_CUSTOMER_UNIT_TABLE.insert(), [{"id": 1, "shop_id": 1, "unit_name": "内部单位"}, {"id": 2, "shop_id": 1, "unit_name": "测试内销客户"}, {"id": 3, "shop_id": 2, "unit_name": "普通单位"}])
        connection.execute(INVENTORY_TABLE.insert(), [
            {"id": record_id, "supplier": supplier, "document_type": document_type, "deleted_at": deleted_at,
             "date": "2026-10-12", "date_value": date(2026, 10, 12), "total_count": -2 if record_id == 17 else 1, "amount": -20 if record_id == 17 else 10}
            for record_id, supplier, document_type, deleted_at in records
        ])
        details = [
            (2, 10, 10), (3, 0, 10), (4, None, 10), (5, 0, 10),
            (6, 10, 0), (7, 10, None), (9, 0, 0), (11, 0, 0),
            (13, 10, 0), (14, 10, 0), (15, 10, 10), (16, 10, 10), (17, 10, -20),
        ]
        connection.execute(INVENTORY_DETAIL_TABLE.insert(), [
            {"id": index, "document_id": document_id, "product_code": "TEST", "unit_price": unit_price, "amount": amount}
            for index, (document_id, unit_price, amount) in enumerate(details, start=1)
        ])
    repository = object.__new__(InventoryRepository)
    repository.engine = engine
    repository.purge_expired_deleted_records = lambda: 0
    try:
        yield repository
    finally:
        engine.dispose()


def test_completion_filters_keep_null_supplier_internal_units_and_accounting_rules(completion_repository):
    completed = completion_repository.list_records(completion_status="completed", exclude_document_type="进货订单", page=1, page_size=100)
    incomplete = completion_repository.list_records(completion_status="incomplete", exclude_document_type="进货订单", page=1, page_size=100)
    assert {row["id"] for row in completed["items"]} == {2, 5, 8, 9, 10, 13, 14, 17}
    assert {row["id"] for row in incomplete["items"]} == {1, 3, 4, 6, 7, 11, 12}
    assert completed["total"] == 8 and incomplete["total"] == 7


def test_completion_pagination_keeps_count_and_all_totals_without_duplicate_customer_matches(completion_repository):
    first = completion_repository.list_records(completion_status="completed", exclude_document_type="进货订单", page=1, page_size=3)
    second = completion_repository.list_records(completion_status="completed", exclude_document_type="进货订单", page=2, page_size=3)
    assert [row["id"] for row in first["items"]] == [17, 14, 13]
    assert [row["id"] for row in second["items"]] == [10, 9, 8]
    assert first["total"] == second["total"] == 8
    assert first["totals"]["all"] == second["totals"]["all"] == {"total_count": "9", "amount": "90"}
    assert first["totals"]["current_page"] == {"total_count": "4", "amount": "40"}


def test_pagination_combines_count_and_sums_in_one_aggregate_query(completion_repository):
    statements = []
    event.listen(completion_repository.engine, "before_cursor_execute", lambda connection, cursor, statement, parameters, context, executemany: statements.append(statement))
    completion_repository.list_records(completion_status="completed", page=1, page_size=20)
    assert len(statements) == 2
    assert "count(*) AS record_count" in statements[0]
    assert "sum(" in statements[0]
    assert "LIMIT" in statements[1]
    assert all("general_customer_units.unit_name = inventory_records.supplier" not in statement for statement in statements)


def test_completion_partial_indexes_only_cover_missing_amount_or_price_rows():
    statements = index_statements()
    assert set(statements) == set(INDEX_NAMES)
    for index in INVENTORY_DETAIL_TABLE.indexes:
        if index.name not in INDEX_NAMES:
            continue
        sql = str(CreateIndex(index).compile(dialect=postgresql.dialect()))
        assert "(document_id) WHERE" in sql
        assert "IS NULL" in sql and " = 0" in sql
        assert statements[index.name].startswith("CREATE INDEX CONCURRENTLY")
