from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
from datetime import date, datetime
import json
from pathlib import Path
import re

from sqlalchemy import create_engine, text

from config import load_settings


DUPLICATE_INDEXES_SQL = """
SELECT table_meta.relname AS table_name, candidate.relname AS index_name,
       pg_relation_size(candidate.oid) AS size_bytes,
       pg_get_indexdef(candidate.oid) AS definition,
       replacement.relname AS replacement_index
FROM pg_index AS candidate_index
JOIN pg_class AS candidate ON candidate.oid = candidate_index.indexrelid
JOIN pg_class AS table_meta ON table_meta.oid = candidate_index.indrelid
JOIN pg_namespace AS namespace ON namespace.oid = table_meta.relnamespace
JOIN pg_index AS replacement_index
  ON replacement_index.indrelid = candidate_index.indrelid
 AND replacement_index.indexrelid <> candidate_index.indexrelid
 AND replacement_index.indkey = candidate_index.indkey
 AND replacement_index.indclass = candidate_index.indclass
 AND replacement_index.indcollation = candidate_index.indcollation
 AND replacement_index.indoption = candidate_index.indoption
 AND replacement_index.indnkeyatts = candidate_index.indnkeyatts
 AND replacement_index.indnatts = candidate_index.indnatts
 AND coalesce(replacement_index.indexprs::text, '') = coalesce(candidate_index.indexprs::text, '')
 AND coalesce(replacement_index.indpred::text, '') = coalesce(candidate_index.indpred::text, '')
JOIN pg_class AS replacement ON replacement.oid = replacement_index.indexrelid
WHERE namespace.nspname = 'public' AND table_meta.relkind = 'r'
  AND NOT candidate_index.indisunique AND NOT candidate_index.indisprimary
  AND candidate_index.indisvalid AND replacement_index.indisvalid
  AND replacement_index.indisunique AND replacement.relam = candidate.relam
  AND NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conindid = candidate.oid)
  AND NOT EXISTS (SELECT 1 FROM pg_inherits WHERE inhrelid = candidate.oid)
ORDER BY pg_relation_size(candidate.oid) DESC
"""
REDUNDANT_INDEX_PATTERN = re.compile(
    r"^(?:idx_fine_table_snapshot_refs_[0-9]{4}_batch_row_index|"
    r"idx_jst_stock_summary_snapshots_date_code|"
    r"idx_product_goods_detail_snapshot_batches_brand_date|"
    r"idx_inventory_account_subjects_name|idx_purchase_order_requirement_brand)$"
)
AUTOVACUUM_OPTIONS = {
    "autovacuum_vacuum_scale_factor": "0.02",
    "autovacuum_vacuum_threshold": "1000",
    "autovacuum_analyze_scale_factor": "0.01",
    "autovacuum_analyze_threshold": "1000",
}


@dataclass(frozen=True)
class OptimizationAction:
    kind: str
    table_name: str
    statement: str
    rollback: str | None = None
    reclaimed_bytes: int = 0


def _quote(identifier: str) -> str:
    if not re.fullmatch(r"[a-z_][a-z0-9_]*", identifier):
        raise ValueError(f"Unsafe SQL identifier: {identifier}")
    return f'"{identifier}"'


def _public_name(identifier: str) -> str:
    return f'"public".{_quote(identifier)}'


def _existing_index(connection, index_name: str):
    return connection.execute(text("""
        SELECT pg_get_indexdef(index_meta.indexrelid) AS definition, index_meta.indisvalid
        FROM pg_index AS index_meta
        WHERE index_meta.indexrelid = to_regclass(:index_name)
    """), {"index_name": f"public.{index_name}"}).mappings().first()


def _index_action(connection, table_name: str, index_name: str, columns: str):
    expected = f"CREATE INDEX {index_name} ON public.{table_name} USING btree ({columns})"
    existing = _existing_index(connection, index_name)
    if existing:
        if not existing["indisvalid"] or existing["definition"] != expected:
            raise ValueError(f"Index {index_name} is invalid or differs from the expected definition")
        return None
    return OptimizationAction(
        "create_index", table_name,
        f"CREATE INDEX CONCURRENTLY {_quote(index_name)} ON {_public_name(table_name)} ({columns})",
        f"DROP INDEX CONCURRENTLY IF EXISTS {_public_name(index_name)}",
    )


