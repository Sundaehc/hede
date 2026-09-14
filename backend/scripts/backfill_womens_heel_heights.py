"""Refresh separate CBANNER women's heel-height fields from the archive workbook."""

from __future__ import annotations

import argparse

from sqlalchemy import func, select, update

from config import load_settings
from domain.schema import PRODUCT_ARCHIVE_TABLES
from scripts.refresh_product_size_fields import load_source_size_records
from storage.db import Database


HEEL_FIELDS = ("heel_height", "rear_heel_height")


def refresh_womens_heel_heights(*, dry_run: bool) -> dict[str, int]:
    settings = load_settings(require_database=True)
    source_by_brand, _ = load_source_size_records(brand_filter="cbanner_womens")
    source_map = source_by_brand["cbanner_womens"]
    table = PRODUCT_ARCHIVE_TABLES["cbanner_womens"]
    database = Database(settings.database_url)
    database.create_tables()

    matched = 0
    updated = 0
    changed_fields = 0
    with database._require_engine().begin() as connection:
        rows = connection.execute(
            select(
                table.c.id,
                table.c.sku,
                table.c.original_sku,
                table.c.heel_height,
                table.c.rear_heel_height,
            )
            .where(table.c.deleted_at.is_(None))
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
            payload: dict[str, str | None] = {
                field_name: source.fields[field_name]
                for field_name in HEEL_FIELDS
                if source.fields.get(field_name)
                and str(row.get(field_name) or "").strip() != source.fields[field_name]
            }
            source_heel_height = source.fields.get("heel_height")
            source_rear_heel_height = source.fields.get("rear_heel_height")
            existing_heel_height = str(row.get("heel_height") or "").strip()
            if (
                not source_heel_height
                and source_rear_heel_height
                and existing_heel_height == source_rear_heel_height
            ):
                payload["heel_height"] = None
            if not payload:
                continue
            matched += 1
            changed_fields += len(payload)
            if not dry_run:
                result = connection.execute(
                    update(table)
                    .where(table.c.id == row["id"])
                    .values(
                        **payload,
                        updated_at=func.date_trunc("minute", func.now()),
                    )
                )
                updated += result.rowcount or 0

    return {
        "matched": matched,
        "updated": updated,
        "changed_fields": changed_fields,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="分别刷新千百度女鞋的跟高和后跟高")
    parser.add_argument("--dry-run", action="store_true", help="只预览，不写入数据库")
    args = parser.parse_args()
    result = refresh_womens_heel_heights(dry_run=args.dry_run)

    print(
        f"matched_products={result['matched']} "
        f"updated_products={result['updated']} "
        f"changed_fields={result['changed_fields']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
