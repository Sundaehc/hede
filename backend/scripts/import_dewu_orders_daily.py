"""Fully replace the unified Dewu order table from four daily exports."""

from __future__ import annotations

import argparse
import traceback
from datetime import date
from pathlib import Path

from config import load_settings
from storage.dewu_order_repository import DewuOrderRepository
from storage.task_status_repository import ScheduledTaskStatusRepository


TASK_NAME = "import_dewu_orders_daily"


def main() -> int:
    parser = argparse.ArgumentParser(description="全量导入千百度、伊伴、烟斗、笑脸得物订单")
    parser.add_argument("--source-root", type=Path, default=None, help="四份得物订单 Excel 所在目录")
    parser.add_argument("--business-date", type=date.fromisoformat, default=date.today(), help="任务业务日期")
    parser.add_argument("--force", action="store_true", help="即使当天已有成功记录也重新导入")
    args = parser.parse_args()

    settings = load_settings(require_database=True)
    assert settings.database_url is not None
    source_root = args.source_root or settings.dewu_order_root
    if source_root is None:
        raise ValueError("DEWU_ORDER_ROOT is required")

    status_repo = ScheduledTaskStatusRepository(settings.database_url)
    if not args.force and status_repo.is_success(TASK_NAME, args.business_date):
        print(f"[SKIP] {args.business_date.isoformat()} already succeeded")
        return 0

    status_repo.mark_running(TASK_NAME, args.business_date, source_path=source_root)
    try:
        result = DewuOrderRepository(settings.database_url).import_all(source_root)
        status_repo.mark_finished(
            TASK_NAME,
            args.business_date,
            status="success",
            message=str(result["message"]),
            result=result,
            source_path=source_root,
        )
        print(f"[DEWU] {result['message']}")
        return 0
    except Exception as exc:  # pragma: no cover - scheduled task diagnosis
        message = f"{type(exc).__name__}: {exc}"
        status_repo.mark_finished(
            TASK_NAME,
            args.business_date,
            status="failed",
            message=message,
            result={"source_root": source_root, "traceback": traceback.format_exc()},
            source_path=source_root,
        )
        print(f"[FAILED] {message}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
