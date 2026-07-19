"""Fill product-goods manual fields from the latest shared brand workbooks."""
from __future__ import annotations

import argparse
from collections import defaultdict
from collections.abc import Iterable
from pathlib import Path
from typing import Any
from zipfile import ZipFile
from xml.etree.ElementTree import iterparse

from sqlalchemy import create_engine, select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from api.product_goods_cache import clear_product_goods_cache
from config import load_settings
from domain.product_goods_schema import PRODUCT_GOODS_OVERRIDES_TABLE
from domain.schema import PRODUCT_TABLES


SHARED_ROOT = Path(
    "\\\\192.168.10.229\\"
    "\u8fd0\u8425\u7ec4\u8d44\u6599\\"
    "9\u5546\u54c1\u7ec4\uff08\u5362\u5609\u8bda\uff09\\"
    "\u5546\u54c1\u5206\u6790\\"
    "\u5546\u54c1\u8fd0\u8425\u8d27\u54c1\u8868"
)
BRAND_FOLDERS = {
    "cbanner_mens": "\u5343\u767e\u5ea6\u7537\u978b",
    "cbanner_womens": "\u5343\u767e\u5ea6\u5973\u978b",
    "yandou": "\u70df\u6597",
    "eblan": "\u4f0a\u4f34",
}
MANUAL_FIELDS = (
    "platform",
    "category_l4",
    "product_role",
    "product_type",
    "douyin_hot",
    "clearance",
    "remark",
)
WRITE_BATCH_SIZE = 1_000
HEADER_ALIASES = {
    "goods_code": ("\u8d27\u53f7", "\u5546\u54c1\u8d27\u53f7", "\u5546\u54c1\u7f16\u7801", "\u539f\u59cb\u8d27\u53f7", "sku", "SKU"),
    "style_code": ("\u6b3e\u53f7", "\u6b3e\u5f0f\u7f16\u7801", "\u539f\u59cb\u6b3e\u53f7", "\u539f\u8d27\u53f7"),
    "platform": ("\u6240\u5c5e\u5e73\u53f0", "\u8fd0\u8425\u5e73\u53f0", "\u5e73\u53f0"),
    "category_l4": ("\u56db\u7ea7\u5206\u7c7b", "4\u7ea7\u5206\u7c7b"),
    "product_role": ("\u5546\u54c1\u89d2\u8272", "\u5546\u54c1\u5b9a\u4f4d"),
    "product_type": ("\u7c7b\u578b", "\u5546\u54c1\u7c7b\u578b"),
    "douyin_hot": ("\u6296\u97f3\u7206\u6b3e", "\u6296\u97f3\u7206\u6b3e\u6807\u7b7e"),
    "clearance": ("\u6e05\u4ed3", "\u6e05\u4ed3\u6807\u8bb0"),
    "remark": ("\u5907\u6ce8", "\u5546\u54c1\u5907\u6ce8"),
}
PRODUCT_SHEET_NAME = "\u5546\u54c1\u660e\u7ec6\u8868"
WORKBOOK_MARKERS = ("\u8d6b\u5fb7", "\u8d27\u54c1\u8868")
XML_NAMESPACE = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
REL_NAMESPACE = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}"
PACKAGE_REL_NAMESPACE = "{http://schemas.openxmlformats.org/package/2006/relationships}"


def _text(value: object) -> str | None:
    if value is None:
        return None
    result = str(value).strip()
    return result or None


def _normalized_header(value: object) -> str:
    return str(value or "").strip().replace("\n", "").replace(" ", "")


def _header_indexes(values: tuple[object, ...]) -> dict[str, int]:
    normalized: dict[str, int] = {}
    for index, value in enumerate(values):
        normalized.setdefault(_normalized_header(value), index)
    indexes: dict[str, int] = {}
    for field, aliases in HEADER_ALIASES.items():
        for alias in aliases:
            index = normalized.get(_normalized_header(alias))
            if index is not None:
                indexes[field] = index
                break
    return indexes


def _find_header(sheet) -> tuple[int, dict[str, int]] | None:
    best: tuple[int, dict[str, int], int] | None = None
    for row_number, values in enumerate(sheet.iter_rows(min_row=1, max_row=min(sheet.max_row, 12), values_only=True), start=1):
        indexes = _header_indexes(values)
        if "goods_code" not in indexes and "style_code" not in indexes:
            continue
        score = 100 * int("goods_code" in indexes) + 50 * int("style_code" in indexes) + sum(field in indexes for field in MANUAL_FIELDS)
        if best is None or score > best[2]:
            best = (row_number, indexes, score)
    return None if best is None else (best[0], best[1])


