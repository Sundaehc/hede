"""Import the JST and VIP raw daily sales reports into annual tables.

Run: python -m scripts.import_daily_sales_reports
"""
from __future__ import annotations

import argparse
import time
import traceback
from datetime import date, datetime, time as day_time, timedelta
from pathlib import Path

from config import load_settings
from scripts.backfill_product_goods_annual_sales import backfill as backfill_product_goods_sales
from storage.daily_sales_repository import DailySalesRepository, JST_FILE_NAME, VIP_FILE_NAME
from storage.factory_channel_sales_summary_repository import FactoryChannelSalesSummaryRepository
from storage.task_status_repository import ScheduledTaskStatusRepository


def _parse_retry_until(value: str | None) -> datetime | None:
    if not value:
        return None
    return datetime.combine(date.today(), day_time.fromisoformat(value))


def _sales_dates(result: dict[str, object]) -> set[date]:
    values = result.get("sales_dates", [])
    if not isinstance(values, (list, tuple, set)):
        return set()
    return {date.fromisoformat(str(value)) for value in values}


def _record_status(
    status_repo: ScheduledTaskStatusRepository,
    task_name: str,
    result: dict[str, object],
    source_file: Path,
    sales_dates: set[date],
    *,
    running_date: date | None = None,
) -> None:
    for business_date in sales_dates:
        if business_date != running_date:
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
    expected_date_group = parser.add_mutually_exclusive_group()
    expected_date_group.add_argument(
        "--require-previous-day",
        action="store_true",
        help="要求源文件必须包含昨天的销售日期，适用于每日计划任务",
    )
    expected_date_group.add_argument(
        "--expected-sales-date",
        type=date.fromisoformat,
        default=None,
        help="要求源文件包含指定销售日期，适用于手工补历史数据",
    )
    parser.add_argument("--retry-until", default=None, help="目标销售日期未就绪时重试到本地时间 HH:MM")
    parser.add_argument("--retry-interval-seconds", type=int, default=1800, help="重试间隔秒数")
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
    expected_sales_date = args.expected_sales_date
    if args.require_previous_day:
        expected_sales_date = date.today() - timedelta(days=1)
    retry_until = _parse_retry_until(args.retry_until)

    repository = DailySalesRepository(settings.database_url)
    status_repo = ScheduledTaskStatusRepository(settings.database_url)
    imported_any = False
    imported_dates: set[date] = set()
    pending_files = files
    unresolved = False

    while pending_files:
        retry_files: list[tuple[str, Path, str]] = []
        attempt_failed = False
        for task_name, source_file, source in pending_files:
            if expected_sales_date is not None:
                status_repo.mark_running(task_name, expected_sales_date, source_path=source_file)
            try:
                result = (
                    repository.import_jst_daily_sales(source_file)
                    if source == "jst"
                    else repository.import_vip_daily_sales(source_file)
                )
                result_dates = _sales_dates(result)
                if expected_sales_date is not None and expected_sales_date not in result_dates:
                    available_dates = ", ".join(sorted(item.isoformat() for item in result_dates)) or "none"
                    message = (
                        f"Source data is not ready: expected {expected_sales_date.isoformat()}, "
                        f"found {available_dates}"
                    )
                    status_repo.mark_finished(
                        task_name,
                        expected_sales_date,
                        status="skipped",
                        message=message,
                        result={**result, "expected_sales_date": expected_sales_date.isoformat()},
                        source_path=source_file,
                    )
                    retry_files.append((task_name, source_file, source))
                    print(f"[WAIT] {source_file.name}: {message}")
                    continue

                _record_status(
                    status_repo,
                    task_name,
                    result,
                    source_file,
                    result_dates,
                    running_date=expected_sales_date,
                )
                imported_any = True
                imported_dates.update(result_dates)
                print(f"[OK] {source_file.name}: {result}")
            except Exception as exc:  # pragma: no cover - scheduled task diagnostics
                attempt_failed = True
                if expected_sales_date is not None:
                    status_repo.mark_finished(
                        task_name,
                        expected_sales_date,
                        status="failed",
                        message=f"{type(exc).__name__}: {exc}",
                        result={"traceback": traceback.format_exc()},
                        source_path=source_file,
                    )
                    retry_files.append((task_name, source_file, source))
                print(f"[FAILED] {source_file}: {type(exc).__name__}: {exc}\n{traceback.format_exc()}")

        if not retry_files:
            unresolved = attempt_failed
            break
        if expected_sales_date is None or retry_until is None or datetime.now() >= retry_until:
            unresolved = True
            break

        sleep_seconds = min(
            max(args.retry_interval_seconds, 1),
            max(int((retry_until - datetime.now()).total_seconds()), 1),
        )
        print(f"[RETRY] target sales date not ready, sleep {sleep_seconds}s")
        time.sleep(sleep_seconds)
        pending_files = retry_files

    failed = unresolved
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
