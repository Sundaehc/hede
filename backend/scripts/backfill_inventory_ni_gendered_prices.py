"""Correct existing NI inventory detail prices from stored gendered size quantities."""
from __future__ import annotations

import argparse
from decimal import Decimal
from pathlib import Path

from sqlalchemy import func, insert, select, update

from config import load_settings
from domain.inventory_schema import INVENTORY_DETAIL_TABLE, INVENTORY_TABLE
from domain.ni_gendered_costs import price_for_sizes, split_sizes_by_gender
from scripts.import_ni_product_archive_from_desktop import DEFAULT_PRICE_FILE, read_gendered_costs
from storage.db import Database


def _decimal(value: object) -> Decimal:
    if value in (None, ""):
        return Decimal("0")
    return Decimal(str(value))


def backfill_inventory_ni_gendered_prices(*, price_file: Path, apply: bool) -> dict[str, int | bool]:
    gendered_costs = read_gendered_costs(price_file)
    if not gendered_costs:
        return {"scanned": 0, "updated": 0, "split_details": 0, "documents": 0, "applied": apply}

    settings = load_settings(require_database=True)
    assert settings.database_url is not None
    database = Database(settings.database_url)
    detail = INVENTORY_DETAIL_TABLE
    record = INVENTORY_TABLE
    updated = 0
    split_details = 0
    changed_document_ids: set[int] = set()
    with database._require_engine().begin() as connection:
        rows = connection.execute(
            select(detail).where(detail.c.product_code.in_(gendered_costs))
        ).mappings()
        scanned_rows = list(rows)
        for row in scanned_rows:
            product_costs = gendered_costs.get(str(row.get("product_code") or ""))
            size_groups = split_sizes_by_gender(row.get("size_quantities") or {})
            quantity = _decimal(row.get("quantity"))
            recognized_quantity = sum(
                (sum(sizes.values(), Decimal("0")) for sizes in size_groups.values()),
                Decimal("0"),
            )
            if product_costs and len(size_groups) > 1 and recognized_quantity == quantity:
                first_gender, first_sizes = next(iter(size_groups.items()))
                first_price = price_for_sizes(product_costs, first_sizes)
                if first_price is None:
                    continue
                updated += 1
                split_details += len(size_groups) - 1
                changed_document_ids.add(int(row["document_id"]))
                if apply:
                    connection.execute(
                        update(detail)
                        .where(detail.c.id == row["id"])
                        .values(
                            size_quantities={size: str(value) for size, value in first_sizes.items()},
                            quantity=sum(first_sizes.values(), Decimal("0")),
                            unit_price=first_price,
                            amount=sum(first_sizes.values(), Decimal("0")) * first_price,
                        )
                    )
                    for gender, sizes in list(size_groups.items())[1:]:
                        price = price_for_sizes(product_costs, sizes)
                        if price is None:
                            continue
                        values = {
                            column.name: row[column.name]
                            for column in detail.columns
                            if column.name not in {"id", "created_at", "updated_at"}
                        }
                        values.update({
                            "size_quantities": {size: str(value) for size, value in sizes.items()},
                            "quantity": sum(sizes.values(), Decimal("0")),
                            "unit_price": price,
                            "amount": sum(sizes.values(), Decimal("0")) * price,
                        })
                        connection.execute(insert(detail).values(**values))
                continue

            new_price = price_for_sizes(product_costs, row.get("size_quantities"))
            if new_price is None or new_price == _decimal(row.get("unit_price")):
                continue
            updated += 1
            changed_document_ids.add(int(row["document_id"]))
            if apply:
                quantity = _decimal(row.get("quantity"))
                connection.execute(
                    update(detail)
                    .where(detail.c.id == row["id"])
                    .values(unit_price=new_price, amount=quantity * new_price)
                )

        if apply and changed_document_ids:
            totals = connection.execute(
                select(
                    detail.c.document_id,
                    func.coalesce(func.sum(detail.c.amount), Decimal("0")).label("amount"),
                )
                .where(detail.c.document_id.in_(changed_document_ids))
                .group_by(detail.c.document_id)
            ).mappings()
            for total in totals:
                connection.execute(
                    update(record)
                    .where(record.c.id == total["document_id"])
                    .values(amount=total["amount"])
                )

    return {
        "scanned": len(scanned_rows),
        "updated": updated,
        "split_details": split_details,
        "documents": len(changed_document_ids),
        "applied": apply,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="按 NI 男女尺码回填库存明细单价")
    parser.add_argument("--price-file", type=Path, default=DEFAULT_PRICE_FILE)
    parser.add_argument("--apply", action="store_true", help="写入数据库；未提供时仅预览")
    args = parser.parse_args()
    summary = backfill_inventory_ni_gendered_prices(price_file=args.price_file, apply=args.apply)
    print(
        f"模式：{'正式回填' if summary['applied'] else '预览（未写入）'}；"
        f"扫描 {summary['scanned']} 条，更新 {summary['updated']} 条明细，新增拆分 {summary['split_details']} 条，"
        f"影响 {summary['documents']} 张单据"
    )


if __name__ == "__main__":
    main()
