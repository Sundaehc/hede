"""Refresh product season_category from source product archive workbooks.

Only the explicit "季节分类" column is used. Sheet-derived fallback seasons are
kept as Chinese labels such as "春季" and "秋季".
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass

from sqlalchemy import create_engine, select, update

from config import load_settings
from domain.schema import PRODUCT_TABLES
from domain.sources import TABLE_NAMES, WORKBOOK_SPECS
from fileio.excel_reader import read_workbook_rows
from transform.rows import normalize_cell


sys.stdout.reconfigure(encoding="utf-8")

VALID_SEASON_VALUES = {
    "春季",
    "春夏",
    "春秋",
    "春秋季",
    "夏季",
    "秋季",
    "秋冬",
    "冬季",
}


@dataclass
class SeasonSource:
    season_category: str
    source: str


@dataclass
class BrandStats:
    scanned_rows: int = 0
    source_rows: int = 0
    source_codes: int = 0
    total_rows: int = 0
    matched_rows: int = 0
    updated_rows: int = 0


def _clean_text(value: object) -> str:
    normalized = normalize_cell(value)
    return "" if normalized is None else str(normalized).strip()


def _valid_season(value: object) -> str:
    text = _clean_text(value)
    return text if text in VALID_SEASON_VALUES else ""


def _row_codes(row: dict[str, object]) -> list[str]:
    codes: list[str] = []
    for key in ("货号", "原始货号"):
        code = _clean_text(row.get(key))
        if code and code not in codes:
            codes.append(code)
    return codes


def load_source_seasons(*, brand_filter: str | None = None) -> tuple[dict[str, dict[str, SeasonSource]], dict[str, BrandStats]]:
    settings = load_settings(require_database=True)
    sources_by_brand: dict[str, dict[str, SeasonSource]] = {brand: {} for brand in TABLE_NAMES}
    stats_by_brand: dict[str, BrandStats] = {brand: BrandStats() for brand in TABLE_NAMES}

    for spec in WORKBOOK_SPECS:
        if brand_filter is not None and spec.brand_group != brand_filter:
            continue

        workbook_path = spec.resolve_path(settings.excel_root)
        workbook_name = workbook_path.stem
        sheet_rows_map = read_workbook_rows(spec, settings.excel_root)
        source_map = sources_by_brand[spec.brand_group]
        stats = stats_by_brand[spec.brand_group]

        for sheet_name, rows in sheet_rows_map.items():
            for row_number, row in enumerate(rows, start=2):
                stats.scanned_rows += 1
                season = _valid_season(row.get("季节分类"))
                if not season:
                    continue
                codes = _row_codes(row)
                if not codes:
                    continue

                stats.source_rows += 1
                source = f"{workbook_name}/{sheet_name}/{row_number}"
                for code in codes:
                    source_map[code] = SeasonSource(season_category=season, source=source)

    for brand, source_map in sources_by_brand.items():
        stats_by_brand[brand].source_codes = len(source_map)
    return sources_by_brand, stats_by_brand


def refresh_product_seasons(*, dry_run: bool, brand_filter: str | None = None) -> dict[str, BrandStats]:
    settings = load_settings(require_database=True)
    sources_by_brand, stats_by_brand = load_source_seasons(brand_filter=brand_filter)

    brands = [brand_filter] if brand_filter else list(TABLE_NAMES)
    engine = create_engine(settings.database_url, future=True)
    with engine.begin() as connection:
        for brand in brands:
            if brand is None:
                continue
            table = PRODUCT_TABLES[brand]
            source_map = sources_by_brand.get(brand, {})
            stats = stats_by_brand[brand]
            rows = connection.execute(
                select(table.c.id, table.c.sku, table.c.original_sku, table.c.season_category)
                .order_by(table.c.id)
            ).mappings()

            for row in rows:
                stats.total_rows += 1
                source = None
                for code in (_clean_text(row.get("sku")), _clean_text(row.get("original_sku"))):
                    if code and code in source_map:
                        source = source_map[code]
                        break
                if source is None:
                    continue

                stats.matched_rows += 1
                current = _clean_text(row.get("season_category"))
                if current == source.season_category:
                    continue

                stats.updated_rows += 1
                if not dry_run:
                    connection.execute(
                        update(table)
                        .where(table.c.id == row["id"])
                        .values(season_category=source.season_category)
                    )

    return stats_by_brand


def main() -> int:
    parser = argparse.ArgumentParser(description="按商品资料档案中的季节分类矫正商品档案季节")
    parser.add_argument("--dry-run", action="store_true", help="只统计，不写入数据库")
    parser.add_argument("--brand", choices=tuple(TABLE_NAMES), help="只处理指定品牌")
    args = parser.parse_args()

    stats_by_brand = refresh_product_seasons(dry_run=args.dry_run, brand_filter=args.brand)
    mode = "dry-run" if args.dry_run else "update"
    print(f"[PRODUCT_SEASON] mode={mode}")
    for brand, stats in stats_by_brand.items():
        if args.brand and brand != args.brand:
            continue
        print(
            f"[PRODUCT_SEASON] {brand}: scanned_source_rows={stats.scanned_rows}, "
            f"source_rows={stats.source_rows}, source_codes={stats.source_codes}, "
            f"total_rows={stats.total_rows}, matched_rows={stats.matched_rows}, "
            f"updated_rows={stats.updated_rows}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
