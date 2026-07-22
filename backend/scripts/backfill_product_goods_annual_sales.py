"""Backfill annual and monthly product-goods sales from persisted sales sources."""

from __future__ import annotations

import argparse
from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date

from sqlalchemy import inspect, select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from config import load_settings
from domain.daily_sales_schema import jst_daily_sales_table_for_year, vip_daily_sales_table_for_year
from domain.product_goods_historical_sales_schema import (
    HISTORICAL_SALES_YEARS,
    product_goods_historical_sales_table_for_year,
)
from domain.product_goods_sales_period_schema import (
    PRODUCT_GOODS_SALES_PERIODS_TABLE,
    ensure_product_goods_sales_periods_table,
)
from domain.schema import PRODUCT_TABLES
from storage.db import Database


DAILY_SALES_YEAR = 2026
BACKFILL_SOURCE_WORKBOOK = "product_goods_annual_sales_backfill"
BACKFILL_SOURCE_SHEET = "database_sales_aggregate"
PERIOD_TYPES = ("year", "month")


def _prefix_index(codes: Iterable[str]) -> dict[str, object]:
    root: dict[str, object] = {}
    for code in codes:
        node = root
        for character in code:
            node = node.setdefault(character, {})  # type: ignore[assignment]
        node["\0"] = code
    return root


def _longest_prefix(code: object, index: dict[str, object]) -> str | None:
    node = index
    matched: str | None = None
    for character in str(code or "").strip():
        child = node.get(character)
        if not isinstance(child, dict):
            break
        node = child
        candidate = node.get("\0")
        if isinstance(candidate, str):
            matched = candidate
    return matched


@dataclass(frozen=True)
class BrandMatcher:
    product_ids: dict[str, int]
    original_skus: dict[str, str]
    style_codes: dict[str, str]
    prefix_index: dict[str, object]

    def resolve(self, product_code: object, style_code: object) -> str | None:
        return _longest_prefix(product_code, self.prefix_index) or self.style_codes.get(str(style_code or "").strip())


@dataclass
class BackfillStats:
    source_rows: dict[int, int]
    matched_rows: dict[int, int]
    unmatched_rows: dict[int, int]
    written_rows: dict[tuple[int, str], int]
    skipped_authoritative: dict[str, dict[str, list[int]]]


def _brand_matchers(connection) -> dict[str, BrandMatcher]:
    result: dict[str, BrandMatcher] = {}
    for brand, table in PRODUCT_TABLES.items():
        product_ids: dict[str, int] = {}
        original_skus: dict[str, str] = {}
        styles: dict[str, list[str]] = defaultdict(list)
        for row in connection.execute(select(table.c.id, table.c.sku, table.c.original_sku)).mappings():
            sku = str(row["sku"] or "").strip()
            if not sku:
                continue
            product_ids[sku] = int(row["id"])
            style = str(row["original_sku"] or "").strip()
            if style:
                original_skus[sku] = style
                styles[style].append(sku)
        result[brand] = BrandMatcher(
            product_ids=product_ids,
            original_skus=original_skus,
            style_codes={style: skus[0] for style, skus in styles.items() if len(skus) == 1},
            prefix_index=_prefix_index(product_ids),
        )
    return result


def _authoritative_years(connection) -> dict[tuple[str, str], set[int]]:
    years: dict[tuple[str, str], set[int]] = defaultdict(set)
    rows = connection.execute(
        select(
            PRODUCT_GOODS_SALES_PERIODS_TABLE.c.brand,
            PRODUCT_GOODS_SALES_PERIODS_TABLE.c.period_type,
            PRODUCT_GOODS_SALES_PERIODS_TABLE.c.period_start,
            PRODUCT_GOODS_SALES_PERIODS_TABLE.c.source_workbook,
        ).where(PRODUCT_GOODS_SALES_PERIODS_TABLE.c.period_type.in_(PERIOD_TYPES))
    ).mappings()
    for row in rows:
        period_start = row["period_start"]
        if not isinstance(period_start, date):
            continue
        if row["source_workbook"] != BACKFILL_SOURCE_WORKBOOK:
            years[(str(row["brand"]), str(row["period_type"]))].add(period_start.year)
    return years


