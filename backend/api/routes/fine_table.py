from __future__ import annotations

from datetime import date, datetime, time, timedelta
from decimal import Decimal
from typing import Any

from fastapi import APIRouter, Query, Request
from sqlalchemy import and_, desc, func, or_, select

from api.fine_table_cache import get_fine_table_cache, set_fine_table_cache
from api.routes.images import image_url_for
from domain.gj_schema import GJ_MERGED_PRODUCT_INFO_TABLE
from domain.schema import PRODUCT_TABLES
from domain.vip_schema import (
    JST_PRICE_TABLE,
    JST_PURCHASE_DIFF_TABLE,
    JST_STOCK_SUMMARY_TABLE,
    JST_SIZE_STOCK_TABLE,
    VIP_DAILY_SNAPSHOT_TABLE,
    VIP_DAILY_TABLE,
    VIP_OPS_TABLE,
    JST_MONTHLY_ORDERS_TABLE,
)


router = APIRouter()

BRAND = "cbanner_womens"
SIZE_LABELS = {
    "220": "34/220",
    "225": "35/225",
    "230": "36/230",
    "235": "37/235",
    "240": "38/240",
    "245": "39/245",
    "250": "40/250",
    "255": "41/255",
    "260": "42/260",
    "265": "43/265",
    "270": "44/270",
    "275": "45/275",
    "280": "46/280",
    "285": "47/285",
}

EXCLUDED_OTHER_PLATFORM_ORDER_STATUSES = {"取消", "异常", "被拆分", "已付款待审核"}
DAILY_SALES_DAYS = 5


def _to_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    if isinstance(value, Decimal):
        return float(value)
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _metric_to_float(value: Any) -> float | None:
    if isinstance(value, str):
        value = value.strip()
        if value.endswith("%"):
            value = value[:-1]
    return _to_float(value)


def _to_int(value: Any) -> int:
    if value is None or value == "":
        return 0
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return 0


def _price_band(price: float | None) -> str | None:
    if price is None:
        return None
    if price < 251:
        return "0-250"
    if price < 301:
        return "251-300"
    if price < 351:
        return "301-350"
    if price < 401:
        return "351-400"
    if price < 451:
        return "401-450"
    if price <= 500:
        return "451-500"
    return "500以上"


def _status_key(status: str | None) -> str:
    if not status:
        return "unknown"
    if "下线" in status or "下架" in status:
        return "offline"
    if "部分" in status:
        return "partial"
    if "上线" in status:
        return "online"
    return "unknown"


def _period_key(report_type: str | None, period: str | None) -> tuple[str, str]:
    return (str(report_type or ""), str(period or ""))


def _daily_metric(daily: dict[tuple[str, str], dict[str, Any]], period: str, field: str) -> Any:
    for report_type in ("罗盘", "环比"):
        row = daily.get((report_type, period))
        if row is not None:
            return row.get(field)
    return None


def _daily_report_metric(daily: dict[tuple[str, str], dict[str, Any]], report_type: str, period: str, field: str) -> Any:
    row = daily.get((report_type, period))
    if row is None:
        return None
    return row.get(field)


def _compass_metric(daily: dict[tuple[str, str], dict[str, Any]], field: str) -> Any:
    for period in ("1d", "3d", "7d", "30d"):
        value = _daily_report_metric(daily, "罗盘", period, field)
        if value not in (None, ""):
            return value
    return None


def _change_rate(current: Any, baseline: Any) -> float | None:
    current_value = _metric_to_float(current)
    baseline_value = _metric_to_float(baseline)
    if current_value is None or baseline_value in (None, 0):
        return None
    return (current_value - baseline_value) / baseline_value


def _date_window(max_day: date, days: int) -> tuple[datetime, datetime]:
    start = datetime.combine(max_day - timedelta(days=days - 1), time.min)
    end = datetime.combine(max_day + timedelta(days=1), time.min)
    return start, end


def _empty_order_bucket() -> dict[str, Any]:
    return {
        "other_3": 0,
        "other_7": 0,
        "other_15": 0,
        "other_30": 0,
        "shop_30": {},
        "daily_sales": [],
    }


