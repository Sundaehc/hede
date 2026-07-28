"""Refresh planner statistics for high-volume operational tables."""
from __future__ import annotations

import argparse
import time
import traceback
from datetime import date

from sqlalchemy import create_engine, inspect, text

from config import load_settings
from storage.task_status_repository import ScheduledTaskStatusRepository


TASK_NAME = "database_maintenance"
ANALYZE_TABLES = (
    "fine_table_snapshot_rows_2024",
    "fine_table_snapshot_rows_2025",
    "fine_table_snapshot_rows_2026",
    "product_goods_detail_snapshots_2024",
    "product_goods_detail_snapshots_2025",
    "product_goods_detail_snapshots_2026",
    "vip_product_ops_snapshots",
    "vip_product_daily_snapshots",
    "vip_daily_sales_2026",
    "jst_daily_sales_2026",
    "jst_daily_stock",
    "jst_monthly_orders",
    "jst_product_price",
    "gj_merged_product_info",
)


def _existing_analyze_tables(engine) -> tuple[str, ...]:
    inspector = inspect(engine)
    return tuple(table_name for table_name in ANALYZE_TABLES if inspector.has_table(table_name))


def main() -> int:
    parser = argparse.ArgumentParser(description="更新高频业务表统计信息")
    parser.add_argument("--business-date", type=date.fromisoformat, default=date.today())
    parser.add_argument("--force", action="store_true", help="当天已成功时仍执行")
    args = parser.parse_args()

    settings = load_settings()
    assert settings.database_url is not None
    status_repository = ScheduledTaskStatusRepository(settings.database_url)
    if not args.force and status_repository.is_success(TASK_NAME, args.business_date):
        print(f"[SKIP] {args.business_date.isoformat()} already succeeded")
        return 0

    status_repository.mark_running(TASK_NAME, args.business_date)
    started_at = time.perf_counter()
    try:
        engine = create_engine(settings.database_url)
        table_names = _existing_analyze_tables(engine)
        with engine.connect().execution_options(isolation_level="AUTOCOMMIT") as connection:
            for table_name in table_names:
                connection.execute(text(f"ANALYZE public.{table_name}"))
        elapsed_seconds = round(time.perf_counter() - started_at, 2)
        result = {"analyzed_tables": list(table_names), "elapsed_seconds": elapsed_seconds}
        status_repository.mark_finished(
            TASK_NAME,
            args.business_date,
            status="success",
            message=f"统计信息更新完成: {len(table_names)} 张表，耗时 {elapsed_seconds} 秒",
            result=result,
        )
        print(f"[DATABASE_MAINTENANCE] analyzed {len(table_names)} tables in {elapsed_seconds}s")
        return 0
    except Exception as exc:  # pragma: no cover - logged for scheduled task diagnosis
        status_repository.mark_finished(
            TASK_NAME,
            args.business_date,
            status="failed",
            message=f"{type(exc).__name__}: {exc}",
            result={"traceback": traceback.format_exc()},
        )
        print(f"[FAILED] {type(exc).__name__}: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
