from __future__ import annotations

from datetime import datetime
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine, event, select

from api.routes import inventory as inventory_routes
from domain.inventory_schema import (
    GENERAL_CUSTOMER_BRAND_TABLE,
    GENERAL_CUSTOMER_SHOP_TABLE,
    GENERAL_CUSTOMER_SORT_PREFERENCE_TABLE,
    GENERAL_CUSTOMER_UNIT_TABLE,
    INVENTORY_DETAIL_TABLE,
    INVENTORY_TABLE,
)
from domain.product_archive_identity_schema import PRODUCT_ARCHIVE_IDENTITY_TABLE
from storage.inventory_repository import InventoryRepository


@pytest.fixture
def customer_repository():
    engine = create_engine("sqlite://")

    @event.listens_for(engine, "connect")
    def configure_connection(connection, record):
        connection.create_function("date_trunc", 2, lambda unit, value: value)
        connection.create_function("now", 0, lambda: datetime.now().isoformat())
        connection.execute("PRAGMA foreign_keys=ON")

    for table in (
        GENERAL_CUSTOMER_BRAND_TABLE, GENERAL_CUSTOMER_SHOP_TABLE,
        GENERAL_CUSTOMER_UNIT_TABLE, GENERAL_CUSTOMER_SORT_PREFERENCE_TABLE,
        PRODUCT_ARCHIVE_IDENTITY_TABLE, INVENTORY_TABLE, INVENTORY_DETAIL_TABLE,
    ):
        table.create(engine)
    with engine.begin() as connection:
        connection.execute(GENERAL_CUSTOMER_BRAND_TABLE.insert(), {"id": 1, "name": "测试品牌"})
        connection.execute(GENERAL_CUSTOMER_SHOP_TABLE.insert(), [
            {"id": 1, "customer_name": "测试品牌", "shop_name": "测试店铺"},
            {"id": 2, "customer_name": "测试品牌", "shop_name": "空店铺"},
        ])
        connection.execute(GENERAL_CUSTOMER_UNIT_TABLE.insert(), [
            {"id": 1, "shop_id": 1, "unit_name": "测试单位"},
            {"id": 2, "shop_id": 2, "unit_name": "空单位"},
        ])
    repository = object.__new__(InventoryRepository)
    repository.engine = engine
    try:
        yield repository
    finally:
        engine.dispose()


def seed_history(repository, name="测试店铺", *, deleted=False):
    with repository.engine.begin() as connection:
        connection.execute(INVENTORY_TABLE.insert(), {
            "id": 1, "document_number": "SALE-001", "document_type": "批发销售单",
            "supplier": name, "date": "2026-08-16", "amount": 100,
            "deleted_at": datetime.now() if deleted else None,
        })
        connection.execute(INVENTORY_DETAIL_TABLE.insert(), {
            "id": 1, "document_id": 1, "product_code": "SKU-001",
            "quantity": 1, "unit_price": 100, "amount": 100,
        })


@pytest.mark.parametrize("name,deleted", [
    ("测试店铺", False), ("测试单位", False), ("测试单位", True), (" 测试店铺 ", False),
])
def test_delete_shop_with_history_disables_and_preserves_documents(customer_repository, name, deleted):
    repository = customer_repository
    seed_history(repository, name, deleted=deleted)
    assert repository.get_general_customer_shop(1)["has_history"] is True
    assert repository.delete_general_customer_shop(1) is True
    shop = repository.get_general_customer_shop(1)
    assert shop["is_active"] is False
    assert shop["unit_count"] == 1
    assert repository.get_record_any_status(1)["supplier"] == name
    with repository.engine.connect() as connection:
        assert connection.execute(select(INVENTORY_DETAIL_TABLE.c.id)).scalars().all() == [1]
    assert any(item["id"] == 1 for item in repository.list_general_customer_shops())
    assert repository.list_general_customer_units()[0]["shop_is_active"] is False


def test_delete_shop_without_history_removes_shop_and_units(customer_repository):
    assert customer_repository.delete_general_customer_shop(2) is True
    assert customer_repository.get_general_customer_shop(2) is None
    assert customer_repository.get_general_customer_unit(2) is None
    assert customer_repository.delete_general_customer_shop(999) is False


@pytest.mark.parametrize("name", ["测试店铺", "测试单位"])
@pytest.mark.parametrize("document_type", ["批发销售单", "批发销售退货单", "应收款增加", "应收款减少"])
def test_disabled_shop_and_units_reject_new_customer_business(customer_repository, name, document_type):
    repository = customer_repository
    repository.set_general_customer_shop_status(1, is_active=False)
    payload = {"id": 1, "document_number": "NEW-001", "supplier": name, "document_type": document_type}
    with pytest.raises(ValueError, match="店铺已停用"):
        repository.create_record(payload)
    with repository.engine.connect() as connection:
        assert connection.execute(select(INVENTORY_TABLE.c.id)).all() == []
    repository.set_general_customer_shop_status(1, is_active=True)
    assert repository.create_record(payload)["supplier"] == name


