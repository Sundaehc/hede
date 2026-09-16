from __future__ import annotations

from decimal import Decimal
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from api.routes.inventory import list_inventory_detail_unit_price_options, list_inventory_details
from storage.inventory_repository import InventoryRepository


class _Repository:
    def __init__(self) -> None:
        self.received: dict[str, object] = {}

    def get_record(self, record_id: int):
        return {"id": record_id, "document_type": "进货单"}

    def list_details_page(self, document_id: int, **kwargs):
        self.received = {"document_id": document_id, **kwargs}
        return {"items": [], "total": 0, "page": kwargs["page"], "page_size": kwargs["page_size"]}

    def list_detail_unit_price_options(self, document_id: int, **kwargs):
        self.received = {"document_id": document_id, **kwargs}
        return {
            "items": [
                {"value": "156.5", "count": 34},
                {"value": None, "count": 2},
            ],
            "total": 2,
            "truncated": False,
        }


def _request(repository: _Repository):
    return SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(inventory_repository=repository)))


def test_inventory_detail_price_filter_is_applied_to_paged_query() -> None:
    repository = _Repository()

    result = list_inventory_details(
        _request(repository),
        42,
        page=2,
        page_size=100,
        unit_price_values="99.50,199.90",
    )

    assert result["total"] == 0
    assert repository.received == {
        "document_id": 42,
        "page": 2,
        "page_size": 100,
        "unit_price_values": [Decimal("99.50"), Decimal("199.90")],
    }


def test_inventory_detail_price_filter_parses_selected_values_and_blank() -> None:
    repository = _Repository()

    list_inventory_details(
        _request(repository),
        42,
        page=1,
        page_size=100,
        unit_price_values="156.50,190,__blank__,156.50",
    )

    assert repository.received["unit_price_values"] == [
        Decimal("156.50"),
        Decimal("190"),
        None,
    ]


def test_inventory_detail_price_filter_rejects_empty_selected_values() -> None:
    repository = _Repository()

    with pytest.raises(HTTPException) as exc_info:
        list_inventory_details(
            _request(repository),
            42,
            page=1,
            page_size=100,
            unit_price_values=",",
        )

    assert exc_info.value.status_code == 400
    assert exc_info.value.detail == "请至少选择一个单价"


def test_inventory_detail_price_options_cover_the_whole_document() -> None:
    repository = _Repository()

    result = list_inventory_detail_unit_price_options(
        _request(repository),
        42,
        search="15",
        limit=300,
    )

    assert result["items"][0] == {"value": "156.5", "count": 34}
    assert repository.received == {
        "document_id": 42,
        "search": "15",
        "limit": 300,
    }


def test_inventory_detail_price_options_and_values_query_database(
    test_database_url: str,
    recreate_tables,
) -> None:
    repository = InventoryRepository(test_database_url)
    record = repository.create_record({
        "date": "2026-09-16",
        "supplier": "单价筛选测试供应商",
        "warehouse": "单价筛选测试仓库",
        "document_type": "进货单",
        "summary": "单价筛选仓储测试",
    })
    document_id = int(record["id"])
    for index, price in enumerate(("156.50", "156.50", "190", None), start=1):
        repository.create_detail({
            "document_id": document_id,
            "product_code": f"PRICE-FILTER-{index}",
            "quantity": "1",
            "unit_price": price,
            "amount": price,
        })

    options = repository.list_detail_unit_price_options(document_id)
    page = repository.list_details_page(
        document_id,
        page=1,
        page_size=100,
        unit_price_values=[Decimal("156.5"), None],
    )

    assert options == {
        "items": [
            {"value": None, "count": 1},
            {"value": "190", "count": 1},
            {"value": "156.5", "count": 2},
        ],
        "total": 3,
        "truncated": False,
    }
    assert page["total"] == 3
    assert {item["product_code"] for item in page["items"]} == {
        "PRICE-FILTER-1",
        "PRICE-FILTER-2",
        "PRICE-FILTER-4",
    }
