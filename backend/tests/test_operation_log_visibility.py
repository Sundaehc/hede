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
