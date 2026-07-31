"""Migrate legacy fine-table rows into deduplicated snapshot references.

Default mode only creates the optimized copy. Use --delete-legacy for a
single date after verifying the optimized snapshot through the application.
"""

from __future__ import annotations

import argparse
from datetime import date
import json

from sqlalchemy import delete, select

from config import load_settings
from domain.fine_table_snapshot_schema import (
    FINE_TABLE_SNAPSHOT_BATCH_TABLE,
    ensure_fine_table_snapshot_ref_table,
    fine_table_snapshot_row_table_for_date,
    fine_table_snapshot_year_table_exists,
)
from storage.fine_table_snapshot_dedup import write_optimized_snapshot_rows
from storage.product_repository import ProductRepository


def _dates(repository: ProductRepository, requested: date | None) -> list[date]:
    if requested is not None:
        return [requested]
    with repository.engine.connect() as connection:
        values = connection.execute(
            select(FINE_TABLE_SNAPSHOT_BATCH_TABLE.c.snapshot_date)
            .distinct()
            .order_by(FINE_TABLE_SNAPSHOT_BATCH_TABLE.c.snapshot_date)
        ).scalars()
        return [value for value in values if isinstance(value, date)]


def migrate_date(repository: ProductRepository, snapshot_date: date, delete_legacy: bool) -> dict[str, int | str]:
    if not fine_table_snapshot_year_table_exists(repository.engine, snapshot_date):
        return {"date": snapshot_date.isoformat(), "batches": 0, "rows": 0, "status": "legacy_table_missing"}
    table = fine_table_snapshot_row_table_for_date(snapshot_date)
    migrated_batches = 0
    migrated_rows = 0
    migrated_batch_ids: list[int] = []
    with repository.engine.connect() as connection:
        batches = list(
            connection.execute(
                select(FINE_TABLE_SNAPSHOT_BATCH_TABLE)
                .where(FINE_TABLE_SNAPSHOT_BATCH_TABLE.c.snapshot_date == snapshot_date)
                .order_by(FINE_TABLE_SNAPSHOT_BATCH_TABLE.c.id)
            ).mappings()
        )
        for batch in batches:
            rows = connection.execute(
                select(table.c.payload)
                .where(table.c.batch_id == batch["id"])
                .order_by(table.c.row_index)
            ).mappings()
            payloads = []
            for row in rows:
                payload = row["payload"]
                if isinstance(payload, dict):
                    payloads.append(dict(payload))
                elif isinstance(payload, str):
                    payloads.append(json.loads(payload))
            if not payloads:
                continue
            ensure_fine_table_snapshot_ref_table(repository.engine, snapshot_date)
            write_optimized_snapshot_rows(
                repository.engine,
                brand=str(batch["brand"]),
                snapshot_date=snapshot_date,
                batch_id=int(batch["id"]),
                payloads=payloads,
            )
            migrated_batches += 1
            migrated_rows += len(payloads)
            migrated_batch_ids.append(int(batch["id"]))

    if delete_legacy and migrated_batch_ids:
        with repository.engine.begin() as connection:
            connection.execute(delete(table).where(table.c.batch_id.in_(migrated_batch_ids)))
    return {
        "date": snapshot_date.isoformat(),
        "batches": migrated_batches,
        "rows": migrated_rows,
        "status": "migrated_and_deleted" if delete_legacy else "migrated",
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--snapshot-date", type=date.fromisoformat)
    parser.add_argument("--delete-legacy", action="store_true")
    args = parser.parse_args()

    settings = load_settings(require_database=True)
    repository = ProductRepository(settings.database_url)
    for snapshot_date in _dates(repository, args.snapshot_date):
        print(migrate_date(repository, snapshot_date, args.delete_legacy))


if __name__ == "__main__":
    main()
