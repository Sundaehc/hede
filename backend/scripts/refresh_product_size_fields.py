"""Refresh product size fields from source product archive workbooks.

This is intentionally narrower than the full product import: it only updates
the "尺寸信息" fields and only writes non-empty values from the source.
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass, field

from sqlalchemy import func, select, update

from config import load_settings
from domain.schema import PRODUCT_TABLES
from domain.sources import TABLE_NAMES, WORKBOOK_SPECS
from fileio.excel_reader import read_workbook_rows
from transform.rows import build_canonical_row


sys.stdout.reconfigure(encoding="utf-8")


SIZE_FIELDS = (
    "heel_height",
    "shoe_width",
    "shoe_length",
    "shaft_circumference",
    "shaft_height",
    "internal_height_increase",
    "internal_height_note",
    "upper_height",
)

FIELD_LABELS = {
    "heel_height": "跟高",
    "shoe_width": "鞋宽",
    "shoe_length": "鞋长",
    "shaft_circumference": "筒围",
    "shaft_height": "筒高",
    "internal_height_increase": "内增高",
    "internal_height_note": "内增高备注",
    "upper_height": "鞋帮",
}


@dataclass
class SourceSizeRecord:
    fields: dict[str, str] = field(default_factory=dict)
    source: str = ""


@dataclass
class SourceStats:
    scanned_rows: int = 0
    usable_rows: int = 0
    usable_codes: int = 0


@dataclass
class UpdateStats:
    total_rows: int = 0
    matched_rows: int = 0
    updated_rows: int = 0
    changed_fields: int = 0
    samples: list[str] = field(default_factory=list)


def _clean_text(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value).strip()


def _non_empty_size_fields(row: dict[str, object]) -> dict[str, str]:
    values: dict[str, str] = {}
    for field_name in SIZE_FIELDS:
        text = _clean_text(row.get(field_name))
        if text:
            values[field_name] = text
    return values


def _match_codes(row: dict[str, object]) -> list[str]:
    codes: list[str] = []
    for field_name in ("sku", "original_sku"):
        code = _clean_text(row.get(field_name))
        if code and code not in codes:
            codes.append(code)
    return codes


def _source_record_for_row(
    row: dict[str, object],
    sources_by_code: dict[str, SourceSizeRecord],
) -> SourceSizeRecord | None:
    for code in _match_codes(row):
        source = sources_by_code.get(code)
        if source is not None:
            return source
    return None


def load_source_size_records(
    *,
    brand_filter: str | None = None,
) -> tuple[dict[str, dict[str, SourceSizeRecord]], dict[str, SourceStats]]:
    settings = load_settings(require_database=True)
    sources_by_brand: dict[str, dict[str, SourceSizeRecord]] = {
        brand: {} for brand in TABLE_NAMES
    }
    stats_by_brand: dict[str, SourceStats] = {
        brand: SourceStats() for brand in TABLE_NAMES
    }

    for spec in WORKBOOK_SPECS:
        if brand_filter is not None and spec.brand_group != brand_filter:
            continue

        workbook_path = spec.resolve_path(settings.excel_root)
        workbook_name = workbook_path.stem
        sheet_rows_map = read_workbook_rows(spec, settings.excel_root)
        brand_sources = sources_by_brand[spec.brand_group]
        brand_stats = stats_by_brand[spec.brand_group]

        for sheet_name, rows in sheet_rows_map.items():
            for row_number, raw_row in enumerate(rows, start=2):
                brand_stats.scanned_rows += 1
                canonical = build_canonical_row(
                    raw_row,
                    workbook_key=workbook_name,
                    sheet_name=sheet_name,
                    row_number=row_number,
                    image_path=None,
                )
                if canonical is None:
                    continue

                fields = _non_empty_size_fields(canonical)
                if not fields:
                    continue

                codes = _match_codes(canonical)
                if not codes:
                    continue

                brand_stats.usable_rows += 1
                source = f"{workbook_name}/{sheet_name}/{row_number}"
                for code in codes:
                    current = brand_sources.setdefault(code, SourceSizeRecord())
                    current.fields.update(fields)
                    current.source = source

    for brand, source_map in sources_by_brand.items():
        stats_by_brand[brand].usable_codes = len(source_map)

    return sources_by_brand, stats_by_brand


def refresh_product_size_fields(
    *,
    dry_run: bool,
    brand_filter: str | None = None,
) -> tuple[dict[str, SourceStats], dict[str, UpdateStats]]:
    settings = load_settings(require_database=True)
    assert settings.database_url is not None

    sources_by_brand, source_stats = load_source_size_records(brand_filter=brand_filter)
    from storage.db import Database

    database = Database(settings.database_url)
    database.create_tables()
    engine = database._require_engine()

    update_stats: dict[str, UpdateStats] = {}
    brands = [brand_filter] if brand_filter else list(TABLE_NAMES)

    with engine.begin() as connection:
        for brand in brands:
            table = PRODUCT_TABLES[brand]
            sources_by_code = sources_by_brand.get(brand, {})
            stats = UpdateStats()
            update_stats[brand] = stats

            columns = [
                table.c.id,
                table.c.sku,
                table.c.original_sku,
                *(table.c[field_name] for field_name in SIZE_FIELDS),
            ]
            rows = connection.execute(select(*columns).order_by(table.c.id)).mappings()
            for row in rows:
                row_dict = dict(row)
                stats.total_rows += 1
                source = _source_record_for_row(row_dict, sources_by_code)
                if source is None:
                    continue

                stats.matched_rows += 1
                payload: dict[str, str] = {}
                for field_name, source_value in source.fields.items():
                    if _clean_text(row_dict.get(field_name)) != source_value:
                        payload[field_name] = source_value

                if not payload:
                    continue

                stats.updated_rows += 1
                stats.changed_fields += len(payload)
                if len(stats.samples) < 5:
                    labels = "，".join(
                        f"{FIELD_LABELS[field_name]}={value}"
                        for field_name, value in payload.items()
                    )
                    stats.samples.append(
                        f"id={row_dict['id']} 货号={_clean_text(row_dict.get('sku'))} "
                        f"原始货号={_clean_text(row_dict.get('original_sku'))}: {labels}"
                    )

                if not dry_run:
                    connection.execute(
                        update(table)
                        .where(table.c.id == row_dict["id"])
                        .values(
                            **payload,
                            updated_at=func.date_trunc("minute", func.now()),
                        )
                    )

    return source_stats, update_stats


def main() -> int:
    parser = argparse.ArgumentParser(description="从商品资料档案数据源刷新商品档案尺寸信息")
    parser.add_argument("--dry-run", action="store_true", help="只预览，不写入数据库")
    parser.add_argument("--brand", choices=sorted(TABLE_NAMES), default=None)
    args = parser.parse_args()

    source_stats, update_stats = refresh_product_size_fields(
        dry_run=args.dry_run,
        brand_filter=args.brand,
    )

    print(f"模式: {'预览，不写入数据库' if args.dry_run else '执行更新'}")
    for brand in ([args.brand] if args.brand else list(TABLE_NAMES)):
        source = source_stats.get(brand, SourceStats())
        update_result = update_stats.get(brand, UpdateStats())
        print(
            f"\n{brand}: 数据源扫描 {source.scanned_rows} 行，"
            f"可用尺寸行 {source.usable_rows} 行，可匹配货号 {source.usable_codes} 个"
        )
        print(
            f"  商品档案 {update_result.total_rows} 条，匹配 {update_result.matched_rows} 条，"
            f"{'待更新' if args.dry_run else '已更新'} {update_result.updated_rows} 条，"
            f"字段变化 {update_result.changed_fields} 个"
        )
        for sample in update_result.samples:
            print(f"  示例: {sample}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