@router.get("/fine-table")
def list_fine_table(
    request: Request,
    query: str | None = None,
    season: str | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(80, ge=1, le=200),
):
    settings = request.app.state.settings
    repository = request.app.state.repository
    product_table = PRODUCT_TABLES[BRAND]
    normalized_query = ",".join(
        term.strip()
        for term in (query or "").replace("\n", ",").split(",")
        if term.strip()
    )
    normalized_season = season if season and season != "all" else "all"
    cache_key = (normalized_query, normalized_season, page, page_size)
    cached = get_fine_table_cache(cache_key)
    if cached is not None:
        return cached

    conditions = []
    if normalized_query:
        terms = normalized_query.split(",")
        if terms:
            search_conditions = []
            for term in terms:
                like = f"%{term}%"
                search_conditions.extend([
                    product_table.c.sku.ilike(like),
                    product_table.c.original_sku.ilike(like),
                    product_table.c.factory_sku.ilike(like),
                ])
            conditions.append(or_(*search_conditions))
    if normalized_season != "all":
        conditions.append(product_table.c.season_category == normalized_season)

    count_stmt = select(func.count()).select_from(product_table)
    items_stmt = (
        select(product_table)
        .order_by(desc(product_table.c.id))
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    if conditions:
        criterion = and_(*conditions)
        count_stmt = count_stmt.where(criterion)
        items_stmt = items_stmt.where(criterion)

    with repository.engine.connect() as conn:
        total = conn.execute(count_stmt).scalar_one()
        product_rows = [dict(row) for row in conn.execute(items_stmt).mappings()]

        skus = [str(row.get("sku") or "").strip() for row in product_rows if row.get("sku")]
        if not skus:
            payload = {"items": [], "total": total, "page": page, "page_size": page_size}
            set_fine_table_cache(cache_key, payload)
            return payload
        original_skus = {
            str(row.get("original_sku") or "").strip()
            for row in product_rows
            if str(row.get("original_sku") or "").strip()
        }
        original_skus_by_code: dict[str, list[str]] = {original_sku: [] for original_sku in original_skus}
        for row in product_rows:
            sku = str(row.get("sku") or "").strip()
            original_sku = str(row.get("original_sku") or "").strip()
            if sku and original_sku:
                original_skus_by_code.setdefault(original_sku, []).append(sku)

        if original_skus:
            for row in conn.execute(
                select(product_table.c.sku, product_table.c.original_sku)
                .where(product_table.c.original_sku.in_(original_skus))
            ).mappings():
                sku = str(row.get("sku") or "").strip()
                original_sku = str(row.get("original_sku") or "").strip()
                if sku and original_sku:
                    original_skus_by_code.setdefault(original_sku, []).append(sku)

        original_sku_by_sku: dict[str, str] = {}
        all_original_group_skus: set[str] = set()
        for original_sku, grouped_skus in original_skus_by_code.items():
            deduped = sorted(set(grouped_skus))
            original_skus_by_code[original_sku] = deduped
            all_original_group_skus.update(deduped)
            for grouped_sku in deduped:
                original_sku_by_sku[grouped_sku] = original_sku

        ops_by_sku: dict[str, dict[str, Any]] = {}
        for row in conn.execute(
            select(VIP_OPS_TABLE)
            .where(VIP_OPS_TABLE.c.goods_code.in_(skus))
            .order_by(desc(VIP_OPS_TABLE.c.updated_at), desc(VIP_OPS_TABLE.c.id))
        ).mappings():
            ops_by_sku.setdefault(str(row["goods_code"]), dict(row))

        price_by_sku: dict[str, dict[str, Any]] = {}
        for row in conn.execute(
            select(JST_PRICE_TABLE)
            .where(JST_PRICE_TABLE.c.goods_code.in_(skus))
            .order_by(desc(JST_PRICE_TABLE.c.updated_at), desc(JST_PRICE_TABLE.c.id))
        ).mappings():
            price_by_sku.setdefault(str(row["goods_code"]), dict(row))

        daily_by_sku: dict[str, dict[tuple[str, str], dict[str, Any]]] = {sku: {} for sku in skus}
        for row in conn.execute(
            select(VIP_DAILY_TABLE)
            .where(VIP_DAILY_TABLE.c.goods_code.in_(skus))
            .order_by(desc(VIP_DAILY_TABLE.c.report_end_date), desc(VIP_DAILY_TABLE.c.updated_at), desc(VIP_DAILY_TABLE.c.id))
        ).mappings():
            sku = str(row["goods_code"])
            key = _period_key(row.get("report_type"), row.get("period"))
            daily_by_sku.setdefault(sku, {}).setdefault(key, dict(row))

        size_stock_by_sku: dict[str, dict[str, int]] = {sku: {} for sku in skus}
        for row in conn.execute(
            select(JST_SIZE_STOCK_TABLE.c.product_code, JST_SIZE_STOCK_TABLE.c.size, func.sum(JST_SIZE_STOCK_TABLE.c.stock_qty).label("qty"))
            .where(JST_SIZE_STOCK_TABLE.c.product_code.in_(skus))
            .group_by(JST_SIZE_STOCK_TABLE.c.product_code, JST_SIZE_STOCK_TABLE.c.size)
        ).mappings():
            sku = str(row["product_code"])
            size = str(row["size"])
            label = SIZE_LABELS.get(size, size)
            size_stock_by_sku.setdefault(sku, {})[label] = _to_int(row["qty"])

        stock_codes = sorted({*skus, *all_original_group_skus})
        stock_summary_by_sku: dict[str, dict[str, int]] = {}
        for row in conn.execute(
            select(
                JST_STOCK_SUMMARY_TABLE.c.product_code,
                func.sum(JST_STOCK_SUMMARY_TABLE.c.defect_stock_qty).label("defect_stock_qty"),
                func.sum(JST_STOCK_SUMMARY_TABLE.c.purchase_in_transit_qty).label("purchase_in_transit_qty"),
                func.sum(JST_STOCK_SUMMARY_TABLE.c.off_shelf_qty).label("off_shelf_qty"),
                func.sum(JST_STOCK_SUMMARY_TABLE.c.order_occupy_qty).label("order_occupy_qty"),
            )
            .where(JST_STOCK_SUMMARY_TABLE.c.product_code.in_(stock_codes))
            .group_by(JST_STOCK_SUMMARY_TABLE.c.product_code)
        ).mappings():
            stock_summary_by_sku[str(row["product_code"])] = {
                "defect_stock_qty": _to_int(row["defect_stock_qty"]),
                "purchase_in_transit_qty": _to_int(row["purchase_in_transit_qty"]),
                "off_shelf_qty": _to_int(row["off_shelf_qty"]),
                "order_occupy_qty": _to_int(row["order_occupy_qty"]),
            }

        defect_in_transit_by_sku: dict[str, int] = {}
        for row in conn.execute(
            select(JST_PURCHASE_DIFF_TABLE.c.product_code, func.sum(JST_PURCHASE_DIFF_TABLE.c.difference_count).label("qty"))
            .where(JST_PURCHASE_DIFF_TABLE.c.product_code.in_(stock_codes))
            .group_by(JST_PURCHASE_DIFF_TABLE.c.product_code)
        ).mappings():
            defect_in_transit_by_sku[str(row["product_code"])] = _to_int(row["qty"])

        latest_gj_product_info_date = conn.execute(
            select(func.max(GJ_MERGED_PRODUCT_INFO_TABLE.c.source_date_value))
            .where(GJ_MERGED_PRODUCT_INFO_TABLE.c.goods_code.in_(skus))
        ).scalar()
        gj_info_by_sku: dict[str, dict[str, Any]] = {}
        if latest_gj_product_info_date is not None:
            for row in conn.execute(
                select(
                    GJ_MERGED_PRODUCT_INFO_TABLE.c.goods_code,
                    GJ_MERGED_PRODUCT_INFO_TABLE.c.product_name,
                    GJ_MERGED_PRODUCT_INFO_TABLE.c.upper_material,
                    GJ_MERGED_PRODUCT_INFO_TABLE.c.lining_material,
                    GJ_MERGED_PRODUCT_INFO_TABLE.c.outsole_material,
                    GJ_MERGED_PRODUCT_INFO_TABLE.c.insole_material,
                )
                .where(GJ_MERGED_PRODUCT_INFO_TABLE.c.goods_code.in_(skus))
                .where(GJ_MERGED_PRODUCT_INFO_TABLE.c.source_date_value == latest_gj_product_info_date)
                .order_by(desc(GJ_MERGED_PRODUCT_INFO_TABLE.c.updated_at), desc(GJ_MERGED_PRODUCT_INFO_TABLE.c.id))
            ).mappings():
                sku = str(row["goods_code"] or "").strip()
                if sku:
                    gj_info_by_sku.setdefault(
                        sku,
                        {
                            "product_name": str(row["product_name"] or "").strip() or None,
                            "upper_material": str(row["upper_material"] or "").strip() or None,
                            "lining_material": str(row["lining_material"] or "").strip() or None,
                            "outsole_material": str(row["outsole_material"] or "").strip() or None,
                            "insole_material": str(row["insole_material"] or "").strip() or None,
                        },
                    )

        original_stock_summary_by_code: dict[str, dict[str, int]] = {}
        original_defect_in_transit_by_code: dict[str, int] = {}
        for original_sku, grouped_skus in original_skus_by_code.items():
            summary = {
                "defect_stock_qty": 0,
                "purchase_in_transit_qty": 0,
                "order_occupy_qty": 0,
            }
            defect_in_transit_total = 0
            for grouped_sku in grouped_skus:
                stock_summary = stock_summary_by_sku.get(grouped_sku, {})
                summary["defect_stock_qty"] += stock_summary.get("defect_stock_qty", 0)
                summary["purchase_in_transit_qty"] += stock_summary.get("purchase_in_transit_qty", 0)
                summary["order_occupy_qty"] += stock_summary.get("order_occupy_qty", 0)
                defect_in_transit_total += defect_in_transit_by_sku.get(grouped_sku, 0)
            original_stock_summary_by_code[original_sku] = summary
            original_defect_in_transit_by_code[original_sku] = defect_in_transit_total

        latest_daily_snapshot_day = conn.execute(
            select(func.max(VIP_DAILY_SNAPSHOT_TABLE.c.snapshot_date))
            .where(VIP_DAILY_SNAPSHOT_TABLE.c.goods_code.in_(skus))
            .where(VIP_DAILY_SNAPSHOT_TABLE.c.report_type == "罗盘")
            .where(VIP_DAILY_SNAPSHOT_TABLE.c.period == "1d")
        ).scalar()
        daily_snapshot_totals: dict[str, dict[date, dict[str, int]]] = {sku: {} for sku in skus}
        if isinstance(latest_daily_snapshot_day, date):
            daily_snapshot_start = latest_daily_snapshot_day - timedelta(days=DAILY_SALES_DAYS - 1)
            for row in conn.execute(
                select(
                    VIP_DAILY_SNAPSHOT_TABLE.c.goods_code,
                    VIP_DAILY_SNAPSHOT_TABLE.c.snapshot_date,
                    func.sum(VIP_DAILY_SNAPSHOT_TABLE.c.sales_volume).label("qty"),
                    func.sum(VIP_DAILY_SNAPSHOT_TABLE.c.detail_uv).label("uv"),
                )
                .where(VIP_DAILY_SNAPSHOT_TABLE.c.goods_code.in_(skus))
                .where(VIP_DAILY_SNAPSHOT_TABLE.c.report_type == "罗盘")
                .where(VIP_DAILY_SNAPSHOT_TABLE.c.period == "1d")
                .where(VIP_DAILY_SNAPSHOT_TABLE.c.snapshot_date >= daily_snapshot_start)
                .where(VIP_DAILY_SNAPSHOT_TABLE.c.snapshot_date <= latest_daily_snapshot_day)
                .group_by(VIP_DAILY_SNAPSHOT_TABLE.c.goods_code, VIP_DAILY_SNAPSHOT_TABLE.c.snapshot_date)
            ).mappings():
                sku = str(row["goods_code"] or "").strip()
                snapshot_date = row["snapshot_date"]
                if sku and isinstance(snapshot_date, date):
                    daily_snapshot_totals.setdefault(sku, {})[snapshot_date] = {
                        "quantity": _to_int(row["qty"]),
                        "uv": _to_int(row["uv"]),
                    }

        max_order_day = conn.execute(select(func.max(JST_MONTHLY_ORDERS_TABLE.c.order_time_at))).scalar()
        max_day = max_order_day.date() if isinstance(max_order_day, datetime) else date.today()
        start_3, end_window = _date_window(max_day, 3)
        start_7, _ = _date_window(max_day, 7)
        start_15, _ = _date_window(max_day, 15)
        start_30, _ = _date_window(max_day, 30)

        orders_by_sku: dict[str, dict[str, Any]] = {sku: _empty_order_bucket() for sku in skus}
        original_orders_by_sku: dict[str, dict[str, Any]] = {sku: _empty_order_bucket() for sku in skus}
        original_orders_by_code: dict[str, dict[str, Any]] = {
            original_sku: _empty_order_bucket()
            for original_sku in original_skus_by_code
        }
        order_codes = sorted({*skus, *all_original_group_skus})
        order_rows = conn.execute(
            select(
                JST_MONTHLY_ORDERS_TABLE.c.style_code,
                JST_MONTHLY_ORDERS_TABLE.c.shop_name,
                JST_MONTHLY_ORDERS_TABLE.c.status,
                JST_MONTHLY_ORDERS_TABLE.c.order_time_at,
                JST_MONTHLY_ORDERS_TABLE.c.quantity,
            )
            .where(JST_MONTHLY_ORDERS_TABLE.c.style_code.in_(order_codes))
            .where(JST_MONTHLY_ORDERS_TABLE.c.order_time_at >= start_30)
            .where(JST_MONTHLY_ORDERS_TABLE.c.order_time_at < end_window)
        ).mappings()

        for row in order_rows:
            order_code = str(row["style_code"] or "").strip()
            order_time = row["order_time_at"]
            if not order_code or not isinstance(order_time, datetime):
                continue
            qty = _to_int(row["quantity"])
            shop_name = str(row.get("shop_name") or "")
            status = str(row.get("status") or "").strip()
            is_vip_shop = "唯品" in shop_name
            bucket = orders_by_sku.get(order_code)

            if not is_vip_shop and status not in EXCLUDED_OTHER_PLATFORM_ORDER_STATUSES:
                buckets = []
                if bucket is not None:
                    buckets.append(bucket)
                original_sku = original_sku_by_sku.get(order_code)
                if original_sku and original_sku in original_orders_by_code:
                    buckets.append(original_orders_by_code[original_sku])
                for target_bucket in buckets:
                    if order_time >= start_3:
                        target_bucket["other_3"] += qty
                    if order_time >= start_7:
                        target_bucket["other_7"] += qty
                    if order_time >= start_15:
                        target_bucket["other_15"] += qty
                    target_bucket["other_30"] += qty
                if bucket is not None:
                    shop_bucket = bucket["shop_30"]
                    shop_bucket[shop_name] = shop_bucket.get(shop_name, 0) + qty

        if isinstance(latest_daily_snapshot_day, date):
            for sku, totals in daily_snapshot_totals.items():
                orders_by_sku[sku]["daily_sales"] = [
                    {
                        "date": (latest_daily_snapshot_day - timedelta(days=offset)).isoformat(),
                        "quantity": totals.get(latest_daily_snapshot_day - timedelta(days=offset), {}).get("quantity", 0),
                        "uv": totals.get(latest_daily_snapshot_day - timedelta(days=offset), {}).get("uv", 0),
                    }
                    for offset in range(DAILY_SALES_DAYS - 1, -1, -1)
                ]

    items = []
    for product in product_rows:
        sku = str(product.get("sku") or "").strip()
        ops = ops_by_sku.get(sku, {})
        price = price_by_sku.get(sku, {})
        daily = daily_by_sku.get(sku, {})
        gj_info = gj_info_by_sku.get(sku, {})
        orders = orders_by_sku.get(sku, {})
        original_sku = str(product.get("original_sku") or "").strip()
        original_orders = original_orders_by_code.get(original_sku, {})
        size_stock = {label: size_stock_by_sku.get(sku, {}).get(label, 0) for label in SIZE_LABELS.values()}

        stock_qty = sum(size_stock.values())
        stock_summary = stock_summary_by_sku.get(sku, {})
        inbound_qty = stock_summary.get("purchase_in_transit_qty", 0)
        defect_in_transit_qty = defect_in_transit_by_sku.get(sku, 0)
        original_stock_summary = original_stock_summary_by_code.get(original_sku, {})
        original_inbound_qty = original_stock_summary.get("purchase_in_transit_qty", 0)
        original_defect_in_transit_qty = original_defect_in_transit_by_code.get(original_sku, 0)
        cost = (
            _to_float(price.get("latest_purchase_price"))
            or _to_float(price.get("preset_price"))
            or _to_float(price.get("cost_unit_price"))
            or _to_float(product.get("cost"))
        )
        final_price = _to_float(ops.get("final_price"))
        market_price = _to_float(ops.get("market_price"))
        vip_price = _to_float(ops.get("vip_price"))
        vip_3 = _to_int(_daily_metric(daily, "3d", "sales_volume"))
        vip_7 = _to_int(_daily_metric(daily, "7d", "sales_volume"))
        vip_15 = _to_int(_daily_metric(daily, "15d", "sales_volume"))
        vip_30 = _to_int(_daily_metric(daily, "30d", "sales_volume"))
        vip_3d_sales_change_rate = _change_rate(
            _daily_report_metric(daily, "罗盘", "3d", "sales_volume"),
            _daily_report_metric(daily, "环比", "3d", "sales_volume"),
        )
        vip_3d_uv_change_rate = _change_rate(
            _daily_report_metric(daily, "罗盘", "3d", "detail_uv"),
            _daily_report_metric(daily, "环比", "3d", "detail_uv"),
        )
        vip_3d_ctr_change_rate = _change_rate(
            _daily_report_metric(daily, "罗盘", "3d", "ctr"),
            _daily_report_metric(daily, "环比", "3d", "ctr"),
        )
        vip_3d_conversion_change_rate = _change_rate(
            _daily_report_metric(daily, "罗盘", "3d", "purchase_conversion"),
            _daily_report_metric(daily, "环比", "3d", "purchase_conversion"),
        )
        vip_7d_sales_change_rate = _change_rate(
            _daily_report_metric(daily, "罗盘", "7d", "sales_volume"),
            _daily_report_metric(daily, "环比", "7d", "sales_volume"),
        )
        vip_7d_uv_change_rate = _change_rate(
            _daily_report_metric(daily, "罗盘", "7d", "detail_uv"),
            _daily_report_metric(daily, "环比", "7d", "detail_uv"),
        )
        vip_7d_ctr_change_rate = _change_rate(
            _daily_report_metric(daily, "罗盘", "7d", "ctr"),
            _daily_report_metric(daily, "环比", "7d", "ctr"),
        )
        vip_7d_conversion_change_rate = _change_rate(
            _daily_report_metric(daily, "罗盘", "7d", "purchase_conversion"),
            _daily_report_metric(daily, "环比", "7d", "purchase_conversion"),
        )
        other_30 = _to_int(orders.get("other_30"))
        vip_daily_average = vip_3 / 3 if vip_3 else 0
        daily_average = vip_daily_average
        projected_15 = stock_qty + inbound_qty - round(daily_average * 15)

        activity_profit = None
        margin_rate = None
        if final_price and cost:
            activity_profit = final_price * 0.76 * 0.86 - 20 - cost - final_price * 0.15
            margin_rate = activity_profit / final_price

        items.append({
            **product,
            "brand": BRAND,
            "image_url": image_url_for(BRAND, product.get("image_path"), settings),
            "product_name": gj_info.get("product_name"),
            "upper_material": gj_info.get("upper_material") or product.get("upper_material"),
            "lining_material": gj_info.get("lining_material") or product.get("lining_material"),
            "outsole_material": gj_info.get("outsole_material") or product.get("outsole_material"),
            "insole_material": gj_info.get("insole_material") or product.get("insole_material"),
            "main_style": _compass_metric(daily, "main_style"),
            "goods_id": ops.get("goods_id"),
            "p_spu": ops.get("p_spu"),
            "style_code": ops.get("style_code"),
            "category_l3": ops.get("category_l3"),
            "goods_status": ops.get("goods_status"),
            "status_key": _status_key(ops.get("goods_status")),
            "sales_tag": ops.get("sales_tag"),
            "goods_tag": ops.get("goods_tag"),
            "latest_purchase_price": cost,
            "final_price": final_price,
            "vip_price": vip_price,
            "market_price": market_price,
            "price_band": _price_band(final_price),
            "activity_profit": activity_profit,
            "margin_rate": margin_rate,
            "discount_rate": final_price / market_price if final_price and market_price else None,
            "vip_1d_sales": _to_int(_daily_metric(daily, "1d", "sales_volume")),
            "vip_3d_sales": vip_3,
            "vip_7d_sales": vip_7,
            "vip_15d_sales": vip_15,
            "vip_30d_sales": vip_30,
            "vip_3d_uv": _to_int(_daily_metric(daily, "3d", "detail_uv")),
            "vip_7d_uv": _to_int(_daily_metric(daily, "7d", "detail_uv")),
            "vip_30d_uv": _to_int(_daily_metric(daily, "30d", "detail_uv")),
            "vip_3d_ctr": _daily_metric(daily, "3d", "ctr"),
            "vip_7d_ctr": _daily_metric(daily, "7d", "ctr"),
            "vip_30d_ctr": _daily_metric(daily, "30d", "ctr"),
            "vip_3d_conversion": _daily_metric(daily, "3d", "purchase_conversion"),
            "vip_7d_conversion": _daily_metric(daily, "7d", "purchase_conversion"),
            "vip_30d_conversion": _daily_metric(daily, "30d", "purchase_conversion"),
            "vip_3d_sales_change_rate": vip_3d_sales_change_rate,
            "vip_3d_uv_change_rate": vip_3d_uv_change_rate,
            "vip_3d_ctr_change_rate": vip_3d_ctr_change_rate,
            "vip_3d_conversion_change_rate": vip_3d_conversion_change_rate,
            "vip_7d_sales_change_rate": vip_7d_sales_change_rate,
            "vip_7d_uv_change_rate": vip_7d_uv_change_rate,
            "vip_7d_ctr_change_rate": vip_7d_ctr_change_rate,
            "vip_7d_conversion_change_rate": vip_7d_conversion_change_rate,
            "vip_30d_reject_count": _to_int(_daily_metric(daily, "30d", "reject_count")),
            "vip_30d_reject_rate": _daily_metric(daily, "30d", "reject_rate"),
            "vip_daily_average_sales": vip_daily_average,
            "other_3d_sales": _to_int(orders.get("other_3")),
            "other_7d_sales": _to_int(orders.get("other_7")),
            "other_15d_sales": _to_int(orders.get("other_15")),
            "other_30d_sales": other_30,
            "original_other_3d_sales": _to_int(original_orders.get("other_3")),
            "original_other_7d_sales": _to_int(original_orders.get("other_7")),
            "original_other_15d_sales": _to_int(original_orders.get("other_15")),
            "original_other_30d_sales": _to_int(original_orders.get("other_30")),
            "shop_30d_sales": [
                {"shop_name": name, "quantity": qty}
                for name, qty in sorted((orders.get("shop_30") or {}).items(), key=lambda item: item[1], reverse=True)
            ][:12],
            "stock_qty": stock_qty,
            "size_stock": size_stock,
            "inbound_qty": inbound_qty,
            "defect_stock": stock_summary.get("defect_stock_qty", 0),
            "original_defect_stock": original_stock_summary.get("defect_stock_qty", 0),
            "original_inbound_qty": original_inbound_qty,
            "original_order_in_transit_stock": original_inbound_qty - original_defect_in_transit_qty,
            "original_defect_in_transit_stock": original_defect_in_transit_qty,
            "off_shelf_stock": stock_summary.get("off_shelf_qty", 0),
            "order_occupy_stock": stock_summary.get("order_occupy_qty", 0),
            "defect_in_transit_stock": defect_in_transit_qty,
            "purchase_diff": defect_in_transit_qty,
            "projected_15d_stock": projected_15,
            "daily_sales": orders.get("daily_sales", []),
        })

    payload = {
        "items": items,
        "total": total,
        "page": page,
        "page_size": page_size,
        "latest_order_date": max_day.isoformat() if "max_day" in locals() else None,
    }
    set_fine_table_cache(cache_key, payload)
    return payload
