"""Audit archive cost values that did not reach product tables."""

from __future__ import annotations

import argparse
import json
from collections import defaultdict
from decimal import Decimal
from pathlib import Path
from zipfile import ZipFile
import xml.etree.ElementTree as ET

from sqlalchemy import create_engine, select

from config import load_settings
from domain.schema import PRODUCT_TABLES
from domain.sources import COLUMN_ALIASES, WORKBOOK_SPECS, WorkbookSpec
from fileio.excel_reader import read_workbook_rows
from transform.rows import build_canonical_row, normalize_header


XLSX_NAMESPACE = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
RELATIONSHIP_NAMESPACE = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}"
PACKAGE_RELATIONSHIP_NAMESPACE = "{http://schemas.openxmlformats.org/package/2006/relationships}"
AUDIT_FIELDS = frozenset({"sku", "original_sku", "cost"})


def _codes(row: dict[str, object]) -> set[str]:
    return {
        str(value).strip()
        for value in (row.get("sku"), row.get("original_sku"))
        if str(value or "").strip()
    }


def _column_index(reference: str) -> int:
    index = 0
    for character in reference:
        if not character.isalpha():
            break
        index = index * 26 + ord(character.upper()) - ord("A") + 1
    return index - 1


def _shared_strings(archive: ZipFile) -> list[str]:
    try:
        source = archive.open("xl/sharedStrings.xml")
    except KeyError:
        return []
    with source:
        root = ET.parse(source).getroot()
    return ["".join(item.itertext()) for item in root.findall(f"{XLSX_NAMESPACE}si")]


def _sheet_paths(archive: ZipFile) -> dict[str, str]:
    workbook = ET.fromstring(archive.read("xl/workbook.xml"))
    relationships = ET.fromstring(archive.read("xl/_rels/workbook.xml.rels"))
    targets = {
        item.attrib.get("Id"): item.attrib.get("Target")
        for item in relationships.findall(f"{PACKAGE_RELATIONSHIP_NAMESPACE}Relationship")
    }
    return {
        item.attrib["name"]: f"xl/{targets[item.attrib[f'{RELATIONSHIP_NAMESPACE}id']].lstrip('/')}"
        for item in workbook.findall(f"{XLSX_NAMESPACE}sheets/{XLSX_NAMESPACE}sheet")
        if item.attrib.get(f"{RELATIONSHIP_NAMESPACE}id") in targets
    }


def _cell_value(cell: ET.Element, shared_strings: list[str]) -> str:
    cell_type = cell.attrib.get("t")
    if cell_type == "inlineStr":
        inline = cell.find(f"{XLSX_NAMESPACE}is")
        return "".join(inline.itertext()) if inline is not None else ""
    value = cell.find(f"{XLSX_NAMESPACE}v")
    if value is None or value.text is None:
        return ""
    if cell_type == "s":
        return shared_strings[int(value.text)]
    return value.text


def _iter_xlsx_rows(workbook_path: Path, spec: WorkbookSpec):
    with ZipFile(workbook_path) as archive:
        shared_strings = _shared_strings(archive)
        sheet_paths = _sheet_paths(archive)
        for sheet_spec in spec.sheets:
            sheet_path = sheet_paths.get(sheet_spec.name)
            if sheet_path is None:
                if sheet_spec.optional:
                    continue
                raise ValueError(f"缺少必要 sheet: {sheet_spec.name}")
            with archive.open(sheet_path) as source:
                relevant_columns: dict[int, str] | None = None
                cost_headers: set[str] = set()
                for _, row in ET.iterparse(source, events=("end",)):
                    if row.tag != f"{XLSX_NAMESPACE}row":
                        continue
                    values = {
                        _column_index(cell.attrib.get("r", "")): _cell_value(cell, shared_strings)
                        for cell in row.findall(f"{XLSX_NAMESPACE}c")
                    }
                    row_number = int(row.attrib.get("r", "0") or 0)
                    row.clear()
                    if relevant_columns is None:
                        headers = {index: normalize_header(value) for index, value in values.items()}
                        cost_headers = {header for header in headers.values() if "成本" in header}
                        relevant_columns = {
                            index: header
                            for index, header in headers.items()
                            if COLUMN_ALIASES.get(header) in AUDIT_FIELDS
                        }
                        continue
                    raw_row = {
                        header: values.get(index)
                        for index, header in relevant_columns.items()
                    }
                    if any(value not in (None, "") for value in raw_row.values()):
                        yield sheet_spec.name, row_number, raw_row, cost_headers


def _iter_source_rows(workbook_path: Path, spec: WorkbookSpec):
    if workbook_path.suffix.lower() in {".xlsx", ".xlsm"}:
        yield from _iter_xlsx_rows(workbook_path, spec)
        return
    for sheet_name, rows in read_workbook_rows(spec, workbook_path.parent).items():
        for row_number, raw_row in enumerate(rows, start=2):
            cost_headers = {str(header).strip() for header in raw_row if "成本" in str(header)}
            yield sheet_name, row_number, raw_row, cost_headers


