"""Backfill VIP daily sales from historical analysis workbooks in a folder."""

from __future__ import annotations

import argparse
from datetime import date
from pathlib import Path

from config import load_settings
from storage.daily_sales_repository import DailySalesRepository
from storage.factory_channel_sales_summary_repository import FactoryChannelSalesSummaryRepository


def main() -> int:
    parser = argparse.ArgumentParser(description="Backfill a VIP daily-sales date range")
    parser.add_argument("--source-dir", type=Path, required=True)
    parser.add_argument("--date-start", type=date.fromisoformat, required=True)
    parser.add_argument("--date-end", type=date.fromisoformat, required=True)
    args = parser.parse_args()

    files = sorted(
        path
        for path in args.source_dir.glob("*.xlsx")
        if not path.name.startswith("~$")
    )
    if not files:
        raise FileNotFoundError(f"未找到唯品Excel: {args.source_dir}")

    settings = load_settings(require_database=True)
    assert settings.database_url is not None
    repository = DailySalesRepository(settings.database_url)

    failed = False
    total_upserted = 0
    for index, source_file in enumerate(files, start=1):
        try:
            result = repository.import_vip_daily_sales_range(
                source_file,
                date_start=args.date_start,
                date_end=args.date_end,
                batch_size=10_000,
            )
            total_upserted += int(result.get("upserted") or 0)
            print(
                f"[OK {index}/{len(files)}] {source_file.name}: "
                f"matched={result.get('matched', 0)} "
                f"upserted={result.get('upserted', 0)} "
                f"skipped={result.get('skipped', 0)}"
            )
        except Exception as error:
            failed = True
            print(f"[FAILED {index}/{len(files)}] {source_file}: {type(error).__name__}: {error}")
    print(f"total_upserted={total_upserted}")
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
