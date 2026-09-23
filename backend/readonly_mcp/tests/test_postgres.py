from datetime import datetime, timedelta, timezone
import os
from pathlib import Path

import psycopg
import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from starlette.testclient import TestClient

from readonly_mcp.admin import ROLES, inspect_deployment, issue_token, setup, upgrade_token_expiry
from readonly_mcp.catalog import PRODUCT_COLUMNS
from readonly_mcp.control import ControlRepository
from readonly_mcp.query import QueryExecutor
from readonly_mcp.server import create_app
from readonly_mcp.settings import BACKEND_ROOT, MCPSettings
from readonly_mcp.sql_policy import validate_query


@pytest.fixture(scope="module")
def database():
    raw = os.getenv("MCP_TEST_DATABASE_URL")
    if not raw:
        pytest.skip("MCP_TEST_DATABASE_URL not set; never uses DATABASE_URL")
    url = make_url(raw)
    if url.host != "127.0.0.1" or url.port != 55439 or url.database != "postgres":
        raise RuntimeError("Integration tests require isolated loopback test cluster on 55439")
    admin = create_engine(raw, isolation_level="AUTOCOMMIT")
    with admin.connect() as connection:
        directory = Path(connection.scalar(text("SHOW data_directory"))).resolve()
        if not directory.is_relative_to((BACKEND_ROOT / "logs").resolve()) or not directory.name.startswith("mcp-pg-test-"):
            raise RuntimeError("Refusing tests outside designated temporary cluster")
        connection.exec_driver_sql("CREATE DATABASE hede_mcp_test")
    admin.dispose()
    url = url.set(database="hede_mcp_test")
    engine = create_engine(url)
    with engine.begin() as connection:
        connection.exec_driver_sql("CREATE TABLE auth_roles (code TEXT PRIMARY KEY, permissions TEXT NOT NULL)")
        connection.exec_driver_sql("CREATE TABLE auth_users (id INTEGER PRIMARY KEY, username TEXT UNIQUE, status TEXT, department_code TEXT, role_code TEXT, password_hash TEXT)")
        connection.exec_driver_sql("INSERT INTO auth_roles VALUES ('design_viewer','product.view'),('finance_user','product.view'),('super_admin','*')")
        connection.execute(text("INSERT INTO auth_users VALUES (1,'designer','active',:design,'design_viewer','private'),(2,'finance','active',:finance,'finance_user','private')"), {"design": "美工部", "finance": "财务部"})
        connection.exec_driver_sql("ALTER TABLE auth_users ADD COLUMN display_name TEXT NOT NULL DEFAULT 'Test user'")
        fields = ",".join(f'"{name}" {kind}' for name, kind in PRODUCT_COLUMNS.items() if name not in {"brand", "has_image"})
        connection.exec_driver_sql(f"CREATE TABLE cbanner_womens_products ({fields}, image_path TEXT, deleted_at TIMESTAMPTZ, cost NUMERIC, raw_payload JSON)")
        connection.exec_driver_sql("INSERT INTO cbanner_womens_products(id,sku,product_name,color,launch_date,image_path,cost,updated_at) VALUES (1,'TEST-001','shoe','brown','2026-09-22','private-share',99,now()),(2,'DELETED','hidden','black','2026-09-22',NULL,99,now())")
        connection.exec_driver_sql("UPDATE cbanner_womens_products SET deleted_at=now() WHERE id=2")
        connection.exec_driver_sql("INSERT INTO cbanner_womens_products(id,sku,product_name) SELECT number, 'ITEM-'||number, 'shoe' FROM generate_series(3,260) number")
        connection.exec_driver_sql("CREATE TABLE product_copywriting (brand TEXT, source_product_id BIGINT, sku TEXT, status TEXT, content TEXT, input_prompt TEXT, model TEXT, generated_at TIMESTAMPTZ)")
        connection.exec_driver_sql("CREATE TABLE product_copywriting_history (id BIGINT, brand TEXT, source_product_id BIGINT, sku TEXT, model TEXT, generated_at TIMESTAMPTZ, snapshot JSON)")
        connection.exec_driver_sql("INSERT INTO product_copywriting VALUES ('cbanner_womens',1,'TEST-001','completed','copy','prompt','model',now())")
        connection.execute(text("INSERT INTO product_copywriting_history VALUES (1,'cbanner_womens',1,'TEST-001','model',now(),CAST(:snapshot AS JSON))"), {"snapshot": '{"content":"history","input_prompt":"old prompt","system_prompt":"private","input_image":{"path":"private-share"}}'})
    passwords = {role: "test-password-" + role for role in ROLES}
    def fail_finalize():
        raise RuntimeError("simulated env conflict")
    with pytest.raises(RuntimeError, match="env conflict"):
        setup(engine, passwords, finalize=fail_finalize)
    with engine.connect() as connection:
        assert connection.scalar(text("SELECT count(*) FROM pg_roles WHERE rolname LIKE 'hede_mcp_%'")) == 0
        assert connection.scalar(text("SELECT count(*) FROM pg_namespace WHERE nspname IN ('mcp_private','mcp_readonly')")) == 0
    setup(engine, passwords)
    settings = MCPSettings(*(url.set(username=role, password=passwords[role]).render_as_string(hide_password=False) for role in ROLES), allowed_hosts=("testserver",))
    control, executor = ControlRepository(settings.control_url), QueryExecutor(settings)
    try:
        yield engine, settings, control, executor
    finally:
        control.close()
        executor.close()
        engine.dispose()


