"""Fill blank CBANNER women's heel heights from the current archive workbook."""

from __future__ import annotations

from sqlalchemy import func, select, update

from config import load_settings
from domain.schema import PRODUCT_ARCHIVE_TABLES
from scripts.refresh_product_size_fields import load_source_size_records
from storage.db import Database


def main() -> int:
    settings = load_settings(require_database=True)
    source_by_brand, _ = load_source_size_records(brand_filter="cbanner_womens")
    source_map = source_by_brand["cbanner_womens"]
    table = PRODUCT_ARCHIVE_TABLES["cbanner_womens"]
    database = Database(settings.database_url)
    database.create_tables()

    matched = 0
    updated = 0
    with database._require_engine().begin() as connection:
        rows = connection.execute(
            select(table.c.id, table.c.sku, table.c.original_sku, table.c.heel_height)
            .where(table.c.deleted_at.is_(None))
            .where(table.c.heel_height.is_(None) | (table.c.heel_height == ""))
        ).mappings()
        for row in rows:
            source = next(
                (
                    source_map.get(code)
                    for code in (row["sku"], row["original_sku"])
                    if code and source_map.get(code) is not None
                ),
                None,
            )
            if source is None:
                continue
            heel_height = source.fields.get("heel_height")
            if not heel_height:
                continue
            matched += 1
            result = connection.execute(
                update(table)
                .where(table.c.id == row["id"])
                .where(table.c.heel_height.is_(None) | (table.c.heel_height == ""))
                .values(
                    heel_height=heel_height,
                    updated_at=func.date_trunc("minute", func.now()),
                )
            )
            updated += result.rowcount or 0

    print(f"matched_blank_products={matched} updated_products={updated}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
