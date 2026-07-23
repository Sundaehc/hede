"""Fill missing product-goods operational fields from historical detail sheets.

The newest workbook wins.  Older workbooks can only fill fields that are still
empty in ``product_goods_overrides``, so this backfill never overwrites current
or manually maintained values.
"""

from __future__ import annotations

import argparse
import re
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Iterable

from sqlalchemy import create_engine, select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from api.product_goods_cache import clear_product_goods_cache
from domain.product_goods_schema import PRODUCT_GOODS_OVERRIDES_TABLE
from domain.schema import PRODUCT_TABLES
from scripts.import_product_goods_manual_fields import (
    BRAND_FOLDERS,
    MANUAL_FIELDS,
    SHARED_ROOT,
    _product_maps,
    _source_rows,
    _text,
    _xlsx_source_choices,
)
from config import load_settings


WORKBOOK_SUFFIXES = {".xlsx", ".xlsm"}
DATE_IN_NAME = re.compile(r"(?<!\d)(?P<month>0?[1-9]|1[0-2])[._-](?P<day>0?[1-9]|[12]\d|3[01])(?!\d)")
YEAR_MONTH_IN_DIR = re.compile(r"(?P<year>20\d{2})[.\-/年](?P<month>0?[1-9]|1[0-2])(?:月|月份)?$")
YEAR_IN_DIR = re.compile(r"^(20\d{2})(?:年)?$")


@dataclass(frozen=True)
class HistoricalWorkbook:
    brand: str
    path: Path
    business_date: date


@dataclass
class BackfillSummary:
    brand: str
    scanned_workbooks: int = 0
    processed_workbooks: int = 0
    skipped_workbooks: int = 0
    source_rows: int = 0
    matched_rows: int = 0
    updated_products: int = 0
    updated_fields: dict[str, int] | None = None

    def __post_init__(self) -> None:
        if self.updated_fields is None:
            self.updated_fields = defaultdict(int)


def _is_target_workbook(path: Path, brand: str) -> bool:
    name = path.name
    if path.suffix.lower() not in WORKBOOK_SUFFIXES or name.startswith("~$"):
        return False
    if brand == "cbanner_womens":
        return "赫德货品表" in name and "男鞋" not in name
    if brand == "cbanner_mens":
        return "赫德货品表" in name and "男鞋" in name
    if brand == "eblan":
        return "伊伴货品表" in name
    return False


def _parent_year_month(path: Path) -> tuple[int | None, int | None]:
    for parent in (path.parent, *path.parents):
        name = parent.name.strip()
        year_month = YEAR_MONTH_IN_DIR.match(name)
        if year_month:
            return int(year_month.group("year")), int(year_month.group("month"))
    for parent in (path.parent, *path.parents):
        year_match = YEAR_IN_DIR.match(parent.name.strip())
        if year_match:
            return int(year_match.group(1)), None
    return None, None


def workbook_business_date(path: Path) -> date:
    year, parent_month = _parent_year_month(path)
    matches = list(DATE_IN_NAME.finditer(path.stem))
    if matches:
        match = matches[-1]
        inferred_year = year or datetime.fromtimestamp(path.stat().st_mtime).year
        try:
            return date(inferred_year, int(match.group("month")), int(match.group("day")))
        except ValueError:
            pass
    if year is not None and parent_month is not None:
        return date(year, parent_month, 1)
    timestamp = datetime.fromtimestamp(path.stat().st_mtime)
    return timestamp.date()


def _workbook_priority(path: Path) -> tuple[int, float, str]:
    name = path.name
    penalty = sum(marker in name for marker in ("副本", "快速", "简洁", "预警", "优化"))
    return -penalty, path.stat().st_mtime, name


def historical_workbooks(root: Path, *, brand: str) -> list[HistoricalWorkbook]:
    by_day: dict[date, Path] = {}
    for path in root.rglob("*"):
        if not path.is_file() or not _is_target_workbook(path, brand):
            continue
        business_date = workbook_business_date(path)
        existing = by_day.get(business_date)
        if existing is None or _workbook_priority(path) > _workbook_priority(existing):
            by_day[business_date] = path
    return [
        HistoricalWorkbook(brand=brand, path=path, business_date=business_date)
        for business_date, path in sorted(by_day.items(), reverse=True)
    ]


def _empty(value: object) -> bool:
    return _text(value) is None


