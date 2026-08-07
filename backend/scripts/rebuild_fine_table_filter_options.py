"""Rebuild cached fine-table filter options from each brand's latest snapshot.

Run:
    python -m scripts.rebuild_fine_table_filter_options
    python -m scripts.rebuild_fine_table_filter_options --brand cbanner_mens
"""

from __future__ import annotations

import argparse

from sqlalchemy import desc, select

from api.routes.fine_table import (
    _ensure_snapshot_tables,
    _refresh_fine_table_filter_option_cache,
)
from config import load_settings
from domain.fine_table_snapshot_schema import (
    FINE_TABLE_SNAPSHOT_BATCH_TABLE,
    fine_table_snapshot_row_table_for_date,
)
from domain.sources import TABLE_NAMES
from storage.fine_table_snapshot_dedup import (
    load_all_optimized_snapshot_rows,
    optimized_snapshot_available,
)
from storage.product_repository import ProductRepository


def main() -> None:
    parser = argparse.ArgumentParser(description="Rebuild latest fine-table filter option caches")
    parser.add_argument("--brand", choices=sorted(TABLE_NAMES), default=None)
    args = parser.parse_args()

    settings = load_settings(require_database=True)
    assert settings.database_url is not None
    repository = ProductRepository(settings.database_url)
    _ensure_snapshot_tables(repository.engine)

    brands = [args.brand] if args.brand else sorted(TABLE_NAMES)
    for brand in brands:
        with repository.engine.connect() as connection:
            batch = connection.execute(
                select(FINE_TABLE_SNAPSHOT_BATCH_TABLE)
                .where(FINE_TABLE_SNAPSHOT_BATCH_TABLE.c.brand == brand)
                .order_by(
                    desc(FINE_TABLE_SNAPSHOT_BATCH_TABLE.c.snapshot_date),
                    desc(FINE_TABLE_SNAPSHOT_BATCH_TABLE.c.id),
                )
                .limit(1)
            ).mappings().first()
        if batch is None:
            print(f"[{brand}] skipped: no snapshot")
            continue

        snapshot_date = batch["snapshot_date"]
        batch_id = int(batch["id"])
        if optimized_snapshot_available(repository.engine, snapshot_date, batch_id):
            rows = load_all_optimized_snapshot_rows(repository.engine, snapshot_date, batch_id)
        else:
            snapshot_table = fine_table_snapshot_row_table_for_date(snapshot_date)
            with repository.engine.connect() as connection:
                rows = [
                    dict(row["payload"] or {})
                    for row in connection.execute(
                        select(snapshot_table.c.payload)
                        .where(snapshot_table.c.batch_id == batch_id)
                        .order_by(snapshot_table.c.row_index)
                    ).mappings()
                ]

        with repository.engine.begin() as connection:
            fields = _refresh_fine_table_filter_option_cache(
                connection,
                brand=brand,
                snapshot_date=snapshot_date,
                rows=rows,
            )
        print(f"[{brand}] date={snapshot_date} rows={len(rows)} fields={fields}")


if __name__ == "__main__":
    main()
