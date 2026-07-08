"""Normalize product season labels from legacy English values to Chinese."""

from __future__ import annotations

import sys

from sqlalchemy import create_engine, text

from config import load_settings
from domain.sources import TABLE_NAMES


sys.stdout.reconfigure(encoding="utf-8")

SEASON_LABEL_MAP = {
    "spring": "春季",
    "summer": "夏季",
    "autumn": "秋季",
    "winter": "冬季",
}


def normalize_product_season_labels() -> dict[str, int]:
    settings = load_settings(require_database=True)
    engine = create_engine(settings.database_url, future=True)
    updated_by_table: dict[str, int] = {}
    with engine.begin() as connection:
        for table_name in TABLE_NAMES.values():
            updated = 0
            for old_value, new_value in SEASON_LABEL_MAP.items():
                result = connection.execute(
                    text(
                        f"update {table_name} "
                        "set season_category = :new_value "
                        "where season_category = :old_value"
                    ),
                    {"old_value": old_value, "new_value": new_value},
                )
                updated += result.rowcount or 0
            updated_by_table[table_name] = updated
    return updated_by_table


def main() -> int:
    result = normalize_product_season_labels()
    for table_name, updated in result.items():
        print(f"{table_name}: updated={updated}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
