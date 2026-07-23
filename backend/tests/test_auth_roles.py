from storage.auth_repository import DEFAULT_ROLE_BY_DEPARTMENT, DEFAULT_ROLES, DEPARTMENTS


def test_customer_service_department_has_product_view_only_role():
    assert {item["code"] for item in DEPARTMENTS} >= {"客服部"}
    assert DEFAULT_ROLE_BY_DEPARTMENT["客服部"] == "customer_service_viewer"

    role = next(item for item in DEFAULT_ROLES if item["code"] == "customer_service_viewer")
    assert role["department_code"] == "客服部"
    assert role["permissions"] == "product.view"
