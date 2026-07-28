"""Synchronize master-data aliases and product-code mappings after daily imports."""
from __future__ import annotations

import argparse
import time
import traceback
from datetime import date

from sqlalchemy import create_engine

from config import load_settings
from domain import master_data_schema  # noqa: F401 - register master-data tables
from domain.schema import METADATA
from scripts.backfill_master_data import (
    ENTITY_SOURCES,
    _refresh_views,
    ensure_master_data_relationship_constraints,
    _upsert_entity_source,
    _upsert_product_archive_codes,
    _upsert_sales_codes,
)
from storage.task_status_repository import ScheduledTaskStatusRepository


TASK_NAME = "master_data_sync"


def main() -> int:
    parser = argparse.ArgumentParser(description="同步商品编码与受控主数据")
    parser.add_argument("--business-date", type=date.fromisoformat, default=date.today())
    parser.add_argument("--force", action="store_true", help="当天已成功时仍执行")
    args = parser.parse_args()

    settings = load_settings()
    assert settings.database_url is not None
    status_repository = ScheduledTaskStatusRepository(settings.database_url)
    if not args.force and status_repository.is_success(TASK_NAME, args.business_date):
        print(f"[SKIP] {args.business_date.isoformat()} already succeeded")
        return 0

    status_repository.mark_running(TASK_NAME, args.business_date)
    started_at = time.perf_counter()
    try:
        engine = create_engine(settings.database_url)
        METADATA.create_all(engine, checkfirst=True)
        ensure_master_data_relationship_constraints(engine)
        alias_count = sum(_upsert_entity_source(engine, source) for source in ENTITY_SOURCES)
        code_count = _upsert_product_archive_codes(engine) + _upsert_sales_codes(engine)
        _refresh_views(engine)
        elapsed_seconds = round(time.perf_counter() - started_at, 2)
        result = {
            "aliases_upserted": alias_count,
            "code_mappings_upserted": code_count,
            "elapsed_seconds": elapsed_seconds,
        }
        status_repository.mark_finished(
            TASK_NAME,
            args.business_date,
            status="success",
            message=f"主数据同步完成，耗时 {elapsed_seconds} 秒",
            result=result,
        )
        print(f"[DONE] {result}")
        return 0
    except Exception as exc:  # pragma: no cover - scheduled task diagnostics
        status_repository.mark_finished(
            TASK_NAME,
            args.business_date,
            status="failed",
            message=f"{type(exc).__name__}: {exc}",
            result={"traceback": traceback.format_exc()},
        )
        print(f"[FAILED] {type(exc).__name__}: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