def test_disabled_shop_keeps_existing_document_editable(customer_repository):
    seed_history(customer_repository)
    customer_repository.delete_general_customer_shop(1)
    record = customer_repository.update_record(1, {"summary": "补充历史备注", "supplier": "测试店铺"})
    assert record["summary"] == "补充历史备注"
    assert record["deleted_at"] is None


def test_cannot_switch_document_to_disabled_unit(customer_repository):
    seed_history(customer_repository, "空店铺")
    customer_repository.set_general_customer_shop_status(1, is_active=False)
    with pytest.raises(ValueError, match="店铺已停用"):
        customer_repository.update_record(1, {"supplier": "测试单位"})
    assert customer_repository.get_record(1)["supplier"] == "空店铺"


def test_brand_and_unit_deletion_cannot_bypass_history_protection(customer_repository):
    seed_history(customer_repository, "测试单位", deleted=True)
    with pytest.raises(ValueError, match="历史业务"):
        customer_repository.delete_general_customer_brand(1)
    with pytest.raises(ValueError, match="历史业务"):
        customer_repository.delete_general_customer_unit(1)
    assert customer_repository.get_general_customer_shop(1) is not None
    assert customer_repository.get_general_customer_unit(1) is not None


def test_disabled_shop_rejects_new_units(customer_repository):
    customer_repository.set_general_customer_shop_status(1, is_active=False)
    with pytest.raises(ValueError, match="店铺已停用"):
        customer_repository.create_general_customer_unit({"shop_id": 1, "unit_name": "新单位"})


def test_disabled_shop_preserves_its_name_and_unit_membership(customer_repository):
    customer_repository.set_general_customer_shop_status(1, is_active=False)
    with pytest.raises(ValueError, match="店铺已停用"):
        customer_repository.update_general_customer_shop(1, {"customer_name": "测试品牌", "shop_name": "改名"})
    with pytest.raises(ValueError, match="店铺已停用"):
        customer_repository.update_general_customer_unit(1, {"shop_id": 2, "unit_name": "转移单位"})
    with pytest.raises(ValueError, match="店铺已停用"):
        customer_repository.update_general_customer_unit(2, {"shop_id": 1, "unit_name": "转入单位"})
    assert customer_repository.get_general_customer_unit(1)["shop_id"] == 1


def test_disabled_shop_keeps_historical_receivable_ledger(customer_repository):
    seed_history(customer_repository, "测试单位")
    before = customer_repository.get_counterparty_ledger(counterparty_type="customer", name="测试单位")
    customer_repository.delete_general_customer_shop(1)
    after = customer_repository.get_counterparty_ledger(counterparty_type="customer", name="测试单位")
    assert before == after
    assert len(after["items"]) == 1
    assert after["ending_balance"] == "100"


def test_template_import_rejects_disabled_customer_before_writing(customer_repository):
    customer_repository.set_general_customer_shop_status(1, is_active=False)
    with pytest.raises(ValueError, match="店铺已停用"):
        customer_repository.import_template_documents([{
            "supplier": "测试单位", "document_type": "批发销售单", "details": [],
        }])
    with customer_repository.engine.connect() as connection:
        assert connection.execute(select(INVENTORY_TABLE.c.id)).all() == []


def test_shop_delete_api_reports_disabled_and_records_operation(customer_repository, monkeypatch):
    seed_history(customer_repository)
    log = Mock()
    monkeypatch.setattr(inventory_routes, "write_operation_log", log)
    request = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(inventory_repository=customer_repository)))
    result = inventory_routes.delete_general_customer_shop(request, 1)
    assert result["item"]["is_active"] is False
    assert "已停用" in result["message"]
    assert log.call_args.kwargs["action"] == "update"
    assert log.call_args.kwargs["after_data"]["is_active"] is False


def test_shop_status_api_validates_status_and_enables_shop(customer_repository, monkeypatch):
    monkeypatch.setattr(inventory_routes, "write_operation_log", Mock())
    request = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(inventory_repository=customer_repository)))
    with pytest.raises(HTTPException) as error:
        inventory_routes.set_general_customer_shop_status(request, 1, {"is_active": "false"})
    assert error.value.status_code == 400
    disabled = inventory_routes.set_general_customer_shop_status(request, 1, {"is_active": False})
    assert disabled["item"]["is_active"] is False
    enabled = inventory_routes.set_general_customer_shop_status(request, 1, {"is_active": True})
    assert enabled["item"]["is_active"] is True


def test_template_preview_excludes_disabled_shops_and_units():
    repository = Mock(spec=InventoryRepository)
    repository.list_general_customer_shops.return_value = [{"shop_name": "测试店铺", "is_active": False}]
    repository.list_general_customer_units.return_value = [{"unit_name": "测试单位", "shop_is_active": False}]
    documents = [SimpleNamespace(document_type="应收款增加", supplier="测试单位", warehouse="", rows=[])]
    with pytest.raises(HTTPException) as error:
        inventory_routes._validate_inventory_template_master_data(repository, documents)
    assert error.value.status_code == 400
    assert "测试单位" in error.value.detail
