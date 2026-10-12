from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select

from api.routes.auth import router
from domain.auth_schema import AUTH_USER_TABLE, METADATA
from storage.auth_repository import AuthRepository


@pytest.fixture
def tab_repository():
    repository = AuthRepository("sqlite://")
    METADATA.create_all(repository.engine)
    repository.seed_defaults()
    for user_id in (1, 2):
        repository.create_user({
            "username": f"tabs-{user_id}", "password": "test-password", "display_name": f"User {user_id}",
            "department_code": "开发部", "role_code": "super_admin", "status": "active",
        }, first_user_is_admin=False)
    yield repository
    repository.engine.dispose()


def test_fixed_tabs_are_isolated_by_account_and_duplicate_pins_are_idempotent(tab_repository):
    assert tab_repository.list_pinned_page_tabs(1) == []
    assert tab_repository.pin_page_tab(1, "/products") == ["/products"]
    assert tab_repository.pin_page_tab(1, "/products") == ["/products"]
    assert tab_repository.pin_page_tab(2, "/inventory") == ["/inventory"]
    assert tab_repository.list_pinned_page_tabs(1) == ["/products"]
    assert tab_repository.unpin_page_tab(2, "/products") == ["/inventory"]
    assert tab_repository.list_pinned_page_tabs(1) == ["/products"]
    assert tab_repository.unpin_page_tab(1, "/products") == []
    assert tab_repository.unpin_page_tab(1, "/products") == []


def test_updating_one_fixed_tab_preserves_others_and_does_not_change_account_data(tab_repository):
    with tab_repository.engine.connect() as connection:
        before = dict(connection.execute(select(AUTH_USER_TABLE).where(AUTH_USER_TABLE.c.id == 1)).mappings().one())
    tab_repository.pin_page_tab(1, "/products")
    tab_repository.pin_page_tab(1, "/inventory")
    assert set(tab_repository.unpin_page_tab(1, "/products")) == {"/inventory"}
    with tab_repository.engine.connect() as connection:
        after = dict(connection.execute(select(AUTH_USER_TABLE).where(AUTH_USER_TABLE.c.id == 1)).mappings().one())
    assert after == before


def test_fixed_tab_table_can_be_added_to_existing_accounts_without_rewriting_them():
    from domain.auth_schema import AUTH_DEPARTMENT_TABLE, AUTH_PINNED_PAGE_TAB_TABLE, AUTH_ROLE_TABLE, AUTH_SESSION_TABLE

    engine = create_engine("sqlite://")
    try:
        METADATA.create_all(engine, tables=[AUTH_DEPARTMENT_TABLE, AUTH_ROLE_TABLE, AUTH_USER_TABLE, AUTH_SESSION_TABLE])
        AUTH_PINNED_PAGE_TAB_TABLE.create(engine, checkfirst=True)
        AUTH_PINNED_PAGE_TAB_TABLE.create(engine, checkfirst=True)
        with engine.connect() as connection:
            assert list(connection.execute(select(AUTH_PINNED_PAGE_TAB_TABLE)).mappings()) == []
    finally:
        engine.dispose()


class TabRepository:
    def __init__(self):
        self.pins = {1: [], 2: ["/inventory"]}

    def get_user_by_session(self, token):
        return {"id": 1, "permissions": []} if token == "valid-session" else None

    def list_pinned_page_tabs(self, user_id):
        return self.pins[user_id]

    def pin_page_tab(self, user_id, page_path):
        if page_path not in self.pins[user_id]:
            self.pins[user_id].append(page_path)
        return self.pins[user_id]

    def unpin_page_tab(self, user_id, page_path):
        self.pins[user_id] = [path for path in self.pins[user_id] if path != page_path]
        return self.pins[user_id]


@pytest.fixture
def tab_client():
    app = FastAPI()
    app.include_router(router)
    app.state.auth_repository = TabRepository()
    with TestClient(app) as client:
        yield client, app.state.auth_repository


@pytest.mark.parametrize("method", ["GET", "PUT", "DELETE"])
def test_fixed_tab_endpoints_require_login(tab_client, method):
    client, _repository = tab_client
    response = client.request(method, "/auth/me/page-tabs", **({} if method == "GET" else {"json": {"page_path": "/products"}}))
    assert response.status_code == 401


def test_fixed_tab_api_only_mutates_the_logged_in_account(tab_client):
    client, repository = tab_client
    client.cookies.set("hede_session", "valid-session")
    assert client.get("/auth/me/page-tabs").json() == {"pinned_paths": []}
    assert client.put("/auth/me/page-tabs", json={"page_path": "/products"}).json() == {"pinned_paths": ["/products"]}
    assert client.request("DELETE", "/auth/me/page-tabs", json={"page_path": "/products"}).json() == {"pinned_paths": []}
    assert repository.pins[2] == ["/inventory"]


@pytest.mark.parametrize("page_path", ["https://example.com", "//example.com", "/login", "/products?sku=secret", "/unknown"])
def test_fixed_tab_api_rejects_unknown_or_external_pages(tab_client, page_path):
    client, repository = tab_client
    client.cookies.set("hede_session", "valid-session")
    assert client.put("/auth/me/page-tabs", json={"page_path": page_path}).status_code == 422
    assert repository.pins[1] == []


def test_fixed_tab_api_rejects_user_id_in_payload(tab_client):
    client, repository = tab_client
    client.cookies.set("hede_session", "valid-session")
    assert client.put("/auth/me/page-tabs", json={"page_path": "/products", "user_id": 2}).status_code == 422
    assert repository.pins == {1: [], 2: ["/inventory"]}
