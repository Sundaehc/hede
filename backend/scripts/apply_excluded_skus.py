"""Remove permanently excluded SKUs from product and fine-table data."""

from __future__ import annotations

from sqlalchemy import delete, func, or_, select, update

from config import load_settings
from domain.excluded_skus import EXCLUDED_SKUS
from domain.fine_table_snapshot_schema import FINE_TABLE_SNAPSHOT_BATCH_TABLE, FINE_TABLE_SNAPSHOT_ROW_TABLE
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
        "fine_table_snapshot_rows": 0,
    }
    result.update({table_name: 0 for table_name in PRODUCT_TABLES})

    with engine.begin() as connection:
        for chunk in _chunks(excluded, CHUNK_SIZE):
            gj_delete = delete(GJ_MERGED_PRODUCT_INFO_TABLE).where(
                or_(
                    GJ_MERGED_PRODUCT_INFO_TABLE.c.goods_code.in_(chunk),
                    GJ_MERGED_PRODUCT_INFO_TABLE.c.original_goods_code.in_(chunk),
                )
            )
            result["gj_merged_product_info"] += connection.execute(gj_delete).rowcount or 0

            snapshot_delete = delete(FINE_TABLE_SNAPSHOT_ROW_TABLE).where(
                or_(
                    FINE_TABLE_SNAPSHOT_ROW_TABLE.c.sku.in_(chunk),
                    FINE_TABLE_SNAPSHOT_ROW_TABLE.c.original_sku.in_(chunk),
                )
            )
            result["fine_table_snapshot_rows"] += connection.execute(snapshot_delete).rowcount or 0

            for brand, table in PRODUCT_TABLES.items():
                product_delete = delete(table).where(
                    or_(
                        table.c.sku.in_(chunk),
                        table.c.original_sku.in_(chunk),
                    )
                )
                result[brand] += connection.execute(product_delete).rowcount or 0

        row_count = (
            select(func.count())
            .select_from(FINE_TABLE_SNAPSHOT_ROW_TABLE)
            .where(FINE_TABLE_SNAPSHOT_ROW_TABLE.c.batch_id == FINE_TABLE_SNAPSHOT_BATCH_TABLE.c.id)
            .scalar_subquery()
        )
        connection.execute(update(FINE_TABLE_SNAPSHOT_BATCH_TABLE).values(total_rows=row_count))

    return result


def main() -> None:
    print(apply_excluded_skus())


if __name__ == "__main__":
    main()
