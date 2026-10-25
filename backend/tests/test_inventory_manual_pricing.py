from datetime import date
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import Integer, MetaData, create_engine, event
from sqlalchemy.pool import StaticPool

from api.routes import inventory as inventory_routes
from domain.inventory_schema import INVENTORY_DETAIL_TABLE, INVENTORY_TABLE
from domain.product_archive_identity_schema import PRODUCT_ARCHIVE_IDENTITY_TABLE
from storage.inventory_repository import InventoryRepository


DOCUMENT_TYPES = (
    "进货订单", "进货单", "进货退货单", "报溢单", "报损单",
    "批发销售单", "批发销售退货单", "同价调拨单",
)
PRODUCT_CODE = "NAG2658015B01"


@pytest.fixture
def pricing_context(monkeypatch):
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    event.listen(engine, "connect", lambda connection, _record: connection.create_function(
        "date_trunc", 2, lambda _unit, value: value,
    ))
    metadata = MetaData()
    PRODUCT_ARCHIVE_IDENTITY_TABLE.to_metadata(metadata)
    for source_table in (INVENTORY_TABLE, INVENTORY_DETAIL_TABLE):
        table = source_table.to_metadata(metadata)
        table.c.id.type = Integer()
        table.create(engine)
    with engine.begin() as connection:
        connection.execute(INVENTORY_TABLE.insert(), [
            {"id": 1, "document_type": "进货单", "date_value": date(2026, 9, 27)},
            {"id": 2, "document_type": "进货订单", "date_value": date(2026, 8, 26)},
        ])
        connection.execute(INVENTORY_DETAIL_TABLE.insert(), [
            {
                "id": detail_id,
                "document_id": detail_id,
                "product_code": PRODUCT_CODE,
                "quantity": 3,
                "unit_price": 268,
                "amount": 804,
                "size_quantities": {"230": "3"},
            }
            for detail_id in (1, 2)
        ])
    repository = object.__new__(InventoryRepository)
    repository.engine = engine
    lookup = Mock(return_value={"product_code": PRODUCT_CODE, "unit_price": "250.6"})
    operation_log = Mock()
    monkeypatch.setattr(inventory_routes, "_purchase_import_brand_for_record", lambda *_args: "ns")
    monkeypatch.setattr(inventory_routes, "_build_purchase_detail_lookup", lookup)
    monkeypatch.setattr(inventory_routes, "write_operation_log", operation_log)
    app = FastAPI()
    app.state.inventory_repository = repository
    app.include_router(inventory_routes.router)
    try:
        with TestClient(app) as client:
            yield SimpleNamespace(client=client, repository=repository, lookup=lookup, operation_log=operation_log)
    finally:
        engine.dispose()


def _save_detail(context, operation, payload):
    if operation == "create":
        return context.client.post("/inventory/1/details", json=payload)
    return context.client.put("/inventory/1/details/1", json=payload)


@pytest.mark.parametrize("document_type", DOCUMENT_TYPES)
@pytest.mark.parametrize("quantity", ["0", "1.5"])
def test_manual_price_is_preserved_without_looking_up_defaults(document_type, quantity):
    payload = inventory_routes._apply_product_archive_cost(
        object(),
        {"document_type": document_type},
        {"product_code": PRODUCT_CODE, "quantity": quantity, "unit_price": "250.60", "amount": "804"},
    )

    assert payload["unit_price"] == "250.6"
    assert Decimal(payload["amount"]) == Decimal(quantity) * Decimal("250.6")


@pytest.mark.parametrize("document_type", DOCUMENT_TYPES)
@pytest.mark.parametrize("operation", ["create", "update"])
def test_manual_save_preserves_entered_price_and_recalculates_totals(pricing_context, document_type, operation):
    with pricing_context.repository.engine.begin() as connection:
        connection.execute(INVENTORY_TABLE.update().where(INVENTORY_TABLE.c.id == 1).values(document_type=document_type))

    response = _save_detail(pricing_context, operation, {
        "product_code": PRODUCT_CODE,
        "quantity": "3",
        "unit_price": "250.60",
        "amount": "804",
        "size_quantities": {"230": "3"},
    })

    assert response.status_code == 200
    assert len(response.json()["items"]) == 1
    saved_detail = pricing_context.repository.get_detail(response.json()["item"]["id"])
    assert saved_detail["unit_price"] == Decimal("250.6")
    assert saved_detail["amount"] == Decimal("751.8")
    assert saved_detail["size_quantities"] == {"230": "3"}
    record = pricing_context.repository.get_record(1)
    expected_amount = Decimal("1555.8") if operation == "create" else Decimal("751.8")
    expected_quantity = Decimal("6") if operation == "create" else Decimal("3")
    if document_type == "进货退货单":
        expected_amount = -expected_amount
        expected_quantity = -expected_quantity
    assert record["amount"] == expected_amount
    assert record["total_count"] == expected_quantity
    assert pricing_context.repository.get_detail(2)["unit_price"] == Decimal("268")
    pricing_context.lookup.assert_not_called()
    log = pricing_context.operation_log.call_args.kwargs
    assert log["action"] == f"detail_{operation}"
    if operation == "update":
        changes = {change["field"]: change for change in log["changed_fields"]}
        assert Decimal(changes["unit_price"]["after"]) == Decimal("250.6")
        assert Decimal(changes["amount"]["after"]) == Decimal("751.8")


