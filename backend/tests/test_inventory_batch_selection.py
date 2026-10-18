from datetime import date, datetime
from types import SimpleNamespace
from unittest.mock import Mock

from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest
from sqlalchemy import create_engine, event, select

from api.inventory_selection import InventorySelectionFilters
from api.routes import inventory as routes
from domain.inventory_schema import (
    GENERAL_CUSTOMER_SHOP_TABLE, GENERAL_CUSTOMER_UNIT_TABLE, INVENTORY_DETAIL_TABLE,
    INVENTORY_TABLE, JST_STOCK_TABLE,
)
from storage.inventory_repository import InventoryRepository


@pytest.fixture
def selection_repository():
    engine = create_engine("sqlite://")
    event.listen(engine, "connect", lambda connection, _record: connection.create_function("date_trunc", 2, lambda _unit, value: value))
    for table in (INVENTORY_TABLE, INVENTORY_DETAIL_TABLE, GENERAL_CUSTOMER_SHOP_TABLE, GENERAL_CUSTOMER_UNIT_TABLE, JST_STOCK_TABLE):
        table.create(engine)
    with engine.begin() as connection:
        connection.execute(INVENTORY_TABLE.insert(), [
            {
                "id": record_id, "document_number": f"DOC-{record_id}",
                "date": "2026-10-18", "date_value": date(2026, 10, 18),
                "document_type": "进货订单" if record_id == 26 else "进货单",
                "supplier": "供应商甲" if record_id <= 20 else "供应商乙",
                "warehouse": "仓库甲", "summary": "批次甲", "handler": "张三",
                "deleted_at": datetime(2026, 10, 17) if record_id == 27 else None,
            }
            for record_id in range(1, 28)
        ])
        connection.execute(INVENTORY_DETAIL_TABLE.insert(), [
            {"id": record_id, "document_id": record_id, "product_code": "SKU-A", "unit_price": 0 if record_id == 25 else 10, "amount": 10}
            for record_id in range(1, 28)
        ])
    repository = object.__new__(InventoryRepository)
    repository.engine = engine
    repository.purge_expired_deleted_records = lambda: 0
    yield repository
    engine.dispose()


@pytest.mark.parametrize("filters", [
    {"completion_status": "completed", "exclude_document_type": "进货订单"},
    {"completion_status": "incomplete", "exclude_document_type": "进货订单"},
    {"document_type": "进货订单"},
    {"suppliers": ["供应商甲"], "warehouses": ["仓库甲"], "summary": "批次甲", "handler": "张三"},
    {"date_start": "2026-10-18", "date_end": "2026-10-18", "document_number": "DOC-1"},
    {"original_sku": "SKU-A", "exclude_document_type": "进货订单"},
])
def test_select_all_uses_exactly_the_list_scope_without_pagination(selection_repository, filters):
    expected = selection_repository.list_records(**filters, page=1, page_size=100)["items"]
    ids = selection_repository.list_record_ids(**filters)
    assert set(ids) == {row["id"] for row in expected}
    assert 27 not in ids
    assert len(ids) == len(set(ids))


def test_selection_snapshot_excludes_later_inserts_and_deletes_every_selected_page(selection_repository):
    ids = selection_repository.list_record_ids(completion_status="completed", exclude_document_type="进货订单")
    assert len(ids) == 24
    with selection_repository.engine.begin() as connection:
        connection.execute(INVENTORY_TABLE.insert().values(id=28, document_type="进货单"))
    assert selection_repository.delete_records(ids) == 24
    with selection_repository.engine.connect() as connection:
        remaining = set(connection.execute(select(INVENTORY_TABLE.c.id).where(INVENTORY_TABLE.c.deleted_at.is_(None))).scalars())
        assert remaining == {25, 26, 28}
        assert connection.execute(select(INVENTORY_DETAIL_TABLE.c.id)).all()


