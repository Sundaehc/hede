from __future__ import annotations

from storage.inventory_repository import InventoryRepository


def test_internal_sales_customer_matches_shop_and_child_unit(
    test_database_url: str,
    recreate_tables,
) -> None:
    repository = InventoryRepository(test_database_url)
    repository.create_general_customer_brand({"name": "测试品牌"})
    internal_shop = repository.create_general_customer_shop({
        "customer_name": "测试品牌",
        "shop_name": "测试品牌-内销客户",
    })
    regular_shop = repository.create_general_customer_shop({
        "customer_name": "测试品牌",
        "shop_name": "测试品牌-天猫店铺",
    })
    internal_unit = repository.create_general_customer_unit({
        "shop_id": internal_shop["id"],
        "unit_name": "测试内销单位",
    })
    regular_unit = repository.create_general_customer_unit({
        "shop_id": regular_shop["id"],
        "unit_name": "测试普通单位",
    })

    assert repository.is_internal_sales_customer(internal_shop["shop_name"]) is True
    assert repository.is_internal_sales_customer(internal_unit["unit_name"]) is True
    assert repository.is_internal_sales_customer(regular_shop["shop_name"]) is False
    assert repository.is_internal_sales_customer(regular_unit["unit_name"]) is False


def test_internal_sales_documents_are_always_completed(
    test_database_url: str,
    recreate_tables,
) -> None:
    repository = InventoryRepository(test_database_url)
    repository.create_general_customer_brand({"name": "完成状态测试品牌"})
    internal_shop = repository.create_general_customer_shop({
        "customer_name": "完成状态测试品牌",
        "shop_name": "完成状态测试品牌-内销客户",
    })
    regular_shop = repository.create_general_customer_shop({
        "customer_name": "完成状态测试品牌",
        "shop_name": "完成状态测试品牌-普通客户",
    })
    internal_without_details = repository.create_record({
        "date": "2026-08-19",
        "supplier": internal_shop["shop_name"],
        "warehouse": "测试仓库",
        "document_type": "批发销售单",
        "summary": "内销无明细",
    })
    internal_with_zero_price = repository.create_record({
        "date": "2026-08-19",
        "supplier": internal_shop["shop_name"],
        "warehouse": "测试仓库",
        "document_type": "批发销售单",
        "summary": "内销零价",
    })
    repository.create_detail({
        "document_id": internal_with_zero_price["id"],
        "product_code": "TEST-INTERNAL",
        "quantity": "1",
        "unit_price": "0",
        "amount": "0",
    })
    regular_with_zero_price = repository.create_record({
        "date": "2026-08-19",
        "supplier": regular_shop["shop_name"],
        "warehouse": "测试仓库",
        "document_type": "批发销售单",
        "summary": "普通客户零价",
    })
    repository.create_detail({
        "document_id": regular_with_zero_price["id"],
        "product_code": "TEST-REGULAR",
        "quantity": "1",
        "unit_price": "0",
        "amount": "0",
    })

    completed = repository.list_records(
        supplier="完成状态测试品牌",
        completion_status="completed",
        page=1,
        page_size=100,
    )
    incomplete = repository.list_records(
        supplier="完成状态测试品牌",
        completion_status="incomplete",
        page=1,
        page_size=100,
    )
    completed_ids = {item["id"] for item in completed["items"]}
    incomplete_ids = {item["id"] for item in incomplete["items"]}

    assert internal_without_details["id"] in completed_ids
    assert internal_with_zero_price["id"] in completed_ids
    assert regular_with_zero_price["id"] not in completed_ids
    assert internal_without_details["id"] not in incomplete_ids
    assert internal_with_zero_price["id"] not in incomplete_ids
    assert regular_with_zero_price["id"] in incomplete_ids
