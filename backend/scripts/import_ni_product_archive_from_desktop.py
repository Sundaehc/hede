"""Import NI product master data and optional one-off unit costs from Desktop XLS files.

This script is intentionally manual-only. It is not registered as a scheduled
task: the NI price workbook is used only to backfill the current cost unit
price when it contains data.
"""
from __future__ import annotations

import argparse
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

import xlrd
from sqlalchemy import func
from sqlalchemy.dialects.postgresql import insert as pg_insert

from config import load_settings
from domain.schema import PRODUCT_ARCHIVE_TABLES
from storage.db import Database


DEFAULT_PRODUCT_FILE = Path.home() / "Desktop" / "NI商品信息数据-2026_08_06-11_04_35.xls"
DEFAULT_PRICE_FILE = Path.home() / "Desktop" / "NI物价信息查询数据-2026_08_06-11_04_46.xls"
PRODUCT_CODE_HEADERS = ("货号", "商品编码", "商品条码")
PRODUCT_SOURCE_FIELDS = {
    "原始货号": "original_sku",
    "工厂货号": "factory_sku",
    "品名": "product_name",
    "鞋垫材质": "insole_material",
    "大底材质": "outsole_material",
    "鞋面材质": "upper_material",
    "内里材质": "lining_material",
    "上市日期": "launch_date",
    "执行标准": "execution_standard",
    "产品型号": "product_model",
    "主供应商": "supplier_name",
}
PRICE_CODE_HEADERS = ("货号", "商品编码", "商品条码")
PRICE_COST_HEADERS = ("成本单价",)


@dataclass(frozen=True)
class ImportSummary:
    product_rows: int
    product_rows_skipped: int
    product_duplicates: int
    cost_rows: int
    cost_rows_skipped: int
    cost_conflicts: int
    matched_costs: int
    applied: bool


def _text(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value).strip()


def _header_text(value: object) -> str:
    return _text(value).replace("\n", "").replace("\r", "").replace(" ", "")


def _find_header_row(sheet, required_headers: tuple[str, ...]) -> tuple[int, dict[str, int]] | None:
    normalized_required = {_header_text(header) for header in required_headers}
    for row_index in range(min(sheet.nrows, 50)):
        headers = {
            _header_text(value): index
            for index, value in enumerate(sheet.row_values(row_index))
            if _header_text(value)
        }
        if normalized_required.intersection(headers):
            return row_index, headers
    return None


def _value(row: list[object], headers: dict[str, int], header: str, *, datemode: int) -> str:
    index = headers.get(_header_text(header))
    if index is None or index >= len(row):
        return ""
    value = row[index]
    if header == "上市日期" and isinstance(value, (int, float)):
        try:
            return xlrd.xldate.xldate_as_datetime(value, datemode).date().isoformat()
        except (OverflowError, ValueError, xlrd.xldate.XLDateError):
            pass
    return _text(value)


def _year_from_launch_date(launch_date: str) -> str:
    try:
        return str(datetime.fromisoformat(launch_date).year)
    except ValueError:
        return ""


def read_product_rows(source_file: Path) -> tuple[list[dict[str, object]], int, int]:
    if not source_file.is_file():
        raise FileNotFoundError(f"找不到 NI 商品信息文件：{source_file}")

    workbook = xlrd.open_workbook(str(source_file))
    rows_by_sku: dict[str, dict[str, object]] = {}
    skipped = 0
    duplicates = 0
    try:
        for sheet in workbook.sheets():
            header_result = _find_header_row(sheet, PRODUCT_CODE_HEADERS)
            if header_result is None:
                continue
            header_row, headers = header_result
            code_header = next((header for header in PRODUCT_CODE_HEADERS if _header_text(header) in headers), None)
            if code_header is None:
                continue
            raw_headers = [_text(value) for value in sheet.row_values(header_row)]
            for row_number in range(header_row + 1, sheet.nrows):
                row = sheet.row_values(row_number)
                sku = _value(row, headers, code_header, datemode=workbook.datemode)
                if not sku:
                    skipped += 1
                    continue
                source_values = {
                    source_header: _value(row, headers, source_header, datemode=workbook.datemode)
                    for source_header in PRODUCT_SOURCE_FIELDS
                }
                raw_payload = {
                    header: _text(row[index])
                    for index, header in enumerate(raw_headers)
                    if header and index < len(row)
                }
                launch_date = source_values["上市日期"]
                supplier_name = source_values["主供应商"] or "NI"
                record: dict[str, object] = {
                    "source_workbook": source_file.name,
                    "source_sheet": sheet.name,
                    "source_row_number": str(row_number + 1),
                    "raw_payload": raw_payload,
                    "sku": sku,
                    "original_sku": source_values["原始货号"] or sku,
                    "factory_sku": source_values["工厂货号"] or None,
                    "product_name": source_values["品名"] or None,
                    "insole_material": source_values["鞋垫材质"] or None,
                    "outsole_material": source_values["大底材质"] or None,
                    "upper_material": source_values["鞋面材质"] or None,
                    "lining_material": source_values["内里材质"] or None,
                    "launch_date": launch_date or None,
                    "year": _year_from_launch_date(launch_date) or None,
                    "execution_standard": source_values["执行标准"] or None,
                    "product_model": source_values["产品型号"] or None,
                    "supplier_name": supplier_name,
                    "group_name": "NI",
                    "extra_fields": {
                        "商品全名": raw_payload.get("商品全名", ""),
                        "商品条码": raw_payload.get("商品条码", ""),
                        "是否停用": raw_payload.get("是否停用", ""),
                    },
                }
                if sku in rows_by_sku:
                    duplicates += 1
                rows_by_sku[sku] = record
    finally:
        workbook.release_resources()

    return list(rows_by_sku.values()), skipped, duplicates


