from datetime import date, datetime
from decimal import Decimal
import json
import time

from psycopg import RawServerCursor
from psycopg.errors import QueryCanceled
from sqlalchemy import create_engine, text

from readonly_mcp.sql_policy import ValidatedQuery
from readonly_mcp.catalog import DATASETS, PROFILE_PERMISSIONS, dataset_allowed_for_profile, profile_permissions


def json_value(value):
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return str(value)
    return value


class QueryExecutor:
    def __init__(self, settings):
        self.settings = settings
        urls = {"products": settings.products_url, "design": settings.design_url, **settings.department_urls}
        self.engines = {profile: create_engine(url, pool_size=2, max_overflow=0, pool_timeout=2, pool_pre_ping=True, hide_parameters=True, connect_args={"connect_timeout": 5}) for profile, url in urls.items()}

    def verify_roles(self, control):
        for profile, engine in {**self.engines, "control": control.engine}.items():
            expected = f"hede_mcp_{profile}"
            with engine.connect() as connection:
                row = connection.execute(text("SELECT current_user AS name, rolsuper, rolcreatedb, rolcreaterole, rolbypassrls, rolreplication FROM pg_catalog.pg_roles WHERE rolname=current_user")).mappings().one()
                if row["name"] != expected or any(row[name] for name in ("rolsuper", "rolcreatedb", "rolcreaterole", "rolbypassrls", "rolreplication")):
                    raise ValueError("MCP数据库角色不符合专用最小权限配置；拒绝启动")
                if connection.scalar(text("SELECT count(*) FROM pg_catalog.pg_auth_members WHERE member=(SELECT oid FROM pg_catalog.pg_roles WHERE rolname=current_user)")):
                    raise ValueError("MCP数据库账号不能继承其他角色")
                if connection.scalar(text("SELECT count(*) FROM pg_catalog.pg_namespace WHERE nspname NOT LIKE 'pg_temp_%' AND has_schema_privilege(current_user,oid,'CREATE')")):
                    raise ValueError("MCP账号不能拥有schema创建权限，请检查PUBLIC授权")
                if connection.scalar(text("SELECT has_database_privilege(current_user,current_database(),'CREATE')")):
                    raise ValueError("MCP账号不能拥有数据库CREATE权限")
                if connection.scalar(text("""SELECT count(*) FROM pg_catalog.pg_proc routine JOIN pg_catalog.pg_namespace space ON space.oid=routine.pronamespace
                    WHERE space.nspname NOT IN ('pg_catalog','information_schema')
                    AND has_function_privilege(current_user,routine.oid,'EXECUTE')""")):
                    raise ValueError("MCP账号能执行自定义函数，请先审查其PUBLIC EXECUTE授权；本服务不自动修改其他业务授权")
                if profile == "control":
                    readable = ("mcp_private.identities",)
                elif profile in PROFILE_PERMISSIONS:
                    readable = tuple(f"mcp_readonly.{name}" for name, definition in DATASETS.items()
                        if name == "products" or dataset_allowed_for_profile(profile, name)
                        or name in {"product_prices", "purchase_orders"} and
                        ("product.view" if name == "product_prices" else "purchase.view") in profile_permissions(profile))
                else:
                    readable = ("mcp_readonly.products",) + (("mcp_readonly.copywriting", "mcp_readonly.copywriting_history") if profile == "design" else ())
                for relation in readable:
                    if not connection.scalar(text("SELECT has_table_privilege(current_user,CAST(:relation AS regclass),'SELECT')"), {"relation": relation}):
                        raise ValueError("MCP授权视图缺失或不可读")
                relations = connection.execute(text("""SELECT space.nspname||'.'||relation.relname AS name,
                    has_table_privilege(current_user,relation.oid,'SELECT') OR has_any_column_privilege(current_user,relation.oid,'SELECT') AS readable,
                    has_table_privilege(current_user,relation.oid,'INSERT,UPDATE,DELETE,TRUNCATE,TRIGGER,REFERENCES')
                        OR has_any_column_privilege(current_user,relation.oid,'INSERT,UPDATE,REFERENCES') AS writable
                    FROM pg_catalog.pg_class relation JOIN pg_catalog.pg_namespace space ON space.oid=relation.relnamespace
                    WHERE space.nspname NOT IN ('pg_catalog','information_schema') AND space.nspname NOT LIKE 'pg_toast%'
                    AND relation.relkind IN ('r','p','v','m','f')""")).mappings()
                for relation in relations:
                    if relation["readable"] and relation["name"] not in readable:
                        raise ValueError("MCP账号存在超出授权视图的查询权限，请检查PUBLIC及列级授权")
                    if relation["writable"] and not (profile == "control" and relation["name"] == "mcp_private.audit"):
                        raise ValueError("MCP账号存在超出审计记录的写权限")
                if profile == "control":
                    if not connection.scalar(text("SELECT has_table_privilege(current_user,'mcp_private.audit','INSERT') AND NOT has_table_privilege(current_user,'mcp_private.audit','UPDATE,DELETE,TRUNCATE,TRIGGER,REFERENCES') AND NOT has_any_column_privilege(current_user,'mcp_private.audit','UPDATE,REFERENCES')")):
                        raise ValueError("MCP审计表只允许INSERT")
                if profile != "control":
                    if connection.scalar(text("SHOW default_transaction_read_only")) != "on":
                        raise ValueError("查询账号必须默认只读")

    def execute(self, profile: str, query: ValidatedQuery) -> dict:
        with self.engines[profile].connect() as connection:
            with connection.begin():
                connection.exec_driver_sql("SET TRANSACTION READ ONLY")
                connection.exec_driver_sql(f"SET LOCAL statement_timeout = {self.settings.timeout_ms}")
                connection.exec_driver_sql("SET LOCAL lock_timeout = 1000")
                connection.exec_driver_sql("SET LOCAL idle_in_transaction_session_timeout = 15000")
                connection.exec_driver_sql("SET LOCAL search_path = pg_catalog, mcp_readonly")
                connection.exec_driver_sql("SET LOCAL timezone = 'Asia/Shanghai'")
                connection.exec_driver_sql("SET LOCAL work_mem = '4MB'")
                raw = connection.connection.driver_connection
                deadline = time.monotonic() + self.settings.timeout_ms / 1000
                with RawServerCursor(raw, "mcp_result") as cursor:
                    cursor.execute(f"SELECT * FROM ({query.sql}) AS mcp_result LIMIT {self.settings.max_rows + 1}", query.parameters)
                    columns = [column.name for column in cursor.description]
                    rows = []
                    size = len(json.dumps(columns, ensure_ascii=False).encode()) + 2000
                    truncated = False
                    while True:
                        remaining_ms = int((deadline - time.monotonic()) * 1000)
                        if remaining_ms <= 0:
                            raise QueryCanceled("MCP查询总时限已达到")
                        connection.exec_driver_sql(f"SET LOCAL statement_timeout = {remaining_ms}")
                        record = cursor.fetchone()
                        if record is None:
                            break
                        converted = [json_value(value) for value in record]
                        size += len(json.dumps(converted, ensure_ascii=False).encode()) + 2
                        if len(rows) >= self.settings.max_rows or size > self.settings.max_bytes:
                            truncated = True
                            break
                        rows.append(converted)
        return {"columns": columns, "rows": rows, "row_count": len(rows), "truncated": truncated, "max_rows": self.settings.max_rows, "timezone": "Asia/Shanghai"}

    def close(self):
        for engine in self.engines.values():
            engine.dispose()
