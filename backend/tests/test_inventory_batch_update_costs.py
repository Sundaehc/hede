from __future__ import annotations

from decimal import Decimal

from storage.inventory_repository import InventoryRepository


def _create_document(
    repository: InventoryRepository,
    *,
    date: str,
    document_type: str,
    product_code: str = "COST-UPDATE-TEST",
    unit_price: str = "10",
) -> dict[str, object]:
    record = repository.create_record({
        "date": date,
        "supplier": "批量改价测试供应商",
        "warehouse": "批量改价测试仓库",
        "document_type": document_type,
        "summary": f"{document_type}-{date}-{unit_price}",
    })
    repository.create_detail({
        "document_id": record["id"],
        "product_code": product_code,
        "quantity": "2",
        "unit_price": unit_price,
        "amount": str(Decimal(unit_price) * 2),
    })
    return repository.get_record(int(record["id"]))


def _unit_price(repository: InventoryRepository, record: dict[str, object]) -> Decimal:
    details = repository.list_details(int(record["id"]))
    return Decimal(str(details[0]["unit_price"]))


def test_batch_update_purchase_costs_filters_document_type(
    test_database_url: str,
    recreate_tables,
) -> None:
    repository = InventoryRepository(test_database_url)
    purchase = _create_document(repository, date="2026-09-01", document_type="进货单")
    purchase_return = _create_document(repository, date="2026-09-01", document_type="进货退货单")
    stock_gain = _create_document(repository, date="2026-09-01", document_type="报溢单")

    result = repository.batch_update_purchase_costs(
        date_start="2026-09-01",
        date_end="2026-09-01",
        document_type="进货单",
        price_updates={"COST-UPDATE-TEST": "25"},
    )

    assert result["updated_details"] == 1
    assert result["updated_documents"] == 1
    assert _unit_price(repository, purchase) == Decimal("25")
    assert _unit_price(repository, purchase_return) == Decimal("10")
    assert _unit_price(repository, stock_gain) == Decimal("10")
    assert Decimal(str(repository.get_record(int(purchase["id"]))["amount"])) == Decimal("50")
    assert Decimal(str(repository.get_record(int(purchase_return["id"]))["amount"])) == Decimal("-20")


def test_batch_update_purchase_costs_filters_document_numbers(
    test_database_url: str,
    recreate_tables,
) -> None:
    repository = InventoryRepository(test_database_url)
    target = _create_document(repository, date="2026-09-01", document_type="进货退货单")
    other = _create_document(repository, date="2026-09-01", document_type="进货退货单", unit_price="12")

    result = repository.batch_update_purchase_costs(
        date_start="2026-09-01",
        date_end="2026-09-01",
        document_type="进货退货单",
        document_numbers=[str(target["document_number"])],
        price_updates={"COST-UPDATE-TEST": "30"},
    )

    assert result["updated_details"] == 1
    assert result["updated_documents"] == 1
    assert result["items"][0]["document_number"] == target["document_number"]
    assert _unit_price(repository, target) == Decimal("30")
    assert _unit_price(repository, other) == Decimal("12")
    assert Decimal(str(repository.get_record(int(target["id"]))["amount"])) == Decimal("-60")
    assert Decimal(str(repository.get_record(int(other["id"]))["amount"])) == Decimal("-24")


def test_purchase_cost_document_options_follow_date_type_and_deleted_status(
    test_database_url: str,
    recreate_tables,
) -> None:
    repository = InventoryRepository(test_database_url)
    target = _create_document(repository, date="2026-09-01", document_type="进货单")
    _create_document(repository, date="2026-09-01", document_type="进货退货单")
    outside_date = _create_document(repository, date="2026-08-31", document_type="进货单")
    deleted = _create_document(repository, date="2026-09-01", document_type="进货单", unit_price="13")
    repository.delete_record(int(deleted["id"]))

    options = repository.list_purchase_cost_document_options(
        date_start="2026-09-01",
        date_end="2026-09-01",
        document_type="进货单",
    )

    assert [item["document_number"] for item in options] == [target["document_number"]]
    assert outside_date["document_number"] not in {item["document_number"] for item in options}
    assert deleted["document_number"] not in {item["document_number"] for item in options}
