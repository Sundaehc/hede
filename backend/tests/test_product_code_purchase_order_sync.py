from __future__ import annotations

from types import SimpleNamespace

import pytest
from sqlalchemy import insert, select

from api.routes import products as product_routes
from api.schemas import ProductWriteRequest
from domain.inventory_schema import INVENTORY_DETAIL_TABLE
from domain.schema import PRODUCT_ARCHIVE_TABLES
from storage.inventory_repository import InventoryRepository
from storage.product_repository import ProductRepository


class _Transaction:
    def __init__(self) -> None:
        self.connection = object()
        self.committed = False
        self.rolled_back = False

    def __enter__(self):
        return self.connection

    def __exit__(self, error_type, *_args):
        self.committed = error_type is None
        self.rolled_back = error_type is not None
        return False


class _RouteProductRepository:
    def __init__(self) -> None:
        self.transaction = _Transaction()
        self.engine = SimpleNamespace(begin=lambda: self.transaction)
        self.existing = {
            "id": 9,
            "source_workbook": "manual_admin",
            "source_sheet": "cbanner_mens",
            "source_row_number": "manual",
            "sku": "OLD-CODE",
            "original_sku": "OLD-ORIGINAL",
            "supplier_name": "测试供应商",
            "extra_fields": {},
        }

    @staticmethod
    def is_product_archive_brand(brand: str) -> bool:
        return brand == "cbanner_mens"

    def get_product(self, brand: str, product_id: int):
        assert brand == "cbanner_mens"
        assert product_id == 9
        return dict(self.existing)

    def update_product(self, brand, product_id, record, *, connection, manual_cost_override):
        assert connection is self.transaction.connection
        assert manual_cost_override is True
        return {**self.existing, **record, "id": product_id, "sku": "NEW-CODE"}

    def purchase_order_product_code_replacements(
        self,
        brand,
        product_id,
        before,
        after,
        *,
        connection,
    ):
        assert connection is self.transaction.connection
        return {"OLD-CODE": "NEW-CODE"}


class _RouteInventoryRepository:
    def __init__(self, *, fail: bool = False) -> None:
        self.fail = fail

    def sync_purchase_order_product_codes(self, connection, **kwargs):
        if self.fail:
            raise RuntimeError("purchase-order-sync-failed")
        assert kwargs["brand"] == "cbanner_mens"
        assert kwargs["replacements"] == {"OLD-CODE": "NEW-CODE"}
        return {"details": 4, "documents": 2, "document_ids": [11, 12]}


def _product_update_request(product_repository, inventory_repository):
    return SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(
        repository=product_repository,
        inventory_repository=inventory_repository,
    )))


def test_product_update_and_purchase_order_sync_share_one_transaction(monkeypatch) -> None:
    repository = _RouteProductRepository()
    request = _product_update_request(repository, _RouteInventoryRepository())
    monkeypatch.setattr(product_routes, "clear_fine_table_cache", lambda: None)
    monkeypatch.setattr(product_routes, "clear_product_goods_cache", lambda: None)
    monkeypatch.setattr(product_routes, "write_operation_log", lambda *_args, **_kwargs: None)

    result = product_routes.update_product(
        request,
        "cbanner_mens",
        9,
        ProductWriteRequest.model_validate({
            "brand": "cbanner_mens",
            "payload": {
                "sku": "NEW-CODE",
                "original_sku": "OLD-ORIGINAL",
            },
        }),
    )

    assert repository.transaction.committed is True
    assert result["purchase_order_sync"]["details"] == 4


def test_product_update_rolls_back_when_purchase_order_sync_fails(monkeypatch) -> None:
    repository = _RouteProductRepository()
    request = _product_update_request(repository, _RouteInventoryRepository(fail=True))
    operation_logs: list[object] = []
    monkeypatch.setattr(product_routes, "write_operation_log", lambda *_args, **kwargs: operation_logs.append(kwargs))

    with pytest.raises(RuntimeError, match="purchase-order-sync-failed"):
        product_routes.update_product(
            request,
            "cbanner_mens",
            9,
            ProductWriteRequest.model_validate({
                "brand": "cbanner_mens",
                "payload": {
                    "sku": "NEW-CODE",
                    "original_sku": "OLD-ORIGINAL",
                },
            }),
        )

    assert repository.transaction.rolled_back is True
    assert operation_logs == []