def _target_years(authoritative_years: dict[tuple[str, str], set[int]]) -> dict[str, dict[str, set[int]]]:
    source_years = {*HISTORICAL_SALES_YEARS, DAILY_SALES_YEAR}
    return {
        brand: {
            period_type: source_years.difference(authoritative_years.get((brand, period_type), set()))
            for period_type in PERIOD_TYPES
        }
        for brand in PRODUCT_TABLES
    }


def _add_sale(
    totals: dict[tuple[str, str, date, str], int],
    *,
    brand: str,
    sales_date: date,
    target_years: dict[str, dict[str, set[int]]],
    matcher: BrandMatcher,
    product_code: object,
    style_code: object,
    quantity: object,
    stats: BackfillStats,
) -> None:
    sales_year = sales_date.year
    stats.source_rows[sales_year] += 1
    sku = matcher.resolve(product_code, style_code)
    if sku is None:
        stats.unmatched_rows[sales_year] += 1
        return
    stats.matched_rows[sales_year] += 1
    periods = (
        ("year", date(sales_year, 1, 1)),
        ("month", date(sales_year, sales_date.month, 1)),
    )
    for period_type, period_start in periods:
        if sales_year in target_years[brand][period_type]:
            totals[(brand, period_type, period_start, sku)] += int(quantity or 0)


def _history_totals(connection, matchers: dict[str, BrandMatcher], target_years: dict[str, dict[str, set[int]]], stats: BackfillStats) -> dict[tuple[str, str, date, str], int]:
    totals: dict[tuple[str, str, date, str], int] = defaultdict(int)
    for sales_year in HISTORICAL_SALES_YEARS:
        table = product_goods_historical_sales_table_for_year(sales_year)
        if not inspect(connection).has_table(table.name):
            continue
        for row in connection.execution_options(stream_results=True).execute(
            select(table.c.brand, table.c.sales_date, table.c.product_code, table.c.original_sku, table.c.sales_quantity)
        ).mappings():
            brand = str(row["brand"] or "").strip()
            sales_date = row["sales_date"]
            if not isinstance(sales_date, date) or brand not in target_years:
                continue
            if not any(sales_year in years for years in target_years[brand].values()):
                continue
            _add_sale(
                totals,
                brand=brand,
                sales_date=sales_date,
                target_years=target_years,
                matcher=matchers[brand],
                product_code=row["product_code"],
                style_code=row["original_sku"],
                quantity=row["sales_quantity"],
                stats=stats,
            )
    return totals


def _daily_totals(connection, matchers: dict[str, BrandMatcher], target_years: dict[str, dict[str, set[int]]], stats: BackfillStats) -> dict[tuple[str, str, date, str], int]:
    totals: dict[tuple[str, str, date, str], int] = defaultdict(int)
    tables = (
        (jst_daily_sales_table_for_year(DAILY_SALES_YEAR), "product_code", "style_code", "net_sales_quantity"),
        (vip_daily_sales_table_for_year(DAILY_SALES_YEAR), "goods_code", "style_code", "sales_quantity"),
    )
    for table, product_column, style_column, quantity_column in tables:
        if not inspect(connection).has_table(table.name):
            continue
        rows = connection.execution_options(stream_results=True).execute(
            select(table.c.sales_date, table.c[product_column], table.c[style_column], table.c[quantity_column])
        ).mappings()
        for row in rows:
            sales_date = row["sales_date"]
            if not isinstance(sales_date, date):
                continue
            for brand, matcher in matchers.items():
                if not any(DAILY_SALES_YEAR in years for years in target_years[brand].values()):
                    continue
                _add_sale(
                    totals,
                    brand=brand,
                    sales_date=sales_date,
                    target_years=target_years,
                    matcher=matcher,
                    product_code=row[product_column],
                    style_code=row[style_column],
                    quantity=row[quantity_column],
                    stats=stats,
                )
    return totals


def _rows_to_write(
    totals: dict[tuple[str, str, date, str], int],
    matchers: dict[str, BrandMatcher],
    *,
    daily_as_of_date: date | None,
) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for (brand, period_type, period_start, sku), quantity in sorted(totals.items()):
        sales_year = period_start.year
        source_as_of_date = daily_as_of_date if sales_year == DAILY_SALES_YEAR else date(sales_year, 12, 31)
        rows.append(
            {
                "brand": brand,
                "product_code": sku,
                "style_code": matchers[brand].original_skus.get(sku),
                "period_type": period_type,
                "period_start": period_start,
                "sales_quantity": quantity,
                "source_as_of_date": source_as_of_date,
                "source_workbook": BACKFILL_SOURCE_WORKBOOK,
                "source_sheet": f"{BACKFILL_SOURCE_SHEET}:{brand}",
                "source_row_number": matchers[brand].product_ids[sku],
            }
        )
    return rows


