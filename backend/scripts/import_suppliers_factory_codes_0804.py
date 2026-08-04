"""Update suppliers from the desktop 2026-08-04 factory-code exports.

Both sources are legacy XLS files whose compound-document metadata may be
incomplete.  The reader therefore falls back to the underlying BIFF workbook
stream when ``xlrd`` cannot expose worksheet rows.

Run a preview first:
    uv run python -m scripts.import_suppliers_factory_codes_0804

Apply the changes:
    uv run python -m scripts.import_suppliers_factory_codes_0804 --apply
"""
from __future__ import annotations

import argparse
import sys
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from struct import unpack_from

import xlrd
from sqlalchemy import create_engine, insert, select, update
from xlrd.book import unpack_SST_table
from xlrd.compdoc import CompDoc

from config import load_settings
from domain.gj_brand import CBANNER_MENS_BRAND, CBANNER_WOMENS_BRAND, infer_supplier_brand_from_name
from domain.inventory_schema import SUPPLIER_TABLE

sys.stdout.reconfigure(encoding="utf-8")

CODE_HEADERS = {"单位编号", "编号", "单位代码"}
NAME_HEADERS = {"单位全名", "单位名称", "全名"}
CONTACT_HEADERS = {"联系人"}
LABELSST = 0x00FD
SST = 0x00FC
CONTINUE = 0x003C
EOF = 0x000A
BOUNDSHEET = 0x0085


@dataclass(frozen=True)
class SourceSpec:
    path: Path
    forced_brand: str | None = None


SOURCES = (
    SourceSpec(Path.home() / "Desktop" / "千百度女鞋的工厂代码8.4.xls", CBANNER_WOMENS_BRAND),
    SourceSpec(Path.home() / "Desktop" / "其他工厂代码8.4.xls"),
)


def _text(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value).strip()


def _normal_xls_rows(path: Path) -> list[list[object]]:
    workbook = xlrd.open_workbook(str(path), ignore_workbook_corruption=True)
    sheet = workbook.sheet_by_index(0)
    if sheet.nrows == 0:
        return []
    return [sheet.row_values(row_index) for row_index in range(sheet.nrows)]


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
    """Read LABELSST cells when the XLS root short-stream size is invalid."""
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


def _source_rows(path: Path) -> list[list[object]]:
    try:
        rows = _normal_xls_rows(path)
    except xlrd.XLRDError:
        rows = []
    return rows or _legacy_xls_rows(path)


def _find_header_indexes(rows: list[list[object]]) -> tuple[int, int, int | None, int] | None:
    for row_index, row in enumerate(rows[:30]):
        headers = {_text(value): index for index, value in enumerate(row) if _text(value)}
        code_index = next((headers[header] for header in CODE_HEADERS if header in headers), None)
        name_index = next((headers[header] for header in NAME_HEADERS if header in headers), None)
        contact_index = next((headers[header] for header in CONTACT_HEADERS if header in headers), None)
        if code_index is not None and name_index is not None:
            return code_index, name_index, contact_index, row_index
    return None


def _read_source(spec: SourceSpec) -> tuple[list[dict[str, str]], int]:
    if not spec.path.exists():
        raise FileNotFoundError(f"未找到来源文件：{spec.path}")
    rows = _source_rows(spec.path)
    indexes = _find_header_indexes(rows)
    if indexes is None:
        raise ValueError(f"{spec.path.name} 未找到单位编号、单位全名表头")
    code_index, name_index, contact_index, header_row = indexes

    records: list[dict[str, str]] = []
    fallback_brand_count = 0
    for row in rows[header_row + 1:]:
        factory_code = _text(row[code_index] if code_index < len(row) else None)
        name = _text(row[name_index] if name_index < len(row) else None)
        if not factory_code or not name:
            continue
        inferred_brand = infer_supplier_brand_from_name(name)
        brand = spec.forced_brand or inferred_brand or CBANNER_MENS_BRAND
        if spec.forced_brand is None and inferred_brand is None:
            fallback_brand_count += 1
        contact = _text(row[contact_index] if contact_index is not None and contact_index < len(row) else None)
        records.append({
            "brand": brand,
            "factory_code": factory_code,
            "name": name,
            "contact": contact,
        })
    return records, fallback_brand_count


