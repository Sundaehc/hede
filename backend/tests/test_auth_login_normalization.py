from __future__ import annotations

from datetime import datetime, timezone

from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.routes.auth import router


class _AuthRepository:
    def __init__(self) -> None:
        self.credentials: tuple[str, str] | None = None

    def authenticate(self, username: str, password: str):
        self.credentials = (username, password)
        return {
            "id": 1,
            "username": username,
            "status": "active",
            "permissions": [],
        }

    def create_session(self, user_id: int, **_kwargs):
        return "session-token", datetime.now(timezone.utc)


def test_login_trims_username_and_password() -> None:
    app = FastAPI()
    app.include_router(router)
    repository = _AuthRepository()
    app.state.auth_repository = repository
    client = TestClient(app)

    response = client.post(
        "/auth/login",
        json={
            "username": " 15858703012 ",
            "password": " password with inner spaces ",
        },
    )

    assert response.status_code == 200
    assert repository.credentials == (
        "15858703012",
        "password with inner spaces",
    )