def _source_costs(
    settings,
    *,
    brands: set[str] | None = None,
) -> tuple[dict[str, dict[str, set[Decimal]]], dict[str, dict[str, object]]]:
    costs_by_brand: dict[str, dict[str, set[Decimal]]] = defaultdict(lambda: defaultdict(set))
    source_summary: dict[str, dict[str, object]] = {}
    for spec in WORKBOOK_SPECS:
        if brands is not None and spec.brand_group not in brands:
            continue
        workbook_path = spec.resolve_path(settings.excel_root)
        workbook_summary = source_summary.setdefault(
            spec.brand_group,
            {"workbooks": [], "rows": 0, "cost_rows": 0, "cost_headers": set()},
        )
        workbook_summary["workbooks"].append(workbook_path.name)
        for sheet_name, row_number, raw_row, cost_headers in _iter_source_rows(workbook_path, spec):
            workbook_summary["rows"] += 1
            workbook_summary["cost_headers"].update(cost_headers)
            canonical = build_canonical_row(
                raw_row,
                workbook_key=workbook_path.stem,
                sheet_name=sheet_name,
                row_number=row_number,
                image_path=None,
            )
            if canonical is None or canonical["cost"] is None:
                continue
            workbook_summary["cost_rows"] += 1
            for code in _codes(canonical):
                costs_by_brand[spec.brand_group][code].add(canonical["cost"])
    return costs_by_brand, source_summary


def _missing_costs(connection, source_costs: dict[str, dict[str, set[Decimal]]], *, brands: set[str] | None) -> dict[str, dict[str, object]]:
    result: dict[str, dict[str, object]] = {}
    for brand, table in PRODUCT_TABLES.items():
        if brands is not None and brand not in brands:
            continue
        archive_costs = source_costs.get(brand, {})
        missing: list[dict[str, object]] = []
        populated = 0
        for row in connection.execute(select(table.c.id, table.c.sku, table.c.original_sku, table.c.cost)).mappings():
            source_values: set[Decimal] = set()
            for code in _codes(dict(row)):
                source_values.update(archive_costs.get(code, set()))
            if row["cost"] is not None:
                populated += 1
            elif source_values:
                missing.append(
                    {
                        "id": row["id"],
                        "sku": row["sku"],
                        "original_sku": row["original_sku"],
                        "source_costs": source_values,
                    }
                )
        result[brand] = {"database_cost_rows": populated, "missing": missing}
    return result


def _summary(
    missing_by_brand: dict[str, dict[str, object]],
    source_summary: dict[str, dict[str, object]],
) -> dict[str, object]:
    result: dict[str, object] = {}
    for brand, values in missing_by_brand.items():
        missing = values["missing"]
        assert isinstance(missing, list)
        summary = dict(source_summary.get(brand, {}))
        summary["cost_headers"] = sorted(summary.get("cost_headers", set()))
        result[brand] = {
            "source": summary,
            "database_cost_rows": values["database_cost_rows"],
            "source_cost_but_database_empty": len(missing),
            "safe_to_backfill": sum(len(item["source_costs"]) == 1 for item in missing),
            "ambiguous_source_costs": sum(len(item["source_costs"]) > 1 for item in missing),
            "samples": [
                {
                    "sku": item["sku"],
                    "original_sku": item["original_sku"],
                    "source_costs": sorted(str(value) for value in item["source_costs"]),
                }
                for item in missing[:30]
            ],
        }
    return result


def audit(*, brands: set[str] | None = None) -> dict[str, object]:
    settings = load_settings(require_database=True)
    assert settings.database_url is not None
    source_costs, source_summary = _source_costs(settings, brands=brands)
    engine = create_engine(settings.database_url, future=True)
    with engine.connect() as connection:
        missing_by_brand = _missing_costs(connection, source_costs, brands=brands)
    return _summary(missing_by_brand, source_summary)


def backfill(*, brands: set[str] | None = None) -> dict[str, object]:
    settings = load_settings(require_database=True)
    assert settings.database_url is not None
    source_costs, source_summary = _source_costs(settings, brands=brands)
    engine = create_engine(settings.database_url, future=True)
    with engine.begin() as connection:
        missing_by_brand = _missing_costs(connection, source_costs, brands=brands)
        for brand, values in missing_by_brand.items():
            table = PRODUCT_TABLES[brand]
            updated = 0
            for item in values["missing"]:
                source_values = item["source_costs"]
                if len(source_values) != 1:
                    continue
                updated += connection.execute(
                    table.update()
                    .where(table.c.id == item["id"])
                    .where(table.c.cost.is_(None))
                    .values(cost=next(iter(source_values)))
                ).rowcount
            values["backfilled"] = updated
    result = _summary(missing_by_brand, source_summary)
    for brand, values in result.items():
        values["backfilled"] = missing_by_brand[brand].get("backfilled", 0)
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="核对商品档案成本是否漏入数据库")
    parser.add_argument("--brand", choices=sorted(PRODUCT_TABLES), action="append")
    parser.add_argument("--apply", action="store_true", help="回填源表成本唯一且数据库为空的记录")
    args = parser.parse_args()
    brands = set(args.brand) if args.brand else None
    result = backfill(brands=brands) if args.apply else audit(brands=brands)
    print(json.dumps(result, ensure_ascii=False, default=str))
