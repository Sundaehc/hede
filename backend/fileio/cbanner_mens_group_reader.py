from __future__ import annotations

from pathlib import Path
import re

import xlrd
from openpyxl import load_workbook

from transform.rows import normalize_cell, normalize_header


DEFAULT_CBANNER_MENS_GROUP_SOURCE = Path(
    r"\\192.168.10.229\运营组资料\9商品组（卢嘉诚）\商品分析\商品运营货品表\千百度男鞋"
)
CBANNER_MENS_GROUP_SHEET_NAME = "商品明细表"
SUPPORTED_WORKBOOK_SUFFIXES = (".xlsx", ".xlsm", ".xls")
WORKBOOK_NAME_PREFIX = "赫德货品表（千百度男鞋）"
SKU_HEADERS = ("货号", "商品货号", "商品编码", "货品编码", "货品货号", "原始货号", "款号")
GROUP_HEADERS = ("组别", "运营组别", "商品组别", "货品组别", "分组")


def _safe_is_file(path: Path) -> bool:
    try:
        return path.is_file()
    except OSError:
        return False


def _safe_is_dir(path: Path) -> bool:
    try:
        return path.is_dir()
    except OSError:
        return False


def resolve_cbanner_mens_group_workbook(source: Path | None) -> Path | None:
    if source is None:
        return None
    if _safe_is_file(source):
        return source

    if not _safe_is_dir(source):
        for suffix in SUPPORTED_WORKBOOK_SUFFIXES:
            candidate = Path(f"{source}{suffix}")
            if _safe_is_file(candidate):
                return candidate
        return None

    candidates: list[Path] = []
    try:
        iterator = source.rglob("*")
        for item in iterator:
            if (
                _safe_is_file(item)
                and item.suffix.lower() in SUPPORTED_WORKBOOK_SUFFIXES
                and item.stem.startswith(WORKBOOK_NAME_PREFIX)
            ):
                candidates.append(item)
    except OSError:
        return None
    if not candidates:
        return None

    def sort_key(path: Path) -> tuple[int, int, int, float, str]:
        path_text = str(path)
        year_match = re.search(r"(20\d{2})年", path_text)
        month_match = re.search(r"(\d{1,2})月份", path_text)
        day_match = re.search(r"(\d{1,2})\.(\d{1,2})", path.stem)
        try:
            modified_at = path.stat().st_mtime
        except OSError:
            modified_at = 0
        year = int(year_match.group(1)) if year_match else 0
        month = int(month_match.group(1)) if month_match else 0
        day = int(day_match.group(2)) if day_match else 0
        return year, month, day, modified_at, path.name

    return max(candidates, key=sort_key)


def _find_header_indexes(headers: list[str]) -> tuple[int, int] | None:
    sku_index = next((index for index, value in enumerate(headers) if value in SKU_HEADERS), None)
    group_index = next((index for index, value in enumerate(headers) if value in GROUP_HEADERS), None)
    if sku_index is None or group_index is None:
        return None
    return sku_index, group_index


def _get_value(row: tuple[object, ...], index: int) -> object:
    if index >= len(row):
        return None
    return row[index]


def _read_xlsx_group_map(workbook_path: Path, sheet_name: str) -> dict[str, str]:
    workbook = load_workbook(workbook_path, data_only=True, read_only=True)
    try:
        if sheet_name not in workbook.sheetnames:
            return {}

        worksheet = workbook[sheet_name]
        header_indexes: tuple[int, int] | None = None
        rows = worksheet.iter_rows(values_only=True)
        for row_number, row in enumerate(rows, start=1):
            headers = [normalize_header(value) for value in row]
            header_indexes = _find_header_indexes(headers)
            if header_indexes is not None:
                break
            if row_number >= 30:
                return {}

        if header_indexes is None:
            return {}

        sku_index, group_index = header_indexes
        groups: dict[str, str] = {}
        for row in rows:
            sku = normalize_cell(_get_value(row, sku_index))
            group_name = normalize_cell(_get_value(row, group_index))
            if sku and group_name:
                groups[str(sku)] = str(group_name)
        return groups
    finally:
        workbook.close()


def _read_xls_group_map(workbook_path: Path, sheet_name: str) -> dict[str, str]:
    workbook = xlrd.open_workbook(workbook_path)
    try:
        worksheet = workbook.sheet_by_name(sheet_name)
    except xlrd.biffh.XLRDError:
        return {}

    header_indexes: tuple[int, int] | None = None
    data_start_row = 0
    for row_index in range(min(worksheet.nrows, 30)):
        headers = [normalize_header(value) for value in worksheet.row_values(row_index)]
        header_indexes = _find_header_indexes(headers)
        if header_indexes is not None:
            data_start_row = row_index + 1
            break

    if header_indexes is None:
        return {}

    sku_index, group_index = header_indexes
    groups: dict[str, str] = {}
    for row_index in range(data_start_row, worksheet.nrows):
        row = tuple(worksheet.row_values(row_index))
        sku = normalize_cell(_get_value(row, sku_index))
        group_name = normalize_cell(_get_value(row, group_index))
        if sku and group_name:
            groups[str(sku)] = str(group_name)
    return groups


def read_cbanner_mens_group_map(source: Path | None) -> dict[str, str]:
    workbook_path = resolve_cbanner_mens_group_workbook(source)
    if workbook_path is None:
        return {}

    if workbook_path.suffix.lower() == ".xls":
        return _read_xls_group_map(workbook_path, CBANNER_MENS_GROUP_SHEET_NAME)
    return _read_xlsx_group_map(workbook_path, CBANNER_MENS_GROUP_SHEET_NAME)
