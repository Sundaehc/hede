"""Import product auxiliary attribute options from the two desktop XLS files."""

from __future__ import annotations

import argparse
from pathlib import Path
from struct import unpack_from

import xlrd
from sqlalchemy import delete
from sqlalchemy.dialects.postgresql import insert as pg_insert
from xlrd.book import unpack_SST_table
from xlrd.compdoc import CompDoc

from config import load_settings
from domain.product_auxiliary_attribute_schema import PRODUCT_AUXILIARY_ATTRIBUTE_TABLE
from storage.db import Database
from transform.rows import normalize_header


DEFAULT_WOMENS_SOURCE = Path.home() / "Desktop" / "千百度女鞋辅助属性数据-2026_08_26-14_20_49.xls"
DEFAULT_OTHER_SOURCE = Path.home() / "Desktop" / "其他品牌的辅助属性数据-2026_08_26-14_21_37.xls"
HEADER_NAMES = ("辅助属性名称", "类型名称")
LABELSST = 0x00FD
SST = 0x00FC
CONTINUE = 0x003C
EOF = 0x000A
BOUNDSHEET = 0x0085


def _text(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value).strip()


def _iter_biff_records(data: bytes, start: int):
    position = start
    while position + 4 <= len(data):
        code, size = unpack_from("<HH", data, position)
        end = position + 4 + size
        if end > len(data):
            break
        yield code, data[position + 4:end], position, end
        position = end


def _legacy_xls_rows(path: Path) -> list[list[object]]:
    workbook_data = CompDoc(path.read_bytes()).get_named_stream("Workbook")
    if not workbook_data:
        return []

    shared_strings: list[str] | None = None
    sheet_offset: int | None = None
    for code, payload, _position, end in _iter_biff_records(workbook_data, 0):
        if code == BOUNDSHEET and len(payload) >= 4 and sheet_offset is None:
            sheet_offset = unpack_from("<I", payload, 0)[0]
        if code == SST:
            chunks = [payload]
            continue_position = end
            while continue_position + 4 <= len(workbook_data):
                next_code, next_size = unpack_from("<HH", workbook_data, continue_position)
                if next_code != CONTINUE or continue_position + 4 + next_size > len(workbook_data):
                    break
                chunks.append(workbook_data[continue_position + 4:continue_position + 4 + next_size])
                continue_position += 4 + next_size
            if len(payload) >= 8:
                unique_count = unpack_from("<I", payload, 4)[0]
                shared_strings, _rich_text = unpack_SST_table(chunks, unique_count)
        if code == EOF:
            break

    if shared_strings is None or sheet_offset is None:
        return []

    cells: dict[tuple[int, int], str] = {}
    for code, payload, _position, _end in _iter_biff_records(workbook_data, sheet_offset):
        if code == LABELSST and len(payload) >= 10:
            row_index, column_index, _xf_index, string_index = unpack_from("<HHHI", payload)
            if string_index < len(shared_strings):
                cells[(row_index, column_index)] = shared_strings[string_index]
        if code == EOF:
            break

    if not cells:
        return []
    max_row = max(row_index for row_index, _column_index in cells)
    max_column = max(column_index for _row_index, column_index in cells)
    return [
        [cells.get((row_index, column_index), "") for column_index in range(max_column + 1)]
        for row_index in range(max_row + 1)
    ]


def _read_rows(path: Path) -> tuple[str, list[list[object]]]:
    workbook = xlrd.open_workbook(str(path), ignore_workbook_corruption=True)
    try:
        sheet = workbook.sheet_by_index(0)
        if sheet.nrows:
            return sheet.name, [sheet.row_values(row_index) for row_index in range(sheet.nrows)]
    finally:
        workbook.release_resources()
    rows = _legacy_xls_rows(path)
    return ("", rows)


def _find_headers(rows: list[list[object]]) -> tuple[int, int, int] | None:
    for row_index, row in enumerate(rows[:30]):
        headers = [normalize_header(value) for value in row]
        attribute_index = next((index for index, value in enumerate(headers) if value == HEADER_NAMES[0]), None)
        type_index = next((index for index, value in enumerate(headers) if value == HEADER_NAMES[1]), None)
        if attribute_index is not None and type_index is not None:
            return row_index, attribute_index, type_index
    return None


def _read_source(path: Path, brand_scope: str) -> list[dict[str, object]]:
    if not path.exists():
        raise FileNotFoundError(f"未找到来源文件：{path}")
    sheet_name, rows = _read_rows(path)
    indexes = _find_headers(rows)
    if indexes is None:
        raise ValueError(f"{path.name} 未找到辅助属性名称、类型名称表头")
    header_row, attribute_index, type_index = indexes
    records: list[dict[str, object]] = []
    seen: set[tuple[str, str, str]] = set()
    for row_number, row in enumerate(rows[header_row + 1:], start=header_row + 2):
        attribute_name = _text(row[attribute_index] if attribute_index < len(row) else None)
        attribute_type = _text(row[type_index] if type_index < len(row) else None)
        if not attribute_name or not attribute_type or attribute_type in {"品牌", "季节"}:
            continue
        key = (brand_scope, attribute_type, attribute_name)
        if key in seen:
            continue
        seen.add(key)
        records.append(
            {
                "brand_scope": brand_scope,
                "attribute_type": attribute_type,
                "attribute_name": attribute_name,
                "source_workbook": path.name,
                "source_sheet": sheet_name,
                "source_row_number": str(row_number),
            }
        )
    return records


def import_product_auxiliary_attributes(
    womens_source: Path = DEFAULT_WOMENS_SOURCE,
    other_source: Path = DEFAULT_OTHER_SOURCE,
    *,
    replace: bool = False,
) -> dict[str, int]:
    rows = [
        *_read_source(womens_source, "cbanner_womens"),
        *_read_source(other_source, "other"),
    ]
    settings = load_settings()
    database = Database(settings.database_url)
    database.create_tables()
    table = PRODUCT_AUXILIARY_ATTRIBUTE_TABLE
    with database._require_engine().begin() as connection:
        table.create(connection, checkfirst=True)
        if replace:
            connection.execute(delete(table))
        if rows:
            statement = pg_insert(table).values(rows)
            statement = statement.on_conflict_do_update(
                index_elements=["brand_scope", "attribute_type", "attribute_name"],
                set_={
                    "source_workbook": statement.excluded.source_workbook,
                    "source_sheet": statement.excluded.source_sheet,
                    "source_row_number": statement.excluded.source_row_number,
                    "updated_at": statement.excluded.updated_at,
                },
            )
            connection.execute(statement)
    return {"cbanner_womens": sum(row["brand_scope"] == "cbanner_womens" for row in rows), "other": sum(row["brand_scope"] == "other" for row in rows), "total": len(rows)}


def main() -> None:
    parser = argparse.ArgumentParser(description="导入商品辅助属性选项")
    parser.add_argument("--womens-source", type=Path, default=DEFAULT_WOMENS_SOURCE)
    parser.add_argument("--other-source", type=Path, default=DEFAULT_OTHER_SOURCE)
    parser.add_argument("--replace", action="store_true")
    args = parser.parse_args()
    result = import_product_auxiliary_attributes(args.womens_source, args.other_source, replace=args.replace)
    print(result)


if __name__ == "__main__":
    main()
