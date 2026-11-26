from __future__ import annotations

from io import BytesIO
from unittest.mock import Mock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from openpyxl import load_workbook
from sqlalchemy import create_engine

from api.routes.inventory import (
    _build_purchase_order_search_rows,
    _list_inventory_export_details,
    router,
)
from domain.inventory_schema import INVENTORY_DETAIL_TABLE, INVENTORY_TABLE
from storage.inventory_repository import InventoryRepository


@pytest.mark.parametrize("mode", ["summary", "size_rows"])
def test_purchase_color_filter_applies_to_all_pages_selection_and_export(monkeypatch, mode):
    repository = Mock()
    repository.list_records.return_value = {"items": [_record(), {**_record(), "id": 11}]}
    repository.list_record_ids.return_value = [10, 11]
    repository.list_matching_details_for_documents.return_value = [
        _detail(1, "01", {"220": "1"}),
        _detail(2, "02", {"220": "2", "225": "1"}),
        {**_detail(3, "", {"220": "3"}), "document_id": 11, "color_name": "", "color_spec": "白色"},
    ]
    monkeypatch.setattr("api.routes.inventory.enrich_purchase_product_remarks", Mock())
    monkeypatch.setattr("api.routes.inventory._load_supplier_export_lookup", Mock(return_value={}))
    app = FastAPI()
    app.state.inventory_repository = repository
    app.include_router(router)
    filters = {"document_type": "进货订单", "product_code": "SKU001", "purchase_colors": ["02 / 颜色02"]}
    with TestClient(app) as client:
        result = client.get("/inventory", params={**filters, "purchase_detail_mode": mode, "page_size": 1})
        assert result.status_code == 200
        payload = result.json()
        assert payload["total"] == (2 if mode == "size_rows" else 1)
        assert [row["color_barcode"] for row in payload["items"]] == ["02"]
        assert {option["value"] for option in payload["purchase_color_options"]} == {"01 / 颜色01", "02 / 颜色02", "白色"}
        assert client.post("/inventory/selection-ids", json=filters).json()["ids"] == [10]
        response = client.get("/inventory/export", params=filters)
        assert response.status_code == 200
        workbook = load_workbook(BytesIO(response.content), read_only=True)
        headers, *exported_rows = workbook.active.values
        workbook.close()
        assert len(exported_rows) == 1
        assert str(exported_rows[0][headers.index("订货数量")]) == "3"


def _record() -> dict[str, object]:
    return {
        "id": 10,
        "document_number": "JHDD-2026-09-16-0001",
        "date": "2026-09-16",
        "supplier": "测试供应商",
        "document_type": "进货订单",
        "extra_fields": {"delivery_date": "2026-09-30"},
    }


def _detail(
    detail_id: int,
    color_barcode: str,
    size_quantities: dict[str, str],
) -> dict[str, object]:
    quantity = sum(int(value) for value in size_quantities.values())
    return {
        "id": detail_id,
        "document_id": 10,
        "product_code": "SKU001",
        "product_name": "测试商品",
        "color_barcode": color_barcode,
        "color_name": f"颜色{color_barcode}",
        "quantity": str(quantity),
        "unit_price": "12.5",
        "amount": str(quantity * 12.5),
        "size_quantities": size_quantities,
    }


def test_purchase_order_search_summary_keeps_colors_separate() -> None:
    rows = _build_purchase_order_search_rows(
        [_record()],
        [
            _detail(1, "01", {"220": "1", "225": "2"}),
            _detail(2, "01", {"220": "2"}),
            _detail(3, "02", {"225": "4"}),
        ],
        "summary",
    )

    assert len(rows) == 2
    assert rows[0]["color_barcode"] == "01"
    assert rows[0]["quantity"] == "5"
    assert rows[0]["amount"] == "62.5"
    assert rows[0]["size_quantities"] == {"220": "3", "225": "2"}
    assert rows[1]["color_barcode"] == "02"
    assert rows[1]["quantity"] == "4"


def test_purchase_order_search_size_rows_split_quantity_and_amount() -> None:
    rows = _build_purchase_order_search_rows(
        [_record()],
        [
            _detail(1, "01", {"220": "1", "225": "2"}),
            _detail(2, "01", {"220": "2"}),
        ],
        "size_rows",
    )

    assert [(row["size_name"], row["quantity"]) for row in rows] == [
        ("220", "3"),
        ("225", "2"),
    ]
    assert sum(float(str(row["amount"])) for row in rows) == 62.5
    assert all(row["unit_price"] == "12.5" for row in rows)


