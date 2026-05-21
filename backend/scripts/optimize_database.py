"""Apply idempotent database optimizations.

Run: python -m scripts.optimize_database
"""
from __future__ import annotations

import orjson
from sqlalchemy import create_engine

from config import load_settings
from domain.schema import METADATA
from domain import vip_schema  # noqa: F401 - register VIP/JST analytics tables
from domain import inventory_schema  # noqa: F401 - register inventory tables
from storage.migrations import apply_core_database_optimizations


def main() -> None:
    settings = load_settings()
    assert settings.database_url is not None
    engine = create_engine(
        settings.database_url,
        future=True,
        json_serializer=lambda value: orjson.dumps(value).decode("utf-8"),
    )

    METADATA.create_all(engine, checkfirst=True)
    apply_core_database_optimizations(engine)
    engine.dispose()
    print("Database optimizations applied.")


if __name__ == "__main__":
    main()
