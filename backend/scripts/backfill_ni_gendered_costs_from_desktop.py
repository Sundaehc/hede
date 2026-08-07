"""Persist NI female/male unit-price pairs without overwriting product master fields."""
from __future__ import annotations

import argparse
from pathlib import Path

from sqlalchemy import select, update

from config import load_settings
from domain.ni_gendered_costs import GENDER_COSTS_FIELD
from domain.schema import PRODUCT_ARCHIVE_TABLES
from scripts.import_ni_product_archive_from_desktop import DEFAULT_PRICE_FILE, read_gendered_costs
from storage.db import Database


def backfill_ni_gendered_costs(*, price_file: Path, apply: bool) -> dict[str, int | bool]:
    gendered_costs = read_gendered_costs(price_file)
    if not gendered_costs:
        return {"source_products": 0, "matched": 0, "updated": 0, "applied": apply}

    settings = load_settings(require_database=True)
    assert settings.database_url is not None
    database = Database(settings.database_url)
    table = PRODUCT_ARCHIVE_TABLES["ni"]
    updated = 0
    matched = 0
    with database._require_engine().begin() as connection:
        rows = connection.execute(
            select(table.c.id, table.c.sku, table.c.original_sku, table.c.extra_fields)
            .where(table.c.sku.in_(gendered_costs) | table.c.original_sku.in_(gendered_costs))
        ).mappings()
        for row in rows:
            costs = gendered_costs.get(str(row.get("sku") or "")) or gendered_costs.get(str(row.get("original_sku") or ""))
            if not costs:
                continue
            matched += 1
            serialized_costs = {gender: str(price) for gender, price in costs.items()}
            extra_fields = dict(row.get("extra_fields") or {})
            if extra_fields.get(GENDER_COSTS_FIELD) == serialized_costs:
                continue
            updated += 1
            if apply:
                extra_fields[GENDER_COSTS_FIELD] = serialized_costs
                connection.execute(
                    update(table)
                    .where(table.c.id == row["id"])
                    .values(extra_fields=extra_fields)
                )
    return {
        "source_products": len(gendered_costs),
        "matched": matched,
        "updated": updated,
        "applied": apply,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="回填 NI 男女码分价，不覆盖商品档案其他字段")
    parser.add_argument("--price-file", type=Path, default=DEFAULT_PRICE_FILE)
    parser.add_argument("--apply", action="store_true", help="写入数据库；未提供时仅预览")
    args = parser.parse_args()
    summary = backfill_ni_gendered_costs(price_file=args.price_file, apply=args.apply)
    print(
        f"模式：{'正式回填' if summary['applied'] else '预览（未写入）'}；"
        f"来源分价 {summary['source_products']} 款，匹配商品 {summary['matched']} 款，"
        f"更新 {summary['updated']} 款"
    )


if __name__ == "__main__":
    main()
