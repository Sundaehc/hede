"""Backfill the fixed barcode construction rules in product archives."""
from __future__ import annotations

from sqlalchemy import or_, select, update

from config import load_settings
from domain.product_defaults import fixed_barcode_build_rule
from domain.schema import PRODUCT_ARCHIVE_TABLES
from storage.product_repository import ProductRepository


def main() -> None:
    repository = ProductRepository(load_settings().database_url)
    total = 0
    by_brand: dict[str, int] = {}
    with repository.engine.begin() as connection:
        for brand, table in PRODUCT_ARCHIVE_TABLES.items():
            updated = 0
            rows = connection.execute(
                select(table.c.id, table.c.sku, table.c.original_sku)
            ).mappings()
            for row in rows:
                rule = fixed_barcode_build_rule(brand, row.get("sku"), row.get("original_sku"))
                if not rule:
                    continue
                result = connection.execute(
                    update(table)
                    .where(table.c.id == row["id"])
                    .where(or_(
                        table.c.barcode_build_rule.is_(None),
                        table.c.barcode_build_rule != rule,
                    ))
                    .values(barcode_build_rule=rule)
                )
                updated += result.rowcount or 0
            by_brand[brand] = updated
            total += updated
    print("；".join(f"{brand}: {count}" for brand, count in by_brand.items()))
    print(f"total updated: {total}")


if __name__ == "__main__":
    main()
