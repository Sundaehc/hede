"""Daily price import with retry and 7-day catch-up.

Run:
    python -m scripts.import_price_daily
    python -m scripts.import_price_daily --source-date 2026-06-08
"""
from __future__ import annotations

import argparse
import time
import traceback
from dataclasses import dataclass
from datetime import date, datetime, time as day_time, timedelta
from pathlib import Path

from config import load_settings
from storage.product_repository import ProductRepository
from storage.task_status_repository import ScheduledTaskStatusRepository
from storage.vip_repository import VipRepository


TASK_NAME = "import_price_daily"


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


def _price_files(price_dir: Path) -> list[Path]:
    files: list[Path] = []
    for ext in (".xlsx", ".xlsm", ".xls"):
        for file_path in sorted(price_dir.glob(f"*{ext}")):
            if file_path.name.startswith("~$"):
                continue
            filename = file_path.stem
            if "合并" in filename and "物价" in filename:
                files.append(file_path)
    return files


def _run_once(
    *,
    repo: VipRepository,
    source_root: Path,
    status_repo: ScheduledTaskStatusRepository,
    dates: list[date],
    force: bool,
) -> RunSummary:
    summary = RunSummary()
    retry_target = dates[-1]
    successful_dates = set() if force else status_repo.successful_dates(TASK_NAME, dates[0], dates[-1])

    for business_date in dates:
        price_dir = _source_dir(source_root, business_date)
        if business_date in successful_dates:
            summary.skipped_success += 1
            print(f"[SKIP] {business_date.isoformat()} already succeeded")
            continue

        status_repo.mark_running(TASK_NAME, business_date, source_path=price_dir)
        try:
            source_exists = price_dir.exists()
        except OSError as exc:
            message = f"物价目录无法访问: {type(exc).__name__}: {exc}"
            status_repo.mark_finished(
                TASK_NAME,
                business_date,
                status="failed",
                message=message,
                result={"source_dir": price_dir, "reason": "source_dir_access_error"},
                source_path=price_dir,
            )
            summary.failed += 1
            if business_date == retry_target:
                summary.retry_target_unresolved = True
            print(f"[FAILED] {business_date.isoformat()} {message}")
            continue
        if not source_exists:
            message = f"物价目录不存在: {price_dir}"
            status_repo.mark_finished(
                TASK_NAME,
                business_date,
                status="skipped",
                message=message,
                result={"source_dir": price_dir, "reason": "missing_source_dir"},
                source_path=price_dir,
            )
            summary.missing_source += 1
            if business_date == retry_target:
                summary.retry_target_unresolved = True
            print(f"[SKIP] {business_date.isoformat()} {message}")
            continue

        try:
            price_files = _price_files(price_dir)
            if not price_files:
                message = f"未找到物价文件: {price_dir}"
                status_repo.mark_finished(
                    TASK_NAME,
                    business_date,
                    status="skipped",
                    message=message,
                    result={"source_dir": price_dir, "reason": "missing_price_file"},
                    source_path=price_dir,
                )
                summary.missing_source += 1
                if business_date == retry_target:
                    summary.retry_target_unresolved = True
                print(f"[SKIP] {business_date.isoformat()} {message}")
                continue
            details = [repo.import_price(file_path) for file_path in price_files]
            imported = sum(int(item.get("imported") or 0) for item in details)
            result = {
                "success": True,
                "batch_date": business_date.isoformat(),
                "total_imported": imported,
                "details": details,
            }
            if imported <= 0:
                message = f"物价文件无有效数据: {price_dir}"
                status_repo.mark_finished(
                    TASK_NAME,
                    business_date,
                    status="failed",
                    message=message,
                    result=result,
                    source_path=price_dir,
                )
                summary.failed += 1
                if business_date == retry_target:
                    summary.retry_target_unresolved = True
                print(f"[FAILED] {business_date.isoformat()} {message}")
                continue
        except Exception as exc:  # pragma: no cover - logged for scheduled task diagnosis
            message = f"{type(exc).__name__}: {exc}"
            status_repo.mark_finished(
                TASK_NAME,
                business_date,
                status="failed",
                message=message,
                result={"source_dir": price_dir, "traceback": traceback.format_exc()},
                source_path=price_dir,
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
                message=f"导入完成: {imported} 条",
                result=result,
                source_path=price_dir,
            )
            summary.imported += 1
            print(f"[PRICE] {business_date.isoformat()} 导入完成, 共 {imported} 条")

    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description="导入每日物价信息，支持重试和近 7 天补采")
    parser.add_argument("--source-date", type=date.fromisoformat, default=None, help="只导入指定日期")
    parser.add_argument("--lookback-days", type=int, default=7, help="检查最近 N 天缺失导入")
    parser.add_argument("--retry-until", default=None, help="当天目标未就绪时重试到本地时间 HH:MM")
    parser.add_argument("--retry-interval-seconds", type=int, default=1800, help="重试间隔秒数")
    parser.add_argument("--force", action="store_true", help="即使状态表已有成功记录也重新导入")
    args = parser.parse_args()

    cfg = load_settings()
    assert cfg.database_url is not None
    assert cfg.jst_price_root is not None, "JST_PRICE_ROOT is required in .env"

    today = date.today()
    dates = [args.source_date] if args.source_date else _recent_dates(today, max(args.lookback_days, 1))
    retry_until = _parse_retry_until(args.retry_until)
    status_repo = ScheduledTaskStatusRepository(cfg.database_url)
    repo = VipRepository(cfg.database_url)

    exit_code = 0
    while True:
        summary = _run_once(
            repo=repo,
            source_root=cfg.jst_price_root,
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

    if exit_code == 0:
        cost_result = ProductRepository(cfg.database_url).sync_costs_from_latest_combined_footwear_price()
        print(
            "[PRODUCT COST] "
            f"source={cost_result['source']} updated={cost_result['updated']} "
            f"brands={cost_result['brands']}"
        )

    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
