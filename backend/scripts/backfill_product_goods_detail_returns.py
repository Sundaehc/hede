"""Backfill product-goods return quantities from imported 商品明细表 sources."""
from __future__ import annotations

import argparse
from collections import Counter
from pathlib import Path

from sqlalchemy import create_engine, select, text

from api.product_goods_cache import clear_product_goods_cache
from config import load_settings
from domain.product_goods_detail_snapshot_schema import (
    PRODUCT_GOODS_DETAIL_SNAPSHOT_BATCHES_TABLE,
    product_goods_detail_snapshots_table_for_year,
)
from scripts.import_product_goods_detail_snapshots import (
    METRIC_FIELDS,
    _first_indexes,
    _first_value,
    _header_row,
    _iter_detail_rows,
    _number,
)


UPDATE_RETURN_SQL = """
update {table_name}
set data = jsonb_set(
    data::jsonb,
    '{{metrics,return_qty}}',
    to_jsonb(cast(:return_quantity as numeric)),
    true
)::json
where brand = :brand
  and snapshot_date = :snapshot_date
  and source_row_number = :source_row_number
"""


def backfill_returns(
    *,
    years: set[int],
    brands: set[str] | None = None,
    latest_only: bool = False,
) -> dict[str, object]:
    settings = load_settings(require_database=True)
    assert settings.database_url is not None
    engine = create_engine(settings.database_url, future=True)
    conditions = [
        PRODUCT_GOODS_DETAIL_SNAPSHOT_BATCHES_TABLE.c.status == "success",
        PRODUCT_GOODS_DETAIL_SNAPSHOT_BATCHES_TABLE.c.snapshot_date.is_not(None),
    ]
    if brands:
        conditions.append(PRODUCT_GOODS_DETAIL_SNAPSHOT_BATCHES_TABLE.c.brand.in_(sorted(brands)))

    with engine.connect() as connection:
        batches = [
            dict(row)
            for row in connection.execute(
                select(
                    PRODUCT_GOODS_DETAIL_SNAPSHOT_BATCHES_TABLE.c.brand,
                    PRODUCT_GOODS_DETAIL_SNAPSHOT_BATCHES_TABLE.c.snapshot_date,
                    PRODUCT_GOODS_DETAIL_SNAPSHOT_BATCHES_TABLE.c.source_path,
                )
                .where(*conditions)
                .order_by(
                    PRODUCT_GOODS_DETAIL_SNAPSHOT_BATCHES_TABLE.c.snapshot_date,
                    PRODUCT_GOODS_DETAIL_SNAPSHOT_BATCHES_TABLE.c.brand,
                )
            ).mappings()
            if row["snapshot_date"].year in years
        ]
    if latest_only:
        latest_batches = {}
        for batch in batches:
            key = (str(batch["brand"]), batch["snapshot_date"].year)
            latest_batches[key] = batch
        batches = sorted(
            latest_batches.values(),
            key=lambda item: (item["snapshot_date"], str(item["brand"])),
        )

    counts: Counter[str] = Counter()
    for index, batch in enumerate(batches, start=1):
        brand = str(batch["brand"])
        snapshot_date = batch["snapshot_date"]
        path = Path(str(batch["source_path"]))
        if not path.is_file():
            counts["missing_files"] += 1
            continue
        try:
            _, headers, header_row, _ = _header_row(path)
            return_indexes = _first_indexes(headers, METRIC_FIELDS["return_qty"])
            if not return_indexes:
                counts["missing_columns"] += 1
                continue
            updates = []
            for source_row_number, values in _iter_detail_rows(
                path,
                header_row=header_row,
                wanted_indexes=set(return_indexes),
            ):
                return_quantity = _number(_first_value(values, return_indexes))
                if return_quantity is None:
                    continue
                updates.append(
                    {
                        "brand": brand,
                        "snapshot_date": snapshot_date,
                        "source_row_number": source_row_number,
                        "return_quantity": return_quantity,
                    }
                )
        except Exception as exc:
            counts["failed_files"] += 1
            print(f"[FAILED] {brand} {snapshot_date} {path.name}: {type(exc).__name__}: {exc}", flush=True)
            continue

        table = product_goods_detail_snapshots_table_for_year(snapshot_date.year)
        with engine.begin() as connection:
            for start in range(0, len(updates), 1_000):
                result = connection.execute(
                    text(UPDATE_RETURN_SQL.format(table_name=table.name)),
                    updates[start:start + 1_000],
                )
                counts["updated_rows"] += max(int(result.rowcount or 0), 0)
        counts["processed_files"] += 1
        if index % 25 == 0 or index == len(batches):
            print(
                f"processed={index}/{len(batches)} files updated_rows={counts['updated_rows']}",
                flush=True,
            )

    if counts["updated_rows"]:
        clear_product_goods_cache()
    return {
        "years": sorted(years),
        "brands": sorted(brands or []),
        "latest_only": latest_only,
        "batches": len(batches),
        **counts,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="回填历史商品明细快照中的退货量")
    parser.add_argument("--year", type=int, action="append", choices=range(2000, 2101))
    parser.add_argument("--brand", action="append")
    parser.add_argument("--latest-only", action="store_true", help="每个品牌和年份只处理最后一个快照")
    args = parser.parse_args()
    print(
        backfill_returns(
            years=set(args.year or (2024, 2025)),
            brands=set(args.brand) if args.brand else None,
            latest_only=args.latest_only,
        )
    )


if __name__ == "__main__":
    main()
