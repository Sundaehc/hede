from __future__ import annotations

from decimal import Decimal

from storage.inventory_repository import InventoryRepository


def _create_priced_document(
    repository: InventoryRepository,
    *,
    date: str,
    customer: str,
    document_type: str,
    product_code: str,
    unit_price: str,
) -> dict[str, object]:
    record = repository.create_record({
        "date": date,
        "supplier": customer,
        "warehouse": "批发测试仓库",
        "document_type": document_type,
        "summary": f"{customer}-{document_type}-{date}-{unit_price}",
    })
    repository.create_detail({
        "document_id": record["id"],
        "product_code": product_code,
        "quantity": "1",
        "unit_price": unit_price,
        "amount": unit_price,
    })
    return record


def test_latest_wholesale_sales_prices_uses_latest_matching_sales_document(
    test_database_url: str,
    recreate_tables,
) -> None:
    repository = InventoryRepository(test_database_url)
    product_code = "WHOLESALE-PRICE-TEST"

    older_sale = _create_priced_document(
        repository,
        date="2026-08-10",
        customer="客户A",
        document_type="批发销售单",
        product_code=product_code,
        unit_price="120",
    )
    latest_sale = _create_priced_document(
        repository,
        date="2026-08-18",
        customer="客户A",
        document_type="批发销售单",
        product_code=product_code,
        unit_price="150",
    )
    _create_priced_document(
        repository,
        date="2026-08-19",
        customer="客户A",
        document_type="批发销售退货单",
        product_code=product_code,
        unit_price="999",
    )
    _create_priced_document(
        repository,
        date="2026-08-19",
        customer="客户B",
        document_type="批发销售单",
        product_code=product_code,
        unit_price="888",
    )
    _create_priced_document(
        repository,
        date="2026-08-20",
        customer="客户A",
        document_type="批发销售单",
        product_code=product_code,
        unit_price="777",
    )
    deleted_sale = _create_priced_document(
        repository,
        date="2026-08-19",
        customer="客户A",
        document_type="批发销售单",
        product_code=product_code,
        unit_price="666",
    )
    repository.delete_record(int(deleted_sale["id"]))

    prices = repository.latest_wholesale_sales_prices(
        customer="客户A",
        product_codes={product_code},
        as_of_date="2026-08-19",
    )
    assert prices == {product_code: Decimal("150.00")}

    earlier_prices = repository.latest_wholesale_sales_prices(
        customer="客户A",
        product_codes={product_code},
        as_of_date="2026-08-17",
    )
    assert earlier_prices == {product_code: Decimal("120.00")}

    excluding_latest = repository.latest_wholesale_sales_prices(
        customer="客户A",
        product_codes={product_code},
        as_of_date="2026-08-19",
        exclude_document_id=latest_sale["id"],
    )
    assert excluding_latest == {product_code: Decimal("120.00")}
    assert older_sale["id"] != latest_sale["id"]
