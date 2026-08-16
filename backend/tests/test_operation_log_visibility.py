from __future__ import annotations

from fastapi.testclient import TestClient


def _login(client: TestClient, username: str, password: str) -> None:
    response = client.post("/auth/login", json={"username": username, "password": password})
    assert response.status_code == 200


def test_non_admin_cannot_view_super_admin_operation_logs(test_app_client: TestClient):
    auth_repository = test_app_client.app.state.auth_repository
    admin = auth_repository.create_user(
        {
            "username": "admin",
            "password": "admin-password",
            "display_name": "Admin",
            "department_code": "开发部",
        },
        first_user_is_admin=True,
    )
    member = auth_repository.create_user(
        {
            "username": "member",
            "password": "member-password",
            "display_name": "Member",
            "department_code": "商品部",
        }
    )
    log_repository = test_app_client.app.state.operation_log_repository
    log_repository.create_log(
        module="product",
        action="update",
        entity_type="product",
        summary="admin change",
        user=admin,
    )
    log_repository.create_log(
        module="product",
        action="update",
        entity_type="product",
        summary="member change",
        user=member,
    )

    _login(test_app_client, "member", "member-password")
    member_response = test_app_client.get("/operation-logs", params={"module": "product"})
    assert member_response.status_code == 200
    assert [item["summary"] for item in member_response.json()["items"]] == ["member change"]

    _login(test_app_client, "admin", "admin-password")
    admin_response = test_app_client.get("/operation-logs", params={"module": "product"})
    assert admin_response.status_code == 200
    assert {item["summary"] for item in admin_response.json()["items"]} == {"admin change", "member change"}


def test_super_admin_product_goods_export_is_written_to_operation_logs(
    test_app_client: TestClient,
):
    auth_repository = test_app_client.app.state.auth_repository
    auth_repository.create_user(
        {
            "username": "admin",
            "password": "admin-password",
            "display_name": "Admin",
            "department_code": "开发部",
        },
        first_user_is_admin=True,
    )

    _login(test_app_client, "admin", "admin-password")
    export_response = test_app_client.post(
        "/product-goods/export-log",
        json={
            "brand": "cbanner_mens",
            "brand_label": "千百度男鞋",
            "exported_rows": 25,
            "total_rows": 86,
            "view": "goods",
            "query": "QA123",
            "filters": 2,
            "history_date": "2026-07-29",
            "column_count": 34,
            "filename": "千百度男鞋_商品货品表.csv",
        },
    )

    assert export_response.status_code == 200

    logs_response = test_app_client.get(
        "/operation-logs", params={"module": "product_goods"}
    )
    assert logs_response.status_code == 200
    assert logs_response.json()["total"] == 1
    log = logs_response.json()["items"][0]
    assert log["action"] == "export"
    assert log["entity_type"] == "product_goods"
    assert log["entity_id"] == "cbanner_mens"
    assert log["role_code"] == "super_admin"
    assert log["username"] == "admin"
    assert log["after_data"] == {
        "brand": "cbanner_mens",
        "brand_label": "千百度男鞋",
        "exported_rows": 25,
        "total_rows": 86,
        "view": "goods",
        "query": "QA123",
        "filters": 2,
        "history_date": "2026-07-29",
        "column_count": 34,
        "filename": "千百度男鞋_商品货品表.csv",
    }


def test_legacy_supplier_brand_logs_are_migrated(test_app_client: TestClient):
    repository = test_app_client.app.state.operation_log_repository
    repository.create_log(
        module="supplier",
        action="create_brand",
        entity_type="supplier_brand",
        summary="新增品牌 历史品牌",
    )

    repository.create_tables()

    brand_logs = repository.list_logs(
        module="supplier_brand",
        query=None,
        page=1,
        page_size=20,
    )
    supplier_logs = repository.list_logs(
        module="supplier",
        query=None,
        page=1,
        page_size=20,
    )
    assert brand_logs["total"] == 1
    assert supplier_logs["total"] == 0
