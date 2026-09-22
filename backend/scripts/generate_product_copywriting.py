from __future__ import annotations

import argparse
import json
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date

from sqlalchemy import func, select

from api.product_copywriting import resolve_doubao_endpoint
from api.product_copywriting_jobs import normalized_launch_date, prepare_copywriting, run_claimed_copywriting
from config import load_settings
from domain.excluded_skus import not_excluded_sku_condition
from storage.product_copywriting_repository import ProductCopywritingRepository
from storage.product_repository import ProductRepository


TARGET_LAUNCH_DATES = (date(2026, 9, 20), date(2026, 9, 21))


def target_products(products) -> list[tuple[str, dict]]:
    values = [value for day in TARGET_LAUNCH_DATES for value in (day.isoformat(), day.strftime("%Y/%m/%d"))]
    targets = []
    for brand in products.product_archive_brands():
        table = products._table_for_brand(brand)
        with products.engine.connect() as connection:
            rows = connection.execute(select(table).where(
                table.c.deleted_at.is_(None),
                func.trim(table.c.launch_date).in_(values),
                not_excluded_sku_condition(table.c.sku, table.c.original_sku),
            ).order_by(table.c.launch_date, table.c.id)).mappings()
            targets.extend((brand, dict(row)) for row in rows)
    return targets


def generate_one(
    settings,
    products,
    saved,
    brand: str,
    product_id: int,
    *,
    retry_failed: bool = False,
    refresh_outdated_template: bool = False,
) -> dict:
    item = products.get_product(brand, product_id)
    launch_date = normalized_launch_date(item.get("launch_date")) if item is not None else None
    if item is None or launch_date not in TARGET_LAUNCH_DATES:
        return {"brand": brand, "product_id": product_id, "status": "outside_scope"}
    if not str(item.get("image_path") or "").strip():
        return {"brand": brand, "product_id": product_id, "sku": item.get("sku"), "status": "skipped", "reason": "missing_image"}
    values = prepare_copywriting(settings, brand, product_id, item)
    result = {"brand": brand, "product_id": product_id, "sku": values["sku"], "launch_date": str(values["launch_date"])}
    token = saved.claim(
        values,
        timeout_seconds=settings.doubao_timeout_seconds,
        retry_failed=retry_failed,
        refresh_outdated_template=refresh_outdated_template,
    )
    if token is None:
        existing = saved.get(brand, product_id)
        return {**result, "status": "skipped", "saved_status": existing["status"] if existing else None}
    return run_claimed_copywriting(settings, products, saved, values, token)


def main() -> int:
    parser = argparse.ArgumentParser(description="仅生成上市日期2026-09-20及2026-09-21的商品提示词并入库")
    parser.add_argument("--execute", action="store_true", help="创建结果表并实际调用模型；默认只预览")
    parser.add_argument("--workers", type=int, choices=(1, 2, 3), default=2)
    parser.add_argument("--limit", type=int)
    parser.add_argument("--retry-failed", action="store_true", help="仅重试失败或已过期任务；不覆盖成功结果")
    parser.add_argument("--refresh-outdated-template", action="store_true", help="重新生成旧模板结果并保留上一版快照；当前模板成功项仍跳过")
    args = parser.parse_args()
    if args.limit is not None and args.limit < 1:
        parser.error("--limit 必须大于0")
    settings = load_settings(require_database=True)
    if args.execute and not settings.ark_api_key:
        parser.error("请先配置 ARK_API_KEY")
    resolve_doubao_endpoint(settings)
    products = ProductRepository(settings.database_url)
    saved = ProductCopywritingRepository(products.engine)
    try:
        targets = target_products(products)
        if args.limit is not None:
            targets = targets[:args.limit]
        print(json.dumps({"target_dates": [str(day) for day in TARGET_LAUNCH_DATES], "target_count": len(targets), "execute": args.execute, "model": settings.doubao_text_model}, ensure_ascii=False), flush=True)
        if not args.execute:
            for brand, item in targets:
                print(json.dumps({"brand": brand, "product_id": item["id"], "sku": item["sku"], "launch_date": item["launch_date"]}, ensure_ascii=False, default=str), flush=True)
            return 0
        saved.create_tables()
        counts = Counter()
        with ThreadPoolExecutor(max_workers=args.workers) as executor:
            tasks = [executor.submit(generate_one, settings, products, saved, brand, item["id"], retry_failed=args.retry_failed, refresh_outdated_template=args.refresh_outdated_template) for brand, item in targets]
            for task in as_completed(tasks):
                result = task.result()
                counts[result["status"]] += 1
                print(json.dumps(result, ensure_ascii=False), flush=True)
        print(json.dumps({"summary": dict(counts)}, ensure_ascii=False), flush=True)
        return 1 if counts["failed"] else 0
    finally:
        products.engine.dispose()


if __name__ == "__main__":
    raise SystemExit(main())
