"""Backfill NI product costs from the one-off Desktop price workbook.

Only ``ni_products.cost`` is changed.  This script is intentionally manual-only
and is not registered as a scheduled task.
"""
from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy import select, update

from config import load_settings
from domain.schema import PRODUCT_ARCHIVE_TABLES
from scripts.import_ni_product_archive_from_desktop import (
    DEFAULT_PRICE_FILE,
    read_costs,
)
from storage.db import Database


@dataclass(frozen=True)
class BackfillSummary:
    source_rows: int
    source_rows_skipped: int
    source_conflicts: int
    matched_products: int
    updated_products: int
    unmatched_codes: int
    applied: bool


def backfill_ni_preset_prices(*, price_file: Path, apply: bool) -> BackfillSummary:
    prices, source_rows, source_rows_skipped, source_conflicts = read_costs(price_file)
    if not prices:
        return BackfillSummary(
            source_rows=source_rows,
            source_rows_skipped=source_rows_skipped,
            source_conflicts=source_conflicts,
            matched_products=0,
            updated_products=0,
            unmatched_codes=0,
            applied=apply,
        )

    settings = load_settings(require_database=True)
    assert settings.database_url is not None
    database = Database(settings.database_url)
    database.create_tables()
    table = PRODUCT_ARCHIVE_TABLES["ni"]

    matched_products = 0
    updated_products = 0
    matched_codes: set[str] = set()
    with database._require_engine().begin() as connection:
        existing_rows = connection.execute(
            select(table.c.id, table.c.sku, table.c.original_sku, table.c.cost)
        ).mappings()
        for row in existing_rows:
            sku = str(row["sku"] or "").strip()
            original_sku = str(row["original_sku"] or "").strip()
            code = sku if sku in prices else original_sku if original_sku in prices else ""
            if not code:
                continue
            matched_products += 1
            matched_codes.add(code)
            new_cost = prices[code]
            if row["cost"] == new_cost:
                continue
            if apply:
                connection.execute(
                    update(table)
                    .where(table.c.id == row["id"])
                    .values(cost=new_cost)
                )
            updated_products += 1

    return BackfillSummary(
        source_rows=source_rows,
        source_rows_skipped=source_rows_skipped,
        source_conflicts=source_conflicts,
        matched_products=matched_products,
        updated_products=updated_products,
        unmatched_codes=len(set(prices) - matched_codes),
        applied=apply,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="将 NI 物价表的预设售价回填为 NI 商品成本")
    parser.add_argument("--price-file", type=Path, default=DEFAULT_PRICE_FILE)
    parser.add_argument("--apply", action="store_true", help="写入数据库；未提供时仅预览")
    args = parser.parse_args()
    summary = backfill_ni_preset_prices(price_file=args.price_file, apply=args.apply)
    print(
        f"模式：{'正式回填' if summary.applied else '预览（未写入数据库）'}；"
        f"来源有效 {summary.source_rows} 条，跳过 {summary.source_rows_skipped} 条，"
        f"冲突 {summary.source_conflicts} 条；匹配商品 {summary.matched_products} 条，"
        f"需更新 {summary.updated_products} 条，未匹配货号 {summary.unmatched_codes} 条"
    )


if __name__ == "__main__":
    main()
