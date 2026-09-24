from __future__ import annotations

import asyncio
import io
from types import SimpleNamespace

import pytest
from fastapi import BackgroundTasks, UploadFile
from openpyxl import Workbook
from sqlalchemy import insert, select, update

from api.routes import products as product_routes
from api.routes import import_export as import_routes
from api.schemas import ProductWriteRequest
from domain.inventory_schema import INVENTORY_DETAIL_TABLE
from domain.product_archive_identity_schema import ensure_product_archive_identity_schema
from domain.schema import PRODUCT_ARCHIVE_TABLES
from storage.inventory_repository import InventoryRepository
from storage.product_repository import ProductRepository
from transform.rows import build_admin_record


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
        return {**self.existing, **record, "id": product_id}

    def product_identity_id(self, brand, product_id, *, connection):
        assert brand == "cbanner_mens"
        assert product_id == 9
        assert connection is self.transaction.connection
        return 77


class _RouteInventoryRepository:
    def __init__(self, *, fail: bool = False, fail_all_documents: bool = False) -> None:
        self.fail = fail
        self.fail_all_documents = fail_all_documents

    def purchase_order_product_identity_scope(self, connection, product_identity_id):
        if self.fail:
            raise RuntimeError("purchase-order-sync-failed")
        assert product_identity_id == 77
        return {"details": 4, "documents": 2, "document_ids": [11, 12]}

    def document_product_identity_scope(self, connection, product_identity_id):
        if self.fail_all_documents:
            raise RuntimeError("document-product-sync-failed")
        assert product_identity_id == 77
        return {"details": 7, "documents": 5, "document_ids": [11, 12, 13, 14, 15]}


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
            "payload": {"sku": "NEW-CODE", "original_sku": "OLD-ORIGINAL"},
        }),
    )

    assert repository.transaction.committed is True
    assert result["purchase_order_sync"]["details"] == 4
    assert result["document_product_sync"]["details"] == 4
    assert "4 条关联单据明细" in result["message"]


@pytest.mark.parametrize(("field", "value", "expected_details"), [
    ("color", "黑色", 7),
    ("color_code", "80", 7),
    ("size_range", "尺码组A", 7),
    ("factory_sku", "FACTORY-NEW", 4),
    ("upper_material", "牛皮", 4),
    ("product_name", "新鞋名", 4),
    ("cost", "99.50", 4),
    ("selling_points", "柔软", 0),
])
def test_product_update_reports_sync_for_changed_fields(monkeypatch, field, value, expected_details):
    repository = _RouteProductRepository()
    request = _product_update_request(repository, _RouteInventoryRepository())
    monkeypatch.setattr(product_routes, "_validate_size_group", lambda *_args: None)
    monkeypatch.setattr(product_routes, "clear_fine_table_cache", lambda: None)
    monkeypatch.setattr(product_routes, "clear_product_goods_cache", lambda: None)
    monkeypatch.setattr(product_routes, "write_operation_log", lambda *_args, **_kwargs: None)
    result = product_routes.update_product(request, "cbanner_mens", 9, ProductWriteRequest.model_validate({
        "brand": "cbanner_mens", "payload": {
            "sku": "OLD-CODE", "original_sku": "OLD-ORIGINAL", field: value,
        },
    }))
    assert result["document_product_sync"]["details"] == expected_details
    assert result["purchase_order_sync"]["details"] == (4 if expected_details else 0)


def test_product_update_rolls_back_when_purchase_order_scope_lookup_fails(monkeypatch) -> None:
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
                "payload": {"sku": "NEW-CODE", "original_sku": "OLD-ORIGINAL"},
            }),
        )

    assert repository.transaction.rolled_back is True
    assert operation_logs == []


def test_product_update_rolls_back_when_all_document_scope_lookup_fails(monkeypatch) -> None:
    repository = _RouteProductRepository()
    request = _product_update_request(repository, _RouteInventoryRepository(fail_all_documents=True))
    operation_logs: list[object] = []
    monkeypatch.setattr(product_routes, "write_operation_log", lambda *_args, **kwargs: operation_logs.append(kwargs))

    with pytest.raises(RuntimeError, match="document-product-sync-failed"):
        product_routes.update_product(
            request,
            "cbanner_mens",
            9,
            ProductWriteRequest.model_validate({
                "brand": "cbanner_mens",
                "payload": {"sku": "NEW-CODE", "original_sku": "OLD-ORIGINAL", "color": "黑色"},
            }),
        )

    assert repository.transaction.rolled_back is True
    assert operation_logs == []


