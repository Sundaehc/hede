from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable, Mapping
from datetime import date
from typing import Any

import orjson
from sqlalchemy import and_, create_engine, delete, func, inspect, insert, select, text

from domain.daily_sales_schema import jst_daily_sales_table_for_year, vip_daily_sales_table_for_year
from domain.factory_channel_sales import channel_group, platform_name, product_for_sale, product_index, sales_metrics, season_group, shop_channel_key
from domain.factory_channel_sales_summary_schema import FACTORY_CHANNEL_SALES_DAILY_SUMMARY_TABLE
from domain.product_goods_shop_channel_schema import PRODUCT_GOODS_SHOP_CHANNEL_MAPPINGS_TABLE
from domain.schema import PRODUCT_TABLES


DATE_MARKER_STATUS = "date_marker"
MATCHED_STATUS = "matched"
UNMATCHED_STATUS = "unmatched"
DUPLICATE_VIP_STATUS = "duplicate_vip"
INSERT_BATCH_SIZE = 1_000


def _json_serializer(value: object) -> str:
    return orjson.dumps(value).decode("utf-8")


def _consumer_sales_channel_condition(channel_column):
    channel = func.coalesce(channel_column, "")
    return and_(
        ~channel.ilike("%采购%"),
        ~channel.ilike("%-公司"),
        ~channel.ilike("%VMI%"),
    )


def summarize_factory_channel_sales(
    *,
    product_rows_by_brand: Mapping[str, list[dict[str, object]]],
    shop_channel_mappings_by_brand: Mapping[str, dict[str, str]],
    vip_rows: Iterable[Mapping[str, object]],
    jst_rows: Iterable[Mapping[str, object]],
    covered_sales_dates: Iterable[date] = (),
) -> list[dict[str, object]]:
    indexes = {
        brand: product_index(product_rows)
        for brand, product_rows in product_rows_by_brand.items()
    }
    quantities: dict[tuple[str, date, str, str, str], dict[str, int]] = defaultdict(
        lambda: {"quantity": 0, "gross_quantity": 0, "return_quantity": 0}
    )
    vip_product_dates: dict[str, set[tuple[str, date]]] = defaultdict(set)
    covered_dates = set(covered_sales_dates)

    def resolve(brand: str, row: Mapping[str, object]) -> dict[str, object] | None:
        by_sku, by_prefix, unique_style_matches = indexes[brand]
        return product_for_sale(
            row.get("product_code"),
            row.get("style_code"),
            by_sku=by_sku,
            by_prefix=by_prefix,
            unique_style_matches=unique_style_matches,
        )

    def add_quantity(key: tuple[str, date, str, str, str], row: Mapping[str, object]) -> None:
        net_quantity, gross_quantity, return_quantity = sales_metrics(dict(row))
        values = quantities[key]
        values["quantity"] += net_quantity
        values["gross_quantity"] += gross_quantity
        values["return_quantity"] += return_quantity

    for row in vip_rows:
        sales_date = row.get("sales_date")
        if not isinstance(sales_date, date):
            continue
        covered_dates.add(sales_date)
        net_quantity, gross_quantity, return_quantity = sales_metrics(dict(row))
        for brand in indexes:
            product = resolve(brand, row)
            if product is None:
                if gross_quantity or return_quantity or net_quantity:
                    add_quantity((brand, sales_date, "", "traditional", UNMATCHED_STATUS), row)
                continue
            sku = str(product.get("sku") or "").strip()
            vip_product_dates[brand].add((sku, sales_date))
            if gross_quantity or return_quantity or net_quantity:
                add_quantity((brand, sales_date, sku, "traditional", MATCHED_STATUS), row)

    for row in jst_rows:
        sales_date = row.get("sales_date")
        if not isinstance(sales_date, date):
            continue
        covered_dates.add(sales_date)
        net_quantity, gross_quantity, return_quantity = sales_metrics(dict(row))
        if not (gross_quantity or return_quantity or net_quantity):
            continue
        raw_channel = row.get("channel")
        for brand in indexes:
            mappings = shop_channel_mappings_by_brand.get(brand, {})
            group = channel_group(raw_channel, mappings)
            product = resolve(brand, row)
            if product is None:
                add_quantity((brand, sales_date, "", group, UNMATCHED_STATUS), row)
                continue
            sku = str(product.get("sku") or "").strip()
            if platform_name(raw_channel, mappings) == "唯品" and (sku, sales_date) in vip_product_dates[brand]:
                if season_group(product.get("season_category")) is None:
                    add_quantity((brand, sales_date, sku, group, DUPLICATE_VIP_STATUS), row)
                continue
            add_quantity((brand, sales_date, sku, group, MATCHED_STATUS), row)

    for brand in indexes:
        for sales_date in covered_dates:
            quantities[(brand, sales_date, "", "", DATE_MARKER_STATUS)] = {
                "quantity": 0,
                "gross_quantity": 0,
                "return_quantity": 0,
            }

    return [
        {
            "brand": brand,
            "sales_date": sales_date,
            "product_code": product_code,
            "channel_group": group,
            "match_status": match_status,
            "quantity": metrics["quantity"],
            "gross_quantity": metrics["gross_quantity"],
            "return_quantity": metrics["return_quantity"],
        }
        for (brand, sales_date, product_code, group, match_status), metrics in quantities.items()
    ]


