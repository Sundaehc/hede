"""Import the current VIP product reports with retry-aware status."""

import argparse
import traceback
from datetime import date
from pathlib import Path

from config import load_settings
from storage.task_status_repository import ScheduledTaskStatusRepository
from storage.vip_repository import VipRepository


TASK_NAME = "import_vip_product_daily"
REQUIRED_REPORT_NAMES = (
    "3环比",
    "3罗盘",
    "7环比",
    "7罗盘",
    "实时商品",
    "常态商品运营",
    "日罗盘",
    "月罗盘",
)


def _missing_reports(vip_dir: Path) -> list[str]:
    stems = {
        path.stem
        for extension in (".xlsx", ".xlsm", ".xls")
        for path in vip_dir.glob(f"*{extension}")
        if not path.name.startswith("~$")
    }
    return [name for name in REQUIRED_REPORT_NAMES if not any(name in stem for stem in stems)]


def main() -> int:
    parser = argparse.ArgumentParser(description="导入当日唯品商品日报")
    parser.add_argument("--business-date", type=date.fromisoformat, default=date.today())
    parser.add_argument("--force", action="store_true", help="当天已经成功时仍重新导入")
    args = parser.parse_args()

    cfg = load_settings(require_database=True)
    assert cfg.database_url is not None
    assert cfg.vip_data_roots, "VIP_DATA_ROOT or YANDOU_VIP_DATA_ROOT is required in .env"
    status_repo = ScheduledTaskStatusRepository(cfg.database_url)
    if not args.force and status_repo.is_success(TASK_NAME, args.business_date):
        print(f"[SKIP] {args.business_date.isoformat()} VIP product import already succeeded")
        return 0

    vip_dirs = [root / args.business_date.strftime("%m.%d") for root in cfg.vip_data_roots]
    source_path = "; ".join(str(path) for path in vip_dirs)
    status_repo.mark_running(TASK_NAME, args.business_date, source_path=source_path)

    missing_sources: list[str] = []
    access_errors: list[str] = []
    for vip_dir in vip_dirs:
        try:
            if not vip_dir.is_dir():
                missing_sources.append(f"目录不存在: {vip_dir}")
                continue
            missing_reports = _missing_reports(vip_dir)
        except OSError as exc:
            access_errors.append(f"{vip_dir}: {type(exc).__name__}: {exc}")
            continue
        if missing_reports:
            missing_sources.append(
                f"报表未齐全: {vip_dir}（缺少 {', '.join(missing_reports)}）"
            )

    if access_errors or missing_sources:
        details = [*access_errors, *missing_sources]
        message = f"唯品商品日报源文件未就绪: {'; '.join(details)}"
        status_repo.mark_finished(
            TASK_NAME,
            args.business_date,
            status="failed" if access_errors else "skipped",
            message=message,
            result={
                "source_dirs": vip_dirs,
                "access_errors": access_errors,
                "missing_sources": missing_sources,
            },
            source_path=source_path,
        )
        print(f"[SKIP] {message}")
        return 1

    repo = VipRepository(cfg.database_url)

    replace_existing = True
    total_imported = 0
    failed_imports: list[str] = []
    import_results: list[dict[str, object]] = []
    try:
        for vip_dir in vip_dirs:
            result = repo.import_all(vip_dir, replace_existing=replace_existing)
            import_results.append({"source_dir": str(vip_dir), **result})
            if result["success"]:
                replace_existing = False
                total_imported += int(result["total_imported"])
                print(f"[VIP] {vip_dir} 导入完成, 共 {result['total_imported']} 条")
            else:
                print(f"[VIP] {result['message']}")
                failed_imports.append(f"{vip_dir}: {result['message']}")
    except Exception as exc:
        failed_imports.append(f"{type(exc).__name__}: {exc}")
        import_results.append({"traceback": traceback.format_exc()})

    if failed_imports or total_imported <= 0:
        message = f"唯品商品日报导入失败: {'; '.join(failed_imports) or '无有效数据'}"
        status_repo.mark_finished(
            TASK_NAME,
            args.business_date,
            status="failed",
            message=message,
            result={"total_imported": total_imported, "details": import_results},
            source_path=source_path,
        )
        print(f"[FAILED] {message}")
        return 1

    status_repo.mark_finished(
        TASK_NAME,
        args.business_date,
        status="success",
        message=f"全部导入完成: {total_imported} 条",
        result={"total_imported": total_imported, "details": import_results},
        source_path=source_path,
    )
    print(
        f"[VIP] {args.business_date.strftime('%m.%d')} "
        f"全部导入完成, 共 {total_imported} 条"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