def test_purchase_order_search_export_uses_only_matching_details() -> None:
    class Repository:
        def __init__(self) -> None:
            self.matching_call: tuple[list[int], str] | None = None

        def list_matching_details_for_documents(
            self,
            document_ids: list[int],
            product_code: str,
        ) -> list[dict[str, object]]:
            self.matching_call = (document_ids, product_code)
            return [{"product_code": product_code}]

        def list_details_for_documents(self, document_ids: list[int]) -> list[dict[str, object]]:
            raise AssertionError("采购单货号搜索导出不应读取单据中的全部商品")

    repository = Repository()
    details = _list_inventory_export_details(
        repository,
        [{"id": 10}, {"id": 11}],
        document_type="进货订单",
        product_code=" SKU001 ",
    )

    assert repository.matching_call == ([10, 11], "SKU001")
    assert details == [{"product_code": "SKU001"}]


@pytest.mark.parametrize("mode", ["summary", "size_rows"])
def test_purchase_order_search_preserves_document_sort_before_paginating(
    test_database_url, recreate_tables, mode,
) -> None:
    repository = object.__new__(InventoryRepository)
    repository.engine = create_engine(test_database_url)
    try:
        with repository.engine.begin() as connection:
            connection.execute(INVENTORY_TABLE.insert(), [
                {"id": document_id, "date": date, "date_value": date, "supplier": supplier, "document_type": "进货订单"}
                for document_id, date, supplier in (
                    (10, "2026-11-24", "B"),
                    (20, "2026-11-01", "A"),
                    (30, "2026-11-24", "A"),
                )
            ])
            connection.execute(INVENTORY_DETAIL_TABLE.insert(), [
                {**_detail(1, "01", {"220": "1", "225": "2"}), "document_id": 10},
                {**_detail(2, "02", {"220": "1", "225": "2"}), "document_id": 10},
                {**_detail(3, "01", {"220": "1", "225": "2"}), "document_id": 20},
                {**_detail(4, "01", {"220": "1", "225": "2"}), "document_id": 30},
                {**_detail(5, "01", {"220": "1"}), "document_id": 20, "product_code": "UNMATCHED"},
            ])
        app = FastAPI()
        app.state.inventory_repository = repository
        app.include_router(router)
        rows_per_detail = 2 if mode == "size_rows" else 1

        with TestClient(app) as client:
            def get_rows(page, *sort):
                response = client.get("/inventory", params=[
                    ("document_type", "进货订单"), ("product_code", "SKU001"),
                    ("purchase_detail_mode", mode), ("page", page),
                    ("page_size", 2 * rows_per_detail), *(("sort", rule) for rule in sort),
                ])
                assert response.status_code == 200
                payload = response.json()
                assert payload["total"] == 4 * rows_per_detail
                assert payload["page"] == page
                return payload["items"]

            for direction, expected in (("asc", [20, 30]), ("desc", [30, 10])):
                page_rows = get_rows(1, f"date:{direction}")
                assert [row["document_id"] for row in page_rows[::rows_per_detail]] == expected

            ascending = get_rows(1, "date:asc", "supplier:asc")
            assert [row["document_id"] for row in ascending] == [20] * rows_per_detail + [30] * rows_per_detail
            assert [row["detail_id"] for row in get_rows(2, "date:asc", "supplier:asc")] == [1] * rows_per_detail + [2] * rows_per_detail

            descending = get_rows(1, "date:desc", "supplier:desc")
            assert [row["detail_id"] for row in descending] == [1] * rows_per_detail + [2] * rows_per_detail
            assert [row["document_id"] for row in get_rows(2, "date:desc", "supplier:desc")] == [30] * rows_per_detail + [20] * rows_per_detail

            default = get_rows(1)
            assert [row["document_id"] for row in default] == [30] * rows_per_detail + [20] * rows_per_detail
            assert [row["row_key"] for row in default[:rows_per_detail]] == [row["row_key"] for row in ascending[rows_per_detail:]]
    finally:
        repository.engine.dispose()