def build_plan(connection, *, drop_redundant: bool = False) -> list[OptimizationAction]:
    if connection.dialect.name != "postgresql":
        raise ValueError("Query optimization requires PostgreSQL")
    tables = {
        row["relname"]: dict(row)
        for row in connection.execute(text("""
            SELECT relation.relname, relation.reloptions
            FROM pg_class AS relation
            JOIN pg_namespace AS namespace ON namespace.oid = relation.relnamespace
            WHERE namespace.nspname = 'public' AND relation.relkind = 'r'
        """)).mappings()
    }
    actions = []
    if "jst_product_price" in tables:
        action = _index_action(
            connection, "jst_product_price", "idx_jst_price_code_date_nulls_last_updated",
            "goods_code, source_date_value DESC NULLS LAST, updated_at DESC, id DESC",
        )
        if action:
            actions.append(action)
    for table_name in sorted(tables):
        if re.fullmatch(r"(?:jst|vip)_daily_sales_[0-9]{4}", table_name) and table_name.endswith(f"_{date.today().year}"):
            action = _index_action(connection, table_name, f"idx_{table_name}_style_date", "style_code, sales_date")
            if action:
                actions.append(action)
    maintenance_tables = {
        f"jst_daily_sales_{date.today().year}", "jst_product_price",
        "fine_table_snapshot_payloads", "fine_table_snapshot_metrics",
        f"fine_table_snapshot_refs_{date.today().year}",
    }
    for table_name in sorted(maintenance_tables & tables.keys()):
        previous = dict(option.split("=", 1) for option in tables[table_name]["reloptions"] or [])
        changes = {key: value for key, value in AUTOVACUUM_OPTIONS.items() if previous.get(key) != value}
        if not changes:
            continue
        settings = ", ".join(f"{key}={value}" for key, value in changes.items())
        restore = {key: previous[key] for key in changes if key in previous}
        reset = [key for key in changes if key not in previous]
        rollback = []
        if restore:
            rollback.append(f"ALTER TABLE {_public_name(table_name)} SET ({', '.join(f'{key}={value}' for key, value in restore.items())});")
        if reset:
            rollback.append(f"ALTER TABLE {_public_name(table_name)} RESET ({', '.join(reset)});")
        actions.append(OptimizationAction(
            "maintenance_options", table_name,
            f"ALTER TABLE {_public_name(table_name)} SET ({settings})", "\n".join(rollback),
        ))
    if drop_redundant:
        for row in connection.execute(text(DUPLICATE_INDEXES_SQL)).mappings():
            if not REDUNDANT_INDEX_PATTERN.fullmatch(row["index_name"]):
                continue
            actions.append(OptimizationAction(
                "drop_duplicate_index", row["table_name"],
                f"DROP INDEX CONCURRENTLY IF EXISTS {_public_name(row['index_name'])}",
                row["definition"].replace("CREATE INDEX ", "CREATE INDEX CONCURRENTLY ", 1),
                int(row["size_bytes"]),
            ))
        old_price_index = _existing_index(connection, "idx_jst_price_code_date_updated")
        expected_old = "CREATE INDEX idx_jst_price_code_date_updated ON public.jst_product_price USING btree (goods_code, source_date_value DESC, updated_at DESC, id DESC)"
        if old_price_index and old_price_index["indisvalid"] and old_price_index["definition"] == expected_old:
            actions.append(OptimizationAction(
                "drop_replaced_index", "jst_product_price",
                'DROP INDEX CONCURRENTLY IF EXISTS "public"."idx_jst_price_code_date_updated"',
                expected_old.replace("CREATE INDEX ", "CREATE INDEX CONCURRENTLY ", 1),
            ))
    daily_table = f"jst_daily_sales_{date.today().year}"
    if daily_table in tables:
        actions.append(OptimizationAction("vacuum", daily_table, f"VACUUM (ANALYZE) {_public_name(daily_table)}"))
    return actions


def execute_plan(connection, actions: list[OptimizationAction], report: dict, output: Path) -> None:
    connection.execute(text("SET lock_timeout = '5s'"))
    connection.execute(text("SET statement_timeout = '15min'"))
    connection.execute(text("SET maintenance_work_mem = '64MB'"))
    for action in actions:
        print(f"[RUN] {action.kind}: {action.table_name}", flush=True)
        connection.execute(text(action.statement))
        report["completed"].append(asdict(action))
        output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Preview or apply verified query optimizations")
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--drop-redundant", action="store_true")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    engine = create_engine(load_settings().database_url)
    generated_at = datetime.now().astimezone()
    output = args.output or Path(__file__).resolve().parents[2] / "outputs" / f"database-query-optimization-{generated_at:%Y%m%d-%H%M%S}.json"
    report = {"generated_at": generated_at.isoformat(), "execute": args.execute, "completed": []}
    try:
        with engine.connect().execution_options(isolation_level="AUTOCOMMIT") as connection:
            actions = build_plan(connection, drop_redundant=args.drop_redundant)
            report["actions"] = [asdict(action) for action in actions]
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
            for action in actions:
                print(f"[PLAN] {action.statement}")
            if args.execute:
                execute_plan(connection, actions, report, output)
    except Exception as exc:
        report["error"] = f"{type(exc).__name__}: {exc}"
        if output.parent.exists():
            output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        raise
    finally:
        engine.dispose()
    print(f"[OUTPUT] {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
