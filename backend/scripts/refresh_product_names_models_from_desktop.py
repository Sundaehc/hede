"""Refresh product names and models from the desktop men's and women's XLS exports.

The source data is matched against both ``sku`` and ``original_sku``.  Empty
source cells never clear an archive value.  When the source has conflicting
non-empty values for the same product and field, that field is skipped so the
script cannot choose a value arbitrarily.

Run a preview first:
    uv run python -m scripts.refresh_product_names_models_from_desktop

Apply the proposed changes:
    uv run python -m scripts.refresh_product_names_models_from_desktop --apply
"""
from __future__ import annotations

import argparse
import sys
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

import xlrd
from sqlalchemy import select, update

from config import load_settings
from domain.schema import PRODUCT_ARCHIVE_TABLES
from storage.product_repository import ProductRepository

sys.stdout.reconfigure(encoding="utf-8")

SOURCES = {
    "cbanner_mens": Path.home() / "Desktop" / "男鞋.xls",
    "cbanner_womens": Path.home() / "Desktop" / "女鞋.xls",
}
SOURCE_FIELD_TO_ARCHIVE_FIELD = {
    "品名": "product_name",
    "产品型号": "product_model",
}
MATCH_HEADERS = ("货号", "原始货号")
TARGET_FIELDS = tuple(SOURCE_FIELD_TO_ARCHIVE_FIELD.values())


@dataclass(frozen=True)
class SourceReadResult:
    values_by_code: dict[str, dict[str, set[str]]]
    data_rows: int
    usable_rows: int


def cell_text(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value).strip()


def find_header_row(sheet) -> tuple[int, dict[str, int]]:
    required_headers = {*MATCH_HEADERS, *SOURCE_FIELD_TO_ARCHIVE_FIELD}
    for row_index in range(min(sheet.nrows, 50)):
        headers = {cell_text(value).replace("\n", "").replace("\r", ""): index for index, value in enumerate(sheet.row_values(row_index))}
        if set(MATCH_HEADERS).issubset(headers) and any(header in headers for header in SOURCE_FIELD_TO_ARCHIVE_FIELD):
            return row_index, headers
    raise ValueError(f"{sheet.name} 未找到货号、原始货号及品名/产品型号表头")


def read_source(path: Path) -> SourceReadResult:
    if not path.exists():
        raise FileNotFoundError(f"未找到来源文件：{path}")

    workbook = xlrd.open_workbook(str(path))
    values_by_code: dict[str, dict[str, set[str]]] = defaultdict(lambda: defaultdict(set))
    data_rows = 0
    usable_rows = 0
    try:
        for sheet in workbook.sheets():
            header_row, headers = find_header_row(sheet)
            source_indexes = {
                source_field: headers[source_field]
                for source_field in SOURCE_FIELD_TO_ARCHIVE_FIELD
                if source_field in headers
            }
            for row_index in range(header_row + 1, sheet.nrows):
                data_rows += 1
                row = sheet.row_values(row_index)
                source_values = {
                    SOURCE_FIELD_TO_ARCHIVE_FIELD[source_field]: cell_text(row[column_index]) if column_index < len(row) else ""
                    for source_field, column_index in source_indexes.items()
                }
                source_values = {field: value for field, value in source_values.items() if value}
                if not source_values:
                    continue
                codes = {
                    cell_text(row[headers[header]])
                    for header in MATCH_HEADERS
                    if headers[header] < len(row) and cell_text(row[headers[header]])
                }
                if not codes:
                    continue
                usable_rows += 1
                for code in codes:
                    for field, value in source_values.items():
                        values_by_code[code][field].add(value)
    finally:
        workbook.release_resources()

    return SourceReadResult(dict(values_by_code), data_rows, usable_rows)


def resolved_values_by_code(values_by_code: dict[str, dict[str, set[str]]]) -> tuple[dict[str, dict[str, str]], int]:
    resolved: dict[str, dict[str, str]] = {}
    conflicts = 0
    for code, field_values in values_by_code.items():
        fields: dict[str, str] = {}
        for field, values in field_values.items():
            if len(values) == 1:
                fields[field] = next(iter(values))
            elif values:
                conflicts += 1
        if fields:
            resolved[code] = fields
    return resolved, conflicts


def merge_source_results(results: list[SourceReadResult]) -> SourceReadResult:
    values_by_code: dict[str, dict[str, set[str]]] = defaultdict(lambda: defaultdict(set))
    for result in results:
        for code, field_values in result.values_by_code.items():
            for field, values in field_values.items():
                values_by_code[code][field].update(values)
    return SourceReadResult(
        dict(values_by_code),
        sum(result.data_rows for result in results),
        sum(result.usable_rows for result in results),
    )


