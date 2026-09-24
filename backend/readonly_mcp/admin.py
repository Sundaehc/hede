import argparse
import json
import os
import re
import secrets
import stat

from dotenv import load_dotenv
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import make_url

from domain.excluded_skus import EXCLUDED_SKUS
from domain.sources import TABLE_NAMES
from readonly_mcp.catalog import PRODUCT_COLUMNS, BUSINESS_TABLE_PERMISSIONS, DATASETS, PROFILE_PERMISSIONS, dataset_allowed_for_profile, profile_permissions
from readonly_mcp.settings import BACKEND_ROOT
from storage.mcp_token_repository import issue_credential


ROLES = ("hede_mcp_products", "hede_mcp_design", "hede_mcp_control")


def protect_config(source, destination):
    if os.name == "nt":
        import win32security
        information = win32security.DACL_SECURITY_INFORMATION
        security = win32security.GetFileSecurity(str(source), information)
        win32security.SetFileSecurity(str(destination), information, security)
    else:
        os.chmod(destination, stat.S_IMODE(source.stat().st_mode) & 0o600)


def quote(value: str) -> str:
    return '"' + value.replace('"', '""') + '"'


def literal(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def inspect_deployment(connection) -> dict:
    functions = connection.execute(text("""SELECT space.nspname AS schema, routine.proname AS name,
        pg_get_function_identity_arguments(routine.oid) AS arguments, routine.prosecdef AS security_definer
        FROM pg_catalog.pg_proc routine JOIN pg_catalog.pg_namespace space ON space.oid=routine.pronamespace
        WHERE space.nspname NOT IN ('pg_catalog','information_schema') AND EXISTS (
            SELECT 1 FROM aclexplode(COALESCE(routine.proacl,acldefault('f',routine.proowner))) permission
            WHERE permission.grantee=0 AND permission.privilege_type='EXECUTE')
        ORDER BY space.nspname,routine.proname,routine.oid""")).mappings().all()
    public_relations = connection.execute(text("""SELECT space.nspname AS schema, relation.relname AS name
        FROM pg_catalog.pg_class relation JOIN pg_catalog.pg_namespace space ON space.oid=relation.relnamespace
        WHERE space.nspname NOT IN ('pg_catalog','information_schema') AND space.nspname NOT LIKE 'pg_toast%'
        AND relation.relkind IN ('r','p','v','m','f') AND (
            EXISTS (SELECT 1 FROM aclexplode(COALESCE(relation.relacl,acldefault('r',relation.relowner))) permission
                WHERE permission.grantee=0)
            OR EXISTS (SELECT 1 FROM pg_catalog.pg_attribute attribute, LATERAL aclexplode(attribute.attacl) permission
                WHERE attribute.attrelid=relation.oid AND permission.grantee=0))
        ORDER BY space.nspname,relation.relname""")).mappings().all()
    public_create = connection.execute(text("""SELECT space.nspname AS schema FROM pg_catalog.pg_namespace space
        WHERE EXISTS (SELECT 1 FROM aclexplode(COALESCE(space.nspacl,acldefault('n',space.nspowner))) permission
            WHERE permission.grantee=0 AND permission.privilege_type='CREATE')""")).mappings().all()
    database_create = bool(connection.scalar(text("""SELECT EXISTS (
        SELECT 1 FROM pg_catalog.pg_database database, LATERAL aclexplode(COALESCE(database.datacl,acldefault('d',database.datdba))) permission
        WHERE database.datname=current_database() AND permission.grantee=0 AND permission.privilege_type='CREATE')""")))
    inspector = inspect(connection)
    required = ("auth_users", "auth_roles", "product_copywriting", "product_copywriting_history")
    missing = [name for name in required if not inspector.has_table(name, schema="public")]
    return {
        "ready_for_setup": not (functions or public_relations or public_create or database_create or missing),
        "public_execute_functions": [dict(row) for row in functions],
        "public_relation_privileges": [dict(row) for row in public_relations],
        "public_schema_create": [dict(row) for row in public_create],
        "public_database_create": database_create, "missing_required_tables": missing,
        "note": "只读诊断，不代表列出的函数有漏洞；需管理员审核PUBLIC授权，不能简单全部撤销以免影响现有业务。",
    }


def setup(engine, passwords: dict[str, str], finalize=None) -> dict:
    with engine.begin() as connection:
        connection.execute(text("SELECT pg_advisory_xact_lock(68473103)"))
        database = connection.scalar(text("SELECT current_database()"))
        existing = connection.execute(text("SELECT rolname FROM pg_roles WHERE rolname IN ('hede_mcp_products','hede_mcp_design','hede_mcp_control')")).scalars().all()
        if existing:
            raise ValueError("MCP角色已存在，setup不覆盖或重置账号；请使用verify检查现有配置")
        if any(inspect(connection).has_schema(name) for name in ("mcp_private", "mcp_readonly")):
            raise ValueError("MCP schema已存在，拒绝覆盖")
        if not inspect_deployment(connection)["ready_for_setup"]:
            raise ValueError("部署前权限或表检查未通过，尚未创建MCP账号；先运行doctor获取只读诊断，不自动修改业务授权")
        for role in ROLES:
            connection.exec_driver_sql(f"CREATE ROLE {quote(role)} LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT NOREPLICATION NOBYPASSRLS CONNECTION LIMIT 8 PASSWORD {literal(passwords[role])}")
            connection.exec_driver_sql(f"GRANT CONNECT ON DATABASE {quote(database)} TO {quote(role)}")
            connection.exec_driver_sql(f"ALTER ROLE {quote(role)} SET search_path = pg_catalog")
            connection.exec_driver_sql(f"ALTER ROLE {quote(role)} SET statement_timeout = '10s'")
            connection.exec_driver_sql(f"ALTER ROLE {quote(role)} SET lock_timeout = '1s'")
            connection.exec_driver_sql(f"ALTER ROLE {quote(role)} SET idle_in_transaction_session_timeout = '15s'")
        for role in ROLES[:2]:
            connection.exec_driver_sql(f"ALTER ROLE {quote(role)} SET default_transaction_read_only = on")
        connection.exec_driver_sql("CREATE SCHEMA mcp_private")
        connection.exec_driver_sql("CREATE SCHEMA mcp_readonly")
        connection.exec_driver_sql("REVOKE ALL ON SCHEMA mcp_private, mcp_readonly FROM PUBLIC")
        connection.exec_driver_sql("""CREATE TABLE mcp_private.tokens (
            id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
            user_id INTEGER NOT NULL REFERENCES public.auth_users(id) ON DELETE CASCADE,
            token_hash TEXT NOT NULL UNIQUE, label TEXT NOT NULL,
            profile TEXT NOT NULL CHECK (profile IN ('products','design')),
            expires_at TIMESTAMPTZ, revoked_at TIMESTAMPTZ,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now())""")
        connection.exec_driver_sql("""CREATE TABLE mcp_private.audit (
            id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
            request_id TEXT NOT NULL, token_id BIGINT NOT NULL, user_id INTEGER NOT NULL,
            tool TEXT NOT NULL, sql_hash TEXT, status TEXT NOT NULL, row_count INTEGER NOT NULL,
            elapsed_ms INTEGER NOT NULL, created_at TIMESTAMPTZ NOT NULL DEFAULT now())""")
        connection.exec_driver_sql("CREATE INDEX mcp_audit_request ON mcp_private.audit(request_id)")
        connection.exec_driver_sql("CREATE INDEX mcp_audit_created ON mcp_private.audit(created_at)")
        connection.exec_driver_sql("""CREATE VIEW mcp_private.identities WITH (security_barrier=true) AS
            SELECT token.id AS token_id, token.user_id, token.token_hash, token.profile, token.expires_at, token.revoked_at,
                users.status, users.department_code, users.role_code, roles.permissions
            FROM mcp_private.tokens token JOIN public.auth_users users ON users.id=token.user_id
            JOIN public.auth_roles roles ON roles.code=users.role_code""")
        connection.exec_driver_sql("GRANT USAGE ON SCHEMA mcp_private TO hede_mcp_control")
        connection.exec_driver_sql("GRANT SELECT ON mcp_private.identities TO hede_mcp_control")
        connection.exec_driver_sql("GRANT INSERT ON mcp_private.audit TO hede_mcp_control")
        connection.exec_driver_sql("GRANT USAGE ON SEQUENCE mcp_private.audit_id_seq TO hede_mcp_control")
        count = refresh_views(connection)
        connection.exec_driver_sql("REVOKE ALL ON ALL TABLES IN SCHEMA mcp_private FROM PUBLIC")
        connection.exec_driver_sql("REVOKE ALL ON ALL SEQUENCES IN SCHEMA mcp_private FROM PUBLIC")
        if finalize is not None:
            finalize()
        return {"created_roles": list(ROLES), "product_sources": count}


def refresh_views(connection) -> int:
    sources = {**TABLE_NAMES, "smiley": "smiley_products", "ni": "ni_products"}
    inspector = inspect(connection)
    if inspector.has_table("supplier_brands", schema="public"):
        for row in connection.execute(text("SELECT code, product_table_name FROM public.supplier_brands WHERE product_archive_enabled=true")).mappings():
            if row["code"] not in sources and re.fullmatch(r"manual_product_archive_[0-9]+", row["product_table_name"] or ""):
                sources[row["code"]] = row["product_table_name"]
    selections = []
    for brand, table_name in sources.items():
        if not inspector.has_table(table_name, schema="public"):
            continue
        columns = []
        for name in PRODUCT_COLUMNS:
            if name == "brand":
                columns.append(f"{literal(brand)}::text AS brand")
            elif name == "has_image":
                columns.append("(NULLIF(btrim(image_path),'') IS NOT NULL) AS has_image")
            else:
                columns.append(quote(name))
        exclusions = ",".join(literal(sku) for sku in sorted(EXCLUDED_SKUS))
        where = "deleted_at IS NULL" + (f" AND (sku IS NULL OR sku NOT IN ({exclusions}))" if exclusions else "")
        selections.append(f"SELECT {', '.join(columns)} FROM public.{quote(table_name)} WHERE {where}")
    if not selections:
        raise ValueError("没有可用商品档案表，不能初始化MCP")
    connection.exec_driver_sql("CREATE OR REPLACE VIEW mcp_readonly.products WITH (security_barrier=true) AS " + " UNION ALL ".join(selections))
    connection.exec_driver_sql("""CREATE OR REPLACE VIEW mcp_readonly.copywriting WITH (security_barrier=true) AS
        SELECT saved.brand, saved.source_product_id AS product_id, saved.sku, saved.status, saved.content,
            saved.input_prompt, saved.model, saved.generated_at
        FROM public.product_copywriting saved JOIN mcp_readonly.products product ON product.brand=saved.brand AND product.id=saved.source_product_id""")
    connection.exec_driver_sql("""CREATE OR REPLACE VIEW mcp_readonly.copywriting_history WITH (security_barrier=true) AS
        SELECT history.id, history.brand, history.source_product_id AS product_id, history.sku,
            history.snapshot->>'content' AS content, history.snapshot->>'input_prompt' AS input_prompt,
            history.model, history.generated_at,
            CASE WHEN history.snapshot->'input_image'->>'source' IN ('us3','shared','local')
                THEN history.snapshot->'input_image'->>'source' ELSE 'unknown' END AS image_source
        FROM public.product_copywriting_history history JOIN mcp_readonly.products product ON product.brand=history.brand AND product.id=history.source_product_id""")
    connection.exec_driver_sql("REVOKE ALL ON ALL TABLES IN SCHEMA mcp_readonly FROM PUBLIC")
    connection.exec_driver_sql("GRANT USAGE ON SCHEMA mcp_readonly TO hede_mcp_products, hede_mcp_design")
    connection.exec_driver_sql("GRANT SELECT ON mcp_readonly.products TO hede_mcp_products, hede_mcp_design")
    connection.exec_driver_sql("GRANT SELECT ON mcp_readonly.copywriting, mcp_readonly.copywriting_history TO hede_mcp_design")
    return len(selections)


def upgrade_department_scope(engine, finalize=None) -> dict:
    with engine.begin() as connection:
        connection.exec_driver_sql("SET LOCAL lock_timeout=1000")
        connection.exec_driver_sql("SET LOCAL statement_timeout=60000")
        connection.execute(text("SELECT pg_advisory_xact_lock(68473103)"))
        if connection.scalar(text("SELECT to_regclass('mcp_private.tokens')")) is None:
            raise ValueError("MCP尚未初始化")
        database = connection.scalar(text("SELECT current_database()"))
        inspector = inspect(connection)
        created = {}
        for profile in PROFILE_PERMISSIONS:
            role = f"hede_mcp_{profile}"
            if connection.scalar(text("SELECT 1 FROM pg_roles WHERE rolname=:role"), {"role": role}):
                raise ValueError(f"{role}已存在；拒绝覆盖账号。请核对部署状态")
            created[profile] = secrets.token_urlsafe(40)
            connection.exec_driver_sql(f"CREATE ROLE {quote(role)} LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT NOREPLICATION NOBYPASSRLS CONNECTION LIMIT 8 PASSWORD {literal(created[profile])}")
            connection.exec_driver_sql(f"GRANT CONNECT ON DATABASE {quote(database)} TO {quote(role)}")
            connection.exec_driver_sql(f"ALTER ROLE {quote(role)} SET search_path = pg_catalog")
            connection.exec_driver_sql(f"ALTER ROLE {quote(role)} SET default_transaction_read_only = on")
            connection.exec_driver_sql(f"ALTER ROLE {quote(role)} SET statement_timeout = '10s'")
            connection.exec_driver_sql(f"ALTER ROLE {quote(role)} SET lock_timeout = '1s'")
            connection.exec_driver_sql(f"ALTER ROLE {quote(role)} SET idle_in_transaction_session_timeout = '15s'")
            connection.exec_driver_sql(f"GRANT USAGE ON SCHEMA mcp_readonly TO {quote(role)}")
            if "product.view" in PROFILE_PERMISSIONS[profile]:
                connection.exec_driver_sql(f"GRANT SELECT ON mcp_readonly.products TO {quote(role)}")
        for name, permission in BUSINESS_TABLE_PERMISSIONS.items():
            columns = DATASETS[name]["columns"]
            if not columns:
                continue
            if name in {"jst_daily_sales", "vip_daily_sales", "product_goods_historical_sales",
                        "product_goods_historical_orders", "product_goods_detail_snapshots"}:
                available = sorted(table for table in inspector.get_table_names(schema="public")
                    if re.fullmatch(rf"{name}_20\d{{2}}", table))
                parent = name if inspector.has_table(name, schema="public") else None
                if parent:
                    available = [parent]
                queries = []
                for table in available:
                    actual_columns = {column["name"] for column in inspector.get_columns(table, schema="public")}
                    if not set(columns) <= actual_columns:
                        raise ValueError(f"{table}字段与授权清单不匹配，拒绝升级")
                    queries.append(f"SELECT {','.join(quote(column) for column in columns)} FROM public.{quote(table)}")
                query = " UNION ALL ".join(queries) if queries else "SELECT " + ",".join(
                    f"NULL::{kind} AS {quote(column)}" for column, kind in columns.items()) + " WHERE false"
            elif inspector.has_table(name, schema="public"):
                actual_columns = {column["name"] for column in inspector.get_columns(name, schema="public")}
                if not set(columns) <= actual_columns:
                    raise ValueError(f"{name}字段与授权清单不匹配，拒绝升级")
                selection = ",".join(quote(column) for column in columns)
                where = " WHERE deleted_at IS NULL" if name == "inventory_records" else ""
                query = f"SELECT {selection} FROM public.{quote(name)}{where}"
            else:
                query = "SELECT " + ",".join(f"NULL::{kind} AS {quote(column)}" for column, kind in columns.items()) + " WHERE false"
            connection.exec_driver_sql(f"CREATE VIEW mcp_readonly.{quote(name)} WITH (security_barrier=true) AS {query}")
            for profile in PROFILE_PERMISSIONS:
                allowed = profile_permissions(profile)
                if permission in allowed and dataset_allowed_for_profile(profile, name):
                    connection.exec_driver_sql(f"GRANT SELECT ON mcp_readonly.{quote(name)} TO {quote('hede_mcp_' + profile)}")
        sources = {**TABLE_NAMES, "smiley": "smiley_products", "ni": "ni_products"}
        if inspector.has_table("supplier_brands", schema="public"):
            for row in connection.execute(text("SELECT code, product_table_name FROM public.supplier_brands WHERE product_archive_enabled=true")).mappings():
                if row["code"] not in sources and re.fullmatch(r"manual_product_archive_[0-9]+", row["product_table_name"] or ""):
                    sources[row["code"]] = row["product_table_name"]
        price_views = []
        exclusions = ",".join(literal(sku) for sku in sorted(EXCLUDED_SKUS))
        for brand, table_name in sources.items():
            if inspector.has_table(table_name, schema="public"):
                where = "deleted_at IS NULL" + (f" AND (sku IS NULL OR sku NOT IN ({exclusions}))" if exclusions else "")
                price_views.append(f"SELECT {literal(brand)}::text AS brand,id,sku,cost,supplier_name FROM public.{quote(table_name)} WHERE {where}")
        if not price_views:
            raise ValueError("商品档案来源缺失，拒绝升级部门范围")
        connection.exec_driver_sql("CREATE VIEW mcp_readonly.product_prices WITH (security_barrier=true) AS " + " UNION ALL ".join(price_views))
        connection.exec_driver_sql("CREATE VIEW mcp_readonly.purchase_orders WITH (security_barrier=true) AS SELECT " + ",".join(quote(column) for column in DATASETS["purchase_orders"]["columns"]) + " FROM public.inventory_records WHERE deleted_at IS NULL AND document_type='进货订单'")
        for profile, allowed in PROFILE_PERMISSIONS.items():
            role = quote("hede_mcp_" + profile)
            if "product.view" in allowed:
                connection.exec_driver_sql(f"GRANT SELECT ON mcp_readonly.product_prices TO {role}")
            if "purchase.view" in allowed:
                connection.exec_driver_sql(f"GRANT SELECT ON mcp_readonly.purchase_orders TO {role}")
        existing = connection.execute(text("""SELECT conname, pg_get_constraintdef(oid) AS definition
            FROM pg_constraint WHERE conrelid='mcp_private.tokens'::regclass AND contype='c'""")).mappings().all()
        profile_constraint = next((row for row in existing if "products" in row["definition"] and "design" in row["definition"]), None)
        if profile_constraint is None:
            raise ValueError("Token范围约束异常，拒绝升级")
        connection.exec_driver_sql(f"ALTER TABLE mcp_private.tokens DROP CONSTRAINT {quote(profile_constraint['conname'])}")
        profiles = ",".join(literal(item) for item in ("products", "design", *PROFILE_PERMISSIONS))
        connection.exec_driver_sql(f"ALTER TABLE mcp_private.tokens ADD CONSTRAINT tokens_profile_check CHECK (profile IN ({profiles}))")
        connection.exec_driver_sql("REVOKE ALL ON ALL TABLES IN SCHEMA mcp_readonly FROM PUBLIC")
        if finalize is not None:
            finalize(created)
        return created


def upgrade_token_expiry(engine) -> bool:
    with engine.begin() as connection:
        connection.exec_driver_sql("SET LOCAL lock_timeout=1000")
        connection.exec_driver_sql("SET LOCAL statement_timeout=5000")
        if connection.scalar(text("SELECT to_regclass('mcp_private.tokens')")) is None:
            raise ValueError("MCP尚未初始化，无法升级Token有效期")
        required = connection.scalar(text("""SELECT attnotnull FROM pg_attribute
            WHERE attrelid='mcp_private.tokens'::regclass AND attname='expires_at' AND NOT attisdropped"""))
        if required is None:
            raise ValueError("Token表缺少expires_at字段，请检查数据库结构")
        if required:
            connection.exec_driver_sql("ALTER TABLE mcp_private.tokens ALTER COLUMN expires_at DROP NOT NULL")
        return bool(required)


def issue_token(engine, username: str, profile: str, days: int | None, label: str) -> tuple[str, int]:
    with engine.begin() as connection:
        result = issue_credential(connection, username=username, profile=profile, days=days, label=label)
        return result["token"], result["item"]["id"]


def main():
    parser = argparse.ArgumentParser(description="仅服务器管理员本地执行；不通过MCP提供账号管理工具")
    subparsers = parser.add_subparsers(dest="command", required=True)
    setup_parser = subparsers.add_parser("setup")
    setup_parser.add_argument("--execute", action="store_true")
    issue = subparsers.add_parser("issue-token")
    issue.add_argument("--username", required=True)
    issue.add_argument("--profile", choices=("products", "design", *PROFILE_PERMISSIONS), default="products")
    expiry = issue.add_mutually_exclusive_group()
    expiry.add_argument("--days", type=int, default=30)
    expiry.add_argument("--permanent", action="store_true", help="永久有效，仍受撤销和账号权限约束")
    issue.add_argument("--label", default="Codex只读查询")
    revoke = subparsers.add_parser("revoke-token")
    revoke.add_argument("--id", type=int, required=True)
    subparsers.add_parser("list-tokens")
    subparsers.add_parser("refresh-views")
    subparsers.add_parser("verify")
    subparsers.add_parser("doctor")
    upgrade = subparsers.add_parser("upgrade-token-expiry")
    upgrade.add_argument("--execute", action="store_true")
    departments = subparsers.add_parser("upgrade-department-scope")
    departments.add_argument("--execute", action="store_true")
    args = parser.parse_args()
    load_dotenv(BACKEND_ROOT / ".env", override=False)
    if args.command == "verify":
        from readonly_mcp.control import ControlRepository
        from readonly_mcp.query import QueryExecutor
        from readonly_mcp.settings import MCPSettings
        settings = MCPSettings.load()
        control, executor = ControlRepository(settings.control_url), QueryExecutor(settings)
        try:
            executor.verify_roles(control)
            print("MCP专用角色校验通过")
        finally:
            control.close()
            executor.close()
        return
    if args.command == "setup" and not args.execute:
        print("预览：新建3个最小权限账号、mcp_readonly视图、mcp_private凭证与审计表；仅追加MCP配置，不改业务数据。执行需加--execute。")
        return
    if args.command == "upgrade-token-expiry" and not args.execute:
        print("预览：仅允许mcp_private.tokens.expires_at为空以支持永久Token，不改变已有Token或账号权限；执行需加--execute。签发永久Token前须更新并重启独立MCP服务。")
        return
    if args.command == "upgrade-department-scope" and not args.execute:
        print("预览：新增四个部门专用最小权限账号、授权业务只读视图及Token范围；不会更改现有Token。执行需加--execute，先停止MCP服务并备份数据库。")
        return
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        raise ValueError("服务器backend/.env缺少DATABASE_URL")
    engine = create_engine(database_url, hide_parameters=True)
    try:
        if args.command == "doctor":
            with engine.begin() as connection:
                connection.exec_driver_sql("SET TRANSACTION READ ONLY")
                connection.exec_driver_sql("SET LOCAL statement_timeout = 5000")
                report = inspect_deployment(connection)
            print(json.dumps(report, ensure_ascii=False, indent=2))
        elif args.command == "setup":
            env_path = BACKEND_ROOT / ".env"
            original = env_path.read_text(encoding="utf-8-sig")
            if re.search(r"(?m)^\s*MCP_(PRODUCTS|DESIGN|CONTROL)_DATABASE_URL\s*=", original):
                raise ValueError("MCP数据库配置已存在，拒绝覆盖")
            passwords = {role: secrets.token_urlsafe(40) for role in ROLES}
            base = make_url(database_url)
            if base.drivername != "postgresql+psycopg" or not base.host or not base.database or base.query:
                raise ValueError("setup要求带主机和库名的postgresql+psycopg URL且不带额外参数；特殊连接由管理员手动配置")
            lines = [f"MCP_{profile.upper()}_DATABASE_URL='{base.set(username=f'hede_mcp_{profile}', password=passwords[f'hede_mcp_{profile}']).render_as_string(hide_password=False)}'" for profile in ("products", "design", "control")]
            if any("'" in value.partition("='")[2][:-1] or "\n" in value or "\r" in value for value in lines):
                raise ValueError("连接串包含不支持的.env字符，请管理员手动配置")
            temporary = env_path.with_name(".env.mcp-pending")
            created = False
            try:
                with temporary.open("x", encoding="utf-8") as stream:
                    created = True
                    protect_config(env_path, temporary)
                    stream.write(original.rstrip() + "\n\n" + "\n".join(lines) + "\n")
                def check_env():
                    if env_path.read_text(encoding="utf-8-sig") != original:
                        raise ValueError("初始化期间.env已改变，数据库操作回滚；请保留用户修改后重试")
                result = setup(engine, passwords, finalize=check_env)
            except Exception:
                if created and temporary.is_file():
                    temporary.unlink()
                raise
            try:
                check_env()
                temporary.replace(env_path)
            except Exception:
                raise ValueError("数据库初始化完成但.env写入失败；凭证保存在backend/.env.mcp-pending，管理员恢复后删除该文件，不要重复setup") from None
            print(json.dumps(result, ensure_ascii=False))
            print("MCP专用连接已写入backend/.env，未显示密码；未签发员工Token或启动服务")
        elif args.command == "issue-token":
            token, token_id = issue_token(engine, args.username, args.profile, None if args.permanent else args.days, args.label)
            expiry_label = "永久有效" if args.permanent else f"有效期{args.days}天"
            print(f"Token ID: {token_id}，{expiry_label}。Token仅显示本次，不要发到聊天或共享日志：")
            print(token)
        elif args.command == "upgrade-token-expiry":
            changed = upgrade_token_expiry(engine)
            print("已升级Token有效期结构，已有Token保持不变" if changed else "Token有效期结构已是新版，无需更改")
            print("签发永久Token前请确认独立MCP服务已更新并重启；无需重新setup或修改隧道配置")
        elif args.command == "upgrade-department-scope":
            env_path = BACKEND_ROOT / ".env"
            original = env_path.read_text(encoding="utf-8-sig")
            if any(re.search(rf"(?m)^\s*MCP_{profile.upper()}_DATABASE_URL\s*=", original) for profile in PROFILE_PERMISSIONS):
                raise ValueError("部门MCP数据库配置已存在，拒绝覆盖")
            base = make_url(database_url)
            if base.drivername != "postgresql+psycopg" or not base.host or not base.database or base.query:
                raise ValueError("升级要求标准postgresql+psycopg URL")
            pending = env_path.with_name(".env.mcp-department-pending")
            if pending.exists():
                raise ValueError("部门MCP恢复文件已存在，先核对配置，不重复升级")
            def finalize(passwords):
                lines = [f"MCP_{profile.upper()}_DATABASE_URL='{base.set(username=f'hede_mcp_{profile}', password=password).render_as_string(hide_password=False)}'" for profile, password in passwords.items()]
                if any("'" in line.partition("='")[2][:-1] or "\n" in line or "\r" in line for line in lines):
                    raise ValueError("连接串包含不支持的.env字符")
                with pending.open("x", encoding="utf-8") as stream:
                    protect_config(env_path, pending)
                    stream.write(original.rstrip() + "\n\n" + "\n".join(lines) + "\n")
                if env_path.read_text(encoding="utf-8-sig") != original:
                    raise ValueError("升级期间.env已改变，请先核对恢复文件")
            try:
                upgrade_department_scope(engine, finalize=finalize)
            except Exception:
                if pending.exists():
                    pending.unlink()
                raise
            if env_path.read_text(encoding="utf-8-sig") != original:
                raise ValueError("数据库已升级但.env发生并发修改；凭证保存在.env.mcp-department-pending，请人工恢复，不重复升级")
            try:
                pending.replace(env_path)
            except Exception:
                raise ValueError("数据库已升级但.env写入失败；凭证保存在.env.mcp-department-pending，请人工恢复，不重复升级") from None
            print("部门MCP角色与视图已升级，连接配置已写入backend/.env；请手动重启独立MCP与中台后端，最后运行verify。未签发或更改现有Token")
        elif args.command == "revoke-token":
            with engine.begin() as connection:
                result = connection.execute(text("UPDATE mcp_private.tokens SET revoked_at=now() WHERE id=:id AND revoked_at IS NULL"), {"id": args.id})
            print(f"已撤销{result.rowcount}个凭证")
        elif args.command == "refresh-views":
            with engine.begin() as connection:
                count = refresh_views(connection)
            print(f"已刷新{count}个商品档案来源的脱敏视图")
        else:
            with engine.connect() as connection:
                rows = connection.execute(text("SELECT id,user_id,label,profile,expires_at,revoked_at FROM mcp_private.tokens ORDER BY id DESC")).mappings().all()
            print(json.dumps([dict(row) for row in rows], ensure_ascii=False, default=str))
    finally:
        engine.dispose()


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        message = str(error) if isinstance(error, ValueError) else type(error).__name__
        raise SystemExit("操作失败：" + message) from None
