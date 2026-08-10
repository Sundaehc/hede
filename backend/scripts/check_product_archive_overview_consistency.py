"""Compare overview workbook color codes and product models with the archive."""
from __future__ import annotations

import sys
from collections import Counter

from sqlalchemy import select

from config import load_settings
from domain.schema import PRODUCT_ARCHIVE_TABLES
from scripts.backfill_product_archive_from_overview import DEFAULT_SOURCE_PATH, read_source, text_value
from storage.product_repository import ProductRepository


CHECK_FIELDS = ("color_code", "product_model")


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    source, _, skipped = read_source(DEFAULT_SOURCE_PATH)
    repository = ProductRepository(load_settings().database_url)
    print(f"来源：{DEFAULT_SOURCE_PATH.name}，未识别品牌行：{skipped}")

    totals = Counter()
    for brand, table in PRODUCT_ARCHIVE_TABLES.items():
        if brand not in source:
            continue
        source_values = source[brand]
        stats = Counter()
        with repository.engine.connect() as connection:
            rows = connection.execute(select(table.c.id, table.c.sku, table.c.original_sku, table.c.color_code, table.c.product_model)).mappings()
            for row in rows:
                candidates: dict[str, set[object]] = {field: set() for field in CHECK_FIELDS}
                for code in {text_value(row["sku"]), text_value(row["original_sku"])} - {""}:
                    for field in CHECK_FIELDS:
                        candidates[field].update(source_values.get(code, {}).get(field, set()))
                if not any(candidates.values()):
                    continue
                stats["matched"] += 1
                for field in CHECK_FIELDS:
                    values = candidates[field]
                    if len(values) > 1:
                        stats[f"{field}_source_conflict"] += 1
                        continue
                    if not values:
                        stats[f"{field}_source_blank"] += 1
                        continue
                    source_value = text_value(next(iter(values)))
                    target_value = text_value(row[field])
                    if not target_value:
                        stats[f"{field}_db_blank"] += 1
                    elif target_value == source_value:
                        stats[f"{field}_same"] += 1
                    else:
                        stats[f"{field}_different"] += 1

        print(
            f"{brand}：匹配 {stats['matched']} 条；"
            f"颜色代码一致 {stats['color_code_same']}，数据库为空 {stats['color_code_db_blank']}，"
            f"不一致 {stats['color_code_different']}，来源冲突 {stats['color_code_source_conflict']}；"
            f"产品型号一致 {stats['product_model_same']}，数据库为空 {stats['product_model_db_blank']}，"
            f"不一致 {stats['product_model_different']}，来源冲突 {stats['product_model_source_conflict']}"
        )
        totals.update(stats)

    print(
        f"合计：颜色代码一致 {totals['color_code_same']}，数据库为空 {totals['color_code_db_blank']}，"
        f"不一致 {totals['color_code_different']}；产品型号一致 {totals['product_model_same']}，"
        f"数据库为空 {totals['product_model_db_blank']}，不一致 {totals['product_model_different']}"
    )


if __name__ == "__main__":
    main()
