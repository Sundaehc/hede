"""Refresh supplier ratings using the current scoring rules."""
from __future__ import annotations

import argparse

from config import load_settings
from domain.gj_brand import SUPPLIER_BRANDS
from storage.inventory_repository import InventoryRepository


def main() -> int:
    parser = argparse.ArgumentParser(description="刷新供应商等级")
    parser.add_argument("--brand", choices=sorted(SUPPLIER_BRANDS), default=None, help="只刷新指定品牌")
    args = parser.parse_args()

    settings = load_settings(require_database=True)
    repository = InventoryRepository(settings.database_url)
    result = repository.refresh_supplier_ratings(brand=args.brand)
    updated = int(result.get("updated") or 0)
    brand_label = result.get("brand") or "all"
    print(f"[SUPPLIER_RATING] refreshed {updated} suppliers, brand={brand_label}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
