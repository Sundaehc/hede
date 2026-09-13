"""Daily import for aftersale return/refund spreadsheet.

Run:
    python -m scripts.import_aftersale_returns_daily
"""
from __future__ import annotations

import argparse
import traceback
from datetime import date, datetime, time as day_time
from pathlib import Path
import time

from config import load_settings
from storage.task_status_repository import ScheduledTaskStatusRepository
from storage.vip_repository import VipRepository


TASK_NAME = "import_aftersale_returns_daily"


def _parse_retry_until(value: str | None) -> datetime | None:
    if not value:
        return None
    return datetime.combine(date.today(), day_time.fromisoformat(value))


def _wait_for_stable_source(
    source_file: Path,
    business_date: date,
    *,
    timeout_seconds: int = 15 * 60,
    minimum_age_seconds: int = 30,
    confirmation_seconds: int = 10,
    poll_interval_seconds: int = 5,
) -> dict[str, object]:
    """Wait until today's export has finished writing before openpyxl reads it."""
    deadline = time.monotonic() + timeout_seconds
    last_signature: tuple[int, int] | None = None
    unchanged_since = time.monotonic()
    last_reason = "source file is not ready"

    while True:
        now_monotonic = time.monotonic()
        try:
            stat = source_file.stat()
            signature = (stat.st_size, stat.st_mtime_ns)
            if signature != last_signature:
                last_signature = signature
                unchanged_since = now_monotonic

            modified_at = datetime.fromtimestamp(stat.st_mtime).astimezone()
            age_seconds = max(0.0, time.time() - stat.st_mtime)
            unchanged_seconds = max(0.0, now_monotonic - unchanged_since)
            is_fresh = modified_at.date() == business_date
            is_stable = (
                stat.st_size > 0
                and age_seconds >= minimum_age_seconds
                and unchanged_seconds >= confirmation_seconds
            )
            if is_fresh and is_stable:
                return {
                    "size_bytes": stat.st_size,
                    "modified_at": modified_at.isoformat(timespec="seconds"),
                    "waited_seconds": max(0, round(timeout_seconds - (deadline - now_monotonic))),
                }

            if not is_fresh:
                last_reason = (
                    f"source file is not the {business_date.isoformat()} export "
                    f"(modified_at={modified_at.isoformat(timespec='seconds')})"
                )
            else:
                last_reason = (
                    f"source file is still being written "
                    f"(age={age_seconds:.0f}s, unchanged={unchanged_seconds:.0f}s)"
                )
        except OSError as exc:
            last_signature = None
            unchanged_since = now_monotonic
            last_reason = f"source file is unavailable: {type(exc).__name__}: {exc}"

        if now_monotonic >= deadline:
            raise TimeoutError(
                f"Timed out after {timeout_seconds}s waiting for a complete source file: "
                f"{source_file}; {last_reason}"
            )
        time.sleep(max(1, poll_interval_seconds))


def _run_once(
    *,
    source_file: Path,
    business_date: date,
    status_repo: ScheduledTaskStatusRepository,
    repo: VipRepository,
) -> bool:
    """Run one import attempt and return whether another attempt is useful."""
    status_repo.mark_running(TASK_NAME, business_date, source_path=source_file)
    try:
        if not source_file.exists():
            message = f"售后退货退款文件不存在: {source_file}"
            status_repo.mark_finished(
                TASK_NAME,
                business_date,
                status="skipped",
                message=message,
                result={"source_file": source_file, "reason": "missing_source_file"},
                source_path=source_file,
            )
            print(f"[WAIT] {message}")
            return True

        print(f"[WAIT] checking source file freshness and stability: {source_file}")
        source_stability = _wait_for_stable_source(source_file, business_date)
        print(
            "[READY] source file is stable: "
            f"modified_at={source_stability['modified_at']} "
            f"size_bytes={source_stability['size_bytes']}"
        )

        result = repo.import_aftersale_returns(source_file)
        result["source_stability"] = source_stability
        imported = int(result.get("imported") or 0)
        if imported <= 0:
            message = f"售后退货退款文件无有效数据: {source_file}"
            status_repo.mark_finished(
                TASK_NAME,
                business_date,
                status="failed",
                message=message,
                result=result,
                source_path=source_file,
            )
            print(f"[FAILED] {message}")
            return True

        status_repo.mark_finished(
            TASK_NAME,
            business_date,
            status="success",
            message=f"导入完成: {imported} 条",
            result=result,
            source_path=source_file,
        )
        print(f"[AFTERSALE] 导入完成, 共 {imported} 条")
        return False
    except Exception as exc:  # pragma: no cover - logged for scheduled task diagnosis
        message = f"{type(exc).__name__}: {exc}"
        status_repo.mark_finished(
            TASK_NAME,
            business_date,
            status="failed",
            message=message,
            result={"source_file": source_file, "traceback": traceback.format_exc()},
            source_path=source_file,
        )
        print(f"[FAILED] {message}")
        return True


def _mark_retry_exhausted(
    status_repo: ScheduledTaskStatusRepository,
    *,
    source_file: Path,
    business_date: date,
) -> None:
    status_repo.mark_finished(
        TASK_NAME,
        business_date,
        status="failed",
        message=(
            f"售后退货退款任务重试截止，仍未完成导入: "
            f"{source_file}"
        ),
        result={"source_file": source_file, "reason": "retry_deadline_reached"},
        source_path=source_file,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="导入售后（退货退款）表，支持失败重试")
    parser.add_argument("--source-file", type=Path, default=None, help="售后退货退款 Excel 文件")
    parser.add_argument("--business-date", type=date.fromisoformat, default=date.today(), help="任务业务日期")
    parser.add_argument("--force", action="store_true", help="即使当天已有成功记录也重新导入")
    parser.add_argument("--retry-until", default=None, help="源文件或导入失败时重试到本地时间 HH:MM")
    parser.add_argument("--retry-interval-seconds", type=int, default=1800, help="重试间隔秒数")
    args = parser.parse_args()
    if args.retry_interval_seconds < 1:
        raise ValueError("--retry-interval-seconds must be at least 1")

    cfg = load_settings()
    assert cfg.database_url is not None
    source_file = args.source_file or cfg.aftersale_return_file
    assert source_file is not None, "AFTERSALE_RETURN_FILE is required"

    status_repo = ScheduledTaskStatusRepository(cfg.database_url)
    repo = VipRepository(cfg.database_url)
    if not args.force and status_repo.is_success(TASK_NAME, args.business_date):
        print(f"[SKIP] {args.business_date.isoformat()} already succeeded")
        return 0

    retry_until = _parse_retry_until(args.retry_until)
    while True:
        retryable = _run_once(
            source_file=source_file,
            business_date=args.business_date,
            status_repo=status_repo,
            repo=repo,
        )
        if not retryable:
            return 0
        if retry_until is None or datetime.now() >= retry_until:
            _mark_retry_exhausted(
                status_repo,
                source_file=source_file,
                business_date=args.business_date,
            )
            print("[RETRY-STOP] retry deadline reached or retry is not configured")
            return 1
        sleep_seconds = min(
            max(args.retry_interval_seconds, 1),
            max(int((retry_until - datetime.now()).total_seconds()), 1),
        )
        print(f"[RETRY] aftersale source/import not ready, sleep {sleep_seconds}s")
        time.sleep(sleep_seconds)


if __name__ == "__main__":
    raise SystemExit(main())