def test_product_code_change_syncs_all_purchase_orders_only_for_matching_brand(
    test_database_url: str,
    recreate_tables,
) -> None:
    products = ProductRepository(test_database_url)
    inventory = InventoryRepository(test_database_url)
    mens_supplier = inventory.create_supplier({"brand": "cbanner_mens", "name": "男鞋供应商"})
    inventory.create_supplier({"brand": "cbanner_womens", "name": "女鞋供应商"})
    inventory.create_supplier({"brand": "cbanner_mens", "name": "跨品牌同名供应商"})
    inventory.create_supplier({"brand": "cbanner_womens", "name": "跨品牌同名供应商"})
    product_table = PRODUCT_ARCHIVE_TABLES["cbanner_mens"]
    with products.engine.begin() as connection:
        product = dict(connection.execute(insert(product_table).values(
            source_workbook="manual_admin",
            source_sheet="cbanner_mens",
            source_row_number="manual",
            raw_payload={},
            sku="OLD-CODE",
            original_sku="ORIGINAL-CODE",
            supplier_name=mens_supplier["name"],
        ).returning(product_table)).mappings().one())

    historical_purchase = inventory.create_record({
        "date": "2025-01-10",
        "supplier": mens_supplier["name"],
        "warehouse": "测试仓库",
        "document_type": "进货订单",
        "summary": "历史采购单",
    })
    current_purchase = inventory.create_record({
        "date": "2026-09-17",
        "supplier": mens_supplier["name"],
        "warehouse": "测试仓库",
        "document_type": "进货订单",
        "summary": "当前采购单",
    })
    inventory_document = inventory.create_record({
        "date": "2026-09-17",
        "supplier": mens_supplier["name"],
        "warehouse": "测试仓库",
        "document_type": "进货单",
        "summary": "经营历程不修改",
    })
    other_brand_purchase = inventory.create_record({
        "date": "2026-09-17",
        "supplier": "女鞋供应商",
        "warehouse": "测试仓库",
        "document_type": "进货订单",
        "summary": "其他品牌采购单不修改",
    })
    legacy_supplier_purchase = inventory.create_record({
        "date": "2024-06-01",
        "supplier": "已从供应商管理删除的旧供应商",
        "warehouse": "测试仓库",
        "document_type": "进货订单",
        "summary": "历史旧供应商采购单",
        "raw_payload": {"brand": "cbanner_mens"},
    })
    ambiguous_supplier_purchase = inventory.create_record({
        "date": "2024-06-01",
        "supplier": "跨品牌同名供应商",
        "warehouse": "测试仓库",
        "document_type": "进货订单",
        "summary": "品牌不明确的同名供应商采购单",
    })
    details = [
        inventory.create_detail({
            "document_id": historical_purchase["id"],
            "product_code": "OLD-CODE",
            "extra_fields": {"image_code": "ORIGINAL-CODE", "style_code": "OLD-CODE"},
            "quantity": "1",
        }),
        inventory.create_detail({
            "document_id": ambiguous_supplier_purchase["id"],
            "product_code": "OLD-CODE",
            "extra_fields": {},
            "quantity": "1",
        }),
        inventory.create_detail({
            "document_id": current_purchase["id"],
            "product_code": "OLD-CODE",
            "extra_fields": {},
            "quantity": "1",
        }),
        inventory.create_detail({
            "document_id": inventory_document["id"],
            "product_code": "OLD-CODE",
            "extra_fields": {},
            "quantity": "1",
        }),
        inventory.create_detail({
            "document_id": other_brand_purchase["id"],
            "product_code": "OLD-CODE",
            "extra_fields": {},
            "quantity": "1",
        }),
        inventory.create_detail({
            "document_id": legacy_supplier_purchase["id"],
            "product_code": "OLD-CODE",
            "extra_fields": {},
            "quantity": "1",
        }),
        inventory.create_detail({
            "document_id": historical_purchase["id"],
            "product_code": "OLD-CODE-SUFFIX",
            "extra_fields": {"image_code": "OLD-CODE"},
            "quantity": "1",
        }),
        inventory.create_detail({
            "document_id": current_purchase["id"],
            "product_code": "UNCHANGED-PRODUCT-CODE",
            "extra_fields": {"image_code": "ORIGINAL-CODE"},
            "quantity": "1",
        }),
    ]

    with products.engine.begin() as connection:
        updated = products.update_product(
            "cbanner_mens",
            int(product["id"]),
            {**product, "sku": "NEW-CODE", "original_sku": "NEW-ORIGINAL-CODE"},
            connection=connection,
        )
        assert updated is not None
        replacements = products.purchase_order_product_code_replacements(
            "cbanner_mens",
            int(product["id"]),
            product,
            updated,
            connection=connection,
        )
        result = inventory.sync_purchase_order_product_codes(
            connection,
            brand="cbanner_mens",
            replacements=replacements,
        )

    assert replacements == {
        "OLD-CODE": "NEW-CODE",
        "ORIGINAL-CODE": "NEW-ORIGINAL-CODE",
    }
    assert result["details"] == 4
    assert result["documents"] == 3
    with inventory.engine.connect() as connection:
        rows = {
            int(row["id"]): dict(row)
            for row in connection.execute(
                select(INVENTORY_DETAIL_TABLE)
                .where(INVENTORY_DETAIL_TABLE.c.id.in_([detail["id"] for detail in details]))
            ).mappings()
        }

    assert rows[int(details[0]["id"])]["product_code"] == "NEW-CODE"
    assert rows[int(details[0]["id"])]["extra_fields"]["image_code"] == "NEW-ORIGINAL-CODE"
    assert rows[int(details[0]["id"])]["extra_fields"]["style_code"] == "NEW-CODE"
    assert rows[int(details[1]["id"])]["product_code"] == "OLD-CODE"
    assert rows[int(details[2]["id"])]["product_code"] == "NEW-CODE"
    assert rows[int(details[3]["id"])]["product_code"] == "OLD-CODE"
    assert rows[int(details[4]["id"])]["product_code"] == "OLD-CODE"
    assert rows[int(details[5]["id"])]["product_code"] == "NEW-CODE"
    assert rows[int(details[6]["id"])]["product_code"] == "OLD-CODE-SUFFIX"
    assert rows[int(details[6]["id"])]["extra_fields"]["image_code"] == "OLD-CODE"
    assert rows[int(details[7]["id"])]["product_code"] == "UNCHANGED-PRODUCT-CODE"
    assert rows[int(details[7]["id"])]["extra_fields"]["image_code"] == "NEW-ORIGINAL-CODE"


