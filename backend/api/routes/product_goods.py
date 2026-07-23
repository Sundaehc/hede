from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, ConfigDict
from collections import defaultdict
from datetime import date, timedelta
import re

from sqlalchemy import desc, func, inspect, or_, select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from api.product_goods_cache import clear_product_goods_cache, get_product_goods_cache, set_product_goods_cache
from api.routes.images import image_url_for
from domain.product_goods_schema import PRODUCT_GOODS_OVERRIDES_TABLE
from domain.product_goods_shop_channel_schema import PRODUCT_GOODS_SHOP_CHANNEL_MAPPINGS_TABLE
from domain.product_goods_historical_sales_schema import HISTORICAL_SALES_YEARS, product_goods_historical_sales_table_for_year
from domain.product_goods_historical_orders_schema import HISTORICAL_ORDER_START_YEAR, product_goods_historical_orders_table_for_year
from domain.product_goods_sales_period_schema import PRODUCT_GOODS_SALES_PERIODS_TABLE
from domain.product_goods_detail_snapshot_schema import (
    PRODUCT_GOODS_DETAIL_SNAPSHOT_BATCHES_TABLE,
    product_goods_detail_snapshots_table_for_year,
)
from domain.schema import PRODUCT_TABLES
from domain.vip_schema import JST_SIZE_STOCK_TABLE, JST_STOCK_SUMMARY_TABLE
from domain.daily_sales_schema import jst_daily_sales_table_for_year, vip_daily_sales_table_for_year
from domain.inventory_schema import SUPPLIER_TABLE
from domain.jst_full_stock_schema import JST_FULL_STOCK_TABLE
from domain.jst_stock_snapshot_schema import JST_SIZE_STOCK_SNAPSHOT_TABLE, JST_STOCK_SUMMARY_SNAPSHOT_TABLE


router = APIRouter()
DEFAULT_BRAND = "cbanner_womens"
SIZE_COLUMNS = ["34", "35", "36", "37", "38", "39", "40", "41", "42", "43", "44"]
PLATFORM_COLUMNS = ["唯品", "天猫", "得物", "拼多多", "京东", "商品卡", "直播赛道", "达播清仓", "拼多多清仓", "其他"]
SIZE_TO_STOCK_CODE = {str(size): str(50 + size * 5) for size in range(34, 45)}
STOCK_CODE_TO_SIZE = {value: key for key, value in SIZE_TO_STOCK_CODE.items()}
SALES_PERIOD_START_YEAR = 2024
LOW_STOCK_SALE_DAYS = 7
HIGH_STOCK_SALE_DAYS = 90


class ProductGoodsUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    platform: str | None = None
    category_l4: str | None = None
    product_role: str | None = None
    product_type: str | None = None
    douyin_hot: str | None = None
    clearance: str | None = None
    remark: str | None = None
    replenishment_by_size: dict[str, int] | None = None
    replenishment_total: int | None = None
    post_replenishment_by_size: dict[str, int] | None = None
    post_replenishment_stock: int | None = None
    post_replenishment_total: int | None = None
    post_replenishment_turnover_days: float | None = None


PRODUCT_GOODS_STANDARD_OVERRIDE_FIELDS = {
    "platform",
    "category_l4",
    "product_role",
    "product_type",
    "douyin_hot",
    "clearance",
    "remark",
}
PRODUCT_GOODS_REPLENISHMENT_FIELDS = {
    "replenishment_by_size",
    "replenishment_total",
    "post_replenishment_by_size",
    "post_replenishment_stock",
    "post_replenishment_total",
    "post_replenishment_turnover_days",
}


def _size_stock_payload(
    connection,
    product_codes: list[str],
    *,
    snapshot_date: date | None = None,
) -> dict[str, dict[str, int]]:
    if not product_codes:
        return {}
    table = JST_SIZE_STOCK_SNAPSHOT_TABLE if snapshot_date is not None else JST_SIZE_STOCK_TABLE
    conditions = [table.c.product_code.in_(product_codes)]
    if snapshot_date is not None:
        conditions.append(table.c.snapshot_date == snapshot_date)
    rows = connection.execute(
        select(
            table.c.product_code,
            table.c.size,
            func.sum(table.c.stock_qty).label("quantity"),
        )
        .where(*conditions)
        .group_by(table.c.product_code, table.c.size)
    ).mappings()
    result: dict[str, dict[str, int]] = {}
    for row in rows:
        code = str(row["product_code"] or "").strip()
        size = STOCK_CODE_TO_SIZE.get(str(row["size"] or "").strip(), str(row["size"] or "").strip())
        if code and size:
            result.setdefault(code, {})[size] = int(row["quantity"] or 0)
    return result


def _full_stock_size(value: object) -> str | None:
    """Return a display size only when the source value maps to one exact size."""
    normalized = str(value or "").strip()
    if normalized.endswith(".0") and normalized[:-2].isdigit():
        normalized = normalized[:-2]
    if normalized in SIZE_COLUMNS:
        return normalized
    return STOCK_CODE_TO_SIZE.get(normalized)


def _stock_health_label(stock_sale_days: float | None, shortage_total: int) -> str | None:
    if shortage_total > 0:
        return "缺货"
    if stock_sale_days is None:
        return None
    if stock_sale_days <= LOW_STOCK_SALE_DAYS:
        return "低库存"
    if stock_sale_days >= HIGH_STOCK_SALE_DAYS:
        return "积压风险"
    return "正常"


