from __future__ import annotations

import argparse
from datetime import date
import json
from pathlib import Path
import time

from sqlalchemy import create_engine, select, text

from api.routes.fine_table import FineTableFilter, _fine_table_row_matches_filter, _snapshot_payload_filter_conditions
from config import load_settings
from domain.fine_table_snapshot_schema import FINE_TABLE_SNAPSHOT_BATCH_TABLE
from scripts.optimize_query_performance import build_plan
from storage.fine_table_snapshot_dedup import load_optimized_snapshot_rows
from storage.stock_snapshot_queries import load_stock_snapshot_dates


def main() -> int:
    parser = argparse.ArgumentParser(description="Read-only verification of optimized query results")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    engine = create_engine(load_settings().database_url)
    report = {"verified_at": date.today().isoformat()}
    try:
        with engine.connect() as connection:
            connection.execute(text("SET statement_timeout = '15s'"))
            started = time.perf_counter()
            optimized_dates = load_stock_snapshot_dates(connection)
            report["stock_dates_optimized_ms"] = round((time.perf_counter() - started) * 1000, 3)
            started = time.perf_counter()
            original_dates = list(connection.execute(text(
                "SELECT DISTINCT snapshot_date FROM public.jst_size_stock_snapshots ORDER BY snapshot_date DESC"
            )).scalars())
            report["stock_dates_original_ms"] = round((time.perf_counter() - started) * 1000, 3)
            if original_dates != optimized_dates:
                raise AssertionError("Stock snapshot date lists differ")
            report["stock_dates_count"] = len(optimized_dates)
            report["stock_dates_equal"] = True
            batch = connection.execute(
                select(FINE_TABLE_SNAPSHOT_BATCH_TABLE)
                .where(FINE_TABLE_SNAPSHOT_BATCH_TABLE.c.brand == "cbanner_mens")
                .order_by(FINE_TABLE_SNAPSHOT_BATCH_TABLE.c.snapshot_date.desc())
                .limit(1)
            ).mappings().first()
            remaining = build_plan(connection, drop_redundant=True)
            report["remaining_schema_actions"] = [action.kind for action in remaining if action.kind != "vacuum"]
            if report["remaining_schema_actions"]:
                raise AssertionError("Optimization schema actions remain")
        if batch:
            started = time.perf_counter()
            rows, total = load_optimized_snapshot_rows(
                engine, batch["snapshot_date"], batch["id"], conditions=[], page=1, page_size=1000000,
            )
            report["snapshot_full_load_ms"] = round((time.perf_counter() - started) * 1000, 3)
            checks = []
            for field in ("factory_name", "season_category", "group_name", "sales_tag", "goods_tag"):
                value = next((str(row[field]).strip() for row in rows if row.get(field)), "")
                for operator in ("in", "not_in"):
                    condition = FineTableFilter(field=field, operator=operator, values=[value])
                    sql_conditions = _snapshot_payload_filter_conditions((condition,))
                    if sql_conditions is None:
                        continue
                    expected = [row for row in rows if _fine_table_row_matches_filter(row, condition)]
                    for page in (1, 2):
                        started = time.perf_counter()
                        items, filtered_total = load_optimized_snapshot_rows(
                            engine, batch["snapshot_date"], batch["id"], conditions=[],
                            payload_conditions=sql_conditions, page=page, page_size=80,
                        )
                        elapsed_ms = round((time.perf_counter() - started) * 1000, 3)
                        if filtered_total != len(expected) or items != expected[(page - 1) * 80:page * 80]:
                            raise AssertionError(f"Snapshot filter differs: {field} {operator}, page {page}")
                        checks.append({"field": field, "operator": operator, "page": page, "total": filtered_total, "elapsed_ms": elapsed_ms})
            report["snapshot_batch_id"] = batch["id"]
            report["snapshot_row_count"] = total
            report["snapshot_filter_checks"] = checks
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0
    finally:
        engine.dispose()


if __name__ == "__main__":
    raise SystemExit(main())
