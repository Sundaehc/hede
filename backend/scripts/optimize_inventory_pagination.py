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


INDEX_NAMES = (
    "idx_inventory_details_missing_amount_document",
    "idx_inventory_details_missing_price_document",
)


def index_statements() -> dict[str, str]:
    return {
        index.name: str(CreateIndex(index).compile(dialect=postgresql.dialect())).replace("CREATE INDEX ", "CREATE INDEX CONCURRENTLY ", 1)
        for index in INVENTORY_DETAIL_TABLE.indexes if index.name in INDEX_NAMES
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Preview or build partial indexes for inventory completion filtering")
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    engine = create_engine(load_settings(require_database=True).database_url)
    report = {"generated_at": datetime.now().astimezone().isoformat(), "execute": args.execute, "indexes": [], "completed": []}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    try:
        with engine.connect().execution_options(isolation_level="AUTOCOMMIT") as connection:
            connection.execute(text("SET lock_timeout = '5s'"))
            connection.execute(text("SET statement_timeout = '5min'"))
            for index_name, statement in sorted(index_statements().items()):
                existing = connection.execute(text("""
                    SELECT index_meta.indisvalid, pg_get_indexdef(index_meta.indexrelid) AS definition
                    FROM pg_index AS index_meta WHERE index_meta.indexrelid=to_regclass(:index_name)
                """), {"index_name": f"public.{index_name}"}).mappings().first()
                expected = {
                    "idx_inventory_details_missing_amount_document": "CREATE INDEX idx_inventory_details_missing_amount_document ON public.inventory_details USING btree (document_id) WHERE ((amount IS NULL) OR (amount = (0)::numeric))",
                    "idx_inventory_details_missing_price_document": "CREATE INDEX idx_inventory_details_missing_price_document ON public.inventory_details USING btree (document_id) WHERE ((unit_price IS NULL) OR (unit_price = (0)::numeric))",
                }[index_name]
                if existing and (not existing["indisvalid"] or existing["definition"] not in {expected, expected.replace("(0)::numeric", "'0'::numeric")}):
                    raise ValueError(f"Index {index_name} is invalid or has a different definition")
                action = {"name": index_name, "statement": statement, "status": "existing" if existing else "pending", "rollback": f"DROP INDEX CONCURRENTLY IF EXISTS public.{index_name}"}
                report["indexes"].append(action)
                args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
                print(f"[PLAN] {action['status']}: {statement}", flush=True)
                if args.execute and not existing:
                    connection.execute(text(statement))
                    action["status"] = "created"
                    report["completed"].append(index_name)
                    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
            if args.execute and report["completed"]:
                connection.execute(text("ANALYZE public.inventory_details"))
    except Exception as exc:
        report["error"] = f"{type(exc).__name__}: {exc}"
        raise
    finally:
        args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        engine.dispose()
    print(f"[OUTPUT] {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
