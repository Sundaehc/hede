from __future__ import annotations

from collections.abc import Mapping

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.exc import IntegrityError

from api.routes.auth import router


class FakeAuthRepository:
    def __init__(self) -> None:
        self.users: dict[str, dict[str, object]] = {}
        self.sessions = {
            "admin-session": {
                "id": 1,
                "username": "admin",
                "display_name": "管理员",
                "department_code": "开发部",
                "department_name": "开发部",
                "role_code": "super_admin",
                "role_name": "超级管理员",
                "status": "active",
                "permissions": ["*"],
            },
            "member-session": {
                "id": 2,
                "username": "member",
                "display_name": "普通用户",
                "department_code": "商品部",
                "department_name": "商品部",
                "role_code": "product_user",
                "role_name": "商品组",
                "status": "active",
                "permissions": ["product.view"],
            },
        }

    def get_user_by_session(self, token: str | None) -> dict[str, object] | None:
        return self.sessions.get(token or "")

    def list_departments(self) -> list[dict[str, object]]:
        return [
            {"id": 1, "code": "开发部", "name": "开发部"},
            {"id": 2, "code": "商品部", "name": "商品部"},
        ]

    def list_roles(self) -> list[dict[str, object]]:
        return [
            {
                "id": 1,
                "code": "super_admin",
                "name": "超级管理员",
                "department_code": None,
                "permissions": ["*"],
            },
            {
                "id": 2,
                "code": "product_user",
                "name": "商品组",
                "department_code": "商品部",
                "permissions": ["product.view"],
            },
        ]

    def create_user(
        self,
        payload: Mapping[str, object],
        *,
        first_user_is_admin: bool = True,
    ) -> dict[str, object]:
        username = str(payload["username"])
        if username in self.users:
            raise IntegrityError("INSERT auth_users", payload, Exception("duplicate"))
        user = {
            "id": len(self.users) + 10,
            "username": username,
            "display_name": payload["display_name"],
            "department_code": payload["department_code"],
            "department_name": payload["department_code"],
            "role_code": payload["role_code"],
            "role_name": "商品组",
            "status": payload["status"],
            "permissions": ["product.view"],
        }
        self.users[username] = user
        return user


class FakeOperationLogRepository:
    def __init__(self) -> None:
        self.items: list[dict[str, object]] = []

    def create_log(self, **payload: object) -> dict[str, object]:
        self.items.append(payload)
        return payload


@pytest.fixture
def admin_user_client() -> tuple[TestClient, FakeAuthRepository, FakeOperationLogRepository]:
    app = FastAPI()
    app.include_router(router)
    auth_repository = FakeAuthRepository()
    operation_log_repository = FakeOperationLogRepository()
    app.state.auth_repository = auth_repository
    app.state.operation_log_repository = operation_log_repository
    client = TestClient(app)
    return client, auth_repository, operation_log_repository


def user_payload(username: str = "product-user") -> dict[str, str]:
    return {
        "username": username,
        "password": "product-password",
        "display_name": "商品用户",
        "department_code": "商品部",
        "role_code": "product_user",
        "status": "active",
    }


def test_super_admin_can_create_user_and_creation_is_logged(admin_user_client):
    client, _auth_repository, log_repository = admin_user_client
    client.cookies.set("hede_session", "admin-session")

    response = client.post("/auth/admin/users", json=user_payload())

    assert response.status_code == 201
    assert response.json()["item"]["username"] == "product-user"
    assert "password_hash" not in response.json()["item"]
    assert log_repository.items[0]["action"] == "create"
    assert log_repository.items[0]["entity_label"] == "product-user"
    assert log_repository.items[0]["after_data"]["password"] == "已设置"
    assert "product-password" not in str(log_repository.items[0])


def test_non_admin_cannot_create_user(admin_user_client):
    client, _auth_repository, _log_repository = admin_user_client
    client.cookies.set("hede_session", "member-session")

    response = client.post("/auth/admin/users", json=user_payload("blocked-user"))

    assert response.status_code == 403
    assert response.json()["detail"] == "权限不足"


def test_admin_create_user_rejects_duplicate_username(admin_user_client):
    client, _auth_repository, _log_repository = admin_user_client
    client.cookies.set("hede_session", "admin-session")

    assert client.post("/auth/admin/users", json=user_payload()).status_code == 201
    duplicate = client.post("/auth/admin/users", json=user_payload())

    assert duplicate.status_code == 409
    assert duplicate.json()["detail"] == "该账号已存在"