def _detail_snapshot_dates(connection, *, brand: str) -> list[date]:
    if not inspect(connection).has_table(PRODUCT_GOODS_DETAIL_SNAPSHOT_BATCHES_TABLE.name):
        return []
    return [
        item
        for item in connection.execute(
            select(PRODUCT_GOODS_DETAIL_SNAPSHOT_BATCHES_TABLE.c.snapshot_date)
            .where(PRODUCT_GOODS_DETAIL_SNAPSHOT_BATCHES_TABLE.c.brand == brand)
            .where(PRODUCT_GOODS_DETAIL_SNAPSHOT_BATCHES_TABLE.c.status == "success")
            .distinct()
            .order_by(desc(PRODUCT_GOODS_DETAIL_SNAPSHOT_BATCHES_TABLE.c.snapshot_date))
        ).scalars()
        if isinstance(item, date)
    ]


def _detail_snapshot_payload(
    connection,
    product_codes: list[str],
    *,
    brand: str,
    snapshot_date: date | None,
) -> dict[str, dict[str, object]]:
    if snapshot_date is None or not product_codes:
        return {}
    table = product_goods_detail_snapshots_table_for_year(snapshot_date.year)
    if not inspect(connection).has_table(table.name):
        return {}
    return {
        str(row["goods_code"]): dict(row["data"] or {})
        for row in connection.execute(
            select(table.c.goods_code, table.c.data)
            .where(table.c.brand == brand)
            .where(table.c.snapshot_date == snapshot_date)
            .where(table.c.goods_code.in_(product_codes))
        ).mappings()
        if str(row["goods_code"] or "").strip()
    }


def _current_full_stock_payload(
    connection,
    product_codes: list[str],
) -> dict[str, dict[str, Any]]:
    """Aggregate the full JST inventory file for the products displayed on one page.

    The source product code contains a base goods code plus a color/size suffix, so
    resolving the longest matching base code prevents one goods code from being
    attributed to a shorter prefix.
    """
    if not product_codes or not inspect(connection).has_table(JST_FULL_STOCK_TABLE.name):
        return {}
    normalized_codes = sorted({code.strip() for code in product_codes if code.strip()}, key=len, reverse=True)
    if not normalized_codes:
        return {}
    code_conditions = [JST_FULL_STOCK_TABLE.c.product_code.startswith(code) for code in normalized_codes]
    rows = connection.execute(
        select(
            JST_FULL_STOCK_TABLE.c.product_code,
            JST_FULL_STOCK_TABLE.c.size,
            JST_FULL_STOCK_TABLE.c.actual_stock_qty,
            JST_FULL_STOCK_TABLE.c.purchase_warehouse_stock_qty,
            JST_FULL_STOCK_TABLE.c.purchase_in_transit_qty,
            JST_FULL_STOCK_TABLE.c.transfer_in_transit_qty,
            JST_FULL_STOCK_TABLE.c.return_in_transit_qty,
            JST_FULL_STOCK_TABLE.c.available_qty,
            JST_FULL_STOCK_TABLE.c.stock_sale_days,
        ).where(or_(*code_conditions))
    ).mappings()
    result: dict[str, dict[str, Any]] = {}
    for row in rows:
        source_code = str(row["product_code"] or "").strip()
        matched_code = next((code for code in normalized_codes if source_code.startswith(code)), None)
        if not matched_code:
            continue
        payload = result.setdefault(
            matched_code,
            {
                "stock_by_size": {},
                "in_transit_by_size": {},
                "available_by_size": {},
                "stock_total": 0,
                "in_transit_total": 0,
                "stock_sale_days": [],
            },
        )
        stock_quantity = int(row["actual_stock_qty"] or 0) + int(row["purchase_warehouse_stock_qty"] or 0)
        in_transit_quantity = (
            int(row["purchase_in_transit_qty"] or 0)
            + int(row["transfer_in_transit_qty"] or 0)
            + int(row["return_in_transit_qty"] or 0)
        )
        payload["stock_total"] += stock_quantity
        payload["in_transit_total"] += in_transit_quantity
        if row["stock_sale_days"] is not None:
            payload["stock_sale_days"].append(float(row["stock_sale_days"]))
        size = _full_stock_size(row["size"])
        if size is not None:
            stock_by_size = payload["stock_by_size"]
            in_transit_by_size = payload["in_transit_by_size"]
            available_by_size = payload["available_by_size"]
            stock_by_size[size] = stock_by_size.get(size, 0) + stock_quantity
            in_transit_by_size[size] = in_transit_by_size.get(size, 0) + in_transit_quantity
            available_by_size[size] = available_by_size.get(size, 0) + int(row["available_qty"] or 0)
    for payload in result.values():
        available_by_size = payload.pop("available_by_size")
        payload["shortage_by_size"] = {
            size: -quantity
            for size, quantity in available_by_size.items()
            if quantity < 0
        }
        payload["shortage_total"] = sum(payload["shortage_by_size"].values())
        stock_sale_days = payload.pop("stock_sale_days")
        payload["stock_sale_days"] = min(stock_sale_days) if stock_sale_days else None
    return result


def _manual_size_quantities(value: object) -> dict[str, int]:
    if not isinstance(value, dict):
        return {}
    quantities: dict[str, int] = {}
    for size, quantity in value.items():
        normalized_size = str(size).strip()
        if normalized_size not in SIZE_COLUMNS:
            continue
        try:
            normalized_quantity = int(quantity)
        except (TypeError, ValueError):
            continue
        if normalized_quantity >= 0:
            quantities[normalized_size] = normalized_quantity
    return quantities


def _manual_number(value: object) -> int | float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return value if value >= 0 else None


def _snapshot_value(values: dict[str, object], key: str, fallback: object) -> object:
    return values[key] if key in values and values[key] is not None else fallback


