import asyncio
from types import SimpleNamespace

import httpx2
from mcp.client import Client
from mcp.client.streamable_http import streamable_http_client
import pytest
from starlette.testclient import TestClient

from readonly_mcp.server import create_app


class FakeControl:
    def __init__(self):
        self.identities = {"hmcp_test-products": {"token_id": 1, "user_id": 1, "profile": "products"}, "hmcp_test-design": {"token_id": 2, "user_id": 2, "profile": "design"}}
        self.events = []
        self.audit_failed = False

    def authenticate(self, token):
        return self.identities.get(token)

    def audit(self, *args):
        if self.audit_failed:
            raise RuntimeError("private audit error")
        self.events.append(args)

    def close(self):
        pass


class FakeExecutor:
    def __init__(self):
        self.queries = []

    def verify_roles(self, control):
        pass

    def execute(self, profile, query):
        self.queries.append((profile, query))
        return {"columns": ["sku"], "rows": [["TEST"]], "row_count": 1, "truncated": False}

    def close(self):
        pass


@pytest.fixture
def service():
    settings = SimpleNamespace(allowed_hosts=("testserver",), allowed_origins=())
    control, executor = FakeControl(), FakeExecutor()
    app = create_app(settings, control=control, executor=executor)
    with TestClient(app) as client:
        yield SimpleNamespace(client=client, control=control, executor=executor)


