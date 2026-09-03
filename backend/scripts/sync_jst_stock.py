"""Sync JST daily stock from Excel with retry-aware task status."""
from __future__ import annotations

import argparse
import traceback
from datetime import date

from config import load_settings
from storage.inventory_repository import InventoryRepository
from storage.task_status_repository import ScheduledTaskStatusRepository


TASK_NAME = "sync_jst_stock_daily"


def main() -> int:
    parser = argparse.ArgumentParser(description="导入聚水潭每日尺码库存")
    parser.add_argument("--business-date", type=date.fromisoformat, default=date.today())
    parser.add_argument("--force", action="store_true", help="当天已经成功时仍重新导入")
    args = parser.parse_args()

    settings = load_settings(require_database=True)
    assert settings.database_url is not None

    status_repo = ScheduledTaskStatusRepository(settings.database_url)
    if not args.force and status_repo.is_success(TASK_NAME, args.business_date):
        print(f"[SKIP] {args.business_date.isoformat()} JST stock already succeeded")
        return 0

    stock_date = args.business_date.strftime("%m.%d")
    source_path = (
        settings.jst_stock_root / stock_date / "商品库存.xlsx"
        if settings.jst_stock_root is not None
        else None
    )
    status_repo.mark_running(TASK_NAME, args.business_date, source_path=source_path)

    try:
        repo = InventoryRepository(settings.database_url)
        result = repo.import_jst_stock(
            jst_stock_root=settings.jst_stock_root,
            stock_date=stock_date,
        )
        imported = int(result.get("imported") or 0)
        message = str(result.get("message") or "未读取到有效库存数据")
        if imported <= 0:
            status_repo.mark_finished(
                TASK_NAME,
                args.business_date,
                status="skipped",
                message=message,
                result=result,
                source_path=source_path,
            )
            print(f"[SKIP] {message}")
            return 1
    except Exception as exc:
        message = f"{type(exc).__name__}: {exc}"
        status_repo.mark_finished(
            TASK_NAME,
            args.business_date,
            status="failed",
            message=message,
            result={"traceback": traceback.format_exc()},
            source_path=source_path,
        )
        print(f"[FAILED] {message}")
        return 1

    status_repo.mark_finished(
        TASK_NAME,
        args.business_date,
        status="success",
        message=message,
        result=result,
        source_path=source_path,
    )
    print(f"[JST库存] {message}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
