from storage.auth_repository import DEFAULT_ROLE_BY_DEPARTMENT, DEFAULT_ROLES, DEPARTMENTS


def test_customer_service_department_has_product_view_only_role():
    assert {item["code"] for item in DEPARTMENTS} >= {"客服部"}
    assert DEFAULT_ROLE_BY_DEPARTMENT["客服部"] == "customer_service_viewer"

    role = next(item for item in DEFAULT_ROLES if item["code"] == "customer_service_viewer")
    assert role["department_code"] == "客服部"
    assert role["permissions"] == "product.view"


def test_operations_role_has_all_purchase_order_permissions():
    role = next(item for item in DEFAULT_ROLES if item["code"] == "operation_user")
    permissions = set(role["permissions"].split(","))

    assert {
        "purchase.view",
        "purchase.manage",
        "purchase.import",
        "purchase.export",
    } <= permissions


def test_product_role_can_create_suppliers_without_inventory_management():
    role = next(item for item in DEFAULT_ROLES if item["code"] == "product_user")
    permissions = set(role["permissions"].split(","))

    assert "supplier.create" in permissions
    assert "inventory.manage" not in permissions


def test_supplier_management_is_available_to_designated_departments_and_super_admin():
    roles = {item["code"]: set(item["permissions"].split(",")) for item in DEFAULT_ROLES}

    assert "*" in roles["super_admin"]
    assert "inventory.view" in roles["finance_user"]
    assert "inventory.view" in roles["product_user"]
    assert "supplier.create" in roles["product_user"]
    assert "inventory.view" in roles["developer_user"]