def _dedupe_records(records: list[dict[str, str]]) -> tuple[list[dict[str, str]], int]:
    by_code: dict[tuple[str, str], dict[str, str]] = {}
    conflict_keys: set[tuple[str, str]] = set()
    for record in records:
        key = (record["brand"], record["factory_code"])
        previous = by_code.get(key)
        if previous is not None and previous["name"] != record["name"]:
            conflict_keys.add(key)
            continue
        by_code[key] = record

    name_codes: dict[tuple[str, str], set[str]] = defaultdict(set)
    for record in by_code.values():
        name_codes[(record["brand"], record["name"])].add(record["factory_code"])
    conflicted_names = {key for key, codes in name_codes.items() if len(codes) > 1}
    return [
        record
        for key, record in by_code.items()
        if key not in conflict_keys and (record["brand"], record["name"]) not in conflicted_names
    ], len(conflict_keys) + len(conflicted_names)


def _unique_lookup(rows: list[dict[str, object]], key_name: str) -> tuple[dict[tuple[str, str], dict[str, object]], set[tuple[str, str]]]:
    lookup: dict[tuple[str, str], dict[str, object]] = {}
    conflicts: set[tuple[str, str]] = set()
    for row in rows:
        brand = _text(row.get("brand"))
        value = _text(row.get(key_name))
        if not brand or not value:
            continue
        key = (brand, value)
        if key in lookup:
            conflicts.add(key)
        else:
            lookup[key] = row
    return lookup, conflicts


def preview_or_apply(*, apply: bool) -> dict[str, int]:
    all_records: list[dict[str, str]] = []
    female_records = 0
    other_records = 0
    fallback_brand_count = 0
    for source in SOURCES:
        records, fallback_count = _read_source(source)
        all_records.extend(records)
        fallback_brand_count += fallback_count
        if source.forced_brand == CBANNER_WOMENS_BRAND:
            female_records += len(records)
        else:
            other_records += len(records)

    records, source_conflicts = _dedupe_records(all_records)
    settings = load_settings()
    engine = create_engine(settings.database_url, future=True)
    inserted = updated = unchanged = match_conflicts = 0
    with engine.begin() as connection:
        existing_rows = [dict(row) for row in connection.execute(select(SUPPLIER_TABLE)).mappings()]
        by_code, code_conflicts = _unique_lookup(existing_rows, "factory_code")
        by_name, name_conflicts = _unique_lookup(existing_rows, "name")
        for record in records:
            code_key = (record["brand"], record["factory_code"])
            name_key = (record["brand"], record["name"])
            code_match = None if code_key in code_conflicts else by_code.get(code_key)
            name_match = None if name_key in name_conflicts else by_name.get(name_key)
            if code_match is not None and name_match is not None and code_match["id"] != name_match["id"]:
                match_conflicts += 1
                continue
            existing = code_match or name_match
            if existing is None:
                if apply:
                    connection.execute(insert(SUPPLIER_TABLE).values(**record))
                inserted += 1
                continue

            changes = {
                key: value
                for key, value in record.items()
                if value and _text(existing.get(key)) != value
            }
            if not changes:
                unchanged += 1
                continue
            if apply:
                connection.execute(
                    update(SUPPLIER_TABLE)
                    .where(SUPPLIER_TABLE.c.id == existing["id"])
                    .values(**changes)
                )
            updated += 1

    engine.dispose()
    return {
        "female_records": female_records,
        "other_records": other_records,
        "records": len(records),
        "fallback_brand_count": fallback_brand_count,
        "source_conflicts": source_conflicts,
        "database_conflicts": len(code_conflicts) + len(name_conflicts) + match_conflicts,
        "inserted": inserted,
        "updated": updated,
        "unchanged": unchanged,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="根据桌面 8.4 工厂代码文件更新供应商管理")
    parser.add_argument("--apply", action="store_true", help="执行更新；未传入时仅预览")
    args = parser.parse_args()
    result = preview_or_apply(apply=args.apply)
    print("模式：" + ("正式更新" if args.apply else "预览（未写入数据库）"))
    print(
        f"女鞋来源 {result['female_records']} 条，其他来源 {result['other_records']} 条，"
        f"去重后 {result['records']} 条；其他文件默认归入千百度男鞋 {result['fallback_brand_count']} 条；"
        f"新增 {result['inserted']} 条，更新 {result['updated']} 条，未变化 {result['unchanged']} 条；"
        f"来源冲突 {result['source_conflicts']} 项，数据库冲突 {result['database_conflicts']} 项"
    )


if __name__ == "__main__":
    main()