def _size_from_color_spec(value: object) -> str | None:
    text = str(value or "")
    matched = re.search(r"(?<!\d)(3[4-9]|4[0-4])(?!\d)", text)
    return matched.group(1) if matched else None


def _shop_channel_key(value: object) -> str:
    return re.sub(r"\s+", "", str(value or "").strip())


def _shop_channel_mapping_payload(connection, brand: str) -> dict[str, str]:
    if not inspect(connection).has_table(PRODUCT_GOODS_SHOP_CHANNEL_MAPPINGS_TABLE.name):
        return {}
    rows = connection.execute(
        select(
            PRODUCT_GOODS_SHOP_CHANNEL_MAPPINGS_TABLE.c.shop_name,
            PRODUCT_GOODS_SHOP_CHANNEL_MAPPINGS_TABLE.c.channel,
        ).where(PRODUCT_GOODS_SHOP_CHANNEL_MAPPINGS_TABLE.c.brand == brand)
    ).mappings()
    return {
        _shop_channel_key(row["shop_name"]): _platform_name(row["channel"])
        for row in rows
        if _shop_channel_key(row["shop_name"]) and str(row["channel"] or "").strip()
    }


def _platform_name(channel: object, shop_channel_mappings: dict[str, str] | None = None) -> str:
    value = str(channel or "").strip()
    mapped_channel = (shop_channel_mappings or {}).get(_shop_channel_key(value))
    if mapped_channel:
        return mapped_channel
    if "唯品" in value:
        return "唯品"
    if "天猫" in value:
        return "天猫"
    if "得物" in value:
        return "得物"
    if "拼多多" in value and "清仓" in value:
        return "拼多多清仓"
    if "拼多多" in value:
        return "拼多多"
    if "京东" in value:
        return "京东"
    if "商品卡" in value:
        return "商品卡"
    if "达播" in value and "清仓" in value:
        return "达播清仓"
    if "直播" in value:
        return "直播赛道"
    return "其他"


def _is_clearance_channel(channel: object, platform: str) -> bool:
    return "清仓" in str(channel or "") or platform in {"达播清仓", "拼多多清仓"}


def _resolve_jst_product_code(
    product_code: object,
    style_code: object,
    product_codes: list[str],
    unique_style_codes: dict[str, str],
) -> str | None:
    normalized_product_code = str(product_code or "").strip()
    if normalized_product_code:
        for candidate in sorted(product_codes, key=len, reverse=True):
            if normalized_product_code.startswith(candidate):
                return candidate
    return unique_style_codes.get(str(style_code or "").strip())


def _historical_order_targets(
    original_sku: object,
    product_codes: list[str],
    style_code_matches: dict[str, list[str]],
) -> list[str]:
    value = str(original_sku or "").strip()
    for product_code in sorted(product_codes, key=len, reverse=True):
        if value.startswith(product_code):
            return [product_code]
    return style_code_matches.get(value, [])


def _historical_order_counts(
    connection,
    product_sales_codes: dict[str, str],
    *,
    brand: str,
) -> dict[str, int]:
    if brand not in {"cbanner_mens", "cbanner_womens", "eblan"} or not product_sales_codes:
        return {}
    product_codes = sorted(product_sales_codes, key=len, reverse=True)
    style_code_matches: dict[str, list[str]] = defaultdict(list)
    for product_code, style_code in product_sales_codes.items():
        if style_code:
            style_code_matches[style_code].append(product_code)
    inspector = inspect(connection)
    counts: dict[str, int] = defaultdict(int)
    for order_year in range(HISTORICAL_ORDER_START_YEAR, date.today().year + 1):
        table = product_goods_historical_orders_table_for_year(order_year)
        if not inspector.has_table(table.name):
            continue
        conditions = [table.c.original_sku.startswith(product_code) for product_code in product_codes]
        if style_code_matches:
            conditions.append(table.c.original_sku.in_(style_code_matches))
        rows = connection.execute(
            select(
                table.c.original_sku,
                func.sum(table.c.order_quantity).label("order_quantity"),
            )
            .where(table.c.brand == brand)
            .where(or_(*conditions))
            .group_by(table.c.original_sku)
        ).mappings()
        for row in rows:
            for code in _historical_order_targets(row["original_sku"], product_codes, style_code_matches):
                counts[code] += int(row["order_quantity"] or 0)
    return dict(counts)


