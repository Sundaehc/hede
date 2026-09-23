from datetime import datetime, timedelta, timezone
import hashlib
from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest
from sqlalchemy import create_engine, event, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.pool import StaticPool

from api.routes import mcp_tokens
from readonly_mcp.admin import issue_token


BASE = "/auth/admin/mcp-tokens"
HEADERS = {"X-Mcp-Admin": "1", "Origin": "https://platform.example.test"}


@pytest.fixture
def token_client():
    engine = create_engine("sqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False})

    @event.listens_for(engine, "connect")
    def attach_schemas(connection, record):
        connection.execute("ATTACH DATABASE ':memory:' AS public")
        connection.execute("ATTACH DATABASE ':memory:' AS mcp_private")

    with engine.begin() as connection:
        connection.exec_driver_sql("CREATE TABLE public.auth_roles(code TEXT PRIMARY KEY,permissions TEXT)")
        connection.exec_driver_sql("CREATE TABLE public.auth_users(id INTEGER PRIMARY KEY,username TEXT,display_name TEXT,status TEXT,department_code TEXT,role_code TEXT)")
        connection.exec_driver_sql("CREATE TABLE mcp_private.tokens(id INTEGER PRIMARY KEY,user_id INTEGER,token_hash TEXT UNIQUE,label TEXT,profile TEXT,expires_at TIMESTAMP,revoked_at TIMESTAMP,created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)")
        connection.exec_driver_sql("CREATE TABLE operation_logs(id INTEGER PRIMARY KEY,module TEXT,action TEXT,entity_type TEXT,entity_id TEXT,entity_label TEXT,summary TEXT,changed_fields JSON,before_data JSON,after_data JSON,user_id BIGINT,username TEXT,display_name TEXT,department_name TEXT,role_code TEXT,created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)")
        connection.execute(text("INSERT INTO public.auth_roles VALUES(:code,:permissions)"), [
            {"code": "super_admin", "permissions": "*"}, {"code": "staff", "permissions": "product.view"},
            {"code": "none", "permissions": "inventory.view"},
        ])
        connection.execute(text("INSERT INTO public.auth_users VALUES(:id,:username,:display_name,:status,:department_code,:role_code)"), [
            {"id": 1, "username": "admin", "display_name": "管理员", "status": "active", "department_code": "开发部", "role_code": "super_admin"},
            {"id": 2, "username": "designer", "display_name": "美工甲", "status": "active", "department_code": "美工部", "role_code": "staff"},
            {"id": 3, "username": "finance", "display_name": "财务甲", "status": "active", "department_code": "财务部", "role_code": "staff"},
            {"id": 4, "username": "disabled", "display_name": "停用", "status": "disabled", "department_code": "美工部", "role_code": "staff"},
            {"id": 5, "username": "no-permission", "display_name": "无权限", "status": "active", "department_code": "美工部", "role_code": "none"},
        ])
    actor = {"id": 1, "username": "admin", "display_name": "管理员", "status": "active", "role_code": "super_admin", "permissions": ["*"]}
    repository = SimpleNamespace(engine=engine, actor=actor)
    repository.get_user_by_session = lambda session: repository.actor if session == "test-session" else None
    app = FastAPI()
    app.state.auth_repository = repository
    app.state.settings = SimpleNamespace(frontend_origins=("https://platform.example.test",))
    app.include_router(mcp_tokens.router)
    with TestClient(app) as client:
        client.cookies.set("hede_session", "test-session")
        yield SimpleNamespace(client=client, engine=engine, repository=repository)
    engine.dispose()


def issue(service, **changes):
    return service.client.post(BASE, headers=HEADERS, json={"user_id": 2, "profile": "design", "days": 30, "label": "测试办公电脑", **changes})


def test_issue_saves_only_hash_and_atomic_audit(token_client):
    response = issue(token_client)
    assert response.status_code == 201
    assert response.headers["cache-control"] == "no-store"
    payload = response.json()
    token = payload["token"]
    assert token.startswith("hmcp_") and len(token) > 40
    with token_client.engine.connect() as connection:
        saved = connection.execute(text("SELECT * FROM mcp_private.tokens")).mappings().one()
        logs = connection.execute(text("SELECT * FROM operation_logs")).mappings().all()
    assert saved["token_hash"] == hashlib.sha256(token.encode()).hexdigest()
    assert len(logs) == 1 and logs[0]["action"] == "mcp_token_issue"
    assert token not in str(saved) + str(logs)
    assert saved["token_hash"] not in str(logs)
    listed = token_client.client.get(BASE)
    assert listed.headers["cache-control"] == "no-store"
    assert token not in listed.text and "token_hash" not in listed.text and "password" not in listed.text
    assert listed.json()["items"][0]["state"] == "active"


@pytest.mark.parametrize("role,permissions,status,expected", [
    ("staff", ["product.view"], "active", 403),
    ("staff", ["system.admin"], "active", 403),
    ("super_admin", ["*"], "disabled", 403),
    ("super_admin", [], "active", 403),
])
def test_all_routes_require_active_super_admin(token_client, role, permissions, status, expected):
    token_client.repository.actor.update(role_code=role, permissions=permissions, status=status)
    for path in (BASE, BASE + "/users"):
        assert token_client.client.get(path).status_code == expected
    assert issue(token_client).status_code == expected
    assert token_client.client.post(BASE + "/1/revoke", json={}, headers=HEADERS).status_code == expected


def test_no_session_fails_even_without_global_auth_middleware(token_client):
    token_client.client.cookies.clear()
    assert token_client.client.get(BASE).status_code == 401
    assert issue(token_client).status_code == 401


@pytest.mark.parametrize("headers", [
    {}, {"X-Mcp-Admin": "1", "Origin": "https://evil.example"},
    {"X-Mcp-Admin": "1", "Origin": "null"},
    {**HEADERS, "Sec-Fetch-Site": "cross-site"},
])
def test_cross_site_mutations_rejected(token_client, headers):
    response = token_client.client.post(BASE, headers=headers, json={"user_id": 2, "label": "no", "days": 30})
    assert response.status_code == 403
    assert token_client.client.post(BASE + "/1/revoke", headers=headers, json={}).status_code == 403


@pytest.mark.parametrize("changes", [{"days": 0}, {"days": 91}, {"days": True}, {"days": 1.5}, {"label": " "}, {"label": "x" * 101}, {"profile": "admin"}, {"user_id": 0}, {"user_id": True}, {"token": "supplied-secret"}])
def test_invalid_payload_rejected(token_client, changes):
    assert issue(token_client, **changes).status_code == 422


@pytest.mark.parametrize("changes", [{"user_id": 3}, {"user_id": 4}, {"user_id": 5}, {"user_id": 999}])
def test_eligibility_is_rechecked_at_issue_time(token_client, changes):
    assert issue(token_client, **changes).status_code == 400
    assert token_client.client.get(BASE).json()["total"] == 0


def test_candidate_search_only_lists_eligible_users_and_profiles(token_client):
    response = token_client.client.get(BASE + "/users").json()
    assert response["total"] == 3
    assert {item["id"] for item in response["items"]} == {1, 2, 3}
    assert next(item for item in response["items"] if item["id"] == 3)["profiles"] == ["products"]
    assert token_client.client.get(BASE + "/users", params={"query": "美工"}).json()["total"] == 1
    assert token_client.client.get(BASE + "/users", params={"query": "%"}).json()["total"] == 0
    assert token_client.client.get(BASE + "/users", params={"query": "' OR 1=1--"}).json()["total"] == 0
    assert token_client.client.get(BASE + "/users", params={"page": 2}).json()["items"] == []


def test_revoke_is_idempotent_and_logged_without_secrets(token_client):
    payload = issue(token_client).json()
    path = BASE + f"/{payload['item']['id']}/revoke"
    assert token_client.client.post(path, headers=HEADERS, json={}).json()["changed"] is True
    assert token_client.client.post(path, headers=HEADERS, json={}).json()["changed"] is False
    assert token_client.client.get(BASE).json()["items"][0]["state"] == "revoked"
    assert token_client.client.post(BASE + "/999/revoke", headers=HEADERS, json={}).status_code == 404
    with token_client.engine.connect() as connection:
        assert connection.scalar(text("SELECT count(*) FROM operation_logs WHERE action='mcp_token_revoke'")) == 1


def test_expiry_and_current_permissions_are_reflected(token_client):
    item_id = issue(token_client).json()["item"]["id"]
    with token_client.engine.begin() as connection:
        connection.execute(text("UPDATE public.auth_users SET department_code='财务部' WHERE id=2"))
    assert token_client.client.get(BASE).json()["items"][0]["state"] == "blocked"
    with token_client.engine.begin() as connection:
        connection.execute(text("UPDATE mcp_private.tokens SET expires_at=:expires WHERE id=:id"), {"expires": datetime.now(timezone.utc) - timedelta(days=1), "id": item_id})
    assert token_client.client.get(BASE).json()["items"][0]["state"] == "expired"


def test_permanent_credentials_store_null_and_keep_current_account_checks(token_client):
    response = issue(token_client, days=None)
    assert response.status_code == 201
    item = response.json()["item"]
    assert item["expires_at"] is None
    with token_client.engine.connect() as connection:
        saved = connection.execute(text("SELECT expires_at FROM mcp_private.tokens WHERE id=:id"), {"id": item["id"]}).scalar_one()
    assert saved is None
    assert token_client.client.get(BASE).json()["items"][0]["state"] == "active"
    with token_client.engine.begin() as connection:
        connection.execute(text("UPDATE public.auth_users SET status='disabled' WHERE id=2"))
    assert token_client.client.get(BASE).json()["items"][0]["state"] == "blocked"


@pytest.mark.parametrize("days", [None, 30])
def test_cli_issue_accepts_permanent_or_finite_expiry(token_client, days):
    token, token_id = issue_token(token_client.engine, "finance", "products", days, "CLI credential")
    assert token.startswith("hmcp_")
    with token_client.engine.connect() as connection:
        expires_at = connection.scalar(text("SELECT expires_at FROM mcp_private.tokens WHERE id=:id"), {"id": token_id})
    assert (expires_at is None) is (days is None)


def test_audit_failure_rolls_back_issue_and_revoke(token_client, monkeypatch):
    original_id = issue(token_client).json()["item"]["id"]
    def fail(*args):
        raise SQLAlchemyError("private database password must not be returned")
    monkeypatch.setattr(mcp_tokens, "audit_change", fail)
    response = issue(token_client)
    assert response.status_code == 503 and "password" not in response.text
    response = token_client.client.post(BASE + f"/{original_id}/revoke", headers=HEADERS, json={})
    assert response.status_code == 503
    listed = token_client.client.get(BASE).json()
    assert listed["total"] == 1 and listed["items"][0]["state"] == "active"


def test_missing_schema_returns_safe_unavailable_error(token_client):
    with token_client.engine.begin() as connection:
        connection.exec_driver_sql("DROP TABLE mcp_private.tokens")
    response = token_client.client.get(BASE)
    assert response.status_code == 503 and "SELECT" not in response.text


def test_cli_and_page_share_the_same_storage(token_client):
    token, token_id = issue_token(token_client.engine, "finance", "products", 30, "CLI credential")
    listed = token_client.client.get(BASE).json()
    assert listed["items"][0]["id"] == token_id
    assert listed["items"][0]["username"] == "finance"
    assert token not in str(listed)
