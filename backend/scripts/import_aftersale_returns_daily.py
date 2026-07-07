"""Daily import for aftersale return/refund spreadsheet.

Run:
    python -m scripts.import_aftersale_returns_daily
"""
from __future__ import annotations

import argparse
import traceback
from datetime import date
from pathlib import Path

from config import load_settings
from storage.task_status_repository import ScheduledTaskStatusRepository
from storage.vip_repository import VipRepository


TASK_NAME = "import_aftersale_returns_daily"


def main() -> int:
    parser = argparse.ArgumentParser(description="导入售后（退货退款）表")
    parser.add_argument("--source-file", type=Path, default=None, help="售后退货退款 Excel 文件")
    parser.add_argument("--business-date", type=date.fromisoformat, default=date.today(), help="任务业务日期")
    parser.add_argument("--force", action="store_true", help="即使当天已有成功记录也重新导入")
    args = parser.parse_args()

    cfg = load_settings()
    assert cfg.database_url is not None
    source_file = args.source_file or cfg.aftersale_return_file
    assert source_file is not None, "AFTERSALE_RETURN_FILE is required"

    status_repo = ScheduledTaskStatusRepository(cfg.database_url)
    if not args.force and status_repo.is_success(TASK_NAME, args.business_date):
        print(f"[SKIP] {args.business_date.isoformat()} already succeeded")
        return 0

    status_repo.mark_running(TASK_NAME, args.business_date, source_path=source_file)
    try:
        if not source_file.exists():
            message = f"售后退货退款文件不存在: {source_file}"
            status_repo.mark_finished(
                TASK_NAME,
                args.business_date,
                status="skipped",
                message=message,
                result={"source_file": source_file, "reason": "missing_source_file"},
                source_path=source_file,
            )
            print(f"[SKIP] {message}")
            return 1

        repo = VipRepository(cfg.database_url)
        result = repo.import_aftersale_returns(source_file)
        imported = int(result.get("imported") or 0)
        if imported <= 0:
            message = f"售后退货退款文件无有效数据: {source_file}"
            status_repo.mark_finished(
                TASK_NAME,
                args.business_date,
                status="failed",
                message=message,
                result=result,
                source_path=source_file,
            )
            print(f"[FAILED] {message}")
            return 1

        status_repo.mark_finished(
            TASK_NAME,
            args.business_date,
            status="success",
            message=f"导入完成: {imported} 条",
            result=result,
            source_path=source_file,
        )
        print(f"[AFTERSALE] 导入完成, 共 {imported} 条")
        return 0
    except Exception as exc:  # pragma: no cover - logged for scheduled task diagnosis
        message = f"{type(exc).__name__}: {exc}"
        status_repo.mark_finished(
            TASK_NAME,
            args.business_date,
            status="failed",
            message=message,
            result={"source_file": source_file, "traceback": traceback.format_exc()},
            source_path=source_file,
        )
        print(f"[FAILED] {message}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
