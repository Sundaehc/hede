"""Import the JST and VIP raw daily sales reports into annual tables.

Run: python -m scripts.import_daily_sales_reports
"""
from __future__ import annotations

import argparse
import traceback
from datetime import date
from pathlib import Path

from config import load_settings
from scripts.backfill_product_goods_annual_sales import backfill as backfill_product_goods_sales
from storage.daily_sales_repository import DailySalesRepository, JST_FILE_NAME, VIP_FILE_NAME
from storage.factory_channel_sales_summary_repository import FactoryChannelSalesSummaryRepository
from storage.task_status_repository import ScheduledTaskStatusRepository


def _record_status(status_repo: ScheduledTaskStatusRepository, task_name: str, result: dict[str, object], source_file: Path) -> None:
    dates = [date.fromisoformat(value) for value in result.get("sales_dates", [])]
    for business_date in dates:
        status_repo.mark_running(task_name, business_date, source_path=source_file)
        status_repo.mark_finished(
            task_name,
            business_date,
            status="success",
            message=f"Imported {result.get('upserted', 0)} rows",
            result=result,
            source_path=source_file,
        )


def main() -> int:
    parser = argparse.ArgumentParser(description="Import JST and VIP daily sales reports")
    parser.add_argument("--source-root", type=Path, default=None)
    parser.add_argument("--jst-file", type=Path, default=None)
    parser.add_argument("--vip-file", type=Path, default=None)
    parser.add_argument("--source", choices=("all", "jst", "vip"), default="all")
    parser.add_argument(
        "--skip-product-goods-refresh",
        action="store_true",
        help="跳过年度/月度货品销量周期刷新，由后续数据源任务统一刷新",
    )
    args = parser.parse_args()

    settings = load_settings(require_database=True)
    assert settings.database_url is not None
    root = args.source_root or settings.daily_sales_report_root
    assert root is not None, "DAILY_SALES_REPORT_ROOT is required"
    files = [
        ("import_jst_daily_sales", args.jst_file or root / JST_FILE_NAME, "jst"),
        ("import_vip_daily_sales", args.vip_file or root / VIP_FILE_NAME, "vip"),
    ]
    if args.source != "all":
        files = [item for item in files if item[2] == args.source]
    repository = DailySalesRepository(settings.database_url)
    status_repo = ScheduledTaskStatusRepository(settings.database_url)
    failed = False
    imported_any = False
    imported_dates: set[date] = set()
    for task_name, source_file, source in files:
        try:
            result = repository.import_jst_daily_sales(source_file) if source == "jst" else repository.import_vip_daily_sales(source_file)
            _record_status(status_repo, task_name, result, source_file)
            imported_any = True
            imported_dates.update(
                date.fromisoformat(value)
                for value in result.get("sales_dates", [])
            )
            print(f"[OK] {source_file.name}: {result}")
        except Exception as exc:  # pragma: no cover - scheduled task diagnostics
            failed = True
            print(f"[FAILED] {source_file}: {type(exc).__name__}: {exc}\n{traceback.format_exc()}")
    if imported_any:
        try:
            summary_repository = FactoryChannelSalesSummaryRepository(settings.database_url)
            dates_by_year: dict[int, set[date]] = {}
            for imported_date in imported_dates or {date.today()}:
                dates_by_year.setdefault(imported_date.year, set()).add(imported_date)
            for summary_year, summary_dates in sorted(dates_by_year.items()):
                summary_result = summary_repository.refresh(
                    sales_year=summary_year,
                    date_start=min(summary_dates),
                    date_end=max(summary_dates),
                )
                print(f"[OK] refreshed factory-channel summary: {summary_result}")
        except Exception as exc:  # pragma: no cover - scheduled task diagnostics
            failed = True
            print(
                "[FAILED] factory-channel summary refresh: "
                f"{type(exc).__name__}: {exc}\n{traceback.format_exc()}"
            )
        if not args.skip_product_goods_refresh:
            try:
                stats = backfill_product_goods_sales(dry_run=False, sales_years={date.today().year})
                print(
                    "[OK] refreshed product-goods sales periods: "
                    f"annual={stats.written_rows[(date.today().year, 'year')]} "
                    f"monthly={stats.written_rows[(date.today().year, 'month')]} "
                    f"preserved={stats.skipped_authoritative_rows}"
                )
            except Exception as exc:  # pragma: no cover - scheduled task diagnostics
                failed = True
                print(
                    "[FAILED] product-goods sales period refresh: "
                    f"{type(exc).__name__}: {exc}\n{traceback.format_exc()}"
                )
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
