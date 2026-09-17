from __future__ import annotations

from api.routes.inventory import (
    _build_purchase_order_search_rows,
    _list_inventory_export_details,
)


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