def _sales_matrix_payload(
    connection,
    engine,
    product_sales_codes: dict[str, str],
    *,
    brand: str,
    as_of_date: date | None = None,
) -> tuple[list[str], dict[str, dict[str, int]], dict[str, dict[str, dict[str, int]]], dict[str, dict[str, int]], dict[str, dict[str, int | None]]]:
    if not product_sales_codes:
        return [], {}, {}, {}, {}
    product_codes = sorted(product_sales_codes, key=len, reverse=True)
    style_code_matches: dict[str, list[str]] = defaultdict(list)
    for product_code, style_code in product_sales_codes.items():
        if style_code:
            style_code_matches[style_code].append(product_code)
    unique_style_codes = {
        style_code: matches[0]
        for style_code, matches in style_code_matches.items()
        if len(matches) == 1
    }
    shop_channel_mappings = _shop_channel_mapping_payload(connection, brand)
    inspector = inspect(engine)
    jst_tables = []
    vip_tables = []
    for year in (date.today().year,):
        jst_table = jst_daily_sales_table_for_year(year)
        vip_table = vip_daily_sales_table_for_year(year)
        if inspector.has_table(jst_table.name):
            jst_tables.append(jst_table)
        if inspector.has_table(vip_table.name):
            vip_tables.append(vip_table)
    tables = [*jst_tables, *vip_tables]
    if not tables:
        return [], {}, {}, {}, {}
    latest_candidates = [
        connection.execute(
            select(func.max(table.c.sales_date)).where(table.c.sales_date <= as_of_date)
            if as_of_date is not None
            else select(func.max(table.c.sales_date))
        ).scalar()
        for table in tables
    ]
    latest = as_of_date or max((item for item in latest_candidates if isinstance(item, date)), default=None)
    if not isinstance(latest, date):
        return [], {}, {}, {}, {}
    dates = [latest - timedelta(days=offset) for offset in range(13, -1, -1)]
    daily_by_sku: dict[str, dict[str, int]] = {}
    platform_by_sku: dict[str, dict[str, dict[str, int]]] = {}
    sales_by_size: dict[str, dict[str, int]] = {}
    summary_by_sku: dict[str, dict[str, int | None]] = defaultdict(lambda: {
        "total_order_count": 0,
        "total_sales": 0,
        "return_qty": 0,
        "yesterday_sales": None,
        "previous_day_sales": None,
        "normal_shelf_sales": 0,
        "clearance_sales": 0,
        "week_sales": 0,
        "normal_shelf_week_sales": 0,
        "clearance_week_sales": 0,
        "last_week_sales": 0,
        "sales_2024": 0,
        "sales_2025": 0,
        "year_sales": 0,
        "month_sales": 0,
    })
    week_start = latest - timedelta(days=6)
    previous_week_start = latest - timedelta(days=13)
    month_start = latest.replace(day=1)
    def add_sale(
        code: str,
        day: date,
        quantity: int,
        *,
        order_count: int = 0,
        return_quantity: int = 0,
        platform: str,
        is_clearance: bool = False,
        size: str | None = None,
    ) -> None:
        summary = summary_by_sku[code]
        summary["total_order_count"] = int(summary["total_order_count"] or 0) + order_count
        summary["total_sales"] = int(summary["total_sales"] or 0) + quantity
        summary["return_qty"] = int(summary["return_qty"] or 0) + return_quantity
        if day.year == 2024:
            summary["sales_2024"] = int(summary["sales_2024"] or 0) + quantity
        if day.year == 2025:
            summary["sales_2025"] = int(summary["sales_2025"] or 0) + quantity
        if day.year == latest.year:
            summary["year_sales"] = int(summary["year_sales"] or 0) + quantity
        if day >= month_start:
            summary["month_sales"] = int(summary["month_sales"] or 0) + quantity
        if day >= week_start:
            summary["week_sales"] = int(summary["week_sales"] or 0) + quantity
            shelf_week_key = "clearance_week_sales" if is_clearance else "normal_shelf_week_sales"
            summary[shelf_week_key] = int(summary[shelf_week_key] or 0) + quantity
        elif day >= previous_week_start:
            summary["last_week_sales"] = int(summary["last_week_sales"] or 0) + quantity
        if day == latest:
            summary["yesterday_sales"] = int(summary["yesterday_sales"] or 0) + quantity
            shelf_day_key = "clearance_sales" if is_clearance else "normal_shelf_sales"
            summary[shelf_day_key] = int(summary[shelf_day_key] or 0) + quantity
        if day == latest - timedelta(days=1):
            summary["previous_day_sales"] = int(summary["previous_day_sales"] or 0) + quantity
        if day >= dates[0]:
            day_key = day.isoformat()
            daily_by_sku.setdefault(code, {})[day_key] = daily_by_sku.setdefault(code, {}).get(day_key, 0) + quantity
            if size:
                sales_by_size.setdefault(code, {})[size] = sales_by_size.setdefault(code, {}).get(size, 0) + quantity
        platform_by_sku.setdefault(code, {})
        for period_key, matches_period in (
            ("daily", day == latest),
            ("weekly", day >= week_start),
            ("monthly", day >= month_start),
        ):
            if matches_period:
                period_values = platform_by_sku[code].setdefault(period_key, {})
                period_values[platform] = period_values.get(platform, 0) + quantity

    vip_product_dates: set[tuple[str, date]] = set()
    for table in vip_tables:
        vip_code_conditions = [table.c.goods_code.startswith(product_code) for product_code in product_codes]
        if unique_style_codes:
            vip_code_conditions.append(table.c.style_code.in_(unique_style_codes))
        rows = connection.execute(
            select(
                table.c.goods_code, table.c.style_code, table.c.sales_date, table.c.size_name, table.c.size_id,
                func.sum(func.coalesce(table.c.sales_quantity, 0)).label("quantity"),
                func.sum(func.coalesce(table.c.customer_count, 0)).label("order_count"),
            )
            .where(or_(*vip_code_conditions))
            .where(table.c.sales_date <= latest)
            .group_by(table.c.goods_code, table.c.style_code, table.c.sales_date, table.c.size_name, table.c.size_id)
        ).mappings()
        for row in rows:
            code = _resolve_jst_product_code(row["goods_code"], row["style_code"], product_codes, unique_style_codes)
            day = row["sales_date"]
            if code is None or not isinstance(day, date):
                continue
            vip_product_dates.add((code, day))
            size = _size_from_color_spec(row["size_name"]) or _size_from_color_spec(row["size_id"])
            add_sale(code, day, int(row["quantity"] or 0), order_count=int(row["order_count"] or 0), platform="唯品", size=size)

    for table in jst_tables:
        code_conditions = [table.c.product_code.startswith(product_code) for product_code in product_codes]
        if unique_style_codes:
            code_conditions.append(table.c.style_code.in_(unique_style_codes))
        rows = connection.execute(
            select(
                table.c.product_code, table.c.style_code, table.c.sales_date, table.c.channel, table.c.color_spec,
                func.sum(func.coalesce(table.c.net_sales_quantity, 0)).label("quantity"),
                func.sum(func.coalesce(table.c.sales_order_count, 0)).label("order_count"),
                func.sum(func.coalesce(table.c.return_quantity, 0)).label("return_quantity"),
            )
            .where(or_(*code_conditions))
            .where(table.c.sales_date <= latest)
            .group_by(table.c.product_code, table.c.style_code, table.c.sales_date, table.c.channel, table.c.color_spec)
        ).mappings()
        for row in rows:
            code = _resolve_jst_product_code(row["product_code"], row["style_code"], product_codes, unique_style_codes)
            day = row["sales_date"]
            quantity = int(row["quantity"] or 0)
            if code is None or not isinstance(day, date):
                continue
            platform = _platform_name(row["channel"], shop_channel_mappings)
            if platform == "唯品" and (code, day) in vip_product_dates:
                continue
            add_sale(
                code,
                day,
                quantity,
                order_count=int(row["order_count"] or 0),
                return_quantity=int(row["return_quantity"] or 0),
                platform=platform,
                is_clearance=_is_clearance_channel(row["channel"], platform),
                size=_size_from_color_spec(row["color_spec"]),
            )
    for sales_year in HISTORICAL_SALES_YEARS:
        history_table = product_goods_historical_sales_table_for_year(sales_year)
        if not inspector.has_table(history_table.name):
            continue
        history_conditions = [history_table.c.product_code.startswith(product_code) for product_code in product_codes]
        if unique_style_codes:
            history_conditions.append(history_table.c.original_sku.in_(unique_style_codes))
        history_rows = connection.execute(
            select(
                history_table.c.product_code,
                history_table.c.original_sku,
                history_table.c.sales_date,
                history_table.c.channel,
                history_table.c.size,
                func.sum(history_table.c.sales_quantity).label("quantity"),
            )
            .where(history_table.c.brand == brand)
            .where(or_(*history_conditions))
            .group_by(
                history_table.c.product_code,
                history_table.c.original_sku,
                history_table.c.sales_date,
                history_table.c.channel,
                history_table.c.size,
            )
        ).mappings()
        for row in history_rows:
            code = _resolve_jst_product_code(row["product_code"], row["original_sku"], product_codes, unique_style_codes)
            sales_date = row["sales_date"]
            if code is None or not isinstance(sales_date, date):
                continue
            platform = _platform_name(row["channel"], shop_channel_mappings)
            add_sale(
                code,
                sales_date,
                int(row["quantity"] or 0),
                platform=platform,
                is_clearance=_is_clearance_channel(row["channel"], platform),
                size=_size_from_color_spec(row["size"]),
            )
    return [item.isoformat() for item in dates], daily_by_sku, platform_by_sku, sales_by_size, dict(summary_by_sku)