@pytest.mark.parametrize("operation", ["create", "update"])
@pytest.mark.parametrize("has_history,expected_price", [(True, "268"), (False, "250.6")])
@pytest.mark.parametrize("price_fields", [{}, {"unit_price": None}, {"unit_price": ""}])
def test_blank_manual_price_still_uses_history_then_archive(pricing_context, operation, has_history, expected_price, price_fields):
    if not has_history:
        with pricing_context.repository.engine.begin() as connection:
            connection.execute(INVENTORY_DETAIL_TABLE.delete().where(INVENTORY_DETAIL_TABLE.c.id == 2))

    response = _save_detail(pricing_context, operation, {
        "product_code": PRODUCT_CODE,
        "quantity": "3",
        "amount": "1",
        "size_quantities": {"230": "3"},
        **price_fields,
    })

    assert response.status_code == 200
    saved_detail = pricing_context.repository.get_detail(response.json()["item"]["id"])
    assert saved_detail["unit_price"] == Decimal(expected_price)
    assert saved_detail["amount"] == Decimal(expected_price) * 3


@pytest.mark.parametrize("operation", ["create", "update"])
@pytest.mark.parametrize("manual_price", ["180.5", ""])
@pytest.mark.parametrize("has_history", [True, False])
def test_ni_gender_defaults_do_not_override_manual_price(pricing_context, operation, manual_price, has_history):
    with pricing_context.repository.engine.begin() as connection:
        if has_history:
            connection.execute(INVENTORY_DETAIL_TABLE.update().where(INVENTORY_DETAIL_TABLE.c.id == 2).values(product_code="NIA2253A020115"))
        else:
            connection.execute(INVENTORY_DETAIL_TABLE.delete().where(INVENTORY_DETAIL_TABLE.c.id == 2))
    pricing_context.lookup.return_value = {
        "product_code": "NIA2253A020115",
        "unit_price": "178",
        "gender_costs": {"女": "178", "男": "190"},
    }

    response = _save_detail(pricing_context, operation, {
        "product_code": "NIA2253A020115",
        "quantity": "3",
        "unit_price": manual_price,
        "amount": "1",
        "size_quantities": {"36": "2", "42": "1"},
    })

    assert response.status_code == 200
    saved_details = [pricing_context.repository.get_detail(item["id"]) for item in response.json()["items"]]
    if manual_price:
        assert len(saved_details) == 1
        assert saved_details[0]["unit_price"] == Decimal("180.5")
        assert saved_details[0]["amount"] == Decimal("541.5")
        assert saved_details[0]["size_quantities"] == {"36": "2", "42": "1"}
        pricing_context.lookup.assert_not_called()
    elif has_history:
        assert len(saved_details) == 1
        assert saved_details[0]["unit_price"] == Decimal("268")
        assert saved_details[0]["amount"] == Decimal("804")
        assert saved_details[0]["size_quantities"] == {"36": "2", "42": "1"}
    else:
        assert [(item["unit_price"], item["amount"], item["size_quantities"]) for item in saved_details] == [
            (Decimal("178"), Decimal("356"), {"36": "2"}),
            (Decimal("190"), Decimal("190"), {"42": "1"}),
        ]


@pytest.mark.parametrize("operation", ["create", "update"])
@pytest.mark.parametrize("document_type", ["批发销售单", "批发销售退货单"])
@pytest.mark.parametrize("allows_zero_price", [True, False])
def test_manual_save_keeps_existing_zero_price_customer_policy(pricing_context, operation, document_type, allows_zero_price):
    with pricing_context.repository.engine.begin() as connection:
        connection.execute(INVENTORY_TABLE.update().where(INVENTORY_TABLE.c.id == 1).values(document_type=document_type))
    pricing_context.repository.allows_zero_price_sales_customer = lambda _name: allows_zero_price

    response = _save_detail(pricing_context, operation, {
        "product_code": PRODUCT_CODE,
        "quantity": "3",
        "unit_price": "0.00",
        "amount": "804",
        "size_quantities": {"230": "3"},
    })

    assert response.status_code == 200
    saved_detail = pricing_context.repository.get_detail(response.json()["item"]["id"])
    expected_price = Decimal("0") if allows_zero_price else Decimal("250.6")
    assert saved_detail["unit_price"] == expected_price
    assert saved_detail["amount"] == expected_price * 3
