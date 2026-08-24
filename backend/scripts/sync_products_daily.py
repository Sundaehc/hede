"""Synchronize product archives once today's GJ and price imports are ready."""

from __future__ import annotations

from dataclasses import asdict
from datetime import date
import traceback

from config import load_settings
from pipeline.import_pipeline import ImportPipeline, PROTECTED_SYNC_BRANDS
from storage.task_status_repository import ScheduledTaskStatusRepository


TASK_NAME = "sync_products_daily"
PREREQUISITE_TASKS = (
    "import_gj_merged_product_info_daily",
    "import_price_daily",
)


def main() -> int:
    settings = load_settings(require_database=True)
    assert settings.database_url is not None
    business_date = date.today()
    status_repo = ScheduledTaskStatusRepository(settings.database_url)

    if status_repo.is_success(TASK_NAME, business_date):
        print(f"[SKIP] {business_date.isoformat()} product sync already succeeded")
        return 0

    pending = [
        task_name
        for task_name in PREREQUISITE_TASKS
        if not status_repo.is_success(task_name, business_date)
    ]
    if pending:
        message = f"等待前置任务完成: {', '.join(pending)}"
        status_repo.mark_finished(
            TASK_NAME,
            business_date,
            status="skipped",
            message=message,
            result={"pending_prerequisites": pending},
        )
        print(f"[SKIP] {business_date.isoformat()} {message}")
        return 0

    status_repo.mark_running(TASK_NAME, business_date)
    try:
        summaries = ImportPipeline(settings).run(
            dry_run=False,
            mode="sync",
            excluded_brands=PROTECTED_SYNC_BRANDS,
        )
        result = {brand: asdict(summary) for brand, summary in summaries.items()}
    except Exception as exc:  # pragma: no cover - scheduled task diagnostics
        message = f"{type(exc).__name__}: {exc}"
        status_repo.mark_finished(
            TASK_NAME,
            business_date,
            status="failed",
            message=message,
            result={"traceback": traceback.format_exc()},
        )
        print(f"[FAILED] {business_date.isoformat()} {message}")
        return 1

    loaded_rows = sum(int(item.get("loaded_rows") or 0) for item in result.values())
    status_repo.mark_finished(
        TASK_NAME,
        business_date,
        status="success",
        message=f"商品档案同步完成: {loaded_rows} 条",
        result=result,
    )
    print(f"[OK] {business_date.isoformat()} product sync loaded={loaded_rows}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