def call(service, tool, arguments=None, token="hmcp_test-products", extra_headers=None):
    return service.client.post("/mcp", headers={
        "Authorization": f"Bearer {token}", "Accept": "application/json, text/event-stream",
        "MCP-Protocol-Version": "2025-06-18", **(extra_headers or {}),
    }, json={"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"name": tool, "arguments": arguments or {}}})


def test_protocol_initialize_and_tools_are_read_only(service):
    headers = {"Authorization": "Bearer hmcp_test-products", "Accept": "application/json, text/event-stream"}
    response = service.client.post("/mcp", headers=headers, json={"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": "2025-06-18", "capabilities": {}, "clientInfo": {"name": "test", "version": "1"}}})
    assert response.status_code == 200
    assert response.json()["result"]["serverInfo"]["name"] == "hede-readonly"
    response = service.client.post("/mcp", headers=headers, json={"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
    tools = response.json()["result"]["tools"]
    assert {tool["name"] for tool in tools} == {"list_datasets", "describe_dataset", "query_readonly"}
    assert all(tool["annotations"]["readOnlyHint"] for tool in tools)


@pytest.mark.parametrize("mode", ["auto", "legacy"])
def test_official_sdk_client_round_trip(mode):
    async def exercise():
        settings = SimpleNamespace(allowed_hosts=("testserver",), allowed_origins=())
        control, executor = FakeControl(), FakeExecutor()
        app = create_app(settings, control=control, executor=executor)
        async with app.router.lifespan_context(app):
            async with httpx2.AsyncClient(
                transport=httpx2.ASGITransport(app=app),
                headers={"Authorization": "Bearer hmcp_test-products"},
            ) as http_client:
                transport = streamable_http_client("http://testserver/mcp", http_client=http_client)
                async with Client(transport, mode=mode, read_timeout_seconds=5) as client:
                    tools = await client.list_tools()
                    assert {tool.name for tool in tools.tools} == {"list_datasets", "describe_dataset", "query_readonly"}
                    datasets = await client.call_tool("list_datasets")
                    assert [item["name"] for item in datasets.structured_content["datasets"]] == ["products"]
                    description = await client.call_tool("describe_dataset", {"dataset": "products"})
                    assert description.structured_content["name"] == "products"
                    result = await client.call_tool("query_readonly", {
                        "sql": "SELECT sku FROM products WHERE sku=:sku", "params": {"sku": "TEST"},
                    })
                    assert not result.is_error
                    assert result.structured_content["rows"] == [["TEST"]]
                    denied = await client.call_tool("query_readonly", {"sql": "DELETE FROM products"})
                    assert denied.is_error
                    assert len(executor.queries) == 1
    asyncio.run(exercise())


def test_personal_identity_has_no_cross_request_leakage(service):
    products = call(service, "list_datasets").json()["result"]["structuredContent"]
    design = call(service, "list_datasets", token="hmcp_test-design").json()["result"]["structuredContent"]
    assert [item["name"] for item in products["datasets"]] == ["products"]
    assert len(design["datasets"]) == 3
    denied = call(service, "describe_dataset", {"dataset": "copywriting_history"}).json()["result"]
    assert denied["isError"] is True
    assert "schema" not in denied


def test_revocation_takes_effect_on_next_request(service):
    assert call(service, "list_datasets").status_code == 200
    service.control.identities.pop("hmcp_test-products")
    assert call(service, "list_datasets").status_code == 401


def test_auth_host_origin_method_and_size_are_checked(service):
    assert service.client.post("/mcp", json={}).status_code == 401
    assert call(service, "list_datasets", token="invalid").status_code == 401
    assert call(service, "list_datasets", extra_headers={"Host": "evil.example"}).status_code == 421
    assert call(service, "list_datasets", extra_headers={"Origin": "https://evil.example"}).status_code == 403
    assert service.client.get("/mcp").status_code == 405
    response = call(service, "query_readonly", {"sql": "x" * 70000})
    assert response.status_code == 413
    assert not service.executor.queries


def test_safe_sql_executed_once_and_audit_contains_no_literals_or_tokens(service):
    response = call(service, "query_readonly", {"sql": "SELECT sku FROM products WHERE sku=:sku", "params": {"sku": "private-value"}})
    assert response.status_code == 200
    assert response.json()["result"]["structuredContent"]["row_count"] == 1
    assert len(service.executor.queries) == 1
    assert service.executor.queries[0][0] == "products"
    assert "private-value" not in str(service.control.events)
    assert "hmcp_test" not in str(service.control.events)
    assert response.headers["cache-control"] == "no-store"


def test_unsafe_sql_and_unavailable_audit_fail_closed(service):
    response = call(service, "query_readonly", {"sql": "DELETE FROM products"})
    assert response.json()["result"]["isError"] is True
    assert not service.executor.queries
    service.control.audit_failed = True
    response = call(service, "query_readonly", {"sql": "SELECT sku FROM products"})
    assert response.json()["result"]["isError"] is True
    assert "private audit error" not in response.text
    assert not service.executor.queries


def test_rate_limit_is_per_token(service):
    for _ in range(60):
        assert call(service, "list_datasets").status_code == 200
    assert call(service, "list_datasets").status_code == 429
    assert call(service, "list_datasets", token="hmcp_test-design").status_code == 200


def test_database_errors_are_sanitized(service):
    def fail(*args):
        raise RuntimeError("private-password postgres://internal/private")
    service.executor.execute = fail
    response = call(service, "query_readonly", {"sql": "SELECT sku FROM products"})
    assert response.json()["result"]["isError"] is True
    assert "private-password" not in response.text and "postgres://" not in response.text


def test_final_audit_failure_withholds_result(service):
    original = service.control.audit
    def audit(*args):
        if args[4] == "completed":
            raise RuntimeError("private audit outage")
        original(*args)
    service.control.audit = audit
    response = call(service, "query_readonly", {"sql": "SELECT sku FROM products"})
    assert response.json()["result"]["isError"] is True
    assert "TEST" not in response.text and "private audit outage" not in response.text


def test_global_concurrency_limit_returns_busy_without_auth_or_query(service):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Event
    entered, release = Event(), Event()
    original = service.executor.execute
    def delayed(*args):
        entered.set()
        assert release.wait(5)
        return original(*args)
    service.executor.execute = delayed
    with ThreadPoolExecutor(max_workers=4) as pool:
        futures = [pool.submit(call, service, "query_readonly", {"sql": "SELECT sku FROM products"}) for _ in range(4)]
        assert entered.wait(5)
        import time
        deadline = time.monotonic() + 5
        while len([event for event in service.control.events if event[4] == "started"]) < 4 and time.monotonic() < deadline:
            time.sleep(0.01)
        try:
            assert call(service, "list_datasets").status_code == 429
        finally:
            release.set()
        assert all(future.result().status_code == 200 for future in futures)
