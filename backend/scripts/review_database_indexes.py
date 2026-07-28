"""Generate a conservative index review report without changing indexes."""
from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path

from sqlalchemy import create_engine, text

from config import load_settings


INDEX_REVIEW_SQL = """
SELECT
    stats.schemaname,
    stats.relname AS table_name,
    stats.indexrelname AS index_name,
    stats.idx_scan,
    stats.idx_tup_read,
    stats.idx_tup_fetch,
    index_meta.indisunique AS is_unique,
    index_meta.indisprimary AS is_primary,
    constraint_meta.contype AS constraint_type,
    pg_size_pretty(pg_relation_size(index_meta.indexrelid)) AS index_size,
    pg_relation_size(index_meta.indexrelid) AS index_size_bytes,
    pg_get_indexdef(index_meta.indexrelid) AS index_definition
FROM pg_stat_user_indexes AS stats
JOIN pg_index AS index_meta ON index_meta.indexrelid = stats.indexrelid
LEFT JOIN pg_constraint AS constraint_meta ON constraint_meta.conindid = stats.indexrelid
WHERE stats.schemaname = 'public'
ORDER BY pg_relation_size(index_meta.indexrelid) DESC, stats.relname, stats.indexrelname
"""


def _recommendation(row: dict[str, object]) -> str:
    if bool(row["is_primary"]) or row["constraint_type"] in {"p", "u", "x"}:
        return "retain_constraint"
    if bool(row["is_unique"]):
        return "retain_unique"
    if int(row["idx_scan"] or 0) > 0:
        return "retain_observed_usage"
    return "review_with_explain"


def _slow_query_summary(connection) -> list[dict[str, object]]:
    extension_exists = connection.execute(
        text("SELECT EXISTS (SELECT 1 FROM pg_extension WHERE extname = 'pg_stat_statements')")
    ).scalar_one()
    if not extension_exists:
        return []
    rows = connection.execute(
        text(
            """
            SELECT calls,
                   round(total_exec_time::numeric, 2) AS total_exec_ms,
                   round(mean_exec_time::numeric, 2) AS mean_exec_ms,
                   rows,
                   left(regexp_replace(query, '\\s+', ' ', 'g'), 500) AS query
            FROM pg_stat_statements
            WHERE dbid = (SELECT oid FROM pg_database WHERE datname = current_database())
            ORDER BY total_exec_time DESC
            LIMIT 20
            """
        )
    ).mappings()
    return [dict(row) for row in rows]


def main() -> int:
    parser = argparse.ArgumentParser(description="生成索引复核报告，不会创建、删除或重建索引")
    parser.add_argument("--output", type=Path, default=None, help="可选 JSON 输出路径")
    args = parser.parse_args()

    settings = load_settings()
    assert settings.database_url is not None
    engine = create_engine(settings.database_url)
    with engine.connect() as connection:
        rows = [dict(row) for row in connection.execute(text(INDEX_REVIEW_SQL)).mappings()]
        slow_queries = _slow_query_summary(connection)
        stats_reset = connection.execute(text("SELECT stats_reset FROM pg_stat_database WHERE datname = current_database()")).scalar_one()

    for row in rows:
        row["recommendation"] = _recommendation(row)
    report = {
        "generated_at": datetime.now().astimezone().isoformat(),
        "stats_reset": stats_reset.isoformat() if stats_reset else None,
        "indexes": rows,
        "slow_queries": slow_queries,
    }
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2, default=str), encoding="utf-8")

    review_count = sum(row["recommendation"] == "review_with_explain" for row in rows)
    print(f"[DONE] indexes={len(rows)} review_with_explain={review_count} slow_queries={len(slow_queries)}")
    if args.output:
        print(f"[OUTPUT] {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
