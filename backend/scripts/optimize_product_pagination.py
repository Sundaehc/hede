from __future__ import annotations

import argparse
from datetime import datetime
import json
from pathlib import Path
import re

from sqlalchemy import create_engine, text

from config import load_settings


PARENT_INDEX = "idx_jst_aftersale_returns_original_code_pattern"


def normalize_index_definition(statement: str) -> str:
    normalized = statement.replace("CONCURRENTLY ", "").replace("public.", "").replace('"', "")
    return " ".join(normalized.split()).rstrip(";")


def build_index_plan(partitions: list[str], *, partitioned: bool) -> list[dict[str, object]]:
    plan = []
    targets = [
        ("gj_merged_product_info", "idx_gj_merged_product_info_source_brand_code",
         "source_date_value, fine_table_brand, goods_code", " INCLUDE (id)"),
        ("product_goods_sales_periods", "idx_product_goods_sales_period_brand_product_pattern",
         "brand, product_code text_pattern_ops", ""),
    ]
    if partitioned:
        targets.extend((table_name, f"idx_{table_name}_original_code_pattern",
                        "original_goods_code text_pattern_ops", "") for table_name in partitions)
    else:
        targets.append(("jst_aftersale_returns", PARENT_INDEX, "original_goods_code text_pattern_ops", ""))
    for table_name, index_name, columns, suffix in targets:
        if not all(re.fullmatch("[a-z_][a-z_0-9]*", name) and len(name) <= 63 for name in (table_name, index_name)):
            raise ValueError("Unsupported table or index name")
        definition = f"CREATE INDEX {index_name} ON public.{table_name} USING btree ({columns}){suffix}"
        plan.append({"name": index_name, "table": table_name, "partitioned": False,
                     "definition": definition, "statement": definition.replace("CREATE INDEX ", "CREATE INDEX CONCURRENTLY ", 1),
                     "rollback": f"DROP INDEX CONCURRENTLY IF EXISTS public.{index_name}"})
    if partitioned:
        definition = f"CREATE INDEX {PARENT_INDEX} ON ONLY public.jst_aftersale_returns USING btree (original_goods_code text_pattern_ops)"
        plan.append({"name": PARENT_INDEX, "table": "jst_aftersale_returns", "partitioned": True,
                     "definition": definition, "statement": definition,
                     "rollback": f"DROP INDEX IF EXISTS public.{PARENT_INDEX}",
                     "attachments": [f"ALTER INDEX public.{PARENT_INDEX} ATTACH PARTITION public.idx_{table_name}_original_code_pattern" for table_name in partitions]})
    return plan


def main() -> int:
    parser = argparse.ArgumentParser(description="Preview or create indexes for product goods and fine-table pagination")
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    report = {"generated_at": datetime.now().astimezone().isoformat(), "execute": args.execute,
              "indexes": [], "completed": [], "attachments": []}
    engine = create_engine(load_settings(require_database=True).database_url)

    def save_report():
        args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    try:
        with engine.connect().execution_options(isolation_level="AUTOCOMMIT") as connection:
            if connection.dialect.name != "postgresql":
                raise ValueError("Index optimization requires PostgreSQL")
            connection.execute(text("SET lock_timeout = '5s'"))
            connection.execute(text("SET statement_timeout = '5min'"))
            partitioned = connection.execute(text("SELECT relkind = 'p' FROM pg_class WHERE oid='public.jst_aftersale_returns'::regclass")).scalar_one()
            partitions = []
            if partitioned:
                partition_rows = connection.execute(text("""
                    SELECT namespace.nspname AS schema, relation.relname AS name, tree.level, tree.isleaf
                    FROM pg_partition_tree('public.jst_aftersale_returns') tree
                    JOIN pg_class relation ON relation.oid=tree.relid
                    JOIN pg_namespace namespace ON namespace.oid=relation.relnamespace
                    WHERE tree.level > 0 ORDER BY relation.relname
                """)).mappings().all()
                if any(row["schema"] != "public" or row["level"] != 1 or not row["isleaf"] for row in partition_rows):
                    raise ValueError("Only direct public-schema leaf partitions are supported")
                partitions = [row["name"] for row in partition_rows]
            report["indexes"] = build_index_plan(partitions, partitioned=partitioned)
            for action in report["indexes"]:
                existing = connection.execute(text("""
                    SELECT index_meta.indisvalid, pg_get_indexdef(index_meta.indexrelid) AS definition
                    FROM pg_index index_meta WHERE index_meta.indexrelid=to_regclass(:name)
                """), {"name": f"public.{action['name']}"}).mappings().first()
                if existing:
                    if normalize_index_definition(existing["definition"]) != normalize_index_definition(action["definition"]):
                        raise ValueError(f"Existing index definition differs: {action['name']}")
                    if not existing["indisvalid"] and not action["partitioned"]:
                        raise ValueError(f"Existing index is invalid: {action['name']}")
                action["status"] = "existing" if existing else "pending"
            save_report()
            for action in report["indexes"]:
                print(f"[PLAN] {action['status']}: {action['statement']}", flush=True)
                if args.execute and action["status"] == "pending":
                    connection.execute(text(action["statement"]))
                    action["status"] = "created"
                    report["completed"].append(action["name"])
                    save_report()
                if args.execute:
                    for statement in action.get("attachments", []):
                        child_name = statement.rsplit(".", 1)[1]
                        attached = connection.execute(text("""
                            SELECT EXISTS (SELECT 1 FROM pg_inherits
                            WHERE inhparent=to_regclass(:parent) AND inhrelid=to_regclass(:child))
                        """), {"parent": f"public.{PARENT_INDEX}", "child": f"public.{child_name}"}).scalar_one()
                        if attached:
                            continue
                        connection.execute(text(statement))
                        report["attachments"].append(statement)
                        save_report()
            if args.execute:
                for action in report["indexes"]:
                    valid = connection.execute(text("SELECT indisvalid FROM pg_index WHERE indexrelid=to_regclass(:name)"),
                                               {"name": f"public.{action['name']}"}).scalar_one()
                    if not valid:
                        raise ValueError(f"Index is not valid after execution: {action['name']}")
                if report["completed"]:
                    for table_name in ("gj_merged_product_info", "product_goods_sales_periods", "jst_aftersale_returns"):
                        connection.execute(text(f"ANALYZE public.{table_name}"))
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
