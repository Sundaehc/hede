from types import SimpleNamespace
from unittest.mock import Mock

from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest

from api.operation_log_utils import localize_mcp_token_log_item
from api.routes import operation_logs


@pytest.mark.parametrize("profile,label", [
    ("products", "商品档案（历史凭证）"),
    ("design", "商品档案 + 美工文案"),
    ("finance", "财务部数据"),
    ("merchandise", "商品部数据"),
    ("operation", "运营部数据"),
    ("development", "开发部数据"),
    ("customer_service", "客服部数据"),
])
@pytest.mark.parametrize("action,verb,suffix", [
    ("mcp_token_issue", "签发", "，永久有效"),
    ("mcp_token_issue", "签发", "，到期时间 2026-11-20 08:00:00+00:00"),
    ("mcp_token_revoke", "撤销", ""),
])
def test_legacy_mcp_log_scopes_are_localized(profile, label, action, verb, suffix):
    summary = f"{verb}MCP凭证 #9，用户ID 26，范围 {profile}{suffix}"
    item = {
        "module": "user", "entity_type": "mcp_token", "action": action,
        "summary": summary, "entity_label": "merchandise 办公电脑",
    }
    result = localize_mcp_token_log_item(item)
    assert result == {**item, "summary": f"{verb}MCP凭证 #9，用户ID 26，范围 {label}{suffix}"}
    assert item["summary"] == summary
    assert localize_mcp_token_log_item(result) == result


@pytest.mark.parametrize("changes", [
    {"module": "product"},
    {"entity_type": "user"},
    {"action": "update"},
    {"summary": "签发MCP凭证 #9，用户ID 26，范围 unknown，永久有效"},
    {"summary": "签发MCP凭证 #9，用户ID 26，范围 merchandise_extra，永久有效"},
    {"summary": "备注 merchandise"},
    {"summary": None},
])
def test_other_log_content_is_unchanged(changes):
    item = {
        "module": "user", "entity_type": "mcp_token", "action": "mcp_token_issue",
        "summary": "签发MCP凭证 #9，用户ID 26，范围 merchandise，永久有效",
        **changes,
    }
    assert localize_mcp_token_log_item(item) == item


def test_operation_log_endpoint_localizes_history_without_updating_stored_log():
    item = {
        "id": 9, "module": "user", "entity_type": "mcp_token", "action": "mcp_token_issue",
        "summary": "签发MCP凭证 #9，用户ID 26，范围 merchandise，永久有效",
    }
    user_item = {**item, "entity_type": "user", "action": "update"}
    repository = SimpleNamespace(list_logs=Mock(return_value={
        "items": [item, user_item], "total": 2, "page": 1, "page_size": 20,
    }))
    app = FastAPI()
    app.state.auth_repository = SimpleNamespace(get_user_by_session=lambda session: {
        "id": 1, "role_code": "super_admin", "permissions": ["*"],
    })
    app.state.operation_log_repository = repository
    app.include_router(operation_logs.router)
    with TestClient(app) as client:
        response = client.get("/operation-logs", params={"module": "user"})
    assert response.status_code == 200
    payload = response.json()
    assert payload == {
        "items": [{**item, "summary": "签发MCP凭证 #9，用户ID 26，范围 商品部数据，永久有效"}, user_item],
        "total": 2, "page": 1, "page_size": 20,
    }
    assert item["summary"] == "签发MCP凭证 #9，用户ID 26，范围 merchandise，永久有效"
    repository.list_logs.assert_called_once_with(
        module="user", query=None, page=1, page_size=20, exclude_super_admin_logs=False,
    )
