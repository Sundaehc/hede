"""Create or validate the PostgreSQL tablespace used by order-history cold data."""

from __future__ import annotations

import os
from pathlib import Path

from sqlalchemy import create_engine, text

from config import load_settings
from domain.order_history_tiering import checked_identifier


def _sql_string_literal(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def main() -> int:
    settings = load_settings(require_database=True)
    assert settings.database_url is not None

    tablespace_name = checked_identifier(
        os.getenv("ORDER_HISTORY_COLD_TABLESPACE", "").strip()
    )
    location_value = os.getenv("ORDER_HISTORY_COLD_LOCATION", "").strip()
    if not location_value:
        raise ValueError("ORDER_HISTORY_COLD_LOCATION is required")
    location = Path(location_value).resolve()
    if not location.is_dir():
        raise ValueError(f"Cold archive directory does not exist: {location}")

    normalized_location = str(location).replace("\\", "/").rstrip("/")
    engine = create_engine(
        settings.database_url,
        future=True,
        isolation_level="AUTOCOMMIT",
    )
    with engine.connect() as connection:
        existing = connection.execute(
            text(
                "SELECT pg_tablespace_location(oid) "
                "FROM pg_tablespace WHERE spcname = :tablespace_name"
            ),
            {"tablespace_name": tablespace_name},
        ).scalar_one_or_none()
        if existing is not None:
            normalized_existing = str(existing).replace("\\", "/").rstrip("/")
            if normalized_existing.casefold() != normalized_location.casefold():
                raise ValueError(
                    f"Tablespace {tablespace_name} already points to {existing}, "
                    f"not {normalized_location}"
                )
            print(f"[READY] {tablespace_name} -> {existing}")
            return 0

        connection.execute(
            text(
                f"CREATE TABLESPACE {tablespace_name} "
                f"LOCATION {_sql_string_literal(normalized_location)}"
            )
        )
        print(f"[CREATED] {tablespace_name} -> {normalized_location}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
