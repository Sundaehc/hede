"""Import the daily JST size stock, stock summary, and purchase difference files."""
from __future__ import annotations

import argparse
import traceback
from datetime import date

from config import load_settings
from storage.task_status_repository import ScheduledTaskStatusRepository
from storage.vip_repository import VipRepository


TASK_NAME = "import_jst_daily"


def main() -> int:
    parser = argparse.ArgumentParser(description="导入聚水潭库存明细")
    parser.add_argument("--business-date", type=date.fromisoformat, default=date.today())
    parser.add_argument("--force", action="store_true", help="当天已经成功时仍重新导入")
    args = parser.parse_args()

    cfg = load_settings()
    assert cfg.database_url is not None
    assert cfg.jst_stock_root is not None, "JST_STOCK_ROOT is required in .env"

    business_date = args.business_date
    today_dir = cfg.jst_stock_root / business_date.strftime("%m.%d")
    size_file = today_dir / "商品库存.xlsx"
    diff_file = today_dir / "采购单管理.xlsx"
    status_repo = ScheduledTaskStatusRepository(cfg.database_url)

    if not args.force and status_repo.is_success(TASK_NAME, business_date):
        print(f"[SKIP] {business_date.isoformat()} 聚水潭库存明细已成功导入")
        return 0

    status_repo.mark_running(TASK_NAME, business_date, source_path=today_dir)
    missing_files = [path for path in (size_file, diff_file) if not path.exists()]
    if missing_files:
        message = "源文件不存在: " + "、".join(str(path) for path in missing_files)
        status_repo.mark_finished(
            TASK_NAME,
            business_date,
            status="skipped",
            message=message,
            result={"missing_files": missing_files},
            source_path=today_dir,
        )
        print(f"[SKIP] {message}")
        return 1

    try:
        repo = VipRepository(cfg.database_url)
        size_result = repo.import_size_stock(size_file, snapshot_date=business_date)
        summary_result = repo.import_stock_summary(size_file, snapshot_date=business_date)
        diff_result = repo.import_purchase_diff(diff_file)
        results = {
            "size_stock": size_result,
            "stock_summary": summary_result,
            "purchase_diff": diff_result,
        }
        imported = {
            name: int(result.get("imported") or 0)
            for name, result in results.items()
        }
        empty_imports = [name for name, count in imported.items() if count <= 0]
        if empty_imports:
            message = "未导入有效数据: " + "、".join(empty_imports)
            status_repo.mark_finished(
                TASK_NAME,
                business_date,
                status="failed",
                message=message,
                result=results,
                source_path=today_dir,
            )
            print(f"[FAILED] {message}")
            return 1

        message = (
            f"导入完成: 尺码库存 {imported['size_stock']} 条，"
            f"库存汇总 {imported['stock_summary']} 条，"
            f"采购差异 {imported['purchase_diff']} 条"
        )
        status_repo.mark_finished(
            TASK_NAME,
            business_date,
            status="success",
            message=message,
            result=results,
            source_path=today_dir,
        )
        print(f"[OK] {message}")
        return 0
    except Exception as exc:  # pragma: no cover - scheduled task diagnostics
        message = f"{type(exc).__name__}: {exc}"
        status_repo.mark_finished(
            TASK_NAME,
            business_date,
            status="failed",
            message=message,
            result={"traceback": traceback.format_exc()},
            source_path=today_dir,
        )
        print(f"[FAILED] {message}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
