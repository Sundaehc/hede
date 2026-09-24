"""Refresh product image paths from configured image roots.

Run:
  python -m scripts.refresh_product_images
  python -m scripts.refresh_product_images --brand cbanner_mens
  python -m scripts.refresh_product_images --overwrite
  python -m scripts.refresh_product_images --daily
"""
from __future__ import annotations

import argparse
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import text

from config import load_settings
from domain.sources import TABLE_NAMES
from scripts.sync_products_daily import TASK_NAME as PRODUCT_TASK_NAME
from storage.product_image_refresh import run_product_image_refresh
from storage.product_image_sync import run_product_image_us3_sync
from storage.product_repository import ProductRepository
from storage.task_status_repository import ScheduledTaskStatusRepository


TASK_NAME = "refresh_product_images_daily"
IMAGE_LOCK_ID = 68473103
SHANGHAI_TIMEZONE = timezone(timedelta(hours=8))


def business_today() -> date:
    return datetime.now(SHANGHAI_TIMEZONE).date()


def refresh_images(settings, repository, *, brand=None, overwrite=False, skip_us3=False, force_us3=False, dry_run_us3=False) -> dict:
    result = run_product_image_refresh(
        settings=settings,
        repository=repository,
        brand=brand,
        overwrite=overwrite,
    )
    if not result.get("accepted", True):
        print("[WAIT] product image refresh is already running")
        raise RuntimeError("图片刷新任务正在运行")
    if result.get("status") != "completed":
        print("[FAILED] product image path refresh did not complete")
        raise RuntimeError("图片路径刷新失败")

    for brand_key, brand_result in result.get("results", {}).items():
        print(
            f"[{brand_key}] scanned={brand_result['scanned']} "
            f"matched={brand_result['matched']} updated={brand_result['updated']} missing={brand_result['missing']}"
        )

    print(result.get("message", "Done."))
    sync_result = None
    if not settings.ucloud_us3_configured or skip_us3:
        print("US3 image sync skipped: storage is not configured or --skip-us3 was specified.")
    else:
        sync_result = run_product_image_us3_sync(
            settings=settings,
            repository=repository,
            brands=[brand] if brand else None,
            force=force_us3,
            dry_run=dry_run_us3,
        )
        print(
            "US3 image sync: "
            f"scanned={sync_result['scanned']} candidates={sync_result['candidates']} "
            f"uploaded={sync_result['uploaded']} unchanged={sync_result['skipped_unchanged']} "
            f"missing={sync_result['missing']} invalid={sync_result['invalid']} "
            f"failed={sync_result['failed']}"
        )
        for error in sync_result.get("errors", []):
            print(f"[US3 ERROR] {error['object_key']}: {error['error']}")
        if sync_result["failed"]:
            raise RuntimeError(f"US3 图片同步失败 {sync_result['failed']} 项")
    return {"image_refresh": result, "us3_sync": sync_result}


def run_daily_refresh(settings, statuses, business_date: date) -> int:
    if not statuses.is_success(PRODUCT_TASK_NAME, business_date):
        statuses.mark_finished(
            TASK_NAME, business_date, status="skipped", message="当天商品档案尚未同步成功，等待档案更新后再同步图片",
        )
        print("[WAIT] today's product archive sync has not succeeded; image refresh was not started")
        return 1
    if statuses.is_success(TASK_NAME, business_date):
        print(f"[SKIP] {business_date.isoformat()} product image refresh already succeeded")
        return 0

    statuses.mark_running(TASK_NAME, business_date)
    repository = None
    try:
        if not settings.ucloud_us3_configured:
            print("[FAILED] daily image refresh requires US3 storage configuration")
            raise RuntimeError("未配置US3，不能完成每日图片同步")
        for image_brand, root in settings.image_roots.items():
            if not root.is_dir():
                print(f"[FAILED] configured image directory is unavailable: {image_brand}")
                raise RuntimeError("图片共享目录不可访问")
        repository = ProductRepository(settings.database_url)
        result = refresh_images(settings, repository)
        if business_today() != business_date:
            print("[FAILED] image refresh crossed midnight; retry with the new business date")
            raise RuntimeError("图片同步跨日，不能标记当天成功")

        statuses.mark_finished(
            TASK_NAME,
            business_date,
            status="success",
            message="商品图片路径与US3同步完成",
            result=result,
        )
        return 0
    except Exception as error:
        statuses.mark_finished(
            TASK_NAME,
            business_date,
            status="failed",
            message="商品图片同步失败，请检查图片刷新和US3日志",
            result={"error_type": type(error).__name__},
        )
        print(f"[FAILED] 商品图片同步失败：{type(error).__name__}")
        return 1
    finally:
        if repository is not None:
            repository.engine.dispose()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--brand", choices=sorted(TABLE_NAMES), default=None)
    parser.add_argument("--overwrite", action="store_true")
    parser.add_argument("--skip-us3", action="store_true")
    parser.add_argument("--force-us3", action="store_true")
    parser.add_argument("--dry-run-us3", action="store_true")
    parser.add_argument("--daily", action="store_true", help="档案同步成功后执行完整图片更新，当天成功后跳过")
    args = parser.parse_args()
    if args.daily and any((args.brand, args.overwrite, args.skip_us3, args.force_us3, args.dry_run_us3)):
        parser.error("--daily 不能与手动刷新参数组合使用")

    settings = load_settings(require_database=True)
    assert settings.database_url is not None
    if args.daily:
        statuses = ScheduledTaskStatusRepository(settings.database_url)
        try:
            with statuses.engine.connect().execution_options(isolation_level="AUTOCOMMIT") as connection:
                acquired = connection.execute(text("SELECT pg_try_advisory_lock(:key)"), {"key": IMAGE_LOCK_ID}).scalar_one()
                if not acquired:
                    print("[WAIT] daily product image refresh is already running")
                    return 1
                try:
                    return run_daily_refresh(settings, statuses, business_today())
                finally:
                    connection.execute(text("SELECT pg_advisory_unlock(:key)"), {"key": IMAGE_LOCK_ID})
        finally:
            statuses.engine.dispose()

    repository = ProductRepository(settings.database_url)
    try:
        refresh_images(
            settings, repository, brand=args.brand, overwrite=args.overwrite,
            skip_us3=args.skip_us3, force_us3=args.force_us3, dry_run_us3=args.dry_run_us3,
        )
        return 0
    except Exception as error:
        print(f"[FAILED] 商品图片同步失败：{type(error).__name__}")
        return 1
    finally:
        repository.engine.dispose()


if __name__ == "__main__":
    raise SystemExit(main())