def build_updates(
    repository: ProductRepository,
    brand: str,
    source: SourceReadResult,
    target_fields: tuple[str, ...] = TARGET_FIELDS,
) -> tuple[list[tuple[int, dict[str, str]]], dict[str, int]]:
    table = PRODUCT_ARCHIVE_TABLES[brand]
    source_values, source_field_conflicts = resolved_values_by_code(source.values_by_code)
    updates: list[tuple[int, dict[str, str]]] = []
    matched_products = 0
    target_field_conflicts = 0
    unchanged_fields = 0

    with repository.engine.connect() as connection:
        rows = connection.execute(
            select(table.c.id, table.c.sku, table.c.original_sku, table.c.product_name, table.c.product_model)
        ).mappings()
        for row in rows:
            db_codes = {cell_text(row.get("sku")), cell_text(row.get("original_sku"))} - {""}
            candidate_values: dict[str, set[str]] = defaultdict(set)
            for code in db_codes:
                for field, value in source_values.get(code, {}).items():
                    candidate_values[field].add(value)
            if not candidate_values:
                continue
            matched_products += 1
            changes: dict[str, str] = {}
            for field, values in candidate_values.items():
                if field not in target_fields:
                    continue
                if len(values) != 1:
                    target_field_conflicts += 1
                    continue
                value = next(iter(values))
                if cell_text(row.get(field)) == value:
                    unchanged_fields += 1
                    continue
                changes[field] = value
            if changes:
                updates.append((int(row["id"]), changes))

    return updates, {
        "source_codes": len(source_values),
        "source_field_conflicts": source_field_conflicts,
        "matched_products": matched_products,
        "target_field_conflicts": target_field_conflicts,
        "unchanged_fields": unchanged_fields,
    }


def apply_updates(repository: ProductRepository, brand: str, updates_to_apply: list[tuple[int, dict[str, str]]]) -> None:
    if not updates_to_apply:
        return
    table = PRODUCT_ARCHIVE_TABLES[brand]
    with repository.engine.begin() as connection:
        for product_id, changes in updates_to_apply:
            connection.execute(update(table).where(table.c.id == product_id).values(**changes))


def main() -> None:
    parser = argparse.ArgumentParser(description="从桌面男鞋、女鞋 XLS 回填商品档案品名和产品型号")
    parser.add_argument("--apply", action="store_true", help="执行数据库更新；未传入时仅预览")
    parser.add_argument(
        "--target-brand",
        choices=("cbanner_mens", "cbanner_womens", "smiley"),
        help="将来源数据回填到指定商品档案品牌",
    )
    args = parser.parse_args()

    repository = ProductRepository(load_settings().database_url)
    total_updates = 0
    print("模式：" + ("正式回填" if args.apply else "预览（未写入数据库）"))
    if args.target_brand == "smiley":
        source = merge_source_results([read_source(path) for path in SOURCES.values()])
        target_fields = TARGET_FIELDS
        updates_to_apply, stats = build_updates(repository, args.target_brand, source, target_fields)
        field_counts = {field: sum(field in changes for _, changes in updates_to_apply) for field in target_fields}
        print(
            f"男鞋.xls + 女鞋.xls -> {args.target_brand}：来源 {source.data_rows} 行，"
            f"有效 {source.usable_rows} 行，来源货号 {stats['source_codes']} 个，"
            f"匹配商品 {stats['matched_products']} 条，待更新 {len(updates_to_apply)} 条，"
            f"品名 {field_counts['product_name']} 项，产品型号 {field_counts['product_model']} 项，"
            f"来源冲突 {stats['source_field_conflicts']} 项，匹配冲突 {stats['target_field_conflicts']} 项"
        )
        if args.apply:
            apply_updates(repository, args.target_brand, updates_to_apply)
        total_updates += len(updates_to_apply)
    else:
        for brand, source_path in SOURCES.items():
            source = read_source(source_path)
            updates_to_apply, stats = build_updates(repository, brand, source)
            field_counts = {field: sum(field in changes for _, changes in updates_to_apply) for field in TARGET_FIELDS}
            print(
                f"{source_path.name} -> {brand}：来源 {source.data_rows} 行，"
                f"有效 {source.usable_rows} 行，来源货号 {stats['source_codes']} 个，"
                f"匹配商品 {stats['matched_products']} 条，待更新 {len(updates_to_apply)} 条，"
                f"品名 {field_counts['product_name']} 项，产品型号 {field_counts['product_model']} 项，"
                f"来源冲突 {stats['source_field_conflicts']} 项，匹配冲突 {stats['target_field_conflicts']} 项"
            )
            if args.apply:
                apply_updates(repository, brand, updates_to_apply)
            total_updates += len(updates_to_apply)

    print(("已回填" if args.apply else "待回填") + f"商品记录：{total_updates} 条")


if __name__ == "__main__":
    main()