@pytest.mark.parametrize(("header", "field", "value", "history_updates"), [
    ("鞋面材质", "upper_material", "牛皮", False),
    ("颜色", "color_name", "黑色", True),
])
def test_import_attribute_change_syncs_existing_details(
    repository, recreate_tables, monkeypatch, header, field, value, history_updates,
):
    inventory = object.__new__(InventoryRepository)
    inventory.engine = repository.engine
    with repository.engine.begin() as connection:
        ensure_product_archive_identity_schema(connection)
    repository.create_product('cbanner_mens', build_admin_record('cbanner_mens', {
        'sku': 'IMPORT-SKU', 'original_sku': 'IMPORT-SKU', 'color': '白色', 'upper_material': '旧材质',
    }))
    details = []
    for document_type in ('进货订单', '进货单'):
        document = inventory.create_record({
            'date': '2026-09-17', 'document_type': document_type, 'raw_payload': {'brand': 'cbanner_mens'},
        })
        details.append(inventory.create_detail({
            'document_id': document['id'], 'product_code': 'IMPORT-SKU', 'color_name': '白色',
            'extra_fields': {'upper_material': '旧材质'}, 'quantity': '2', 'unit_price': '100', 'amount': '200',
        }))
    workbook = Workbook()
    workbook.active.append(['货号', header])
    workbook.active.append(['IMPORT-SKU', value])
    buffer = io.BytesIO()
    workbook.save(buffer)
    workbook.close()
    buffer.seek(0)
    request = _product_update_request(repository, inventory)
    monkeypatch.setattr(import_routes, 'get_image_matcher', lambda *_args: None)
    response = asyncio.run(import_routes.import_products(
        request, BackgroundTasks(), 'cbanner_mens', UploadFile(filename='products.xlsx', file=buffer),
    ))
    assert response['updated'] == 1
    assert response['purchase_order_sync']['details'] == 1
    with repository.engine.connect() as connection:
        rows = list(connection.execute(select(INVENTORY_DETAIL_TABLE).order_by(INVENTORY_DETAIL_TABLE.c.id)).mappings())
    for row, is_purchase in zip(rows, (True, False), strict=True):
        actual = row['extra_fields'][field] if field == 'upper_material' else row[field]
        expected = value if is_purchase or history_updates else '旧材质'
        assert actual == expected
        assert row['product_code'] == 'IMPORT-SKU'
        assert row['amount'] == 200


def test_stable_product_identity_only_syncs_purchase_codes(
    test_database_url: str,
    recreate_tables,
) -> None:
    products = ProductRepository(test_database_url)
    inventory = object.__new__(InventoryRepository)
    inventory.engine = products.engine
    with products.engine.begin() as connection:
        ensure_product_archive_identity_schema(connection)
    mens_supplier = inventory.create_supplier({"brand": "cbanner_mens", "name": "男鞋供应商"})
    inventory.create_supplier({"brand": "cbanner_womens", "name": "女鞋供应商"})
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
        product_identity_id = products.product_identity_id(
            "cbanner_mens",
            int(product["id"]),
            connection=connection,
        )
    assert product_identity_id is not None

    historical_purchase = inventory.create_record({
        "date": "2025-01-10",
        "supplier": mens_supplier["name"],
        "warehouse": "测试仓库",
        "document_type": "进货订单",
        "summary": "历史采购单",
        "raw_payload": {"brand": "cbanner_mens"},
    })
    current_purchase = inventory.create_record({
        "date": "2026-09-17",
        "supplier": mens_supplier["name"],
        "warehouse": "测试仓库",
        "document_type": "进货订单",
        "summary": "当前采购单",
        "raw_payload": {"brand": "cbanner_mens"},
    })
    inventory_document = inventory.create_record({
        "date": "2026-09-17",
        "supplier": mens_supplier["name"],
        "warehouse": "测试仓库",
        "document_type": "进货单",
        "summary": "经营历程同步修改",
    })
    other_brand_purchase = inventory.create_record({
        "date": "2026-09-17",
        "supplier": "女鞋供应商",
        "warehouse": "测试仓库",
        "document_type": "进货订单",
        "summary": "其他品牌采购单不修改",
        "raw_payload": {"brand": "cbanner_womens"},
    })
    details = [
        inventory.create_detail({
            "document_id": historical_purchase["id"],
            "product_code": "OLD-CODE",
            "extra_fields": {"image_code": "ORIGINAL-CODE", "style_code": "OLD-CODE"},
            "quantity": "1",
        }),
        inventory.create_detail({
            "document_id": current_purchase["id"],
            "product_identity_id": product_identity_id,
            "product_code": "OLD-CODE",
            "extra_fields": {},
            "quantity": "1",
        }),
        inventory.create_detail({
            "document_id": inventory_document["id"],
            "product_identity_id": product_identity_id,
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
            "document_id": historical_purchase["id"],
            "product_code": "OLD-CODE-SUFFIX",
            "extra_fields": {},
            "quantity": "1",
        }),
    ]

    with products.engine.begin() as connection:
        connection.execute(
            update(product_table)
            .where(product_table.c.id == product["id"])
            .values(sku="NEW-CODE", original_sku="NEW-ORIGINAL-CODE")
        )
        scope = inventory.purchase_order_product_identity_scope(connection, product_identity_id)
        all_scope = inventory.document_product_identity_scope(connection, product_identity_id)

    assert scope["details"] == 2
    assert scope["documents"] == 2
    assert all_scope["details"] == 3
    assert all_scope["documents"] == 3
    with inventory.engine.connect() as connection:
        rows = {
            int(row["id"]): dict(row)
            for row in connection.execute(
                select(INVENTORY_DETAIL_TABLE)
                .where(INVENTORY_DETAIL_TABLE.c.id.in_([detail["id"] for detail in details]))
            ).mappings()
        }

    assert rows[int(details[0]["id"])]["product_identity_id"] == product_identity_id
    assert rows[int(details[0]["id"])]["product_code"] == "NEW-CODE"
    assert rows[int(details[0]["id"])]["extra_fields"]["image_code"] == "NEW-ORIGINAL-CODE"
    assert rows[int(details[0]["id"])]["extra_fields"]["style_code"] == "NEW-CODE"
    assert rows[int(details[1]["id"])]["product_code"] == "NEW-CODE"
    assert rows[int(details[2]["id"])]["product_identity_id"] == product_identity_id
    assert rows[int(details[2]["id"])]["product_code"] == "OLD-CODE"
    assert rows[int(details[3]["id"])]["product_identity_id"] is None
    assert rows[int(details[3]["id"])]["product_code"] == "OLD-CODE"
    assert rows[int(details[4]["id"])]["product_identity_id"] is None
    assert rows[int(details[4]["id"])]["product_code"] == "OLD-CODE-SUFFIX"
