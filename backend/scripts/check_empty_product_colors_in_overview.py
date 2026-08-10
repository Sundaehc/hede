"""Check whether archive rows with blank colors have a color in the overview."""
from __future__ import annotations

import sys
import argparse
from collections import Counter

from sqlalchemy import or_, select, func

from config import load_settings
from domain.schema import PRODUCT_ARCHIVE_TABLES
from scripts.align_product_color_model_from_overview import DEFAULT_SOURCE_PATH, read_source, text_value
from storage.product_repository import ProductRepository


def is_blank(column):
    return or_(column.is_(None), func.btrim(column) == "")


def main() -> None:
    parser = argparse.ArgumentParser(description="核对总览 Excel 中空颜色商品的来源情况")
    parser.add_argument("--show-skus", action="store_true", help="输出全部货号")
    args = parser.parse_args()
    sys.stdout.reconfigure(encoding="utf-8")
    source, unclassified = read_source(DEFAULT_SOURCE_PATH, ("color",))
    repository = ProductRepository(load_settings().database_url)
    print(f"来源：{DEFAULT_SOURCE_PATH.name}，未识别品牌行：{unclassified}")
    total = Counter()
    with repository.engine.connect() as connection:
        for brand, table in PRODUCT_ARCHIVE_TABLES.items():
            rows = connection.execute(
                select(table.c.sku, table.c.original_sku, table.c.color, table.c.color_code)
                .where(is_blank(table.c.color))
            ).mappings()
            stats = Counter()
            examples = []
            codes_by_category: dict[str, list[str]] = {
                "Excel有颜色": [],
                "来源冲突": [],
                "Excel颜色为空": [],
                "Excel无颜色或未匹配": [],
            }
            conflict_values: dict[str, tuple[str, ...]] = {}
            for row in rows:
                stats["database_blank"] += 1
                candidates = None
                matched_source = False
                for code_type, code in (("货号", text_value(row["sku"])), ("原始货号", text_value(row["original_sku"]))):
                    if not code:
                        continue
                    source_record = source.get(brand, {}).get(code_type, {}).get(code)
                    if source_record is not None:
                        candidates = source_record.get("color", set())
                        matched_source = True
                        break
                if matched_source and len(candidates) > 1:
                    stats["source_conflict"] += 1
                    category = "来源冲突"
                    conflict_values[str(row["sku"])] = tuple(sorted(candidates))
                elif matched_source and len(candidates) == 1:
                    stats["source_has_color"] += 1
                    category = "Excel有颜色"
                elif matched_source:
                    stats["source_blank"] += 1
                    category = "Excel颜色为空"
                else:
                    stats["source_no_color"] += 1
                    category = "Excel无颜色或未匹配"
                codes_by_category[category].append(str(row["sku"]))
                if len(examples) < 5:
                    examples.append(f"{row['sku']}({category})")
            print(
                f"{brand}：数据库空颜色 {stats['database_blank']}，Excel有颜色 {stats['source_has_color']}，"
                f"来源冲突 {stats['source_conflict']}，Excel颜色为空 {stats['source_blank']}，"
                f"Excel无颜色或未匹配 {stats['source_no_color']}；"
                f"示例：{'、'.join(examples) or '-'}"
            )
            if args.show_skus:
                for category, codes in codes_by_category.items():
                    if codes:
                        print(f"  {category}：{'、'.join(codes)}")
                if conflict_values:
                    for sku, colors in conflict_values.items():
                        print(f"  {sku}：{'、'.join(colors)}")
            total.update(stats)
    print(
        f"合计：数据库空颜色 {total['database_blank']}，Excel有颜色 {total['source_has_color']}，"
        f"来源冲突 {total['source_conflict']}，Excel颜色为空 {total['source_blank']}，"
        f"Excel无颜色或未匹配 {total['source_no_color']}"
    )


if __name__ == "__main__":
    main()
