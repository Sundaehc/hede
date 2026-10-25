from datetime import datetime
from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.pool import StaticPool

from api.routes.inventory import router
from domain.inventory_schema import INVENTORY_DETAIL_TABLE, INVENTORY_TABLE
from storage.inventory_repository import InventoryRepository


@pytest.fixture
def handler_repository():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    event.listen(engine, "connect", lambda connection, _record: connection.create_function(
        "date_trunc", 2, lambda _unit, value: value,
    ))
    INVENTORY_TABLE.create(engine)
    INVENTORY_DETAIL_TABLE.create(engine)
    with engine.begin() as connection:
        connection.execute(INVENTORY_TABLE.insert(), [
            {
                "id": record_id,
                "document_number": f"DOC-{record_id}",
                "document_type": "进货订单" if record_id == 4 else "进货单",
                "handler": handler,
                "total_count": record_id,
                "amount": record_id * 10,
                "deleted_at": datetime(2026, 10, 23) if record_id == 6 else None,
            }
            for record_id, handler in enumerate(
                ["张三", "李四", "张三丰", "李四", "王五", "张三", None, "Alice Smith", "ALICE"],
                start=1,
            )
        ])
    repository = object.__new__(InventoryRepository)
    repository.engine = engine
    repository.purge_expired_deleted_records = lambda: 0
    try:
        yield repository
    finally:
        engine.dispose()


@pytest.mark.parametrize("separator", [",", "，", ";", "；", "、", "\n", "\r\n"])
def test_handler_filter_matches_any_name_with_supported_separators(handler_repository, separator):
    filters = {"handler": f" 张三 {separator} 李四 "}
    result = handler_repository.list_records(**filters, page=1, page_size=20)
    assert [item["id"] for item in result["items"]] == [4, 3, 2, 1]
    assert result["total"] == 4
    assert handler_repository.list_record_ids(**filters) == [1, 2, 3, 4]


@pytest.mark.parametrize("handler,expected_ids", [
    ("张三", [1, 3]),
    (" 张三，张三丰;张三， ", [1, 3]),
    (" alice , 不存在 ", [8, 9]),
    (" Alice Smith ", [8]),
    (" ,，;；、\r\n ", [1, 2, 3, 4, 5, 7, 8, 9]),
    ("不存在,也不存在", []),
])
def test_handler_filter_preserves_partial_matching_and_normalizes_empty_values(handler_repository, handler, expected_ids):
    result = handler_repository.list_records(handler=handler, page=1, page_size=20)
    assert {item["id"] for item in result["items"]} == set(expected_ids)
    assert result["total"] == len(expected_ids)
    assert handler_repository.list_record_ids(handler=handler) == expected_ids


def test_handler_filter_keeps_totals_and_document_scope_consistent(handler_repository):
    result = handler_repository.list_records(
        handler="张三,张三丰,李四",
        exclude_document_type="进货订单",
        page=1,
        page_size=1,
    )
    assert [item["id"] for item in result["items"]] == [3]
    assert result["total"] == 3
    assert result["totals"] == {
        "current_page": {"total_count": "3", "amount": "30"},
        "all": {"total_count": "6", "amount": "60"},
    }
    assert handler_repository.list_record_ids(
        handler="张三,李四", document_type="进货订单",
    ) == [4]


@pytest.mark.parametrize("document_type,expected_ids", [("进货单", [1, 2, 3]), ("进货订单", [4])])
def test_handler_filter_is_shared_by_list_export_and_cross_page_selection(handler_repository, document_type, expected_ids):
    app = FastAPI()
    app.state.inventory_repository = handler_repository
    app.include_router(router)
    filters = {"handler": " 张三，李四\n张三 ", "document_type": document_type}
    with TestClient(app) as client:
        response = client.get("/inventory", params={**filters, "page": 1, "page_size": 1})
        assert response.status_code == 200
        assert response.json()["total"] == len(expected_ids)
        assert [item["id"] for item in response.json()["items"]] == [expected_ids[-1]]

        response = client.post("/inventory/selection-ids", json=filters)
        assert response.status_code == 200
        assert response.json()["ids"] == expected_ids
        assert response.headers["cache-control"] == "no-store"

        exported_calls = []
        original_list_records = handler_repository.list_records

        def capture_exported_records(**kwargs):
            result = original_list_records(**kwargs)
            exported_calls.append(result)
            return result

        handler_repository.list_records = capture_exported_records
        response = client.get("/inventory/export", params=filters)
        assert response.status_code == 200
        assert response.headers["content-type"].startswith("application/vnd.openxmlformats")
        assert {item["id"] for item in exported_calls[0]["items"]} == set(expected_ids)
