from __future__ import annotations

import argparse
from datetime import date, datetime, time, timedelta
import json
from pathlib import Path
from uuid import uuid4

from sqlalchemy import create_engine, text

from config import load_settings
from domain.jst_monthly_order_identity import monthly_order_record_key_sql


MISSING_KEY_SQL = "(orders.record_key IS NULL OR btrim(orders.record_key) = '')"
WINDOW_SQL = "orders.order_time_at >= :date_start AND orders.order_time_at < :date_end"
BACKUP_TABLE = "jst_monthly_order_key_repairs"


def date_window(start: date, end: date) -> dict[str, datetime]:
    if end < start:
        raise ValueError("结束日期不能早于开始日期")
    return {
        "date_start": datetime.combine(start, time.min),
        "date_end": datetime.combine(end + timedelta(days=1), time.min),
    }


def audit_record_keys(connection, parameters: dict[str, datetime]) -> dict[str, object]:
    coverage = [dict(row) for row in connection.execute(text(f"""
        SELECT to_char(date_trunc('month', orders.order_time_at), 'YYYY-MM') AS month,
               count(*) AS total, count(*) FILTER (WHERE {MISSING_KEY_SQL}) AS missing
        FROM public.jst_monthly_orders orders WHERE {WINDOW_SQL}
        GROUP BY 1 ORDER BY 1
    """), parameters).mappings()]
    fingerprint = monthly_order_record_key_sql()
    duplicates = dict(connection.execute(text(f"""
        WITH candidates AS (
            SELECT orders.order_time_at,
                   CASE WHEN {MISSING_KEY_SQL} THEN {fingerprint}
                        ELSE orders.record_key END AS next_key
            FROM public.jst_monthly_orders orders WHERE {WINDOW_SQL}
        ), duplicates AS (
            SELECT order_time_at, next_key, count(*) AS total
            FROM candidates GROUP BY 1, 2 HAVING count(*) > 1
        )
        SELECT count(*) AS groups, coalesce(sum(total - 1), 0)::bigint AS extra_rows
        FROM duplicates
    """), parameters).mappings().one())
    coarse = dict(connection.execute(text(f"""
        SELECT count(*) AS groups, coalesce(sum(total - 1), 0)::bigint AS extra_rows
        FROM (
            SELECT count(*) AS total FROM public.jst_monthly_orders orders
            WHERE {WINDOW_SQL}
            GROUP BY internal_order_id, product_code, order_time_at HAVING count(*) > 1
        ) duplicates
    """), parameters).mappings().one())
    return {
        "coverage": coverage,
        "total": sum(int(row["total"]) for row in coverage),
        "missing": sum(int(row["missing"]) for row in coverage),
        "prospective_key_duplicates": duplicates,
        "coarse_duplicates_not_safe_to_delete": coarse,
    }


def apply_record_key_backfill(connection, parameters: dict[str, datetime]) -> dict[str, object]:
    connection.execute(text("LOCK TABLE public.jst_monthly_orders IN SHARE ROW EXCLUSIVE MODE"))
    before = audit_record_keys(connection, parameters)
    if before["prospective_key_duplicates"]["groups"]:
        raise ValueError("新去重键存在冲突，已停止回填；必须先逐组核对，不能直接删除订单")
    if not before["missing"]:
        return {"updated": 0, "before": before, "after": before}
    run_id = str(uuid4())
    connection.execute(text(f"""
        CREATE TABLE IF NOT EXISTS public.{BACKUP_TABLE} (
            run_id text NOT NULL,
            record_id bigint NOT NULL,
            order_time_at timestamp without time zone NOT NULL,
            previous_key text,
            repaired_key text NOT NULL,
            repaired_at timestamp with time zone NOT NULL DEFAULT now(),
            PRIMARY KEY (run_id, record_id, order_time_at)
        )
    """))
    backup_result = connection.execute(text(f"""
        INSERT INTO public.{BACKUP_TABLE} (run_id, record_id, order_time_at, previous_key, repaired_key)
        SELECT :run_id, orders.id, orders.order_time_at, orders.record_key,
               {monthly_order_record_key_sql()}
        FROM public.jst_monthly_orders orders
        WHERE {WINDOW_SQL} AND {MISSING_KEY_SQL}
    """), {**parameters, "run_id": run_id})
    updated_result = connection.execute(text(f"""
        UPDATE public.jst_monthly_orders orders SET record_key = backup.repaired_key
        FROM public.{BACKUP_TABLE} backup
        WHERE backup.run_id = :run_id AND orders.id = backup.record_id
          AND orders.order_time_at = backup.order_time_at
          AND {WINDOW_SQL} AND {MISSING_KEY_SQL}
    """), {**parameters, "run_id": run_id})
    if backup_result.rowcount != before["missing"] or updated_result.rowcount != before["missing"]:
        raise RuntimeError("回填数量与备份数量不一致，事务将回滚")
    after = audit_record_keys(connection, parameters)
    if after["missing"] or after["total"] != before["total"] or after["prospective_key_duplicates"]["groups"]:
        raise RuntimeError("回填后覆盖率、行数或唯一性检查失败，事务将回滚")
    return {"run_id": run_id, "backup_table": BACKUP_TABLE, "updated": updated_result.rowcount, "before": before, "after": after}


def main() -> int:
    parser = argparse.ArgumentParser(description="只回填聚水潭订单缺失去重键；默认只读，不删除订单")
    parser.add_argument("--date-start", type=date.fromisoformat, required=True)
    parser.add_argument("--date-end", type=date.fromisoformat, required=True)
    parser.add_argument("--apply", action="store_true", help="备份原键后在同一事务内回填，不删除订单")
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()
    parameters = date_window(args.date_start, args.date_end)
    settings = load_settings(require_database=True)
    engine = create_engine(settings.database_url, connect_args={"connect_timeout": 10})
    try:
        with engine.begin() as connection:
            connection.execute(text("SET LOCAL lock_timeout = '10s'"))
            connection.execute(text("SET LOCAL statement_timeout = '300s'"))
            if not args.apply:
                connection.execute(text("SET TRANSACTION READ ONLY"))
            report = {
                "mode": "apply" if args.apply else "dry-run",
                "date_start": args.date_start.isoformat(),
                "date_end": args.date_end.isoformat(),
                "result": apply_record_key_backfill(connection, parameters) if args.apply else audit_record_keys(connection, parameters),
            }
        output = json.dumps(report, ensure_ascii=False, indent=2)
        if args.report:
            args.report.parent.mkdir(parents=True, exist_ok=True)
            args.report.write_text(output + "\n", encoding="utf-8")
        print(output)
    finally:
        engine.dispose()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
