"""Create fine-table snapshots.

Run:
    python -m scripts.snapshot_fine_table
    python -m scripts.snapshot_fine_table --brand cbanner_mens
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import date
from typing import Any

from api.routes.fine_table import create_fine_table_snapshot
from config import load_settings
from domain.sources import TABLE_NAMES
from storage.product_repository import ProductRepository


@dataclass
class _AppState:
    settings: Any
    repository: ProductRepository


@dataclass
class _App:
    state: _AppState


@dataclass
class _Request:
    app: _App


def main() -> None:
    parser = argparse.ArgumentParser(description="Create daily fine-table snapshots")
    parser.add_argument("--brand", choices=sorted(TABLE_NAMES), default=None)
    parser.add_argument("--snapshot-date", type=date.fromisoformat, default=None)
    args = parser.parse_args()

    settings = load_settings(require_database=True)
    assert settings.database_url is not None
    request = _Request(app=_App(state=_AppState(settings=settings, repository=ProductRepository(settings.database_url))))
    brands = [args.brand] if args.brand else sorted(TABLE_NAMES)

    for brand in brands:
        result = create_fine_table_snapshot(
            request,  # type: ignore[arg-type]
            brand=brand,
            snapshot_date=args.snapshot_date,
        )
        print(
            f"[{brand}] date={result['item']['snapshot_date']} "
            f"rows={result['rows']} replaced={result['replaced']} message={result['message']}"
        )


if __name__ == "__main__":
    main()