def test_dedicated_roles_and_database_privileges(database):
    _, _, control, executor = database
    executor.verify_roles(control)
    for profile, engine in executor.engines.items():
        with engine.connect() as connection:
            assert connection.scalar(text("SHOW default_transaction_read_only")) == "on"
        for sql in ("SELECT * FROM public.auth_users", "SELECT cost FROM public.cbanner_womens_products", "SELECT * FROM mcp_private.tokens", "UPDATE mcp_readonly.products SET sku='bad'", "CREATE TABLE public.bad(id int)"):
            with engine.connect() as connection:
                with pytest.raises(Exception):
                    connection.exec_driver_sql(sql)
        if profile == "products":
            with engine.connect() as connection:
                with pytest.raises(Exception):
                    connection.exec_driver_sql("SELECT * FROM mcp_readonly.copywriting_history")


def test_real_query_parameters_rows_and_projection(database):
    _, _, _, executor = database
    result = executor.execute("products", validate_query("SELECT sku,has_image FROM products WHERE sku=:sku", {"sku": "TEST-001"}, {"profile": "products"}))
    assert result["rows"] == [["TEST-001", True]]
    assert result["truncated"] is False
    bounded = executor.execute("products", validate_query("SELECT sku FROM products ORDER BY id", {}, {"profile": "products"}))
    assert bounded["row_count"] == 200
    assert bounded["truncated"] is True
    assert ["DELETED"] not in bounded["rows"]
    injection = executor.execute("products", validate_query("SELECT sku FROM products WHERE sku=:sku", {"sku": "' OR true; DROP TABLE auth_users;--"}, {"profile": "products"}))
    assert injection["rows"] == []
    joined = executor.execute("design", validate_query("SELECT p.sku,h.content,h.image_source FROM products p JOIN copywriting_history h ON p.id=h.product_id AND p.brand=h.brand", {}, {"profile": "design"}))
    assert joined["rows"] == [["TEST-001", "history", "unknown"]]


def test_result_bytes_limit(database):
    engine, _, _, executor = database
    with engine.begin() as connection:
        connection.execute(text("UPDATE cbanner_womens_products SET selling_points=:value WHERE id=1"), {"value": "x" * 600000})
    try:
        result = executor.execute("products", validate_query("SELECT selling_points FROM products WHERE id=1", {}, {"profile": "products"}))
        assert result["rows"] == []
        assert result["truncated"] is True
    finally:
        with engine.begin() as connection:
            connection.exec_driver_sql("UPDATE cbanner_womens_products SET selling_points=NULL WHERE id=1")


def test_token_binding_expiry_revocation_and_department_changes(database):
    engine, _, control, _ = database
    token, token_id = issue_token(engine, "designer", "design", 1, "test")
    assert control.authenticate(token)["profile"] == "design"
    with pytest.raises(ValueError):
        issue_token(engine, "finance", "design", 1, "denied")
    with engine.begin() as connection:
        connection.execute(text("UPDATE auth_users SET department_code=:department WHERE id=1"), {"department": "财务部"})
    assert control.authenticate(token) is None
    with engine.begin() as connection:
        connection.execute(text("UPDATE auth_users SET department_code=:department WHERE id=1"), {"department": "美工部"})
        connection.exec_driver_sql("UPDATE auth_roles SET permissions='' WHERE code='design_viewer'")
    assert control.authenticate(token) is None
    with engine.begin() as connection:
        connection.exec_driver_sql("UPDATE auth_roles SET permissions='product.view' WHERE code='design_viewer'")
        connection.exec_driver_sql("UPDATE auth_users SET status='inactive' WHERE id=1")
    assert control.authenticate(token) is None
    with engine.begin() as connection:
        connection.exec_driver_sql("UPDATE auth_users SET status='active' WHERE id=1")
        connection.execute(text("UPDATE mcp_private.tokens SET expires_at=:expiry WHERE id=:id"), {"id": token_id, "expiry": datetime.now(timezone.utc) - timedelta(seconds=1)})
    assert control.authenticate(token) is None
    with engine.begin() as connection:
        connection.execute(text("UPDATE mcp_private.tokens SET expires_at=now()+interval '1 day',revoked_at=now() WHERE id=:id"), {"id": token_id})
    assert control.authenticate(token) is None


