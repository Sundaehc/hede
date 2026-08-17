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
