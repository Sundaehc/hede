"""Refresh product image paths from configured image roots.

Run:
  python -m scripts.refresh_product_images
  python -m scripts.refresh_product_images --brand cbanner_mens
  python -m scripts.refresh_product_images --overwrite
"""
from __future__ import annotations

import argparse

from config import load_settings
from domain.sources import TABLE_NAMES
from storage.product_image_refresh import run_product_image_refresh
from storage.product_repository import ProductRepository


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--brand", choices=sorted(TABLE_NAMES), default=None)
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args()

    settings = load_settings()
    assert settings.database_url is not None
    repository = ProductRepository(settings.database_url)
    result = run_product_image_refresh(
        settings=settings,
        repository=repository,
        brand=args.brand,
        overwrite=args.overwrite,
    )
    if not result.get("accepted", True):
        print(result["message"])
        return

    for brand, brand_result in result.get("results", {}).items():
        print(
            f"[{brand}] scanned={brand_result['scanned']} "
            f"matched={brand_result['matched']} updated={brand_result['updated']} missing={brand_result['missing']}"
        )

    print(result.get("message", "Done."))


if __name__ == "__main__":
    main()