def _decimal(value: object) -> Decimal | None:
    text = _text(value).replace(",", "")
    if not text:
        return None
    try:
        return Decimal(text)
    except InvalidOperation:
        return None


def read_costs(source_file: Path) -> tuple[dict[str, Decimal], int, int, int]:
    if not source_file.is_file():
        raise FileNotFoundError(f"找不到 NI 物价信息文件：{source_file}")

    workbook = xlrd.open_workbook(str(source_file))
    values_by_code: dict[str, set[Decimal]] = defaultdict(set)
    rows_read = 0
    skipped = 0
    try:
        for sheet in workbook.sheets():
            header_result = _find_header_row(sheet, PRODUCT_CODE_HEADERS + PRICE_COST_HEADERS)
            if header_result is None:
                continue
            header_row, headers = header_result
            code_header = next((header for header in PRICE_CODE_HEADERS if _header_text(header) in headers), None)
            cost_header = next((header for header in PRICE_COST_HEADERS if _header_text(header) in headers), None)
            if code_header is None or cost_header is None:
                continue
            for row_number in range(header_row + 1, sheet.nrows):
                row = sheet.row_values(row_number)
                code = _value(row, headers, code_header, datemode=workbook.datemode)
                cost_index = headers[_header_text(cost_header)]
                cost = _decimal(row[cost_index] if cost_index < len(row) else None)
                if not code or cost is None:
                    skipped += 1
                    continue
                rows_read += 1
                values_by_code[code].add(cost)
    finally:
        workbook.release_resources()

    conflicts = sum(len(values) > 1 for values in values_by_code.values())
    return (
        {code: next(iter(values)) for code, values in values_by_code.items() if len(values) == 1},
        rows_read,
        skipped,
        conflicts,
    )


def import_ni_product_archive(*, product_file: Path, price_file: Path, apply: bool) -> ImportSummary:
    product_rows, product_rows_skipped, product_duplicates = read_product_rows(product_file)
    costs, cost_rows, cost_rows_skipped, cost_conflicts = read_costs(price_file)
    matched_costs = 0
    for row in product_rows:
        cost = costs.get(_text(row.get("sku"))) or costs.get(_text(row.get("original_sku")))
        if cost is not None:
            row["cost"] = cost
            matched_costs += 1

    if apply and product_rows:
        settings = load_settings(require_database=True)
        assert settings.database_url is not None
        database = Database(settings.database_url)
        database.create_tables()
        table = PRODUCT_ARCHIVE_TABLES["ni"]
        update_columns = [
            column.name
            for column in table.columns
            if column.name not in {"id", "sku", "created_at", "cost"}
        ]
        with database._require_engine().begin() as connection:
            statement = pg_insert(table).values(product_rows)
            excluded = statement.excluded
            set_values = {column: getattr(excluded, column) for column in update_columns}
            set_values["cost"] = func.coalesce(excluded.cost, table.c.cost)
            set_values["updated_at"] = func.date_trunc("minute", func.now())
            connection.execute(statement.on_conflict_do_update(index_elements=["sku"], set_=set_values))

    return ImportSummary(
        product_rows=len(product_rows),
        product_rows_skipped=product_rows_skipped,
        product_duplicates=product_duplicates,
        cost_rows=cost_rows,
        cost_rows_skipped=cost_rows_skipped,
        cost_conflicts=cost_conflicts,
        matched_costs=matched_costs,
        applied=apply,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="手动导入 NI 商品信息和一次性成本单价")
    parser.add_argument("--product-file", type=Path, default=DEFAULT_PRODUCT_FILE)
    parser.add_argument("--price-file", type=Path, default=DEFAULT_PRICE_FILE)
    parser.add_argument("--apply", action="store_true", help="写入数据库；未提供时仅预览")
    args = parser.parse_args()
    summary = import_ni_product_archive(
        product_file=args.product_file,
        price_file=args.price_file,
        apply=args.apply,
    )
    print(
        f"模式：{'正式导入' if summary.applied else '预览（未写入数据库）'}；"
        f"商品 {summary.product_rows} 条，跳过 {summary.product_rows_skipped} 条，重复 {summary.product_duplicates} 条；"
        f"物价有效 {summary.cost_rows} 条，跳过 {summary.cost_rows_skipped} 条，冲突 {summary.cost_conflicts} 条；"
        f"匹配成本 {summary.matched_costs} 条"
    )


if __name__ == "__main__":
    main()
