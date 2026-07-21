"""Refresh 伊伴鞋盒类型和卖点 from the product archive workbook."""

from __future__ import annotations

import argparse
from dataclasses import dataclass, field

from sqlalchemy import func, select, update

from config import load_settings
from domain.schema import PRODUCT_TABLES
from domain.sources import WORKBOOK_SPECS
from fileio.excel_reader import read_workbook_rows
from storage.db import Database
from transform.rows import build_canonical_row, normalize_cell


BRAND = "eblan"
DETAIL_FIELDS = ("shoe_box_type", "selling_points")
FIELD_LABELS = {
    "shoe_box_type": "鞋盒类型",
    "selling_points": "卖点",
}
INVALID_DETAIL_VALUES = {"0", "0.0"}


@dataclass
class SourceRecord:
    fields: dict[str, str] = field(default_factory=dict)


@dataclass
class RefreshStats:
    scanned_source_rows: int = 0
    usable_source_rows: int = 0
    source_codes: int = 0
    total_products: int = 0
    matched_products: int = 0
    updated_products: int = 0
    changed_fields: int = 0
    samples: list[str] = field(default_factory=list)


def _clean_text(value: object) -> str:
    normalized = normalize_cell(value)
    return "" if normalized is None else str(normalized).strip()


def _detail_text(value: object) -> str:
    text = _clean_text(value)
    return "" if text in INVALID_DETAIL_VALUES else text


def _codes(row: dict[str, object]) -> list[str]:
    return list(dict.fromkeys(
        code
        for field_name in ("sku", "original_sku")
        if (code := _clean_text(row.get(field_name)))
    ))


def load_source_records() -> tuple[dict[str, SourceRecord], RefreshStats]:
    settings = load_settings(require_database=True)
    spec = next(item for item in WORKBOOK_SPECS if item.brand_group == BRAND)
    workbook_path = spec.resolve_path(settings.excel_root)
    rows_by_sheet = read_workbook_rows(spec, settings.excel_root)
    records: dict[str, SourceRecord] = {}
    stats = RefreshStats()

    for sheet_name, rows in rows_by_sheet.items():
        for row_number, raw_row in enumerate(rows, start=2):
            stats.scanned_source_rows += 1
            canonical = build_canonical_row(
                raw_row,
                workbook_key=workbook_path.stem,
                sheet_name=sheet_name,
                row_number=row_number,
                image_path=None,
            )
            if canonical is None:
                continue
            fields = {}
            for field_name in DETAIL_FIELDS:
                value = _detail_text(canonical.get(field_name))
                if not value and field_name == "shoe_box_type":
                    value = _detail_text(canonical.get("shoe_box_spec"))
                if value:
                    fields[field_name] = value
            if not fields:
                continue
            codes = _codes(canonical)
            if not codes:
                continue
            stats.usable_source_rows += 1
            for code in codes:
                records.setdefault(code, SourceRecord()).fields.update(fields)

    stats.source_codes = len(records)
    return records, stats


def refresh(*, dry_run: bool) -> RefreshStats:
    settings = load_settings(require_database=True)
    assert settings.database_url is not None
    source_by_code, stats = load_source_records()
    database = Database(settings.database_url)
    database.create_tables()
    table = PRODUCT_TABLES[BRAND]

    with database._require_engine().begin() as connection:
        rows = connection.execute(
            select(
                table.c.id,
                table.c.sku,
                table.c.original_sku,
                *(table.c[field_name] for field_name in DETAIL_FIELDS),
            ).order_by(table.c.id)
        ).mappings()
        for row in rows:
            stats.total_products += 1
            source = next((source_by_code[code] for code in _codes(dict(row)) if code in source_by_code), None)
            if source is None:
                continue
            stats.matched_products += 1
            payload = {
                field_name: value
                for field_name, value in source.fields.items()
                if _clean_text(row[field_name]) != value
            }
            if not payload:
                continue
            stats.updated_products += 1
            stats.changed_fields += len(payload)
            if len(stats.samples) < 5:
                labels = "，".join(f"{FIELD_LABELS[name]}={value}" for name, value in payload.items())
                stats.samples.append(f"货号={_clean_text(row['sku'])}: {labels}")
            if not dry_run:
                connection.execute(
                    update(table)
                    .where(table.c.id == row["id"])
                    .values(**payload, updated_at=func.date_trunc("minute", func.now()))
                )
    return stats


def main() -> int:
    parser = argparse.ArgumentParser(description="从伊伴商品资料档案回填鞋盒类型和卖点")
    parser.add_argument("--dry-run", action="store_true", help="只统计，不写入数据库")
    args = parser.parse_args()
    stats = refresh(dry_run=args.dry_run)
    action = "待更新" if args.dry_run else "已更新"
    print(
        f"伊伴来源扫描 {stats.scanned_source_rows} 行，可用 {stats.usable_source_rows} 行，"
        f"可匹配货号 {stats.source_codes} 个；商品档案 {stats.total_products} 条，"
        f"匹配 {stats.matched_products} 条，{action} {stats.updated_products} 条，"
        f"字段变化 {stats.changed_fields} 个"
    )
    for sample in stats.samples:
        print(f"示例: {sample}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
