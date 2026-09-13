"""Report partition retention status and optionally mark old partitions as cold."""
from __future__ import annotations

import argparse
import json
from datetime import date
from pathlib import Path

from sqlalchemy import create_engine, text

from config import load_settings


PARTITION_PARENTS = (
    "fine_table_snapshot_rows",
    "product_goods_detail_snapshots",
    "jst_daily_sales",
    "vip_daily_sales",
    "product_goods_historical_sales",
    "product_goods_historical_orders",
)


def _cutoff_date(reference_date: date, hot_months: int) -> date:
    month_index = reference_date.year * 12 + reference_date.month - 1 - hot_months
    year, month_zero_index = divmod(month_index, 12)
    return date(year, month_zero_index + 1, 1)


def _partitions(engine) -> list[dict[str, object]]:
    with engine.connect() as connection:
        rows = connection.execute(
            text(
                """
                SELECT parent.relname AS parent_name,
                       child.relname AS partition_name,
                       pg_get_expr(child.relpartbound, child.oid) AS bound,
                       pg_relation_size(child.oid) AS size_bytes,
                       obj_description(child.oid, 'pg_class') AS comment
                FROM pg_inherits
                JOIN pg_class parent ON parent.oid = inhparent
                JOIN pg_class child ON child.oid = inhrelid
                WHERE parent.relname = ANY(CAST(:parent_names AS text[]))
                ORDER BY parent.relname, child.relname
                """
            ),
            {"parent_names": list(PARTITION_PARENTS)},
        ).mappings()
        return [dict(row) for row in rows]


def _partition_year(partition_name: str) -> int | None:
    suffix = partition_name.rsplit("_", 1)[-1]
    return int(suffix) if len(suffix) == 4 and suffix.isdigit() else None


def main() -> int:
    parser = argparse.ArgumentParser(description="查看并标记历史分区冷热状态")
    parser.add_argument("--hot-months", type=int, default=24, help="热数据保留月数，默认 24")
    parser.add_argument("--reference-date", type=date.fromisoformat, default=date.today())
    parser.add_argument("--apply", action="store_true", help="写入分区冷热注释；默认仅读取报告")
    parser.add_argument("--output", type=Path, default=None, help="可选 JSON 输出路径")
    args = parser.parse_args()
    if args.hot_months < 1:
        raise ValueError("hot_months must be positive")

    settings = load_settings()
    assert settings.database_url is not None
    engine = create_engine(settings.database_url)
    cutoff = _cutoff_date(args.reference_date, args.hot_months)
    partitions = _partitions(engine)
    report: list[dict[str, object]] = []
    for row in partitions:
        partition_year = _partition_year(str(row["partition_name"]))
        partition_end = date(partition_year + 1, 1, 1) if partition_year is not None else None
        tier = "cold" if partition_end is not None and partition_end <= cutoff else "hot"
        report.append({**row, "tier": tier})

    if args.apply:
        with engine.begin() as connection:
            for row in report:
                comment = f"retention_tier={row['tier']}; reviewed_on={args.reference_date.isoformat()}"
                connection.execute(
                    text(f"COMMENT ON TABLE public.{row['partition_name']} IS :comment"),
                    {"comment": comment},
                )

    result = {
        "reference_date": args.reference_date.isoformat(),
        "hot_months": args.hot_months,
        "cutoff_date": cutoff.isoformat(),
        "partitions": report,
    }
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2, default=str), encoding="utf-8")

    hot_count = sum(row["tier"] == "hot" for row in report)
    cold_count = sum(row["tier"] == "cold" for row in report)
    print(f"[DONE] hot={hot_count} cold={cold_count} cutoff={cutoff.isoformat()} apply={args.apply}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
