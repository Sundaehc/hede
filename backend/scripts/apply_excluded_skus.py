"""Remove permanently excluded SKUs from product and fine-table data."""

from __future__ import annotations

from datetime import date

from sqlalchemy import delete, func, or_, select, update

from config import load_settings
from domain.excluded_skus import EXCLUDED_SKUS
from domain.fine_table_snapshot_schema import (
    FINE_TABLE_SNAPSHOT_BATCH_TABLE,
    fine_table_snapshot_row_table_for_date,
    fine_table_snapshot_ref_table_for_date,
    fine_table_snapshot_ref_table_exists,
    fine_table_snapshot_year_table_exists,
)
from domain.gj_schema import GJ_MERGED_PRODUCT_INFO_TABLE
from domain.schema import PRODUCT_TABLES
from storage.db import Database


CHUNK_SIZE = 1000


def _chunks(values: list[str], size: int):
    for start in range(0, len(values), size):
        yield values[start:start + size]


def apply_excluded_skus() -> dict[str, int]:
    settings = load_settings(require_database=True)
    assert settings.database_url is not None
    database = Database(settings.database_url)
    database.create_tables()
    engine = database._require_engine()
    excluded = sorted(EXCLUDED_SKUS)
    result: dict[str, int] = {
        "excluded_skus": len(excluded),
        "gj_merged_product_info": 0,
    }
    result.update({table_name: 0 for table_name in PRODUCT_TABLES})
    optimized_snapshot_tables = []

    with engine.begin() as connection:
        snapshot_year_tables = []
        snapshot_dates = connection.execute(
            select(FINE_TABLE_SNAPSHOT_BATCH_TABLE.c.snapshot_date).distinct()
        ).scalars()
        for snapshot_date in sorted({value for value in snapshot_dates if isinstance(value, date)}):
            if fine_table_snapshot_year_table_exists(engine, snapshot_date):
                table = fine_table_snapshot_row_table_for_date(snapshot_date)
                if table.name not in result:
                    result[table.name] = 0
                    snapshot_year_tables.append(table)
            if fine_table_snapshot_ref_table_exists(engine, snapshot_date):
                ref_table = fine_table_snapshot_ref_table_for_date(snapshot_date)
                if ref_table.name not in result:
                    result[ref_table.name] = 0
                    optimized_snapshot_tables.append(ref_table)

        for chunk in _chunks(excluded, CHUNK_SIZE):
            gj_delete = delete(GJ_MERGED_PRODUCT_INFO_TABLE).where(
                or_(
                    GJ_MERGED_PRODUCT_INFO_TABLE.c.goods_code.in_(chunk),
                    GJ_MERGED_PRODUCT_INFO_TABLE.c.original_goods_code.in_(chunk),
                )
            )
            result["gj_merged_product_info"] += connection.execute(gj_delete).rowcount or 0

            for snapshot_table in snapshot_year_tables:
                snapshot_delete = delete(snapshot_table).where(
                    or_(
                        snapshot_table.c.sku.in_(chunk),
                        snapshot_table.c.original_sku.in_(chunk),
                    )
                )
                result[snapshot_table.name] += connection.execute(snapshot_delete).rowcount or 0

            for snapshot_table in optimized_snapshot_tables:
                snapshot_delete = delete(snapshot_table).where(
                    or_(
                        snapshot_table.c.sku.in_(chunk),
                        snapshot_table.c.original_sku.in_(chunk),
                    )
                )
                result[snapshot_table.name] += connection.execute(snapshot_delete).rowcount or 0

            for brand, table in PRODUCT_TABLES.items():
                product_delete = delete(table).where(
                    or_(
                        table.c.sku.in_(chunk),
                        table.c.original_sku.in_(chunk),
                    )
                )
                result[brand] += connection.execute(product_delete).rowcount or 0

        for batch in connection.execute(select(FINE_TABLE_SNAPSHOT_BATCH_TABLE)).mappings():
            snapshot_date = batch["snapshot_date"]
            if not isinstance(snapshot_date, date):
                continue
            ref_count = 0
            if fine_table_snapshot_ref_table_exists(engine, snapshot_date):
                ref_table = fine_table_snapshot_ref_table_for_date(snapshot_date)
                ref_count = int(
                    connection.execute(
                        select(func.count())
                        .select_from(ref_table)
                        .where(ref_table.c.batch_id == batch["id"])
                    ).scalar_one()
                )
            if ref_count:
                total_rows = ref_count
            elif fine_table_snapshot_year_table_exists(engine, snapshot_date):
                legacy_table = fine_table_snapshot_row_table_for_date(snapshot_date)
                total_rows = int(
                    connection.execute(
                        select(func.count())
                        .select_from(legacy_table)
                        .where(legacy_table.c.batch_id == batch["id"])
                    ).scalar_one()
                )
            else:
                total_rows = 0
            connection.execute(
                update(FINE_TABLE_SNAPSHOT_BATCH_TABLE)
                .where(FINE_TABLE_SNAPSHOT_BATCH_TABLE.c.id == batch["id"])
                .values(total_rows=total_rows)
            )

    return result


def main() -> None:
    print(apply_excluded_skus())


if __name__ == "__main__":
    main()
