"""Preview or remove unreferenced deduplicated fine-table snapshot content."""

from __future__ import annotations

import argparse
import json

from config import load_settings
from storage.fine_table_snapshot_dedup import cleanup_orphaned_snapshot_content
from storage.product_repository import ProductRepository


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--execute",
        action="store_true",
        help="actually delete content that is not referenced by any optimized snapshot",
    )
    args = parser.parse_args()

    settings = load_settings(require_database=True)
    repository = ProductRepository(settings.database_url)
    result = cleanup_orphaned_snapshot_content(repository.engine, execute=args.execute)
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
