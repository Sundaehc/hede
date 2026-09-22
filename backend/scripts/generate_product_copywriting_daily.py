from __future__ import annotations

import argparse
import json
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime, timedelta, timezone

from fastapi import HTTPException
from sqlalchemy import func, inspect, select

from api.product_copywriting import resolve_doubao_endpoint
from api.product_copywriting_jobs import normalized_launch_date, prepare_copywriting, run_claimed_copywriting
from config import load_settings
from domain.excluded_skus import not_excluded_sku_condition
from domain.product_copywriting_schema import PRODUCT_COPYWRITING_TABLE
from storage.product_copywriting_repository import ProductCopywritingRepository
from storage.product_repository import ProductRepository
from storage.task_status_repository import ScheduledTaskStatusRepository


TASK_NAME = "generate_product_copywriting_daily"
SHANGHAI_TIMEZONE = timezone(timedelta(hours=8))


def business_today() -> date:
    return datetime.now(SHANGHAI_TIMEZONE).date()


def recent_launch_dates(business_date: date) -> tuple[date, ...]:
    return tuple(business_date - timedelta(days=offset) for offset in range(2, -1, -1))


def target_products(products, business_date: date) -> list[tuple[str, dict]]:
    dates = recent_launch_dates(business_date)
    date_values = [value for day in dates for value in (day.isoformat(), day.strftime("%Y/%m/%d"))]
    saved_table = PRODUCT_COPYWRITING_TABLE
    saved_table_exists = inspect(products.engine).has_table(saved_table.name)
    targets = []
    for brand in products.product_archive_brands():
        table = products._table_for_brand(brand)
        conditions = [
            table.c.deleted_at.is_(None),
            func.trim(table.c.launch_date).in_(date_values),
            table.c.image_path.isnot(None),
            func.trim(table.c.image_path) != "",
            not_excluded_sku_condition(table.c.sku, table.c.original_sku),
        ]
        if saved_table_exists:
            conditions.append(~select(saved_table.c.id).where(
                saved_table.c.brand == brand,
                saved_table.c.source_product_id == table.c.id,
            ).exists())
        with products.engine.connect() as connection:
            rows = connection.execute(select(table).where(*conditions).order_by(table.c.launch_date, table.c.id)).mappings()
            targets.extend((brand, dict(row)) for row in rows if str(row["image_path"]).strip())
    return targets


def generate_one(settings, products, saved, brand: str, product_id: int, business_date: date) -> dict:
    result = {"brand": brand, "product_id": product_id}
    try:
        if saved.get(brand, product_id) is not None:
            return {**result, "status": "skipped", "reason": "existing_record"}
        item = products.get_product(brand, product_id)
        if item is None or normalized_launch_date(item.get("launch_date")) not in recent_launch_dates(business_date):
            return {**result, "status": "skipped", "reason": "outside_scope"}
        if not str(item.get("image_path") or "").strip():
            return {**result, "status": "skipped", "reason": "missing_image"}
        values = prepare_copywriting(settings, brand, product_id, item)
        token = saved.claim(values, timeout_seconds=settings.doubao_timeout_seconds, only_if_missing=True)
        if token is None:
            return {**result, "status": "skipped", "reason": "existing_record"}
        return run_claimed_copywriting(settings, products, saved, values, token)
    except HTTPException as error:
        return {**result, "status": "failed", "error_status": error.status_code}
    except Exception:
        return {**result, "status": "failed", "error_status": 500}


def run_daily_generation(settings, business_date: date) -> dict:
    products = ProductRepository(settings.database_url)
    saved = ProductCopywritingRepository(products.engine)
    try:
        saved.create_tables()
        targets = target_products(products, business_date)
        if targets:
            if not settings.ark_api_key:
                raise HTTPException(status_code=503, detail="未配置模型密钥，自动生成未执行")
            resolve_doubao_endpoint(settings)
        counts = Counter()
        with ThreadPoolExecutor(max_workers=2) as executor:
            futures = [executor.submit(generate_one, settings, products, saved, brand, item["id"], business_date) for brand, item in targets]
            for future in as_completed(futures):
                result = future.result()
                counts[result["status"]] += 1
                print(json.dumps(result, ensure_ascii=False), flush=True)
        return {
            "start_date": recent_launch_dates(business_date)[0].isoformat(),
            "end_date": business_date.isoformat(),
            "target_count": len(targets), **dict(counts),
        }
    finally:
        products.engine.dispose()


def main() -> int:
    parser = argparse.ArgumentParser(description="仅补生成最近3天（含当天）有主图且无提示词记录的商品；默认只读预览")
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args()
    settings = load_settings(require_database=True)
    business_date = business_today()
    if not args.execute:
        products = ProductRepository(settings.database_url)
        try:
            targets = target_products(products, business_date)
            print(json.dumps({
                "execute": False, "start_date": recent_launch_dates(business_date)[0].isoformat(),
                "end_date": business_date.isoformat(), "target_count": len(targets),
                "brands": dict(Counter(brand for brand, _ in targets)),
            }, ensure_ascii=False))
            return 0
        finally:
            products.engine.dispose()
    statuses = ScheduledTaskStatusRepository(settings.database_url)
    try:
        if not statuses.is_success("sync_products_daily", business_date):
            print("[SKIP] 当天商品档案尚未同步成功，不生成提示词")
            return 1
        result = run_daily_generation(settings, business_date)
        print(json.dumps({"summary": result}, ensure_ascii=False))
        return 1 if result.get("failed") else 0
    finally:
        statuses.engine.dispose()


if __name__ == "__main__":
    raise SystemExit(main())
