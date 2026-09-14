"""Refresh selected C.banner women's archive fields from its source workbook."""

from __future__ import annotations

import argparse
from collections import Counter
from dataclasses import dataclass

from sqlalchemy import func, select, update

from config import load_settings
from domain.schema import PRODUCT_ARCHIVE_TABLES
from domain.sources import WORKBOOK_SPECS
from fileio.excel_reader import read_workbook_rows
from storage.db import Database
from transform.rows import (
    CBANNER_WOMENS_STYLE_FIELD_LABELS,
    extract_cbanner_womens_style_fields,
    normalize_cell,
)


BRAND = "cbanner_womens"
SOURCE_LABELS = CBANNER_WOMENS_STYLE_FIELD_LABELS


@dataclass(frozen=True)
class SourceValue:
    value: str
    source: str


def _source_fields(raw_row: dict[str, object]) -> dict[str, str]:
    return extract_cbanner_womens_style_fields(raw_row)


def load_source_fields() -> tuple[dict[str, dict[str, SourceValue]], int, str]:
    settings = load_settings(require_database=True)
    spec = next(spec for spec in WORKBOOK_SPECS if spec.brand_group == BRAND)
    source_path = spec.resolve_path(settings.excel_root)
    by_code: dict[str, dict[str, SourceValue]] = {}
    scanned = 0
    for sheet, rows in read_workbook_rows(spec, settings.excel_root).items():
        for row_number, raw_row in enumerate(rows, start=2):
            scanned += 1
            fields = _source_fields(raw_row)
            if not fields:
                continue
            codes = {
                str(normalize_cell(raw_row.get(label)) or "").strip()
                for label in ("货号", "原始货号")
            } - {""}
            for code in codes:
                target = by_code.setdefault(code, {})
                for field, value in fields.items():
                    target[field] = SourceValue(value, f"{source_path.name}/{sheet}/{row_number}")
    return by_code, scanned, str(source_path)


def refresh(*, dry_run: bool) -> dict[str, object]:
    by_code, scanned, source_path = load_source_fields()
    database = Database(load_settings(require_database=True).database_url)
    database.create_tables()
    table = PRODUCT_ARCHIVE_TABLES[BRAND]
    changes: Counter[str] = Counter()
    matched = changed = 0
    samples: list[dict[str, object]] = []

    with database._require_engine().begin() as connection:
        rows = connection.execute(
            select(table.c.id, table.c.sku, table.c.original_sku,
                   *(table.c[field] for field in SOURCE_LABELS))
            .where(table.c.deleted_at.is_(None))
            .order_by(table.c.id)
        ).mappings()
        for row in rows:
            source = next(
                (by_code[code] for code in (row["sku"], row["original_sku"])
                 if code and code in by_code),
                None,
            )
            if source is None:
                continue
            matched += 1
            payload = {
                field: source_value.value
                for field, source_value in source.items()
                if str(row[field] or "").strip() != source_value.value
            }
            if not payload:
                continue
            changed += 1
            changes.update(payload.keys())
            if len(samples) < 8:
                samples.append({
                    "sku": row["sku"],
                    "source": next(iter(source.values())).source,
                    "changes": {field: [row[field], value] for field, value in payload.items()},
                })
            if not dry_run:
                connection.execute(
                    update(table).where(table.c.id == row["id"]).values(
                        **payload,
                        updated_at=func.date_trunc("minute", func.now()),
                    )
                )

    return {
        "source": source_path,
        "scanned": scanned,
        "source_codes": len(by_code),
        "matched_products": matched,
        "changed_products": changed,
        "field_changes": dict(changes),
        "samples": samples,
        "dry_run": dry_run,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="同步千百度女鞋10项款式字段")
    parser.add_argument("--dry-run", action="store_true", help="仅预览变更")
    args = parser.parse_args()
    result = refresh(dry_run=args.dry_run)
    for key, value in result.items():
        print(f"{key}={value}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