def test_large_batch_is_chunked_and_retains_only_active_records_for_logs(selection_repository):
    with selection_repository.engine.begin() as connection:
        connection.execute(INVENTORY_TABLE.insert(), [{"id": record_id} for record_id in range(100, 2305)])
    ids = list(range(100, 2305)) + [27, 100]
    assert len(selection_repository.get_records_by_ids(ids)) == 2205
    assert selection_repository.delete_records(ids) == 2205
    assert selection_repository.get_records_by_ids(ids) == []


def test_select_all_only_queries_ids_without_limits_or_totals(selection_repository):
    statements = []
    event.listen(selection_repository.engine, "before_cursor_execute", lambda _connection, _cursor, statement, _parameters, _context, _executemany: statements.append(statement))
    assert len(selection_repository.list_record_ids(exclude_document_type="进货订单")) == 25
    assert len(statements) == 1
    assert "LIMIT" not in statements[0]
    assert "count(" not in statements[0]
    assert "inventory_records.amount" not in statements[0]


def test_chunked_deletion_rolls_back_the_whole_batch_on_failure(selection_repository):
    with selection_repository.engine.begin() as connection:
        connection.execute(INVENTORY_TABLE.insert(), [{"id": record_id} for record_id in range(100, 1205)])
    updates = []

    def interrupt_second_chunk(_connection, _cursor, statement, _parameters, _context, _executemany):
        if statement.startswith("UPDATE inventory_records"):
            updates.append(statement)
            if len(updates) == 2:
                raise RuntimeError("interrupted batch")

    event.listen(selection_repository.engine, "before_cursor_execute", interrupt_second_chunk)
    with pytest.raises(RuntimeError, match="interrupted batch"):
        selection_repository.delete_records(list(range(100, 1205)))
    event.remove(selection_repository.engine, "before_cursor_execute", interrupt_second_chunk)
    assert len(selection_repository.get_records_by_ids(list(range(100, 1205)))) == 1105


def test_selection_endpoint_is_read_only_normalizes_types_and_disables_caching():
    repository = SimpleNamespace(list_record_ids=Mock(return_value=[1, 2, 30]))
    request = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(inventory_repository=repository)))
    response = routes.list_inventory_selection_ids(request, InventorySelectionFilters(document_types=["工厂进货单"], exclude_document_type="进货订单", completion_status="completed"))
    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    assert repository.list_record_ids.call_args.kwargs["document_types"] == ["进货单"]
    assert b'"ids":[1,2,30]' in response.body


def test_selection_endpoint_rejects_unknown_filters_and_invalid_completion_status():
    app = FastAPI()
    app.include_router(routes.router)
    with TestClient(app) as client:
        assert client.post("/inventory/selection-ids", json={"completion_status": "typo"}).status_code == 422
        assert client.post("/inventory/selection-ids", json={"page_size": 20}).status_code == 422


def test_delete_route_fetches_logs_in_batches_and_deduplicates_ids(monkeypatch):
    repository = SimpleNamespace(
        get_records_by_ids=Mock(return_value=[{"id": 1, "document_type": "进货单", "document_number": "DOC-1"}]),
        delete_records=Mock(return_value=1),
    )
    request = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(inventory_repository=repository)))
    operation_log = Mock()
    monkeypatch.setattr(routes, "write_operation_log", operation_log)
    assert routes.batch_delete_inventory(request, {"ids": [1, 1]})["deleted"] == 1
    repository.get_records_by_ids.assert_called_once_with([1])
    repository.delete_records.assert_called_once_with([1])
    assert operation_log.call_args.kwargs["before_data"]["ids"] == [1]


@pytest.mark.parametrize("ids", ["1,2", [True], [1.5], [-1], ["invalid"]])
def test_invalid_delete_selection_never_reaches_the_repository(ids):
    repository = SimpleNamespace(get_records_by_ids=Mock(), delete_records=Mock())
    request = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(inventory_repository=repository)))
    with pytest.raises(routes.HTTPException) as error:
        routes.batch_delete_inventory(request, {"ids": ids})
    assert error.value.status_code == 400
    repository.delete_records.assert_not_called()