def _xlsx_sheet_names(archive: ZipFile) -> list[str]:
    import xml.etree.ElementTree as element_tree

    workbook = element_tree.fromstring(archive.read("xl/workbook.xml"))
    return [sheet.attrib["name"] for sheet in workbook.iter(f"{XML_NAMESPACE}sheet") if sheet.attrib.get("name")]


def _workbook_candidates(root: Path) -> Iterable[Path]:
    candidates = [
        path
        for path in root.rglob("*")
        if path.is_file()
        and path.suffix.lower() in {".xlsx", ".xlsm"}
        and not path.name.startswith("~$")
        and any(marker in path.name for marker in WORKBOOK_MARKERS)
    ]
    return sorted(candidates, key=lambda path: path.stat().st_mtime, reverse=True)


def select_source_workbook(root: Path) -> tuple[Path, str, int, dict[str, int]]:
    for path in _workbook_candidates(root):
        choices = _xlsx_source_choices(path)
        if choices:
            _, sheet_name, header_row, indexes = max(choices, key=lambda item: item[0])
            return path, sheet_name, header_row, indexes
    raise FileNotFoundError(f"No product-goods workbook with manual fields found under {root}")


def discover_sources(root: Path, *, limit: int = 12) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    for path in _workbook_candidates(root):
        try:
            choices = _xlsx_source_choices(path)
        except Exception:
            continue
        if not choices:
            continue
        score, sheet_name, header_row, indexes = max(choices, key=lambda item: item[0])
        candidates.append({
            "source": str(path),
            "sheet": sheet_name,
            "header_row": header_row,
            "score": score,
            "columns": [field for field in MANUAL_FIELDS if field in indexes],
        })
    return sorted(candidates, key=lambda item: (-int(item["score"]), str(item["source"])),)[:limit]


def _source_rows(path: Path, sheet_name: str, header_row: int, indexes: dict[str, int]) -> Iterable[dict[str, str | None]]:
    if path.suffix.lower() in {".xlsx", ".xlsm"}:
        yield from _xlsx_source_rows(path, sheet_name, header_row, indexes)
        return
    workbook = load_workbook(path, data_only=True, read_only=True)
    try:
        sheet = workbook[sheet_name]
        for values in sheet.iter_rows(min_row=header_row + 1, values_only=True):
            row = {
                field: _text(values[index]) if index < len(values) else None
                for field, index in indexes.items()
            }
            if row.get("goods_code") or row.get("style_code"):
                yield row
    finally:
        workbook.close()


def _column_index(cell_reference: str) -> int:
    result = 0
    for character in cell_reference:
        if character.isdigit():
            break
        result = result * 26 + ord(character.upper()) - 64
    return result - 1


def _shared_strings(archive: ZipFile) -> list[str]:
    if "xl/sharedStrings.xml" not in archive.namelist():
        return []
    values: list[str] = []
    with archive.open("xl/sharedStrings.xml") as stream:
        for _, element in iterparse(stream, events=("end",)):
            if element.tag == f"{XML_NAMESPACE}si":
                values.append("".join(text.text or "" for text in element.iter(f"{XML_NAMESPACE}t")))
                element.clear()
    return values


def _sheet_xml_path(archive: ZipFile, sheet_name: str) -> str:
    import xml.etree.ElementTree as element_tree

    workbook = element_tree.fromstring(archive.read("xl/workbook.xml"))
    relationship_id = next(
        sheet.attrib.get(f"{REL_NAMESPACE}id")
        for sheet in workbook.iter(f"{XML_NAMESPACE}sheet")
        if sheet.attrib.get("name") == sheet_name
    )
    relationships = element_tree.fromstring(archive.read("xl/_rels/workbook.xml.rels"))
    target = next(
        relationship.attrib["Target"]
        for relationship in relationships.iter(f"{PACKAGE_REL_NAMESPACE}Relationship")
        if relationship.attrib.get("Id") == relationship_id
    )
    return f"xl/{target.lstrip('/')}" if not target.startswith("/") else target.lstrip("/")


