"""Compare blank archive season/year fields with the overview workbook."""
from __future__ import annotations

import sys
from collections import Counter

from sqlalchemy import func, or_, select

from config import load_settings
from domain.schema import PRODUCT_ARCHIVE_TABLES
from scripts.align_product_color_model_from_overview import DEFAULT_SOURCE_PATH, read_source, text_value
from storage.product_repository import ProductRepository


FIELDS = ("season_category", "year")
SOURCE_LABELS = {"season_category": "季节分类", "year": "年份"}


def is_blank(column):
    return or_(column.is_(None), func.btrim(column) == "")


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    source, unclassified = read_source(DEFAULT_SOURCE_PATH, FIELDS)
    repository = ProductRepository(load_settings().database_url)
    print(f"来源：{DEFAULT_SOURCE_PATH.name}，未识别品牌行：{unclassified}")
    totals = Counter()

    with repository.engine.connect() as connection:
        for brand, table in PRODUCT_ARCHIVE_TABLES.items():
            stats = Counter()
            rows = connection.execute(
                select(table.c.sku, table.c.original_sku, table.c.season_category, table.c.year)
                .where(or_(is_blank(table.c.season_category), is_blank(table.c.year)))
            ).mappings()
            for row in rows:
                for field in FIELDS:
                    if row[field] is not None and str(row[field]).strip():
                        continue
                    stats[f"{field}_db_empty"] += 1
                    candidates = None
                    for code_type, code in (("货号", text_value(row["sku"])), ("原始货号", text_value(row["original_sku"]))):
                        if not code:
                            continue
                        source_record = source.get(brand, {}).get(code_type, {}).get(code)
                        if source_record is not None:
                            candidates = source_record.get(field, set())
                            break
                    if candidates is None:
                        stats[f"{field}_no_match"] += 1
                    elif len(candidates) > 1:
                        stats[f"{field}_conflict"] += 1
                    elif len(candidates) == 1:
                        stats[f"{field}_source_has_value"] += 1
                    else:
                        stats[f"{field}_source_empty"] += 1

            print(
                f"{brand}："
                + "；".join(
                    f"{SOURCE_LABELS[field]}数据库空 {stats[f'{field}_db_empty']}，"
                    f"Excel有值 {stats[f'{field}_source_has_value']}，"
                    f"Excel空 {stats[f'{field}_source_empty']}，"
                    f"冲突 {stats[f'{field}_conflict']}，未匹配 {stats[f'{field}_no_match']}"
                    for field in FIELDS
                )
            )
            totals.update(stats)

    print(
        "合计："
        + "；".join(
            f"{SOURCE_LABELS[field]}数据库空 {totals[f'{field}_db_empty']}，"
            f"Excel有值 {totals[f'{field}_source_has_value']}，"
            f"Excel空 {totals[f'{field}_source_empty']}，"
            f"冲突 {totals[f'{field}_conflict']}，未匹配 {totals[f'{field}_no_match']}"
            for field in FIELDS
        )
    )


if __name__ == "__main__":
    main()
