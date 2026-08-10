"""Align archive color codes and product models with the overview workbook."""
from __future__ import annotations

import argparse
import sys
from collections import Counter, defaultdict
from pathlib import Path

from openpyxl import load_workbook
from sqlalchemy import select, update

from config import load_settings
from domain.schema import PRODUCT_ARCHIVE_TABLES
from storage.product_repository import ProductRepository
from transform.rows import normalize_cell, normalize_header


DEFAULT_SOURCE_PATH = Path.home() / "Desktop" / "总览商品信息档案 (1).xlsx"
BRAND_MAP = {
    "千百度男鞋": "cbanner_mens",
    "千百度女鞋": "cbanner_womens",
    "烟斗": "yandou",
    "伊伴": "eblan",
}
MATCH_HEADERS = ("货号", "原始货号")
FIELDS = ("颜色代码", "产品型号")
FIELD_MAP = {"颜色代码": "color_code", "产品型号": "product_model"}


def text_value(value: object) -> str:
    normalized = normalize_cell(value)
    return str(normalized).strip() if normalized is not None else ""


def find_headers(sheet) -> tuple[int, dict[str, int]]:
    required = {*MATCH_HEADERS, "品牌", *FIELDS}
    for row_index in range(1, min(sheet.max_row, 30) + 1):
        values = next(sheet.iter_rows(min_row=row_index, max_row=row_index, values_only=True))
        headers = {
            normalize_header(value): index
            for index, value in enumerate(values)
            if normalize_header(value)
        }
        if required.issubset(headers):
            return row_index, headers
    raise ValueError(f"{sheet.title} 未找到颜色代码/产品型号对齐所需表头")


def read_source(path: Path) -> tuple[dict[str, dict[str, dict[str, set[str]]]], int]:
    if not path.exists():
        raise FileNotFoundError(f"未找到来源文件：{path}")
    source: dict[str, dict[str, dict[str, set[str]]]] = defaultdict(
        lambda: defaultdict(lambda: defaultdict(set))
    )
    unclassified = 0
    workbook = load_workbook(path, data_only=True, read_only=True)
    try:
        for sheet in workbook.worksheets:
            header_row, headers = find_headers(sheet)
            for row in sheet.iter_rows(min_row=header_row + 1, values_only=True):
                if not any(value is not None for value in row):
                    continue
                brand = BRAND_MAP.get(text_value(row[headers["品牌"]]))
                if brand is None:
                    unclassified += 1
                    continue
                field_values = {
                    FIELD_MAP[source_field]: text_value(row[headers[source_field]])
                    for source_field in FIELDS
                    if headers[source_field] < len(row) and text_value(row[headers[source_field]])
                }
                if not field_values:
                    continue
                for header in MATCH_HEADERS:
                    code = text_value(row[headers[header]]) if headers[header] < len(row) else ""
                    if not code:
                        continue
                    for field, value in field_values.items():
                        source[brand][code][field].add(value)
    finally:
        workbook.close()
    return {
        brand: {code: dict(fields) for code, fields in codes.items()}
        for brand, codes in source.items()
    }, unclassified


def build_updates(repository: ProductRepository, brand: str, source):
    table = PRODUCT_ARCHIVE_TABLES[brand]
    updates: list[tuple[int, dict[str, str]]] = []
    stats = Counter()
    with repository.engine.connect() as connection:
        rows = connection.execute(
            select(table.c.id, table.c.sku, table.c.original_sku, table.c.color_code, table.c.product_model)
        ).mappings()
        for row in rows:
            stats["total"] += 1
            codes = [text_value(row["sku"]), text_value(row["original_sku"])]
            changes: dict[str, str] = {}
            for field in FIELD_MAP.values():
                source_value = None
                selected_code = None
                for code in codes:
                    if not code or code not in source:
                        continue
                    candidates = source[code].get(field, set())
                    if len(candidates) > 1:
                        stats[f"{field}_conflict"] += 1
                        source_value = None
                        selected_code = code
                        break
                    if len(candidates) == 1:
                        source_value = next(iter(candidates))
                        selected_code = code
                        break
                if selected_code is None or source_value is None:
                    continue
                stats[f"{field}_matched"] += 1
                if text_value(row[field]) == source_value:
                    stats[f"{field}_same"] += 1
                else:
                    changes[field] = source_value
                    stats[f"{field}_different"] += 1
            if changes:
                updates.append((int(row["id"]), changes))
    return updates, stats


def apply_updates(repository: ProductRepository, brand: str, updates: list[tuple[int, dict[str, str]]]) -> None:
    if not updates:
        return
    table = PRODUCT_ARCHIVE_TABLES[brand]
    with repository.engine.begin() as connection:
        for product_id, changes in updates:
            connection.execute(update(table).where(table.c.id == product_id).values(**changes))


def main() -> None:
    parser = argparse.ArgumentParser(description="按总览商品信息档案对齐颜色代码和产品型号")
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE_PATH)
    parser.add_argument("--apply", action="store_true", help="写入数据库；默认仅预览")
    args = parser.parse_args()
    sys.stdout.reconfigure(encoding="utf-8")

    source, unclassified = read_source(args.source)
    repository = ProductRepository(load_settings().database_url)
    print("模式：" + ("正式对齐" if args.apply else "预览（未写入数据库）"))
    print(f"来源：{args.source.name}，未识别品牌行：{unclassified}")

    total_updates = 0
    for brand in BRAND_MAP.values():
        updates, stats = build_updates(repository, brand, source.get(brand, {}))
        print(
            f"{brand}：颜色代码匹配 {stats['color_code_matched']}，一致 {stats['color_code_same']}，"
            f"需对齐 {stats['color_code_different']}，冲突 {stats['color_code_conflict']}；"
            f"产品型号匹配 {stats['product_model_matched']}，一致 {stats['product_model_same']}，"
            f"需对齐 {stats['product_model_different']}，冲突 {stats['product_model_conflict']}；"
            f"涉及商品 {len(updates)} 条"
        )
        if args.apply:
            apply_updates(repository, brand, updates)
        total_updates += len(updates)
    print(("已对齐" if args.apply else "待对齐") + f"商品记录：{total_updates} 条")


if __name__ == "__main__":
    main()