def _sales_period_payload(
    connection,
    engine,
    product_sales_codes: dict[str, str],
    *,
    brand: str,
    as_of_date: date | None = None,
) -> tuple[list[str], list[str], dict[str, dict[str, int]], dict[str, dict[str, int]]]:
    latest_period = date.today()
    annual_columns = [str(year) for year in range(SALES_PERIOD_START_YEAR, latest_period.year + 1)]
    monthly_columns = [
        f"{year % 100:02d}-{month}"
        for year in range(SALES_PERIOD_START_YEAR, latest_period.year + 1)
        for month in range(1, 13)
        if (year, month) <= (latest_period.year, latest_period.month)
    ]
    if not product_sales_codes or not inspect(engine).has_table(PRODUCT_GOODS_SALES_PERIODS_TABLE.name):
        return annual_columns, monthly_columns, {}, {}
    product_codes = sorted(product_sales_codes, key=len, reverse=True)
    style_code_matches: dict[str, list[str]] = defaultdict(list)
    for product_code, style_code in product_sales_codes.items():
        if style_code:
            style_code_matches[style_code].append(product_code)
    unique_style_codes = {
        style_code: matches[0]
        for style_code, matches in style_code_matches.items()
        if len(matches) == 1
    }
    conditions = [PRODUCT_GOODS_SALES_PERIODS_TABLE.c.product_code.startswith(product_code) for product_code in product_codes]
    if unique_style_codes:
        conditions.append(PRODUCT_GOODS_SALES_PERIODS_TABLE.c.style_code.in_(unique_style_codes))
    statement = (
        select(
            PRODUCT_GOODS_SALES_PERIODS_TABLE.c.product_code,
            PRODUCT_GOODS_SALES_PERIODS_TABLE.c.style_code,
            PRODUCT_GOODS_SALES_PERIODS_TABLE.c.period_type,
            PRODUCT_GOODS_SALES_PERIODS_TABLE.c.period_start,
            PRODUCT_GOODS_SALES_PERIODS_TABLE.c.sales_quantity,
        )
        .where(PRODUCT_GOODS_SALES_PERIODS_TABLE.c.brand == brand)
        .where(or_(*conditions))
    )
    if as_of_date is not None:
        statement = statement.where(
            or_(
                PRODUCT_GOODS_SALES_PERIODS_TABLE.c.source_as_of_date.is_(None),
                PRODUCT_GOODS_SALES_PERIODS_TABLE.c.source_as_of_date <= as_of_date,
            )
        )
    annual_by_sku: dict[str, dict[str, int]] = {}
    monthly_by_sku: dict[str, dict[str, int]] = {}
    for row in connection.execute(statement).mappings():
        code = _resolve_jst_product_code(row["product_code"], row["style_code"], product_codes, unique_style_codes)
        period_start = row["period_start"]
        if code is None or not isinstance(period_start, date):
            continue
        quantity = int(row["sales_quantity"] or 0)
        if row["period_type"] == "year":
            key = str(period_start.year)
            annual_by_sku.setdefault(code, {})[key] = quantity
        elif row["period_type"] == "month":
            key = f"{period_start.year % 100:02d}-{period_start.month}"
            monthly_by_sku.setdefault(code, {})[key] = quantity
    return annual_columns, monthly_columns, annual_by_sku, monthly_by_sku


