import pytest

from api.auth_middleware import required_permission_for_request


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
