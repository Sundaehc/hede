"""Preview or install warehouse query indexes and transactional invalidation."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from sqlalchemy import create_engine, text

from config import load_settings
from domain.warehouse_inventory_revision_schema import CAPABILITIES_SQL, SOURCE_TABLES, install_revision_tracking


INDEX_NAME = "idx_inventory_details_warehouse_stock"
INDEX_SQL = (
    f"CREATE INDEX CONCURRENTLY IF NOT EXISTS {INDEX_NAME} ON public.inventory_details "
    "(document_id) INCLUDE (product_code, product_name, color_name, color_spec, quantity)"
)
EXPECTED_DEFINITION = (
    f"CREATE INDEX {INDEX_NAME} ON public.inventory_details USING btree (document_id) "
    "INCLUDE (product_code, product_name, color_name, color_spec, quantity)"
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--execute", action="store_true", help="Apply changes; default is read-only preview")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    report = {"execute": args.execute, "index_sql": INDEX_SQL, "sources": list(SOURCE_TABLES)}
    engine = create_engine(load_settings(require_database=True).database_url, pool_size=1, max_overflow=0)
    try:
        with engine.connect().execution_options(isolation_level="AUTOCOMMIT") as connection:
            if connection.dialect.name != "postgresql":
                raise ValueError("Warehouse query preparation requires PostgreSQL")
            connection.execute(text("SET lock_timeout = '5s'"))
            connection.execute(text("SET statement_timeout = '180s'"))
            connection.execute(text("SET maintenance_work_mem = '32MB'"))
            connection.execute(text("SET max_parallel_maintenance_workers = 0"))
            index = connection.execute(text(
                "SELECT indisvalid, indisready, pg_get_indexdef(indexrelid) AS definition "
                "FROM pg_index WHERE indexrelid = to_regclass(:index)"
            ), {"index": "public." + INDEX_NAME}).mappings().first()
            if index is not None and (not index["indisvalid"] or index["definition"] != EXPECTED_DEFINITION):
                raise ValueError("Existing warehouse index is invalid or has a different definition; inspect before retrying")
            report["before"] = dict(connection.execute(CAPABILITIES_SQL).mappings().one())
            if args.execute:
                connection.execute(text(INDEX_SQL))
        if args.execute:
            # Trigger changes are atomic, bounded by a short lock wait.
            with engine.begin() as connection:
                connection.execute(text("SET LOCAL lock_timeout = '5s'"))
                connection.execute(text("SET LOCAL statement_timeout = '15s'"))
                install_revision_tracking(connection)
        with engine.connect() as connection:
            report["after"] = dict(connection.execute(CAPABILITIES_SQL).mappings().one())
    finally:
        engine.dispose()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=True), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
