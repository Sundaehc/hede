from __future__ import annotations

from storage.inventory_repository import InventoryRepository


def _detail(product_code: str, color_barcode: str, quantity: str) -> dict[str, object]:
    return {
        "product_code": product_code,
        "product_name": product_code,
        "color_spec": color_barcode,
        "color_barcode": color_barcode,
        "color_name": color_barcode,
        "quantity": quantity,
        "unit_price": "10",
        "amount": str(int(quantity) * 10),
        "size_quantities": {"240": quantity},
        "extra_fields": {},
    }


def test_merge_imported_details_keeps_rows_absent_from_workbook(test_database_url: str, recreate_tables) -> None:
    repository = InventoryRepository(test_database_url)
    record = repository.create_record({"document_type": "进货单", "date": "2026-08-04"})
    document_id = int(record["id"])

    repository.create_details([
        {**_detail("A001", "01", "1"), "document_id": document_id},
        {**_detail("B001", "02", "2"), "document_id": document_id},
    ], document_id)

    result = repository.merge_imported_details(document_id, [
        _detail("A001", "01", "3"),
        _detail("C001", "03", "4"),
    ])

    assert result == {"added": 1, "updated": 1, "total": 2}
    details = {str(item["product_code"]): item for item in repository.list_details(document_id)}
    assert set(details) == {"A001", "B001", "C001"}
    assert str(details["A001"]["quantity"]) == "3.00"
    assert str(details["B001"]["quantity"]) == "2.00"
    assert str(details["C001"]["quantity"]) == "4.00"

