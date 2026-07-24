"""Persist the calculated current product-goods view as daily snapshots.

Run:
    python -m scripts.snapshot_product_goods
    python -m scripts.snapshot_product_goods --brand cbanner_womens
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any

from api.routes.product_goods import create_product_goods_calculated_snapshot
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
    parser = argparse.ArgumentParser(description="Create calculated daily product-goods snapshots")
    parser.add_argument("--brand", choices=sorted(TABLE_NAMES), default=None)
    date_group = parser.add_mutually_exclusive_group()
    date_group.add_argument("--snapshot-date", type=date.fromisoformat, default=None)
    date_group.add_argument("--previous-day", action="store_true")
    args = parser.parse_args()

    settings = load_settings(require_database=True)
    assert settings.database_url is not None
    request = _Request(
        app=_App(
            state=_AppState(
                settings=settings,
                repository=ProductRepository(settings.database_url),
            )
        )
    )
    brands = [args.brand] if args.brand else sorted(TABLE_NAMES)
    snapshot_date = args.snapshot_date or (date.today() - timedelta(days=1) if args.previous_day else None)
    failed = False
    for brand in brands:
        try:
            result = create_product_goods_calculated_snapshot(
                request,  # type: ignore[arg-type]
                brand=brand,
                snapshot_date=snapshot_date,
            )
            print(f"[OK] {result}")
        except Exception as exc:  # pragma: no cover - task logging is exercised in production
            failed = True
            print(f"[FAILED] {brand}: {type(exc).__name__}: {exc}")
    if failed:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
