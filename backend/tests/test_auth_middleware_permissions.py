from unittest.mock import Mock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api import auth_middleware
from api.auth_middleware import required_permission_for_request
from api.routes.inventory import router as inventory_router


def test_supplier_mutations_accept_dedicated_or_inventory_management_permissions():
    assert required_permission_for_request("POST", "/suppliers") == (
        "supplier.create",
        "inventory.manage",
    )
    assert required_permission_for_request("PUT", "/suppliers/12") == (
        "supplier.manage",
        "inventory.manage",
    )
    assert required_permission_for_request("DELETE", "/suppliers/12") == (
        "supplier.manage",
        "inventory.manage",
    )


def test_product_import_template_requires_product_import_permission():
    assert required_permission_for_request("GET", "/import/template") == "product.import"


@pytest.mark.parametrize("method", ["GET", "HEAD"])
def test_product_price_export_accepts_dedicated_or_full_export_permission(method):
    assert required_permission_for_request(method, "/export", export_mode="price") == (
        "product.export",
        "product.price_export",
    )


@pytest.mark.parametrize("mode", [None, "", "with_sizes", "unknown", "PRICE", "price "])
@pytest.mark.parametrize("method", ["GET", "HEAD"])
def test_other_product_export_modes_still_require_full_export_permission(method, mode):
    assert required_permission_for_request(method, "/export", export_mode=mode) == "product.export"


@pytest.mark.parametrize("method", ["POST", "PUT", "PATCH", "DELETE"])
def test_price_mode_does_not_grant_product_export_mutations(method):
    assert required_permission_for_request(method, "/export", export_mode="price") == "product.export"


@pytest.mark.parametrize("method", ["POST", "GET"])
def test_inventory_import_task_endpoints_require_import_management_permissions(method):
    assert required_permission_for_request(method, "/inventory/import-template/tasks/" + "a" * 32) == (
        "inventory.manage", "purchase.import", "purchase.manage",
    )


def test_inventory_selection_and_deletion_require_management_permission():
    for path in ("/inventory/selection-ids", "/inventory/batch-delete"):
        assert required_permission_for_request("POST", path) == ("inventory.manage", "purchase.manage")


def test_inventory_history_readonly_preserves_purchase_management(monkeypatch):
    app = FastAPI()
    app.middleware("http")(auth_middleware.auth_middleware)
    app.include_router(inventory_router)
    app.state.auth_repository = Mock(has_users=Mock(return_value=True))
    permissions = ["inventory.view", "inventory.export", "purchase.manage", "purchase.import", "inventory.history_readonly"]
    monkeypatch.setattr(auth_middleware, "get_current_user_from_request", lambda _: {"permissions": permissions})
    repository = app.state.inventory_repository = Mock()
    history_record = {"id": 1, "document_type": "批发销售单"}
    purchase_record = {"id": 2, "document_type": "进货订单"}
    repository.get_record.side_effect = {1: history_record, 2: purchase_record}.get
    repository.get_records_by_ids.return_value = [history_record, purchase_record]
    repository.list_records.return_value = {"items": [history_record]}
    repository.list_details_for_documents.return_value = []
    repository.update_record.return_value = purchase_record
    client = TestClient(app)

    assert client.get("/inventory/1").status_code == 200
    export = client.get("/inventory/export")
    assert export.status_code == 200
    assert export.content.startswith(b"PK")
    assert client.post("/inventory", json={"document_type": "批发销售单"}).status_code == 403
    assert client.put("/inventory/1", json={"document_type": "进货订单"}).status_code == 403
    assert client.put("/inventory/2", json={"document_type": "批发销售单"}).status_code == 403
    assert client.post("/inventory/1/details", json={}).status_code == 403
    assert client.post("/inventory/batch-delete", json={"ids": [1, 2]}).status_code == 403
    assert client.post("/inventory/import-template/preview").status_code == 403
    assert client.post("/inventory/batch-update-costs", json={}).status_code == 403
    repository.update_record.assert_not_called()
    repository.delete_records.assert_not_called()
    assert client.put("/inventory/2", json={"summary": "采购单更新"}).status_code == 200
