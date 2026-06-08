"""Run GJ merged product info import with retry and 7-day catch-up.

Run:
    python -m scripts.import_gj_merged_product_info_daily
    python -m scripts.import_gj_merged_product_info_daily --source-date 2026-06-08
"""
from __future__ import annotations

import argparse
import time
import traceback
from dataclasses import dataclass
from datetime import date, datetime, time as day_time, timedelta
from pathlib import Path

from config import load_settings
from scripts.import_gj_merged_product_info import import_gj_merged_product_info
from storage.task_status_repository import ScheduledTaskStatusRepository


TASK_NAME = "import_gj_merged_product_info_daily"


@dataclass
class RunSummary:
    imported: int = 0
    skipped_success: int = 0
    missing_source: int = 0
    failed: int = 0
    retry_target_unresolved: bool = False


def _recent_dates(today: date, days: int) -> list[date]:
    return [today - timedelta(days=offset) for offset in range(days - 1, -1, -1)]


def _parse_retry_until(value: str | None) -> datetime | None:
    if not value:
        return None
    parsed = day_time.fromisoformat(value)
    return datetime.combine(date.today(), parsed)


def _source_dir(root: Path, business_date: date) -> Path:
    return root / business_date.isoformat()


def _run_once(
    *,
    database_url: str,
    source_root: Path,
    status_repo: ScheduledTaskStatusRepository,
    dates: list[date],
    force: bool,
) -> RunSummary:
    summary = RunSummary()
    retry_target = dates[-1]
    successful_dates = set() if force else status_repo.successful_dates(TASK_NAME, dates[0], dates[-1])

    for business_date in dates:
        source_dir = _source_dir(source_root, business_date)
        if business_date in successful_dates:
            summary.skipped_success += 1
            print(f"[SKIP] {business_date.isoformat()} already succeeded")
            continue

        status_repo.mark_running(TASK_NAME, business_date, source_path=source_dir)
        try:
            source_exists = source_dir.exists()
        except OSError as exc:
            message = f"源目录无法访问: {type(exc).__name__}: {exc}"
            status_repo.mark_finished(
                TASK_NAME,
                business_date,
                status="failed",
                message=message,
                result={"source_dir": source_dir, "reason": "source_dir_access_error"},
                source_path=source_dir,
            )
            summary.failed += 1
            if business_date == retry_target:
                summary.retry_target_unresolved = True
            print(f"[FAILED] {business_date.isoformat()} {message}")
            continue
        if not source_exists:
            message = f"源目录不存在: {source_dir}"
            status_repo.mark_finished(
                TASK_NAME,
                business_date,
                status="skipped",
                message=message,
                result={"source_dir": source_dir, "reason": "missing_source_dir"},
                source_path=source_dir,
            )
            summary.missing_source += 1
            if business_date == retry_target:
                summary.retry_target_unresolved = True
            print(f"[SKIP] {business_date.isoformat()} {message}")
            continue

        try:
            result = import_gj_merged_product_info(database_url, source_dir)
        except FileNotFoundError as exc:
            message = str(exc)
            status_repo.mark_finished(
                TASK_NAME,
                business_date,
                status="skipped",
                message=message,
                result={"source_dir": source_dir, "reason": "missing_source_file"},
                source_path=source_dir,
            )
            summary.missing_source += 1
            if business_date == retry_target:
                summary.retry_target_unresolved = True
            print(f"[SKIP] {business_date.isoformat()} {message}")
        except Exception as exc:  # pragma: no cover - logged for scheduled task diagnosis
            message = f"{type(exc).__name__}: {exc}"
            status_repo.mark_finished(
                TASK_NAME,
                business_date,
                status="failed",
                message=message,
                result={"source_dir": source_dir, "traceback": traceback.format_exc()},
                source_path=source_dir,
            )
            summary.failed += 1
            if business_date == retry_target:
                summary.retry_target_unresolved = True
            print(f"[FAILED] {business_date.isoformat()} {message}")
        else:
            status_repo.mark_finished(
                TASK_NAME,
                business_date,
                status="success",
                message=f"导入完成: {result.get('imported', 0)} 条",
                result=result,
                source_path=source_dir,
            )
            summary.imported += 1
            print(f"[OK] {business_date.isoformat()} {result}")

    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description="导入管家婆男女鞋合并商品信息，支持重试和近 7 天补采")
    parser.add_argument("--source-date", type=date.fromisoformat, default=None, help="只导入指定日期")
    parser.add_argument("--lookback-days", type=int, default=7, help="检查最近 N 天缺失导入")
    parser.add_argument("--retry-until", default=None, help="当天目标未就绪时重试到本地时间 HH:MM")
    parser.add_argument("--retry-interval-seconds", type=int, default=1800, help="重试间隔秒数")
    parser.add_argument("--force", action="store_true", help="即使状态表已有成功记录也重新导入")
    args = parser.parse_args()

    settings = load_settings(require_database=True)
    assert settings.database_url is not None
    assert settings.jst_price_root is not None, "JST_PRICE_ROOT is required in .env"

    today = date.today()
    dates = [args.source_date] if args.source_date else _recent_dates(today, max(args.lookback_days, 1))
    retry_until = _parse_retry_until(args.retry_until)
    status_repo = ScheduledTaskStatusRepository(settings.database_url)

    exit_code = 0
    while True:
        summary = _run_once(
            database_url=settings.database_url,
            source_root=settings.jst_price_root,
            status_repo=status_repo,
            dates=dates,
            force=args.force,
        )
        print(
            "[SUMMARY] "
            f"imported={summary.imported} skipped_success={summary.skipped_success} "
            f"missing_source={summary.missing_source} failed={summary.failed} "
            f"retry_target_unresolved={summary.retry_target_unresolved}"
        )

        exit_code = 1 if summary.failed else 0
        if not summary.retry_target_unresolved:
            break
        if retry_until is None or datetime.now() >= retry_until:
            exit_code = 1
            break
        sleep_seconds = min(max(args.retry_interval_seconds, 1), max(int((retry_until - datetime.now()).total_seconds()), 1))
        print(f"[RETRY] target date not ready, sleep {sleep_seconds}s")
        time.sleep(sleep_seconds)

    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
