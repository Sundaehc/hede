from __future__ import annotations

from storage.inventory_repository import InventoryRepository


def _detail(document_id: int, product_code: str) -> dict[str, object]:
    return {
        "document_id": document_id,
        "product_code": product_code,
        "product_name": product_code,
        "quantity": "1",
        "unit_price": "10",
        "amount": "10",
        "size_quantities": {"240": "1"},
        "extra_fields": {},
    }


def test_purchase_inbound_details_support_multiple_exact_warehouses(
    test_database_url: str,
    recreate_tables,
) -> None:
    repository = InventoryRepository(test_database_url)
    first = repository.create_record({
        "document_type": "进货单",
        "date": "2026-08-04",
        "warehouse": "千百度仙岩仓库",
    })
    second = repository.create_record({
        "document_type": "进货单",
        "date": "2026-08-04",
        "warehouse": "千百度公司仓库",
    })
    excluded = repository.create_record({
        "document_type": "进货单",
        "date": "2026-08-04",
        "warehouse": "千百度仙岩仓库备用区",
    })
    repository.create_details([_detail(int(first["id"]), "A001")], int(first["id"]))
    repository.create_details([_detail(int(second["id"]), "B001")], int(second["id"]))
    repository.create_details([_detail(int(excluded["id"]), "C001")], int(excluded["id"]))

    result = repository.list_purchase_inbound_details(
        warehouse=["千百度仙岩仓库", "千百度公司仓库"],
        page=1,
        page_size=50,
    )

    assert result["total"] == 2
    assert {item["product_code"] for item in result["items"]} == {"A001", "B001"}