def _daily_as_of_date(connection) -> date | None:
    candidates: list[date] = []
    for table in (jst_daily_sales_table_for_year(DAILY_SALES_YEAR), vip_daily_sales_table_for_year(DAILY_SALES_YEAR)):
        if not inspect(connection).has_table(table.name):
            continue
        value = connection.execute(select(table.c.sales_date).order_by(table.c.sales_date.desc()).limit(1)).scalar()
        if isinstance(value, date):
            candidates.append(value)
    return max(candidates, default=None)


def _write_rows(connection, rows: list[dict[str, object]]) -> int:
    written = 0
    for start in range(0, len(rows), 1_000):
        chunk = rows[start:start + 1_000]
        statement = pg_insert(PRODUCT_GOODS_SALES_PERIODS_TABLE).values(chunk)
        statement = statement.on_conflict_do_update(
            constraint="uq_product_goods_sales_period_source",
            set_={
                "brand": statement.excluded.brand,
                "product_code": statement.excluded.product_code,
                "style_code": statement.excluded.style_code,
                "sales_quantity": statement.excluded.sales_quantity,
                "source_as_of_date": statement.excluded.source_as_of_date,
            },
        )
        connection.execution_options(stream_results=False).execute(statement)
        written += len(chunk)
    return written


def backfill(*, dry_run: bool) -> BackfillStats:
    settings = load_settings(require_database=True)
    assert settings.database_url is not None
    database = Database(settings.database_url)
    engine = database._require_engine()
    ensure_product_goods_sales_periods_table(engine)
    stats = BackfillStats(
        source_rows=defaultdict(int),
        matched_rows=defaultdict(int),
        unmatched_rows=defaultdict(int),
        written_rows=defaultdict(int),
        skipped_authoritative={},
    )
    with engine.begin() as connection:
        matchers = _brand_matchers(connection)
        authoritative_years = _authoritative_years(connection)
        target_years = _target_years(authoritative_years)
        stats.skipped_authoritative = {
            brand: {
                period_type: sorted(authoritative_years.get((brand, period_type), set()).intersection({*HISTORICAL_SALES_YEARS, DAILY_SALES_YEAR}))
                for period_type in PERIOD_TYPES
                if authoritative_years.get((brand, period_type), set()).intersection({*HISTORICAL_SALES_YEARS, DAILY_SALES_YEAR})
            }
            for brand in PRODUCT_TABLES
        }
        stats.skipped_authoritative = {brand: periods for brand, periods in stats.skipped_authoritative.items() if periods}
        totals = _history_totals(connection, matchers, target_years, stats)
        for key, quantity in _daily_totals(connection, matchers, target_years, stats).items():
            totals[key] += quantity
        rows = _rows_to_write(totals, matchers, daily_as_of_date=_daily_as_of_date(connection))
        for row in rows:
            stats.written_rows[(int(row["period_start"].year), str(row["period_type"]))] += 1
        if not dry_run:
            _write_rows(connection, rows)
    return stats


def main() -> int:
    parser = argparse.ArgumentParser(description="Backfill annual and monthly product-goods sales from database sales sources")
    parser.add_argument("--dry-run", action="store_true", help="Report the backfill without writing")
    args = parser.parse_args()
    stats = backfill(dry_run=args.dry_run)
    for sales_year in sorted({*HISTORICAL_SALES_YEARS, DAILY_SALES_YEAR}):
        print(
            f"{sales_year}: source_rows={stats.source_rows[sales_year]} "
            f"matched_rows={stats.matched_rows[sales_year]} "
            f"unmatched_rows={stats.unmatched_rows[sales_year]} "
            f"{'would_write' if args.dry_run else 'written'}_annual={stats.written_rows[(sales_year, 'year')]} "
            f"{'would_write' if args.dry_run else 'written'}_monthly={stats.written_rows[(sales_year, 'month')]}"
        )
    print(f"skipped_authoritative={stats.skipped_authoritative}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