def _cell_value(cell, shared_strings: list[str]) -> str | None:
    value = cell.find(f"{XML_NAMESPACE}v")
    inline = cell.find(f"{XML_NAMESPACE}is")
    if inline is not None:
        return "".join(item.text or "" for item in inline.iter(f"{XML_NAMESPACE}t")) or None
    if value is None or value.text is None:
        return None
    if cell.attrib.get("t") == "s":
        index = int(value.text)
        return shared_strings[index] if 0 <= index < len(shared_strings) else None
    return value.text


def _xlsx_source_rows(path: Path, sheet_name: str, header_row: int, indexes: dict[str, int]) -> Iterable[dict[str, str | None]]:
    with ZipFile(path) as archive:
        shared_strings = _shared_strings(archive)
        sheet_path = _sheet_xml_path(archive, sheet_name)
        wanted_indexes = set(indexes.values())
        with archive.open(sheet_path) as stream:
            for _, row in iterparse(stream, events=("end",)):
                if row.tag != f"{XML_NAMESPACE}row":
                    continue
                row_number = int(row.attrib.get("r") or 0)
                if row_number <= header_row:
                    row.clear()
                    continue
                by_column = {
                    _column_index(cell.attrib.get("r", "")): _cell_value(cell, shared_strings)
                    for cell in row.iter(f"{XML_NAMESPACE}c")
                    if _column_index(cell.attrib.get("r", "")) in wanted_indexes
                }
                result = {field: _text(by_column.get(index)) for field, index in indexes.items()}
                row.clear()
                if result.get("goods_code") or result.get("style_code"):
                    yield result


def _xlsx_source_choices(path: Path) -> list[tuple[int, str, int, dict[str, int]]]:
    with ZipFile(path) as archive:
        sheet_names = _xlsx_sheet_names(archive)
    candidates = [PRODUCT_SHEET_NAME] if PRODUCT_SHEET_NAME in sheet_names else sheet_names
    choices: list[tuple[int, str, int, dict[str, int]]] = []
    for sheet_name in candidates:
        with ZipFile(path) as archive:
            shared_strings = _shared_strings(archive)
            sheet_path = _sheet_xml_path(archive, sheet_name)
            with archive.open(sheet_path) as stream:
                for _, row in iterparse(stream, events=("end",)):
                    if row.tag != f"{XML_NAMESPACE}row":
                        continue
                    row_number = int(row.attrib.get("r") or 0)
                    if row_number > 12:
                        row.clear()
                        break
                    values_by_column = {
                        _column_index(cell.attrib.get("r", "")): _cell_value(cell, shared_strings)
                        for cell in row.iter(f"{XML_NAMESPACE}c")
                    }
                    max_column = max(values_by_column, default=-1)
                    values = tuple(values_by_column.get(index) for index in range(max_column + 1))
                    indexes = _header_indexes(values)
                    if "goods_code" in indexes or "style_code" in indexes:
                        score = 100 * int("goods_code" in indexes) + 50 * int("style_code" in indexes) + sum(field in indexes for field in MANUAL_FIELDS)
                        choices.append((score, sheet_name, row_number, indexes))
                    row.clear()
    return choices


def inspect_source(path: Path) -> dict[str, Any]:
    choices = _xlsx_source_choices(path)
    if not choices:
        raise ValueError(f"No product-goods headers found in {path}")
    _, sheet_name, header_row, indexes = max(choices, key=lambda item: item[0])
    rows = 0
    values = defaultdict(int)
    for row in _source_rows(path, sheet_name, header_row, indexes):
        rows += 1
        for field in MANUAL_FIELDS:
            if row.get(field) is not None:
                values[field] += 1
    return {
        "source": f"{path.name} / {sheet_name}",
        "rows": rows,
        "columns": [field for field in MANUAL_FIELDS if field in indexes],
        "field_values": dict(values),
    }


def _product_maps(connection, brand: str) -> tuple[dict[str, int], dict[str, int]]:
    product_table = PRODUCT_TABLES[brand]
    by_sku: dict[str, int] = {}
    styles: dict[str, list[int]] = defaultdict(list)
    for row in connection.execute(select(product_table.c.id, product_table.c.sku, product_table.c.original_sku)).mappings():
        product_id = int(row["id"])
        sku = _text(row["sku"])
        style_code = _text(row["original_sku"])
        if sku:
            by_sku[sku] = product_id
        if style_code:
            styles[style_code].append(product_id)
    by_unique_style = {style_code: ids[0] for style_code, ids in styles.items() if len(ids) == 1}
    return by_sku, by_unique_style


