"""Sync today's JST daily stock from Excel to database.

Run: python -m scripts.sync_jst_stock
Schedule: daily (e.g. via Windows Task Scheduler or cron)
"""
from __future__ import annotations

from datetime import datetime

from config import load_settings
from storage.inventory_repository import InventoryRepository


def main() -> None:
    settings = load_settings(require_database=True)
    repo = InventoryRepository(settings.database_url)

    today = datetime.now()
    stock_date = f"{today.month:02d}.{today.day:02d}"

    result = repo.import_jst_stock(
        jst_stock_root=settings.jst_stock_root,
        stock_date=stock_date,
    )
    print(result["message"])


if __name__ == "__main__":
    main()