@router.get("/product-goods")
def list_product_goods(
    request: Request,
    brand: str = Query(DEFAULT_BRAND),
    query: str | None = None,
    platform: str | None = None,
    year: str | None = None,
    snapshot_date: date | None = None,
    cache_bust: str | None = None,
    page: int = 1,
    page_size: int = 50,
):
    if brand not in PRODUCT_TABLES:
        raise HTTPException(status_code=400, detail=f"Invalid brand: {brand}")
    page = max(page, 1)
    page_size = min(max(page_size, 1), 500)
    normalized_query = (query or "").strip()
    normalized_platform = (platform or "").strip()
    normalized_year = (year or "").strip()
    normalized_snapshot_date = snapshot_date.isoformat() if snapshot_date else ""
    cache_key = (brand, normalized_query, normalized_platform, normalized_year, normalized_snapshot_date, page, page_size)
    if not cache_bust:
        cached = get_product_goods_cache(cache_key)
        if cached is not None:
            return cached
    product_table = PRODUCT_TABLES[brand]
    override = PRODUCT_GOODS_OVERRIDES_TABLE
    conditions = []
    if normalized_query:
        term = f"%{normalized_query}%"
        conditions.append(or_(product_table.c.sku.ilike(term), product_table.c.original_sku.ilike(term), product_table.c.factory_sku.ilike(term), product_table.c.color.ilike(term)))
    if normalized_year:
        conditions.append(product_table.c.year.ilike(f"%{normalized_year}%"))
    if normalized_platform:
        conditions.append(override.c.platform == normalized_platform)
    join = product_table.outerjoin(override, (override.c.brand == brand) & (override.c.product_id == product_table.c.id))
    statement = select(product_table, override).select_from(join)
    count_statement = select(func.count()).select_from(join)
    for condition in conditions:
        statement = statement.where(condition)
        count_statement = count_statement.where(condition)
    statement = statement.order_by(product_table.c.year.desc().nulls_last(), product_table.c.sku).offset((page - 1) * page_size).limit(page_size)

    settings = request.app.state.settings
    repository = request.app.state.repository
    with repository.engine.connect() as connection:
        stock_snapshot_dates = [
            item
            for item in connection.execute(
                select(JST_SIZE_STOCK_SNAPSHOT_TABLE.c.snapshot_date)
                .distinct()
                .order_by(desc(JST_SIZE_STOCK_SNAPSHOT_TABLE.c.snapshot_date))
            ).scalars()
            if isinstance(item, date)
        ]
        detail_snapshot_dates = _detail_snapshot_dates(connection, brand=brand)
        snapshot_dates = sorted({*stock_snapshot_dates, *detail_snapshot_dates}, reverse=True)
        if snapshot_date is not None and snapshot_date not in snapshot_dates:
            raise HTTPException(status_code=404, detail=f"未找到 {snapshot_date.isoformat()} 的货品表快照")
        total = int(connection.execute(count_statement).scalar() or 0)
        rows = connection.execute(statement).mappings().all()
        product_codes = sorted({str(row.get("sku") or "").strip() for row in rows if str(row.get("sku") or "").strip()})
        if snapshot_date is None:
            full_stocks = _current_full_stock_payload(connection, product_codes)
            fallback_product_codes = [code for code in product_codes if code not in full_stocks]
            size_stocks = _size_stock_payload(connection, fallback_product_codes)
            summary_table = JST_STOCK_SUMMARY_TABLE
            summary_filter = summary_table.c.product_code.in_(product_codes)
        else:
            full_stocks = {}
            size_stocks = _size_stock_payload(connection, product_codes, snapshot_date=snapshot_date)
            summary_table = JST_STOCK_SUMMARY_SNAPSHOT_TABLE
            summary_filter = (summary_table.c.product_code.in_(product_codes)) & (summary_table.c.snapshot_date == snapshot_date)
        summaries = {
            str(row["product_code"]): dict(row)
            for row in connection.execute(
                select(summary_table).where(summary_filter)
            ).mappings()
        } if product_codes else {}
        product_sales_codes = {
            str(row.get("sku") or "").strip(): str(row.get("original_sku") or "").strip()
            for row in rows
            if str(row.get("sku") or "").strip()
        }
        detail_snapshots = _detail_snapshot_payload(
            connection,
            product_codes,
            brand=brand,
            snapshot_date=snapshot_date,
        )
        daily_dates, daily_sales, platform_sales, sales_by_size, sales_summary = _sales_matrix_payload(
            connection,
            repository.engine,
            product_sales_codes,
            brand=brand,
            as_of_date=snapshot_date,
        )
        historical_order_counts = _historical_order_counts(connection, product_sales_codes, brand=brand)
        annual_sales_columns, monthly_sales_columns, annual_sales, monthly_sales = _sales_period_payload(
            connection,
            repository.engine,
            product_sales_codes,
            brand=brand,
            as_of_date=snapshot_date,
        )
        supplier_names = sorted({str(row.get("supplier_name") or "").strip() for row in rows if str(row.get("supplier_name") or "").strip()})
        supplier_codes = {
            str(row["name"]): row["factory_code"]
            for row in connection.execute(
                select(SUPPLIER_TABLE.c.name, SUPPLIER_TABLE.c.factory_code).where(SUPPLIER_TABLE.c.name.in_(supplier_names))
            ).mappings()
        } if supplier_names else {}

    if detail_snapshots:
        daily_dates = sorted({
            day
            for snapshot in detail_snapshots.values()
            for day in (snapshot.get("daily_sales_by_date") or {})
            if isinstance(day, str)
        })
        annual_sales_columns = sorted({
            period
            for snapshot in detail_snapshots.values()
            for period in (snapshot.get("annual_sales") or {})
            if isinstance(period, str)
        })
        monthly_sales_columns = sorted(
            {
                period
                for snapshot in detail_snapshots.values()
                for period in (snapshot.get("monthly_sales") or {})
                if isinstance(period, str)
            },
            key=lambda value: tuple(int(item) for item in value.split("-", 1)),
        )

    items: list[dict[str, Any]] = []
    for row in rows:
        sku = str(row.get("sku") or "").strip()
        detail_snapshot = detail_snapshots.get(sku, {})
        snapshot_metrics = detail_snapshot.get("metrics") if isinstance(detail_snapshot.get("metrics"), dict) else {}
        full_stock = full_stocks.get(sku)
        stock_by_size = dict(detail_snapshot.get("stock_by_size") or (full_stock["stock_by_size"] if full_stock else size_stocks.get(sku, {})))
        in_transit_by_size = dict(detail_snapshot.get("in_transit_by_size") or (full_stock["in_transit_by_size"] if full_stock else {}))
        shortage_by_size = dict(detail_snapshot.get("shortage_by_size") or (full_stock["shortage_by_size"] if full_stock else {}))
        shortage_total = int(full_stock["shortage_total"]) if full_stock else 0
        stock_total = int(_snapshot_value(snapshot_metrics, "stock_total", full_stock["stock_total"] if full_stock else sum(stock_by_size.values())) or 0)
        summary = summaries.get(sku, {})
        in_transit_total = int(_snapshot_value(snapshot_metrics, "in_transit_total", full_stock["in_transit_total"] if full_stock else int(summary.get("purchase_in_transit_qty") or 0)) or 0)
        inventory_by_size = dict(detail_snapshot.get("inventory_by_size") or {
            size: int(stock_by_size.get(size, 0)) + int(in_transit_by_size.get(size, 0))
            for size in sorted(set(stock_by_size) | set(in_transit_by_size), key=lambda value: int(value))
        })
        inventory_total = int(_snapshot_value(snapshot_metrics, "inventory_total", stock_total + in_transit_total) or 0)
        sales = sales_summary.get(sku, {})
        extra_fields = row.get("extra_fields") if isinstance(row.get("extra_fields"), dict) else {}
        replenishment_by_size = dict(detail_snapshot.get("replenishment_by_size") or _manual_size_quantities(extra_fields.get("replenishment_by_size")))
        post_replenishment_by_size = dict(detail_snapshot.get("post_replenishment_by_size") or _manual_size_quantities(extra_fields.get("post_replenishment_by_size")))
        yesterday_sales = int(sales.get("yesterday_sales") or 0)
        previous_day_sales = int(sales.get("previous_day_sales") or 0)
        total_order_count = historical_order_counts.get(sku, sales.get("total_order_count"))
        metrics = {
            "total_order_count": total_order_count,
            "total_sales": sales.get("total_sales"),
            "stock_plus_purchase": stock_total,
            "in_transit_total": in_transit_total,
            "return_qty": sales.get("return_qty"),
            "post_replenishment_stock": _manual_number(extra_fields.get("post_replenishment_stock")),
            "post_replenishment_turnover_days": _manual_number(extra_fields.get("post_replenishment_turnover_days")),
            "day_over_day": yesterday_sales - previous_day_sales,
            "yesterday_sales": yesterday_sales,
            "normal_shelf_sales": sales.get("normal_shelf_sales", 0),
            "clearance_sales": sales.get("clearance_sales", 0),
            "week_sales": sales.get("week_sales", 0),
            "normal_shelf_week_sales": sales.get("normal_shelf_week_sales", 0),
            "clearance_week_sales": sales.get("clearance_week_sales", 0),
            "last_week_sales": sales.get("last_week_sales"),
            "same_week_sales": None,
            "same_week_non_douyin_sales": None,
            "shortage_total": shortage_total,
            "stock_health": _stock_health_label(full_stock["stock_sale_days"], shortage_total) if full_stock else None,
            "broken_size_sku": None,
            "sales_size_total": sum(sales_by_size.get(sku, {}).values()) if sales_by_size.get(sku) else None,
            "replenishment_total": _manual_number(extra_fields.get("replenishment_total")),
            "post_replenishment_total": _manual_number(extra_fields.get("post_replenishment_total")),
            "three_day_change": None,
            "sales_2024": sales.get("sales_2024"),
            "sales_2025": sales.get("sales_2025"),
            "year_sales": sales.get("year_sales"),
            "month_sales": sales.get("month_sales"),
        }
        metrics.update(snapshot_metrics)
        items.append({
            "id": row["id"], "brand": brand, "year": detail_snapshot.get("year") or row.get("year"), "season": detail_snapshot.get("season") or row.get("season_category"),
            "platform": detail_snapshot.get("platform") or row.get("platform"), "category_l4": detail_snapshot.get("category_l4") or row.get("category_l4"),
            "first_order_date": detail_snapshot.get("first_order_date") or row.get("first_order_time"), "factory_sku": detail_snapshot.get("factory_sku") or row.get("factory_sku"),
            "factory_code": detail_snapshot.get("factory_code") or supplier_codes.get(str(row.get("supplier_name") or "").strip()), "factory_name": detail_snapshot.get("factory_name") or row.get("supplier_name"), "style_code": detail_snapshot.get("style_code") or row.get("original_sku"), "goods_code": row.get("sku"),
            "color": detail_snapshot.get("color") or row.get("color"), "image_url": image_url_for(brand, row.get("image_path"), settings),
            "cost": detail_snapshot.get("cost") or (str(row["cost"]) if row.get("cost") is not None else None),
            "product_role": detail_snapshot.get("product_role") or row.get("product_role"), "product_type": detail_snapshot.get("product_type") or row.get("product_type"),
            "douyin_hot": detail_snapshot.get("douyin_hot") or row.get("douyin_hot"), "clearance": detail_snapshot.get("clearance") or row.get("clearance"), "remark": detail_snapshot.get("remark") or row.get("remark"),
            "stock_by_size": stock_by_size, "stock_total": stock_total,
            "in_transit_total": in_transit_total,
            "inventory_total": inventory_total,
            "daily_sales_by_date": detail_snapshot.get("daily_sales_by_date") or daily_sales.get(sku, {}),
            "annual_sales": detail_snapshot.get("annual_sales") or annual_sales.get(sku, {}),
            "monthly_sales": detail_snapshot.get("monthly_sales") or monthly_sales.get(sku, {}),
            "platform_sales": platform_sales.get(sku, {}),
            "daily_platform_sales": detail_snapshot.get("daily_platform_sales") or platform_sales.get(sku, {}).get("daily", {}),
            "weekly_platform_sales": detail_snapshot.get("weekly_platform_sales") or platform_sales.get(sku, {}).get("weekly", {}),
            "monthly_platform_sales": detail_snapshot.get("monthly_platform_sales") or platform_sales.get(sku, {}).get("monthly", {}),
            "in_transit_by_size": in_transit_by_size, "inventory_by_size": inventory_by_size, "shortage_by_size": shortage_by_size,
            "sales_by_size": sales_by_size.get(sku, {}), "replenishment_by_size": replenishment_by_size, "post_replenishment_by_size": post_replenishment_by_size,
            "metrics": metrics,
        })
    payload = {
        "items": items,
        "total": total,
        "page": page,
        "page_size": page_size,
        "daily_dates": daily_dates,
        "annual_sales_columns": annual_sales_columns,
        "monthly_sales_columns": monthly_sales_columns,
        "size_columns": SIZE_COLUMNS,
        "platform_columns": PLATFORM_COLUMNS,
        "snapshot_date": snapshot_date.isoformat() if snapshot_date else None,
        "snapshot_dates": [item.isoformat() for item in snapshot_dates],
    }
    set_product_goods_cache(cache_key, payload)
    return payload


