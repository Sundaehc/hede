"""Synchronize product images referenced by the archive to UCloud US3."""
from __future__ import annotations

import argparse
import json

from config import load_settings
from storage.product_image_sync import run_product_image_us3_sync
from storage.product_repository import ProductRepository


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--brand", action="append", default=None)
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--limit", type=int, default=None)
    args = parser.parse_args()

    settings = load_settings()
    if not settings.ucloud_us3_configured:
        raise SystemExit("UCloud US3 image storage is not fully configured in backend/.env")
    assert settings.database_url is not None
    repository = ProductRepository(settings.database_url)
    result = run_product_image_us3_sync(
        settings=settings,
        repository=repository,
        brands=args.brand,
        force=args.force,
        dry_run=args.dry_run,
        max_uploads=args.limit,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if result["failed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
