"""Import the current monthly JST order export with retry-aware status."""

import argparse
import traceback
from datetime import date
from pathlib import Path

from config import load_settings
from storage.task_status_repository import ScheduledTaskStatusRepository
from storage.vip_repository import VipRepository


TASK_NAME = "import_monthly_order_daily"


def main() -> int:
    parser = argparse.ArgumentParser(description="导入当日月聚水潭订单")
    parser.add_argument("--business-date", type=date.fromisoformat, default=date.today())
    parser.add_argument("--force", action="store_true", help="当天已经成功时仍重新导入")
    args = parser.parse_args()

    cfg = load_settings(require_database=True)
    assert cfg.database_url is not None
    assert cfg.jst_stock_root is not None, "JST_STOCK_ROOT is required in .env"

    status_repo = ScheduledTaskStatusRepository(cfg.database_url)
    if not args.force and status_repo.is_success(TASK_NAME, args.business_date):
        print(f"[SKIP] {args.business_date.isoformat()} monthly order already succeeded")
        return 0

    repo = VipRepository(cfg.database_url)
    other_platform_dir = cfg.jst_stock_root.parent / "其他平台" / args.business_date.strftime("%m.%d")
    file_path = other_platform_dir / "月聚水潭.xlsx"
    status_repo.mark_running(TASK_NAME, args.business_date, source_path=file_path)

    try:
        source_exists = file_path.is_file()
    except OSError as exc:
        message = f"月聚水潭文件无法访问: {type(exc).__name__}: {exc}"
        status_repo.mark_finished(
            TASK_NAME,
            args.business_date,
            status="failed",
            message=message,
            result={"source_file": file_path, "reason": "source_access_error"},
            source_path=file_path,
        )
        print(f"[FAILED] {message}")
        return 1

    if not source_exists:
        message = f"月聚水潭文件不存在: {file_path}"
        status_repo.mark_finished(
            TASK_NAME,
            args.business_date,
            status="skipped",
            message=message,
            result={"source_file": file_path, "reason": "missing_source_file"},
            source_path=file_path,
        )
        print(f"[SKIP] {message}")
        return 1

    try:
        result = repo.import_monthly_order(file_path)
        imported = int(result.get("imported") or 0)
        if imported <= 0:
            raise ValueError(str(result.get("message") or "月聚水潭文件无有效数据"))
    except Exception as exc:
        message = f"{type(exc).__name__}: {exc}"
        status_repo.mark_finished(
            TASK_NAME,
            args.business_date,
            status="failed",
            message=message,
            result={"source_file": file_path, "traceback": traceback.format_exc()},
            source_path=file_path,
        )
        print(f"[FAILED] {message}")
        return 1

    status_repo.mark_finished(
        TASK_NAME,
        args.business_date,
        status="success",
        message=f"导入完成: {imported} 条",
        result={"source_file": file_path, **result},
        source_path=file_path,
    )
    print(
        f"[JST月订单] {args.business_date.strftime('%m.%d')} "
        f"导入完成, 共 {imported} 条"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