@router.patch("/product-goods/{product_id}")
def update_product_goods(request: Request, product_id: int, body: ProductGoodsUpdateRequest, brand: str = Query(DEFAULT_BRAND)):
    if brand not in PRODUCT_TABLES:
        raise HTTPException(status_code=400, detail=f"Invalid brand: {brand}")
    repository = request.app.state.repository
    product_table = PRODUCT_TABLES[brand]
    with repository.engine.begin() as connection:
        exists = connection.execute(select(product_table.c.id).where(product_table.c.id == product_id)).scalar_one_or_none()
        if exists is None:
            raise HTTPException(status_code=404, detail="Product not found")
        standard_values = {
            field: getattr(body, field)
            for field in PRODUCT_GOODS_STANDARD_OVERRIDE_FIELDS
            if field in body.model_fields_set
        }
        manual_replenishment_fields = PRODUCT_GOODS_REPLENISHMENT_FIELDS.intersection(body.model_fields_set)
        if not standard_values and not manual_replenishment_fields:
            raise HTTPException(status_code=400, detail="No fields to update")
        existing_extra_fields = connection.execute(
            select(PRODUCT_GOODS_OVERRIDES_TABLE.c.extra_fields).where(
                (PRODUCT_GOODS_OVERRIDES_TABLE.c.brand == brand)
                & (PRODUCT_GOODS_OVERRIDES_TABLE.c.product_id == product_id)
            )
        ).scalar_one_or_none()
        extra_fields = dict(existing_extra_fields) if isinstance(existing_extra_fields, dict) else {}
        for field in manual_replenishment_fields:
            field_value = getattr(body, field)
            if field_value is None:
                extra_fields.pop(field, None)
            else:
                extra_fields[field] = field_value
        values = {"brand": brand, "product_id": product_id, **standard_values}
        if manual_replenishment_fields:
            values["extra_fields"] = extra_fields or None
        update_values = dict(standard_values)
        if manual_replenishment_fields:
            update_values["extra_fields"] = values["extra_fields"]
        statement = pg_insert(PRODUCT_GOODS_OVERRIDES_TABLE).values(**values).on_conflict_do_update(
            index_elements=["brand", "product_id"],
            set_=update_values,
        )
        connection.execute(statement)
    clear_product_goods_cache()
    from api.operation_log_utils import write_operation_log

    write_operation_log(
        request,
        module="product_goods",
        action="update",
        entity_type="product_goods",
        entity_id=product_id,
        entity_label=str(product_id),
        summary="编辑商品货品表运营字段",
        after_data={
            "brand": brand,
            **standard_values,
            **{field: getattr(body, field) for field in manual_replenishment_fields},
        },
    )
    return {"message": "Product goods fields updated"}