def _source_choice(path: Path) -> tuple[str, int, dict[str, int]] | None:
    choices = _xlsx_source_choices(path)
    if not choices:
        return None
    _, sheet_name, header_row, indexes = max(choices, key=lambda item: item[0])
    if not any(field in indexes for field in MANUAL_FIELDS):
        return None
    return sheet_name, header_row, indexes


def _upsert_records(engine, records: list[dict[str, object]]) -> None:
    if not records:
        return
    PRODUCT_GOODS_OVERRIDES_TABLE.create(engine, checkfirst=True)
    with engine.begin() as connection:
        for index in range(0, len(records), 1_000):
            statement = pg_insert(PRODUCT_GOODS_OVERRIDES_TABLE).values(records[index:index + 1_000])
            connection.execute(
                statement.on_conflict_do_update(
                    index_elements=["brand", "product_id"],
                    set_={field: getattr(statement.excluded, field) for field in MANUAL_FIELDS},
                )
            )


def backfill_brand(
    brand: str,
    *,
    root: Path,
    dry_run: bool,
    max_workbooks: int | None = None,
) -> BackfillSummary:
    settings = load_settings(require_database=True)
    assert settings.database_url is not None
    engine = create_engine(settings.database_url, future=True)
    summary = BackfillSummary(brand=brand)
    workbooks = historical_workbooks(root, brand=brand)
    if max_workbooks is not None:
        workbooks = workbooks[:max_workbooks]
    summary.scanned_workbooks = len(workbooks)

    with engine.connect() as connection:
        by_sku, by_unique_style = _product_maps(connection, brand)
        existing = {
            int(row["product_id"]): {field: row.get(field) for field in MANUAL_FIELDS}
            for row in connection.execute(
                select(PRODUCT_GOODS_OVERRIDES_TABLE).where(PRODUCT_GOODS_OVERRIDES_TABLE.c.brand == brand)
            ).mappings()
        }

    values_by_product: dict[int, dict[str, object]] = {
        product_id: dict(values)
        for product_id, values in existing.items()
    }
    dirty_product_ids: set[int] = set()

    for workbook in workbooks:
        choice = _source_choice(workbook.path)
        if choice is None:
            summary.skipped_workbooks += 1
            continue
        sheet_name, header_row, indexes = choice
        summary.processed_workbooks += 1
        changed_in_workbook: set[int] = set()
        for row in _source_rows(workbook.path, sheet_name, header_row, indexes):
            summary.source_rows += 1
            product_id = by_sku.get(row.get("goods_code") or "")
            if product_id is None:
                product_id = by_unique_style.get(row.get("style_code") or "")
            if product_id is None:
                continue
            summary.matched_rows += 1
            values = values_by_product.setdefault(product_id, {field: None for field in MANUAL_FIELDS})
            for field in MANUAL_FIELDS:
                source_value = row.get(field)
                if _empty(values.get(field)) and not _empty(source_value):
                    values[field] = source_value
                    summary.updated_fields[field] += 1
                    changed_in_workbook.add(product_id)
        if changed_in_workbook:
            dirty_product_ids.update(changed_in_workbook)
            if not dry_run:
                _upsert_records(
                    engine,
                    [
                        {"brand": brand, "product_id": product_id, **values_by_product[product_id]}
                        for product_id in sorted(changed_in_workbook)
                    ],
                )
        print(
            f"[{brand}] {workbook.business_date.isoformat()} {workbook.path.name} "
            f"rows={summary.source_rows} changed={len(changed_in_workbook)}",
            flush=True,
        )

    summary.updated_products = len(dirty_product_ids)
    summary.updated_fields = dict(sorted(summary.updated_fields.items()))
    if dirty_product_ids and not dry_run:
        clear_product_goods_cache()
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description="从历史商品明细表回填缺失的货品表运营字段")
    parser.add_argument("--brand", choices=sorted(BRAND_FOLDERS), action="append")
    parser.add_argument("--root", type=Path, help="单品牌历史目录；需同时传入一个 --brand")
    parser.add_argument("--max-workbooks", type=int, default=None)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    brands = args.brand or ("cbanner_womens", "cbanner_mens", "eblan")
    if args.root is not None and len(brands) != 1:
        parser.error("--root requires exactly one --brand")
    for brand in brands:
        root = args.root or SHARED_ROOT / BRAND_FOLDERS[brand]
        print(backfill_brand(brand, root=root, dry_run=args.dry_run, max_workbooks=args.max_workbooks))


if __name__ == "__main__":
    main()
