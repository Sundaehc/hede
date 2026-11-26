"""Refresh product size and optional women's style fields from shared archives.

Only non-empty values for the selected fields are written to existing products.
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass, field

from sqlalchemy import func, select, update
from sqlalchemy.engine import Connection

from config import Settings, load_settings
from domain.schema import PRODUCT_TABLES
from domain.sources import TABLE_NAMES, WORKBOOK_SPECS
from fileio.excel_reader import read_workbook_rows
from transform.rows import CBANNER_WOMENS_STYLE_FIELD_LABELS, build_canonical_row


FIELD_LABELS = {
    "heel_height": "跟高",
    "rear_heel_height": "后跟高",
    "shoe_width": "鞋宽",
    "shoe_length": "鞋长",
    "shaft_circumference": "筒围",
    "shaft_height": "筒高",
    "internal_height_increase": "内增高",
    "internal_height_note": "内增高备注",
    "upper_height": "鞋帮",
}


def _refresh_fields(brand: str, include_womens_style: bool) -> dict[str, str]:
    if brand == "cbanner_womens" and include_womens_style:
        return FIELD_LABELS | {field: labels[0] for field, labels in CBANNER_WOMENS_STYLE_FIELD_LABELS.items()}
    return FIELD_LABELS


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


def _non_empty_fields(row: dict[str, object], fields: dict[str, str]) -> dict[str, str]:
    values: dict[str, str] = {}
    for field_name in fields:
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
    settings: Settings | None = None,
    include_womens_style: bool = False,
) -> tuple[dict[str, dict[str, SourceSizeRecord]], dict[str, SourceStats]]:
    settings = settings or load_settings(require_database=True)
    sources_by_brand: dict[str, dict[str, SourceSizeRecord]] = {
        brand: {} for brand in TABLE_NAMES
    }
    original_skus_by_brand: dict[str, dict[str, set[str]]] = {brand: {} for brand in TABLE_NAMES}
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
        original_skus = original_skus_by_brand[spec.brand_group]
        brand_stats = stats_by_brand[spec.brand_group]
        refresh_fields = _refresh_fields(spec.brand_group, include_womens_style)

        for sheet_name, rows in sheet_rows_map.items():
            for row_number, raw_row in enumerate(rows, start=2):
                brand_stats.scanned_rows += 1
                canonical = build_canonical_row(
                    raw_row,
                    workbook_key=workbook_name,
                    sheet_name=sheet_name,
                    row_number=row_number,
                    image_path=None,
                    brand_group=spec.brand_group,
                )
                if canonical is None:
                    continue
                sku, original_sku = (_clean_text(canonical[field]) for field in ("sku", "original_sku"))
                if original_sku:
                    original_skus.setdefault(original_sku, set()).add(sku)

                fields = _non_empty_fields(canonical, refresh_fields)
                if not fields:
                    continue

                brand_stats.usable_rows += 1
                source = f"{workbook_name}/{sheet_name}/{row_number}"
                current = brand_sources.setdefault(sku, SourceSizeRecord())
                current.fields.update(fields)
                current.source = source

    for brand, source_map in sources_by_brand.items():
        exact_sources = dict(source_map)
        for original_sku, skus in original_skus_by_brand[brand].items():
            if len(skus) == 1:
                source = exact_sources.get(next(iter(skus)))
                if source is not None:
                    source_map.setdefault(original_sku, source)
        stats_by_brand[brand].usable_codes = len(source_map)

    return sources_by_brand, stats_by_brand


def refresh_product_size_fields(
    *,
    dry_run: bool,
    brand_filter: str | None = None,
    settings: Settings | None = None,
    include_womens_style: bool = False,
) -> tuple[dict[str, SourceStats], dict[str, UpdateStats]]:
    settings = settings or load_settings(require_database=True)
    assert settings.database_url is not None

    sources_by_brand, source_stats = load_source_size_records(
        brand_filter=brand_filter, settings=settings, include_womens_style=include_womens_style,
    )
    from storage.db import Database

    database = Database(settings.database_url)
    engine = database._require_engine()
    brands = [brand_filter] if brand_filter else list(TABLE_NAMES)
    try:
        with engine.begin() as connection:
            update_stats = _update_archive_fields(connection, brands, sources_by_brand, dry_run, include_womens_style)
    finally:
        engine.dispose()
    return source_stats, update_stats


def _update_archive_fields(
    connection: Connection,
    brands: list[str],
    sources_by_brand: dict[str, dict[str, SourceSizeRecord]],
    dry_run: bool,
    include_womens_style: bool,
) -> dict[str, UpdateStats]:
    update_stats: dict[str, UpdateStats] = {}
    for brand in brands:
        table = PRODUCT_TABLES[brand]
        refresh_fields = _refresh_fields(brand, include_womens_style)
        sources_by_code = sources_by_brand.get(brand, {})
        stats = UpdateStats()
        update_stats[brand] = stats

        columns = [
            table.c.id,
            table.c.sku,
            table.c.original_sku,
            *(table.c[field_name] for field_name in refresh_fields),
        ]
        rows = connection.execute(select(*columns).where(table.c.deleted_at.is_(None)).order_by(table.c.id)).mappings()
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

            if not dry_run:
                result = connection.execute(
                    update(table)
                    .where(table.c.id == row_dict["id"], table.c.deleted_at.is_(None))
                    .values(**payload, updated_at=func.date_trunc("minute", func.now()))
                )
                if not result.rowcount:
                    continue
            stats.updated_rows += 1
            stats.changed_fields += len(payload)
            if len(stats.samples) < 5:
                labels = "，".join(
                    f"{refresh_fields[field_name]}={value}"
                    for field_name, value in payload.items()
                )
                stats.samples.append(
                    f"id={row_dict['id']} 货号={_clean_text(row_dict.get('sku'))} "
                    f"原始货号={_clean_text(row_dict.get('original_sku'))}: {labels}"
                )

    return update_stats


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description="从商品资料档案数据源刷新商品档案尺寸信息")
    parser.add_argument("--dry-run", action="store_true", help="只预览，不写入数据库")
    parser.add_argument("--brand", choices=sorted(TABLE_NAMES), default=None)
    parser.add_argument("--include-womens-style", action="store_true", help="同时同步千百度女鞋专用款式字段")
    args = parser.parse_args()

    source_stats, update_stats = refresh_product_size_fields(
        dry_run=args.dry_run,
        brand_filter=args.brand,
        include_womens_style=args.include_womens_style,
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
