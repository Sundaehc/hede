"""Backfill JST daily sales from one or more historical analysis workbooks."""

from __future__ import annotations

import argparse
from datetime import date
from pathlib import Path

from config import load_settings
from storage.daily_sales_repository import DailySalesRepository
from storage.factory_channel_sales_summary_repository import FactoryChannelSalesSummaryRepository


def main() -> int:
    parser = argparse.ArgumentParser(description="Backfill a JST daily-sales date range")
    parser.add_argument("files", type=Path, nargs="+")
    parser.add_argument("--date-start", type=date.fromisoformat, required=True)
    parser.add_argument("--date-end", type=date.fromisoformat, required=True)
    args = parser.parse_args()

    settings = load_settings(require_database=True)
    assert settings.database_url is not None
    repository = DailySalesRepository(settings.database_url)

    failed = False
    for source_file in args.files:
        try:
            result = repository.import_jst_daily_sales_range(
                source_file,
                date_start=args.date_start,
                date_end=args.date_end,
            )
            print(f"[OK] {source_file.name}: {result}")
        except Exception as error:
            failed = True
            print(f"[FAILED] {source_file}: {type(error).__name__}: {error}")
    if not failed:
        result = FactoryChannelSalesSummaryRepository(settings.database_url).refresh(
            sales_year=args.date_start.year,
            date_start=args.date_start,
            date_end=args.date_end,
        )
        print(f"[OK] refreshed factory-channel summary: {result}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
