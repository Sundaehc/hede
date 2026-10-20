from __future__ import annotations

import argparse
from datetime import datetime
import json
from pathlib import Path

from sqlalchemy import create_engine, text

from config import load_settings


MIGRATION_PATH = Path(__file__).resolve().parents[2] / "database" / "inventory-numeric-capacity-2026-10-20.sql"


def snapshot(connection):
    columns = connection.execute(text("""
        SELECT table_name, column_name, numeric_precision, numeric_scale
        FROM information_schema.columns WHERE table_schema = 'public'
          AND ((table_name = 'inventory_records' AND column_name IN ('total_count', 'amount'))
            OR (table_name = 'inventory_details' AND column_name IN ('quantity', 'unit_price', 'amount')))
        ORDER BY table_name, column_name
    """)).mappings().all()
    views = connection.execute(text("""
        SELECT namespace.nspname AS schema, relation.relname AS name,
            pg_get_userbyid(relation.relowner) AS owner, relation.reloptions,
            pg_get_viewdef(relation.oid, true) AS definition,
            (SELECT jsonb_agg(jsonb_build_object('grantee', acl.grantee, 'grantor', acl.grantor,
                'privilege', acl.privilege_type, 'grantable', acl.is_grantable)
                ORDER BY acl.grantee, acl.grantor, acl.privilege_type, acl.is_grantable)
             FROM aclexplode(coalesce(relation.relacl, acldefault('r', relation.relowner))) acl) AS permissions
        FROM pg_class relation JOIN pg_namespace namespace ON namespace.oid = relation.relnamespace
        WHERE relation.oid IN (
            SELECT rewrite.ev_class FROM pg_depend dependency JOIN pg_rewrite rewrite ON rewrite.oid = dependency.objid
            WHERE dependency.classid = 'pg_rewrite'::regclass AND dependency.refclassid = 'pg_class'::regclass
              AND dependency.refobjid IN ('public.inventory_records'::regclass, 'public.inventory_details'::regclass)
              AND rewrite.ev_class <> dependency.refobjid)
        ORDER BY namespace.nspname, relation.relname
    """)).mappings().all()
    tables = connection.execute(text("""
        SELECT relname, relfilenode FROM pg_class
        WHERE oid IN ('public.inventory_records'::regclass, 'public.inventory_details'::regclass)
        ORDER BY relname
    """)).mappings().all()
    indexes = connection.execute(text("""
        SELECT relation.relname, pg_get_indexdef(indexrelid) AS definition, indisvalid
        FROM pg_index JOIN pg_class relation ON relation.oid = indexrelid
        WHERE indrelid IN ('public.inventory_records'::regclass, 'public.inventory_details'::regclass)
        ORDER BY relation.relname
    """)).mappings().all()
    return {"columns": [dict(row) for row in columns], "views": [dict(row) for row in views],
            "tables": [dict(row) for row in tables], "indexes": [dict(row) for row in indexes]}


def expand(connection):
    connection.execute(text("SET LOCAL search_path = pg_catalog"))
    connection.execute(text("SET LOCAL statement_timeout = '30s'"))
    before = snapshot(connection)
    connection.execute(text(MIGRATION_PATH.read_text(encoding="utf-8")))
    after = snapshot(connection)
    if len(after["columns"]) != 5 or any(
        row["numeric_precision"] != 18 or row["numeric_scale"] != 2 for row in after["columns"]
    ):
        raise RuntimeError("扩容后字段精度校验失败，事务已回滚")
    if any(before[key] != after[key] for key in ("views", "tables", "indexes")):
        raise RuntimeError("扩容后视图、权限、索引或表文件发生非预期变化，事务已回滚")
    return before, after


def main():
    parser = argparse.ArgumentParser(description="经营历程数值精度扩容（默认仅检查）")
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    engine = create_engine(load_settings().database_url)
    report = {"generated_at": datetime.now().astimezone().isoformat(), "execute": args.execute, "committed": False}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    try:
        with engine.connect() as connection:
            report["before"] = snapshot(connection)
            connection.rollback()
            args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
            if args.execute:
                with connection.begin():
                    report["before"], report["after"] = expand(connection)
                report["committed"] = True
                print("经营历程5个数值字段已扩容至 numeric(18,2)，视图及权限核验通过", flush=True)
            else:
                print("只读检查完成，未修改数据库", flush=True)
    except Exception as error:
        report["error"] = f"{type(error).__name__}: {error}"
        raise
    finally:
        args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
        engine.dispose()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