class FactoryChannelSalesSummaryRepository:
    def __init__(self, database_url: str):
        self.engine = create_engine(database_url, future=True, json_serializer=_json_serializer)

    def refresh(
        self,
        *,
        sales_year: int,
        date_start: date | None = None,
        date_end: date | None = None,
    ) -> dict[str, Any]:
        range_start = date_start or date(sales_year, 1, 1)
        range_end = date_end or date(sales_year, 12, 31)
        if range_start > range_end:
            raise ValueError("date_start cannot be later than date_end")
        if range_start.year != sales_year or range_end.year != sales_year:
            raise ValueError("Factory-channel summary refresh must stay within one calendar year")

        FACTORY_CHANNEL_SALES_DAILY_SUMMARY_TABLE.create(self.engine, checkfirst=True)
        inspector = inspect(self.engine)
        jst_table = jst_daily_sales_table_for_year(sales_year)
        vip_table = vip_daily_sales_table_for_year(sales_year)

        with self.engine.connect() as connection:
            product_rows_by_brand = {
                brand: [
                    dict(row)
                    for row in connection.execute(
                        select(table.c.sku, table.c.original_sku, table.c.season_category)
                        .where(table.c.deleted_at.is_(None))
                        .where(table.c.sku.is_not(None))
                    ).mappings()
                ]
                for brand, table in PRODUCT_TABLES.items()
            }
            shop_channel_mappings_by_brand: dict[str, dict[str, str]] = defaultdict(dict)
            if inspector.has_table(PRODUCT_GOODS_SHOP_CHANNEL_MAPPINGS_TABLE.name):
                for row in connection.execute(
                    select(
                        PRODUCT_GOODS_SHOP_CHANNEL_MAPPINGS_TABLE.c.brand,
                        PRODUCT_GOODS_SHOP_CHANNEL_MAPPINGS_TABLE.c.shop_name,
                        PRODUCT_GOODS_SHOP_CHANNEL_MAPPINGS_TABLE.c.channel,
                    )
                ).mappings():
                    key = shop_channel_key(row["shop_name"])
                    if key and str(row["channel"] or "").strip():
                        shop_channel_mappings_by_brand[str(row["brand"])][key] = platform_name(row["channel"])

            vip_rows: Iterable[Mapping[str, object]] = ()
            covered_sales_dates: set[date] = set()
            if inspector.has_table(vip_table.name):
                covered_sales_dates.update(
                    connection.execute(
                        select(vip_table.c.sales_date)
                        .where(vip_table.c.sales_date.between(range_start, range_end))
                        .distinct()
                    ).scalars()
                )
                vip_rows = connection.execute(
                    select(
                        vip_table.c.goods_code.label("product_code"),
                        vip_table.c.style_code,
                        vip_table.c.sales_date,
                        func.sum(func.coalesce(vip_table.c.sales_quantity, 0)).label("quantity"),
                        func.sum(func.coalesce(vip_table.c.sales_quantity, 0)).label("gross_quantity"),
                        func.sum(func.coalesce(vip_table.c.sales_quantity, 0) * 0).label("return_quantity"),
                    )
                    .where(vip_table.c.sales_date.between(range_start, range_end))
                    .where(func.coalesce(vip_table.c.sales_quantity, 0) != 0)
                    .group_by(vip_table.c.goods_code, vip_table.c.style_code, vip_table.c.sales_date)
                ).mappings()

                # VIP rows must be consumed before the JST query reuses this
                # connection, because they establish authoritative product-date coverage.
                vip_rows = list(vip_rows)

            jst_rows: Iterable[Mapping[str, object]] = ()
            if inspector.has_table(jst_table.name):
                covered_sales_dates.update(
                    connection.execute(
                        select(jst_table.c.sales_date)
                        .where(jst_table.c.sales_date.between(range_start, range_end))
                        .distinct()
                    ).scalars()
                )
                jst_rows = connection.execute(
                    select(
                        jst_table.c.product_code,
                        jst_table.c.style_code,
                        jst_table.c.channel,
                        jst_table.c.sales_date,
                        func.sum(func.coalesce(jst_table.c.net_sales_quantity, 0)).label("quantity"),
                        func.sum(func.coalesce(jst_table.c.sales_quantity, 0)).label("gross_quantity"),
                        func.sum(func.coalesce(jst_table.c.return_quantity, 0)).label("return_quantity"),
                    )
                    .where(jst_table.c.sales_date.between(range_start, range_end))
                    .where(_consumer_sales_channel_condition(jst_table.c.channel))
                    .where(func.coalesce(jst_table.c.net_sales_quantity, 0) != 0)
                    .group_by(
                        jst_table.c.product_code,
                        jst_table.c.style_code,
                        jst_table.c.channel,
                        jst_table.c.sales_date,
                    )
                ).mappings()
                jst_rows = list(jst_rows)

        rows = summarize_factory_channel_sales(
            product_rows_by_brand=product_rows_by_brand,
            shop_channel_mappings_by_brand=shop_channel_mappings_by_brand,
            vip_rows=vip_rows,
            jst_rows=jst_rows,
            covered_sales_dates=covered_sales_dates,
        )

        with self.engine.begin() as connection:
            connection.execute(text(
                f"ALTER TABLE {FACTORY_CHANNEL_SALES_DAILY_SUMMARY_TABLE.name} "
                "ADD COLUMN IF NOT EXISTS gross_quantity BIGINT NOT NULL DEFAULT 0"
            ))
            connection.execute(text(
                f"ALTER TABLE {FACTORY_CHANNEL_SALES_DAILY_SUMMARY_TABLE.name} "
                "ADD COLUMN IF NOT EXISTS return_quantity BIGINT NOT NULL DEFAULT 0"
            ))
            connection.execute(
                delete(FACTORY_CHANNEL_SALES_DAILY_SUMMARY_TABLE).where(
                    FACTORY_CHANNEL_SALES_DAILY_SUMMARY_TABLE.c.sales_date.between(range_start, range_end)
                )
            )
            for offset in range(0, len(rows), INSERT_BATCH_SIZE):
                connection.execute(
                    insert(FACTORY_CHANNEL_SALES_DAILY_SUMMARY_TABLE),
                    rows[offset:offset + INSERT_BATCH_SIZE],
                )
            connection.exec_driver_sql("ANALYZE factory_channel_sales_daily_summaries")

        matched_rows = sum(1 for row in rows if row["match_status"] == MATCHED_STATUS)
        unmatched_rows = sum(1 for row in rows if row["match_status"] == UNMATCHED_STATUS)
        return {
            "sales_year": sales_year,
            "date_start": range_start.isoformat(),
            "date_end": range_end.isoformat(),
            "written": len(rows),
            "matched_rows": matched_rows,
            "unmatched_rows": unmatched_rows,
        }