def test_shared_original_code_is_not_used_for_bulk_purchase_order_rename(
    test_database_url: str,
    recreate_tables,
) -> None:
    products = ProductRepository(test_database_url)
    table = PRODUCT_ARCHIVE_TABLES["cbanner_mens"]
    with products.engine.begin() as connection:
        first = dict(connection.execute(insert(table).values(
            source_workbook="manual_admin",
            source_sheet="cbanner_mens",
            source_row_number="1",
            raw_payload={},
            sku="SKU-A",
            original_sku="SHARED-ORIGINAL",
        ).returning(table)).mappings().one())
        connection.execute(insert(table).values(
            source_workbook="manual_admin",
            source_sheet="cbanner_mens",
            source_row_number="2",
            raw_payload={},
            sku="SKU-B",
            original_sku="SHARED-ORIGINAL",
        ))
        updated = products.update_product(
            "cbanner_mens",
            int(first["id"]),
            {**first, "original_sku": "NEW-ORIGINAL"},
            connection=connection,
        )
        assert updated is not None
        replacements = products.purchase_order_product_code_replacements(
            "cbanner_mens",
            int(first["id"]),
            first,
            updated,
            connection=connection,
        )

    assert replacements == {}


def test_code_still_retained_by_same_product_is_not_renamed() -> None:
    products = object.__new__(ProductRepository)
    replacements = products.purchase_order_product_code_replacements(
        "cbanner_mens",
        1,
        {"sku": "OLD-CODE", "original_sku": "OLD-CODE"},
        {"sku": "NEW-CODE", "original_sku": "OLD-CODE"},
        connection=object(),
    )

    assert replacements == {}


def test_same_old_code_with_two_new_meanings_is_not_renamed() -> None:
    products = object.__new__(ProductRepository)
    replacements = products.purchase_order_product_code_replacements(
        "cbanner_mens",
        1,
        {"sku": "OLD-CODE", "original_sku": "OLD-CODE"},
        {"sku": "NEW-SKU", "original_sku": "NEW-ORIGINAL"},
        connection=object(),
    )

    assert replacements == {}
