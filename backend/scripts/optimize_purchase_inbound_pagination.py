from __future__ import annotations

import argparse
from datetime import datetime
import json
from pathlib import Path

from sqlalchemy import create_engine, text
from sqlalchemy.dialects import postgresql
from sqlalchemy.schema import CreateIndex

from config import load_settings
from domain.inventory_schema import INVENTORY_DETAIL_TABLE


INDEX_NAME = "idx_inventory_details_document_page"


def index_statement() -> str:
    index = next(index for index in INVENTORY_DETAIL_TABLE.indexes if index.name == INDEX_NAME)
    return str(CreateIndex(index).compile(dialect=postgresql.dialect())).replace(" ON inventory_details ", " ON public.inventory_details ", 1)


def normalize_definition(statement: str) -> str:
    return " ".join(statement.replace("CONCURRENTLY ", "").replace("public.", "").split()).rstrip(";")


def main() -> int:
    parser = argparse.ArgumentParser(description="Preview or build the covering index for purchase inbound pagination")
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    statement = index_statement().replace("CREATE INDEX ", "CREATE INDEX CONCURRENTLY ", 1)
    report = {
        "generated_at": datetime.now().astimezone().isoformat(),
        "execute": args.execute,
        "name": INDEX_NAME,
        "statement": statement,
        "rollback": f"DROP INDEX CONCURRENTLY IF EXISTS public.{INDEX_NAME}",
        "status": "pending",
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)

    def save_report() -> None:
        args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    engine = create_engine(load_settings(require_database=True).database_url)
    try:
        with engine.connect().execution_options(isolation_level="AUTOCOMMIT") as connection:
            if connection.dialect.name != "postgresql":
                raise ValueError("Index optimization requires PostgreSQL")
            connection.execute(text("SET lock_timeout = '5s'"))
            connection.execute(text("SET statement_timeout = '5min'"))
            existing = connection.execute(text("""
                SELECT indisvalid, pg_get_indexdef(indexrelid) AS definition
                FROM pg_index WHERE indexrelid = to_regclass(:name)
            """), {"name": f"public.{INDEX_NAME}"}).mappings().first()
            if existing:
                if not existing["indisvalid"] or normalize_definition(existing["definition"]) != normalize_definition(statement):
                    raise ValueError(f"Index {INDEX_NAME} is invalid or has a different definition")
                report["status"] = "existing"
            save_report()
            print(f"[PLAN] {report['status']}: {statement}", flush=True)
            if args.execute and not existing:
                connection.execute(text(statement))
                report["status"] = "created"
                save_report()
                valid = connection.execute(text("SELECT indisvalid FROM pg_index WHERE indexrelid = to_regclass(:name)"),
                                           {"name": f"public.{INDEX_NAME}"}).scalar_one()
                if not valid:
                    raise ValueError(f"Index {INDEX_NAME} is invalid after creation")
                connection.execute(text("ANALYZE public.inventory_details"))
    except Exception as error:
        report["error"] = f"{type(error).__name__}: {error}"
        raise
    finally:
        save_report()
        engine.dispose()
    print(f"[OUTPUT] {args.output}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
