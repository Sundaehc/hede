from datetime import date, datetime

import pytest
from sqlalchemy import create_engine, event

from domain.inventory_schema import INVENTORY_DETAIL_TABLE, INVENTORY_TABLE, SUPPLIER_TABLE
from scripts.optimize_purchase_inbound_pagination import INDEX_NAME, index_statement, normalize_definition
from storage.inventory_repository import InventoryRepository


@pytest.fixture
def inbound_repository():
    engine = create_engine("sqlite://")
    event.listen(engine, "connect", lambda connection, record: connection.create_function("date_trunc", 2, lambda unit, value: value))
    for table in (INVENTORY_TABLE, INVENTORY_DETAIL_TABLE, SUPPLIER_TABLE):
        table.create(engine)
    with engine.begin() as connection:
        connection.execute(SUPPLIER_TABLE.insert(), [{"id": 1, "brand": "test", "name": "供应商", "factory_code": "UNIT-1"}])
        records = [
            (1, "进货单", "2026-08-04", date(2026, 8, 4), "A001", None),
            (2, "进货退货单", "2026-08-03", date(2026, 8, 3), "B001", None),
            (3, "进货单", "2026-08-04", date(2026, 8, 4), "A002", None),
            (4, "进货单", "2026-08-04", date(2026, 8, 4), "A003", datetime(2026, 8, 5)),
            (5, "批发销售单", "2026-08-02", date(2026, 8, 2), "C001", None),
            (6, "进货单", "未知日期", None, "D001", None),
            (7, "进货单", None, None, None, None),
            (8, "进货单", "2026-08-01", date(2026, 8, 1), "EMPTY", None),
        ]
        connection.execute(INVENTORY_TABLE.insert(), [
            {"id": record_id, "document_type": document_type, "date": date_text, "date_value": date_value,
             "document_number": number, "deleted_at": deleted_at, "supplier": "供应商", "warehouse": "总仓"}
            for record_id, document_type, date_text, date_value, number, deleted_at in records
        ])
        details = [(11, 1, 2, 20), (12, 1, None, None), (21, 2, 3, 30), (31, 3, 4, 40),
                   (41, 4, 100, 1000), (51, 5, 100, 1000), (61, 6, 5, 50), (71, 7, 6, 60)]
        connection.execute(INVENTORY_DETAIL_TABLE.insert(), [
            {"id": detail_id, "document_id": document_id, "product_code": f"SKU-{detail_id}",
             "product_name": "休闲鞋", "color_name": None, "color_spec": "黑色", "quantity": quantity,
             "amount": amount, "size_quantities": {"240": "1"}, "extra_fields": {"factory_code": "FACTORY-1"}}
            for detail_id, document_id, quantity, amount in details
        ])
    repository = object.__new__(InventoryRepository)
    repository.engine = engine
    try:
        yield repository
    finally:
        engine.dispose()


def test_pagination_preserves_order_row_numbers_totals_and_nullable_dates(inbound_repository):
    items = []
    for page in range(1, 4):
        result = inbound_repository.list_purchase_inbound_details(page=page, page_size=2)
        assert result["total"] == 6
        assert result["totals"]["all"] == {
            "purchase_quantity": "14", "purchase_amount": "140", "retail_amount": "",
        }
        items.extend(result["items"])
    assert [item["detail_id"] for item in items[:4]] == [21, 11, 12, 31]
    assert {item["detail_id"] for item in items[4:]} == {61, 71}
    assert [item["row_number"] for item in items] == list(range(1, 7))
    assert items[0]["purchase_quantity"] == "-3"
    assert items[0]["purchase_amount"] == "-30"
    assert items[1]["color_name"] == "黑色"
    assert items[1]["size_quantities"] == {"240": "1"}
    assert items[1]["factory_code"] == "FACTORY-1"
    assert items[1]["unit_code"] == "UNIT-1"
    assert items[2]["purchase_quantity"] == "0"


def test_count_and_totals_share_one_query_and_only_page_ids_are_sorted(inbound_repository):
    statements = []
    event.listen(inbound_repository.engine, "before_cursor_execute", lambda connection, cursor, statement, parameters, context, executemany: statements.append(statement))
    result = inbound_repository.list_purchase_inbound_details(page=2, page_size=2)
    assert len(statements) == 3
    assert "count(*) AS detail_count" in statements[0]
    assert "sum(" in statements[0]
    page_query = statements[1]
    page_selection = page_query.split("WITH purchase_inbound_page AS", 1)[1].split("LIMIT", 1)[0]
    assert "inventory_details.id AS detail_id" in page_selection
    assert "size_quantities" not in page_selection
    assert "extra_fields" not in page_selection
    assert "product_name" not in page_selection
    assert "JOIN inventory_details ON inventory_details.id = purchase_inbound_page.detail_id" in page_query
    assert [item["detail_id"] for item in result["items"]] == [12, 31]
    assert result["totals"]["current_page"]["purchase_quantity"] == "4"


@pytest.mark.parametrize("filters,expected_ids", [
    ({"date_start": "2026-08-04", "date_end": "2026-08-04"}, [11, 12, 31]),
    ({"document_type": "进货退货单"}, [21]),
    ({"supplier": "供应", "warehouse": ["总仓", "总仓", "不存在"]}, [21, 11, 12, 31, 71, 61]),
    ({"product_code": "SKU-11"}, [11]),
    ({"product_name": "休闲", "color_name": "黑", "size_name": "240"}, [21, 11, 12, 31, 71, 61]),
    ({"warehouse": ["总仓备用区"]}, []),
])
def test_filters_apply_before_pagination_and_aggregation(inbound_repository, filters, expected_ids):
    result = inbound_repository.list_purchase_inbound_details(**filters, page=1, page_size=100)
    assert result["total"] == len(expected_ids)
    assert {item["detail_id"] for item in result["items"]} == set(expected_ids)
    assert result["totals"]["current_page"] == result["totals"]["all"]


@pytest.mark.parametrize("page,filters,expected_total", [(4, {}, 6), (1, {"product_code": "missing"}, 0)])
def test_empty_or_out_of_range_pages_skip_detail_and_supplier_queries(inbound_repository, page, filters, expected_total):
    statements = []
    event.listen(inbound_repository.engine, "before_cursor_execute", lambda connection, cursor, statement, parameters, context, executemany: statements.append(statement))
    result = inbound_repository.list_purchase_inbound_details(**filters, page=page, page_size=2)
    assert result["items"] == []
    assert result["total"] == expected_total
    assert result["totals"]["current_page"] == {"purchase_quantity": "0", "purchase_amount": "0", "retail_amount": ""}
    assert len(statements) == 1


def test_covering_index_supports_document_join_page_ids_and_totals():
    statement = index_statement()
    assert INDEX_NAME in statement
    assert "USING btree (document_id, id) INCLUDE (quantity, amount)" in statement
    assert normalize_definition(statement) == normalize_definition(statement.replace("CREATE INDEX ", "CREATE INDEX CONCURRENTLY ").replace(" ON inventory_details ", " ON public.inventory_details "))