def test_permanent_token_is_authenticated_until_revoked_or_blocked(database):
    engine, _, control, _ = database
    token, token_id = issue_token(engine, "designer", "design", None, "permanent")
    assert control.authenticate(token)["profile"] == "design"
    with engine.begin() as connection:
        connection.execute(text("UPDATE auth_roles SET permissions='' WHERE code='design_viewer'"))
    assert control.authenticate(token) is None
    with engine.begin() as connection:
        connection.exec_driver_sql("UPDATE auth_roles SET permissions='product.view' WHERE code='design_viewer'")
        connection.execute(text("UPDATE mcp_private.tokens SET revoked_at=now() WHERE id=:id"), {"id": token_id})
    assert control.authenticate(token) is None


def test_real_protocol_to_database_and_audit(database):
    engine, settings, _, _ = database
    token, token_id = issue_token(engine, "designer", "design", 1, "protocol")
    with TestClient(create_app(settings)) as client:
        headers = {"Authorization": f"Bearer {token}", "Accept": "application/json, text/event-stream", "MCP-Protocol-Version": "2025-06-18"}
        response = client.post("/mcp", headers=headers, json={"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"name": "query_readonly", "arguments": {"sql": "SELECT sku FROM products WHERE id=:id", "params": {"id": 1}}}})
        assert response.status_code == 200
        assert response.json()["result"]["structuredContent"]["rows"] == [["TEST-001"]]
    with engine.connect() as connection:
        rows = connection.execute(text("SELECT status,sql_hash,row_count FROM mcp_private.audit WHERE token_id=:id ORDER BY id"), {"id": token_id}).mappings().all()
        assert [row["status"] for row in rows] == ["started", "completed"]
        assert rows[-1]["row_count"] == 1
        assert len(rows[-1]["sql_hash"]) == 64


def test_statement_timeout_is_real_and_does_not_poison_next_connection(database):
    _, settings, _, executor = database
    from readonly_mcp.sql_policy import ValidatedQuery
    from dataclasses import replace
    executor.settings = replace(settings, timeout_ms=30)
    try:
        with pytest.raises(psycopg.errors.QueryCanceled):
            executor.execute("products", ValidatedQuery("SELECT pg_sleep(1)", (), ("products",)))
        result = executor.execute("products", validate_query("SELECT sku FROM products WHERE id=1", {}, {"profile": "products"}))
        assert result["row_count"] == 1
    finally:
        executor.settings = settings


@pytest.mark.parametrize("grant,revoke", [
    ("GRANT SELECT(password_hash) ON auth_users TO hede_mcp_products", "REVOKE SELECT(password_hash) ON auth_users FROM hede_mcp_products"),
    ("GRANT CREATE ON SCHEMA public TO hede_mcp_products", "REVOKE CREATE ON SCHEMA public FROM hede_mcp_products"),
    ("GRANT SELECT ON auth_users TO hede_mcp_control", "REVOKE SELECT ON auth_users FROM hede_mcp_control"),
    ("GRANT UPDATE ON mcp_private.audit TO hede_mcp_control", "REVOKE UPDATE ON mcp_private.audit FROM hede_mcp_control"),
    ("GRANT UPDATE(row_count) ON mcp_private.audit TO hede_mcp_control", "REVOKE UPDATE(row_count) ON mcp_private.audit FROM hede_mcp_control"),
])
def test_startup_refuses_excess_privileges(database, grant, revoke):
    engine, _, control, executor = database
    with engine.begin() as connection:
        connection.exec_driver_sql(grant)
    try:
        with pytest.raises(ValueError):
            executor.verify_roles(control)
    finally:
        with engine.begin() as connection:
            connection.exec_driver_sql(revoke)
    executor.verify_roles(control)


def test_startup_refuses_public_custom_function_execution(database):
    engine, _, control, executor = database
    with engine.begin() as connection:
        connection.exec_driver_sql("CREATE FUNCTION public.mcp_test_custom() RETURNS int LANGUAGE sql AS 'SELECT 1'")
    try:
        with engine.connect() as connection:
            report = inspect_deployment(connection)
            assert report["ready_for_setup"] is False
            assert any(item["name"] == "mcp_test_custom" for item in report["public_execute_functions"])
        with pytest.raises(ValueError, match="自定义函数"):
            executor.verify_roles(control)
    finally:
        with engine.begin() as connection:
            connection.exec_driver_sql("DROP FUNCTION public.mcp_test_custom()")
    executor.verify_roles(control)


def test_setup_never_overwrites_existing_roles(database):
    engine, _, _, _ = database
    with pytest.raises(ValueError, match="已存在"):
        setup(engine, {role: "unchanged" for role in ROLES})


def test_fetch_deadline_is_shared_across_rows(database):
    _, settings, _, executor = database
    from dataclasses import replace
    from readonly_mcp.sql_policy import ValidatedQuery
    executor.settings = replace(settings, timeout_ms=150)
    try:
        with pytest.raises(psycopg.errors.QueryCanceled):
            executor.execute("products", ValidatedQuery("SELECT pg_sleep(0.06),id FROM mcp_readonly.products LIMIT 10", (), ("products",)))
    finally:
        executor.settings = settings
