"""Migrate rolling order history tables to PostgreSQL annual partitions."""

from __future__ import annotations

import json

from sqlalchemy import create_engine, text

from config import load_settings
from domain.history_partitioning import migrate_order_history_tables


def main() -> int:
    settings = load_settings(require_database=True)
    assert settings.database_url is not None
    engine = create_engine(settings.database_url, future=True)

    with engine.begin() as connection:
        connection.execute(text("SET LOCAL statement_timeout = 0"))
        connection.execute(text("SET LOCAL lock_timeout = '30s'"))
        results = migrate_order_history_tables(connection)

    with engine.begin() as connection:
        for table_name in (
            "jst_monthly_orders",
            "jst_aftersale_returns",
            "dewu_orders",
        ):
            connection.execute(text(f"ANALYZE public.{table_name}"))

    print(json.dumps(results, ensure_ascii=False, default=str, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