def import_brand(brand: str, *, root: Path, dry_run: bool, source_path: Path | None = None) -> dict[str, Any]:
    if source_path is None:
        source_path, sheet_name, header_row, indexes = select_source_workbook(root)
    else:
        choices = _xlsx_source_choices(source_path)
        if not choices:
            raise ValueError(f"No product-goods headers found in {source_path}")
        _, sheet_name, header_row, indexes = max(choices, key=lambda item: item[0])
    settings = load_settings(require_database=True)
    assert settings.database_url is not None
    engine = create_engine(settings.database_url, future=True)
    with engine.connect() as connection:
        by_sku, by_unique_style = _product_maps(connection, brand)
        existing = {
            int(row["product_id"]): {field: row.get(field) for field in MANUAL_FIELDS}
            for row in connection.execute(
                select(PRODUCT_GOODS_OVERRIDES_TABLE).where(PRODUCT_GOODS_OVERRIDES_TABLE.c.brand == brand)
            ).mappings()
        }

    source_rows = 0
    matched_rows = 0
    matched_by_sku = 0
    matched_by_style = 0
    conflicts = 0
    updates: dict[int, dict[str, str]] = {}
    field_counts: dict[str, int] = defaultdict(int)
    for row in _source_rows(source_path, sheet_name, header_row, indexes):
        source_rows += 1
        goods_code = row.get("goods_code")
        style_code = row.get("style_code")
        product_id = by_sku.get(goods_code or "")
        if product_id is not None:
            matched_by_sku += 1
        else:
            product_id = by_unique_style.get(style_code or "")
            if product_id is not None:
                matched_by_style += 1
        if product_id is None:
            continue
        matched_rows += 1
        target = updates.setdefault(product_id, {})
        for field in MANUAL_FIELDS:
            source_value = row.get(field)
            if source_value is None:
                continue
            previous = target.get(field)
            if previous is not None and previous != source_value:
                conflicts += 1
                continue
            if previous is None:
                target[field] = source_value
                field_counts[field] += 1

    records = []
    for product_id, source_values in updates.items():
        values = {field: existing.get(product_id, {}).get(field) for field in MANUAL_FIELDS}
        values.update(source_values)
        records.append({"brand": brand, "product_id": product_id, **values})

    if records and not dry_run:
        PRODUCT_GOODS_OVERRIDES_TABLE.create(engine, checkfirst=True)
        with engine.begin() as connection:
            for start in range(0, len(records), WRITE_BATCH_SIZE):
                statement = pg_insert(PRODUCT_GOODS_OVERRIDES_TABLE).values(records[start:start + WRITE_BATCH_SIZE])
                connection.execute(
                    statement.on_conflict_do_update(
                        index_elements=["brand", "product_id"],
                        set_={field: getattr(statement.excluded, field) for field in MANUAL_FIELDS},
                    )
                )
        clear_product_goods_cache()

    return {
        "brand": brand,
        "source": f"{source_path.name} / {sheet_name}",
        "columns": [field for field in MANUAL_FIELDS if field in indexes],
        "source_rows": source_rows,
        "matched_rows": matched_rows,
        "matched_by_sku": matched_by_sku,
        "matched_by_style": matched_by_style,
        "products_updated": len(records),
        "field_values": dict(field_counts),
        "conflicts_skipped": conflicts,
        "dry_run": dry_run,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Fill product-goods manual fields from shared workbooks")
    parser.add_argument("--brand", choices=sorted(BRAND_FOLDERS), action="append")
    parser.add_argument("--source", type=Path, help="Explicit source workbook; requires exactly one --brand")
    parser.add_argument("--discover", action="store_true", help="List the best source files without importing")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    brands = args.brand or list(BRAND_FOLDERS)
    if args.source is not None and len(brands) != 1:
        parser.error("--source requires exactly one --brand")
    for brand in brands:
        if args.discover:
            print({"brand": brand, "sources": discover_sources(SHARED_ROOT / BRAND_FOLDERS[brand])})
            continue
        result = import_brand(brand, root=SHARED_ROOT / BRAND_FOLDERS[brand], dry_run=args.dry_run, source_path=args.source)
        print(result)


if __name__ == "__main__":
    main()
