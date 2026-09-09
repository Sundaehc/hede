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
from storage.product_image_sync import run_product_image_us3_sync
from storage.product_repository import ProductRepository


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--brand", choices=sorted(TABLE_NAMES), default=None)
    parser.add_argument("--overwrite", action="store_true")
    parser.add_argument("--skip-us3", action="store_true")
    parser.add_argument("--force-us3", action="store_true")
    parser.add_argument("--dry-run-us3", action="store_true")
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

    if not settings.ucloud_us3_configured or args.skip_us3:
        print("US3 image sync skipped: storage is not configured or --skip-us3 was specified.")
        return

    sync_result = run_product_image_us3_sync(
        settings=settings,
        repository=repository,
        brands=[args.brand] if args.brand else None,
        force=args.force_us3,
        dry_run=args.dry_run_us3,
    )
    print(
        "US3 image sync: "
        f"scanned={sync_result['scanned']} candidates={sync_result['candidates']} "
        f"uploaded={sync_result['uploaded']} unchanged={sync_result['skipped_unchanged']} "
        f"missing={sync_result['missing']} invalid={sync_result['invalid']} "
        f"failed={sync_result['failed']}"
    )
    for error in sync_result.get("errors", []):
        print(f"[US3 ERROR] {error['object_key']}: {error['error']}")
    if sync_result["failed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
