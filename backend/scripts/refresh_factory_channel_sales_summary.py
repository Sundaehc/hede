"""Refresh the optimized daily sales layer used by the factory-channel dashboard."""

from __future__ import annotations

import argparse
from datetime import date

from config import load_settings
from storage.factory_channel_sales_summary_repository import FactoryChannelSalesSummaryRepository


def main() -> int:
    parser = argparse.ArgumentParser(description="刷新工厂渠道看板销量汇总")
    parser.add_argument("--year", type=int, default=date.today().year)
    parser.add_argument("--date-start", type=date.fromisoformat, default=None)
    parser.add_argument("--date-end", type=date.fromisoformat, default=None)
    parser.add_argument("--brand", action="append", dest="brands", help="仅补算指定档案品牌，可重复指定")
    parser.add_argument("--dry-run", action="store_true", help="只读试算，不修改汇总数据")
    args = parser.parse_args()

    settings = load_settings(require_database=True)
    assert settings.database_url is not None
    result = FactoryChannelSalesSummaryRepository(settings.database_url).refresh(
        sales_year=args.year,
        date_start=args.date_start,
        date_end=args.date_end,
        brands=args.brands,
        dry_run=args.dry_run,
    )
    print(result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

