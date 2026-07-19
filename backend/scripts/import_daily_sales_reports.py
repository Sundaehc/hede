"""Import the JST and VIP raw daily sales reports into annual tables.

Run: python -m scripts.import_daily_sales_reports
"""
from __future__ import annotations

import argparse
import traceback
from datetime import date
from pathlib import Path

from config import load_settings
from storage.daily_sales_repository import DailySalesRepository, JST_FILE_NAME, VIP_FILE_NAME
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
    args = parser.parse_args()

    settings = load_settings(require_database=True)
    assert settings.database_url is not None
    root = args.source_root or settings.daily_sales_report_root
    assert root is not None, "DAILY_SALES_REPORT_ROOT is required"
    files = [
        ("import_jst_daily_sales", args.jst_file or root / JST_FILE_NAME, "jst"),
        ("import_vip_daily_sales", args.vip_file or root / VIP_FILE_NAME, "vip"),
    ]
    repository = DailySalesRepository(settings.database_url)
    status_repo = ScheduledTaskStatusRepository(settings.database_url)
    failed = False
    for task_name, source_file, source in files:
        try:
            result = repository.import_jst_daily_sales(source_file) if source == "jst" else repository.import_vip_daily_sales(source_file)
            _record_status(status_repo, task_name, result, source_file)
            print(f"[OK] {source_file.name}: {result}")
        except Exception as exc:  # pragma: no cover - scheduled task diagnostics
            failed = True
            print(f"[FAILED] {source_file}: {type(exc).__name__}: {exc}\n{traceback.format_exc()}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
