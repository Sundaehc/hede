from __future__ import annotations

from datetime import date, datetime, time, timedelta
from decimal import Decimal
import json
from math import ceil
import re
from typing import Any, Literal

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.encoders import jsonable_encoder
from pydantic import BaseModel
from sqlalchemy import Text, and_, cast, delete, desc, false, func, insert, or_, select, update

from api.fine_table_cache import get_fine_table_cache, set_fine_table_cache
from api.operation_log_utils import write_operation_log
from api.routes.images import image_url_for
from api.schemas import BrandKey
from domain.excluded_skus import is_excluded_sku, not_excluded_sku_condition
from domain.fields import PRODUCT_FIELDS
from domain.fine_table_snapshot_schema import (
    FINE_TABLE_SNAPSHOT_BATCH_TABLE,
    FINE_TABLE_SNAPSHOT_METRICS_TABLE,
    FINE_TABLE_SNAPSHOT_PAYLOADS_TABLE,
    ensure_fine_table_snapshot_row_table,
    ensure_fine_table_snapshot_ref_table,
    fine_table_snapshot_row_table_for_date,
    fine_table_snapshot_ref_table_for_date,
    fine_table_snapshot_ref_table_exists,
    fine_table_snapshot_year_table_exists,
)
from domain.gj_brand import CBANNER_MENS_BRAND, CBANNER_WOMENS_BRAND
from domain.gj_schema import GJ_MERGED_PRODUCT_INFO_TABLE
from domain.inventory_schema import SUPPLIER_TABLE
from domain.product_defaults import apply_product_defaults
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
from storage.fine_table_snapshot_dedup import (
    load_optimized_snapshot_rows,
    optimized_snapshot_available,
    write_optimized_snapshot_rows,
)


router = APIRouter()

DEFAULT_BRAND: BrandKey = "cbanner_mens"
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
SNAPSHOT_PAGE_SIZE = 200


class FineTableExportLogRequest(BaseModel):
    brand: BrandKey
    brand_label: str | None = None
    exported_rows: int = 0
    total_rows: int | None = None
    view: str | None = None
    query: str | None = None
    sku_prefix: str | None = None
    history_date: str | None = None
    column_mode: str | None = None
    column_count: int | None = None
    filename: str | None = None


FineTableFilterOperator = Literal["in", "not_in"]
FINE_TABLE_FILTER_FIELDS = {
    "sku",
    "original_sku",
    "status",
    "group_name",
    "product_level",
    "year",
    "season_category",
    "factory_code",
    "factory_name",
    "product_name",
    "main_style",
    "style_code",
    "goods_id",
    "p_spu",
    "category_l3",
    "factory_sku",
    "execution_standard",
    "upper_material",
    "lining_material",
    "outsole_material",
    "insole_material",
    "first_order_time",
    "sales_tag",
    "goods_tag",
    "cost",
    "final_price",
    "vip_price",
    "market_price",
    "price_band",
    "activity_profit",
    "margin_rate",
    "vip_1d_sales",
    "vip_3d_sales",
    "vip_7d_sales",
    "vip_15d_sales",
    "vip_30d_sales",
    "vip_daily_average_sales",
    "vip_projected_15d_sales",
    "other_3d_sales",
    "other_7d_sales",
    "other_15d_sales",
    "other_30d_sales",
    "other_daily_average_sales",
    "other_projected_15d_sales",
    "original_other_3d_sales",
    "original_other_7d_sales",
    "original_all_7d_sales",
    "original_other_15d_sales",
    "original_other_30d_sales",
    "vip_3d_uv",
    "vip_7d_uv",
    "vip_30d_uv",
    "vip_3d_ctr",
    "vip_7d_ctr",
    "vip_30d_ctr",
    "vip_3d_exposure",
    "vip_7d_exposure",
    "vip_30d_exposure",
    "vip_3d_conversion",
    "vip_7d_conversion",
    "vip_30d_conversion",
    "vip_3d_sales_change_rate",
    "vip_3d_uv_change_rate",
    "vip_3d_ctr_change_rate",
    "vip_3d_conversion_change_rate",
    "vip_7d_sales_change_rate",
    "vip_7d_uv_change_rate",
    "vip_7d_ctr_change_rate",
    "vip_7d_conversion_change_rate",
    "vip_30d_reject_count",
    "vip_30d_reject_rate",
    "stock_qty",
    "original_stock_qty",
    "projected_5d_stock_no_inbound",
    "inbound_qty",
    "defect_stock",
    "original_defect_stock",
    "original_inbound_qty",
    "original_order_in_transit_stock",
    "original_defect_in_transit_stock",
    "off_shelf_stock",
    "order_occupy_stock",
    "order_in_transit_stock",
    "defect_in_transit_stock",
    "vip_projected_15d_stock",
    "other_projected_15d_stock",
    "risk",
    "image",
}

# These fields can be narrowed before the expensive sales/inventory assembly.
# The displayed value of cost is sourced from the latest price row, so it is
# deliberately evaluated against the assembled payload instead.
FINE_TABLE_SQL_FILTER_FIELDS = FINE_TABLE_FILTER_FIELDS - {
    field for field in FINE_TABLE_FILTER_FIELDS
    if field not in {
        "sku", "original_sku", "group_name", "product_level", "year",
        "season_category", "factory_code", "factory_name", "factory_sku",
        "upper_material", "lining_material", "outsole_material",
        "insole_material", "first_order_time",
    }
}
FINE_TABLE_DYNAMIC_FILTER_PATTERN = re.compile(r"^(?:daily_sales_(\d+)_(?:quantity|uv)|size_.+)$")


class FineTableFilter(BaseModel):
    field: str
    operator: FineTableFilterOperator
    values: list[str]


def _parse_fine_table_filters(raw_filters: str | None) -> tuple[FineTableFilter, ...]:
    if not raw_filters:
        return ()
    try:
        payload = json.loads(raw_filters)
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=400, detail="筛选条件格式无效") from exc
    if not isinstance(payload, list) or len(payload) > 20:
        raise HTTPException(status_code=400, detail="筛选条件最多 20 条")
    filters: list[FineTableFilter] = []
    for item in payload:
        if not isinstance(item, dict):
            raise HTTPException(status_code=400, detail="筛选条件格式无效")
        try:
            condition = FineTableFilter.model_validate(item)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail="筛选条件格式无效") from exc
        condition.field = condition.field.strip()
        condition.values = [value.strip() for value in condition.values]
        if not _is_supported_fine_table_filter_field(condition.field):
            raise HTTPException(status_code=400, detail=f"不支持按 {condition.field or '该字段'} 筛选")
        if len(condition.values) > 5_000:
            raise HTTPException(status_code=400, detail="单个字段最多选择 5000 个值")
        filters.append(condition)
    return tuple(filters)


def _is_supported_fine_table_filter_field(field: str) -> bool:
    return field in FINE_TABLE_FILTER_FIELDS or bool(FINE_TABLE_DYNAMIC_FILTER_PATTERN.fullmatch(field))


def _fine_table_filter_columns(product_table, brand: BrandKey):
    factory_code_column = (
        select(SUPPLIER_TABLE.c.factory_code)
        .where(SUPPLIER_TABLE.c.name == product_table.c.supplier_name)
        .where(SUPPLIER_TABLE.c.brand == brand)
        .limit(1)
        .scalar_subquery()
    )
    return {
        "sku": product_table.c.sku,
        "original_sku": product_table.c.original_sku,
        "group_name": product_table.c.group_name,
        "product_level": product_table.c.product_level,
        "year": product_table.c.year,
        "season_category": product_table.c.season_category,
        "factory_code": factory_code_column,
        "factory_name": product_table.c.supplier_name,
        "factory_sku": product_table.c.factory_sku,
        "upper_material": product_table.c.upper_material,
        "lining_material": product_table.c.lining_material,
        "outsole_material": product_table.c.outsole_material,
        "insole_material": product_table.c.insole_material,
        "first_order_time": product_table.c.first_order_time,
        "cost": product_table.c.cost,
    }


def _fine_table_filter_condition(column, operator: FineTableFilterOperator, values: list[str]):
    normalized = func.coalesce(func.trim(cast(column, Text)), "")
    normalized_values = sorted({value.lower() for value in values})
    if operator == "in":
        return func.lower(normalized).in_(normalized_values) if normalized_values else false()
    return func.lower(normalized).not_in(normalized_values) if normalized_values else normalized == normalized


def _fine_table_filter_conditions(
    product_table,
    brand: BrandKey,
    filters: tuple[FineTableFilter, ...],
) -> list:
    columns = _fine_table_filter_columns(product_table, brand)
    return [
        _fine_table_filter_condition(columns[item.field], item.operator, item.values)
        for item in filters
    ]


def _fine_table_status_label(row: dict[str, Any]) -> str:
    goods_status = str(row.get("goods_status") or "").strip()
    if goods_status:
        return goods_status
    return {
        "online": "商品上线",
        "partial": "部分上线",
        "offline": "已下线",
    }.get(str(row.get("status_key") or ""), "未知")


def _fine_table_metric_number(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return _metric_to_float(value)


def _fine_table_exposure(uv: Any, ctr: Any) -> int | None:
    uv_value = _fine_table_metric_number(uv)
    ctr_value = _metric_to_float(ctr)
    if uv_value is None or ctr_value in (None, 0):
        return None
    if isinstance(ctr, str) and "%" in ctr:
        ctr_value /= 100
    elif abs(ctr_value) > 1:
        ctr_value /= 100
    return round(uv_value / ctr_value) if ctr_value else None


def _fine_table_filter_value(row: dict[str, Any], field: str) -> Any:
    if field == "status":
        return _fine_table_status_label(row)
    if field == "image":
        return "有图片" if row.get("image_url") or row.get("image_path") else "无图片"
    if field == "category_l3":
        return row.get("category_l3") or row.get("product_model")
    if field == "cost":
        return row.get("latest_purchase_price") if row.get("latest_purchase_price") not in (None, "") else row.get("cost")
    if field == "vip_projected_15d_sales":
        return _fine_table_metric_number(row.get("vip_daily_average_sales")) * 15 if row.get("vip_daily_average_sales") is not None else None
    if field == "other_daily_average_sales":
        return _fine_table_metric_number(row.get("other_30d_sales")) / 30 if row.get("other_30d_sales") is not None else None
    if field == "other_projected_15d_sales":
        daily = _fine_table_filter_value(row, "other_daily_average_sales")
        return daily * 15 if daily is not None else None
    if field == "projected_5d_stock_no_inbound":
        vip_daily = _fine_table_metric_number(row.get("vip_daily_average_sales")) or 0
        other_daily = _fine_table_metric_number(row.get("other_30d_sales")) or 0
        return (_fine_table_metric_number(row.get("stock_qty")) or 0) - (vip_daily * 5 + other_daily / 30 * 5)
    if field == "order_in_transit_stock":
        return (_fine_table_metric_number(row.get("inbound_qty")) or 0) - (_fine_table_metric_number(row.get("defect_in_transit_stock")) or 0)
    if field == "vip_projected_15d_stock":
        stock = _fine_table_metric_number(row.get("stock_qty")) or 0
        inbound = _fine_table_metric_number(row.get("inbound_qty")) or 0
        sales = _fine_table_filter_value(row, "vip_projected_15d_sales") or 0
        return stock + inbound - sales
    if field == "other_projected_15d_stock":
        return (_fine_table_filter_value(row, "vip_projected_15d_stock") or 0) - (_fine_table_filter_value(row, "other_projected_15d_sales") or 0)
    if field == "risk":
        vip_stock = _fine_table_filter_value(row, "vip_projected_15d_stock") or 0
        other_stock = _fine_table_filter_value(row, "other_projected_15d_stock") or 0
        if min(vip_stock, other_stock) < 0:
            return "15天后缺口"
        if (_fine_table_metric_number(row.get("stock_qty")) or 0) < ((_fine_table_metric_number(row.get("vip_7d_sales")) or 0) + (_fine_table_metric_number(row.get("other_7d_sales")) or 0)):
            return "低库存"
        return "正常"
    if field in {"vip_3d_exposure", "vip_7d_exposure", "vip_30d_exposure"}:
        period = field.split("_")[1]
        return _fine_table_exposure(row.get(f"vip_{period}_uv"), row.get(f"vip_{period}_ctr"))
    daily_match = re.fullmatch(r"daily_sales_(\d+)_(quantity|uv)", field)
    if daily_match:
        index = int(daily_match.group(1))
        metric = daily_match.group(2)
        daily_sales = row.get("daily_sales") or []
        if index >= len(daily_sales):
            return 0
        return daily_sales[index].get(metric, 0) if isinstance(daily_sales[index], dict) else 0
    if field.startswith("size_"):
        return (row.get("size_stock") or {}).get(field.removeprefix("size_"), 0)
    return row.get(field)


def _fine_table_scalar_equal(left: Any, right: str) -> bool:
    if left in (None, ""):
        return right == ""
    left_number = _fine_table_metric_number(left)
    right_number = _fine_table_metric_number(right)
    if left_number is not None and right_number is not None:
        return left_number == right_number
    return str(left).strip().lower() == str(right).strip().lower()


def _fine_table_row_matches_filter(row: dict[str, Any], condition: FineTableFilter) -> bool:
    value = _fine_table_filter_value(row, condition.field)
    matched = any(_fine_table_scalar_equal(value, candidate) for candidate in condition.values)
    return matched if condition.operator == "in" else not matched


def _fine_table_rows_match_filters(rows: list[dict[str, Any]], filters: tuple[FineTableFilter, ...]) -> list[dict[str, Any]]:
    if not filters:
        return rows
    return [row for row in rows if all(_fine_table_row_matches_filter(row, condition) for condition in filters)]


def _fine_table_filter_option_text(value: Any) -> str:
    if value in (None, ""):
        return ""
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value)


def _ensure_snapshot_tables(engine) -> None:
    FINE_TABLE_SNAPSHOT_BATCH_TABLE.create(engine, checkfirst=True)
    FINE_TABLE_SNAPSHOT_PAYLOADS_TABLE.create(engine, checkfirst=True)
    FINE_TABLE_SNAPSHOT_METRICS_TABLE.create(engine, checkfirst=True)


def _snapshot_batch_payload(row: dict[str, Any]) -> dict[str, Any]:
    snapshot_date = row.get("snapshot_date")
    latest_order_date = row.get("latest_order_date")
    created_at = row.get("created_at")
    updated_at = row.get("updated_at")
    return {
        "id": row.get("id"),
        "brand": row.get("brand"),
        "snapshot_date": snapshot_date.isoformat() if isinstance(snapshot_date, date) else snapshot_date,
        "total_rows": row.get("total_rows") or 0,
        "latest_order_date": latest_order_date.isoformat() if isinstance(latest_order_date, date) else latest_order_date,
        "created_at": created_at.isoformat() if isinstance(created_at, datetime) else created_at,
        "updated_at": updated_at.isoformat() if isinstance(updated_at, datetime) else updated_at,
    }


def _json_payload(value: Any) -> Any:
    encoded = jsonable_encoder(value)
    if isinstance(encoded, dict):
        return {str(key): _json_payload(item) for key, item in encoded.items()}
    if isinstance(encoded, list):
        return [_json_payload(item) for item in encoded]
    return encoded


def _parse_iso_date(value: Any) -> date | None:
    if isinstance(value, date):
        return value
    if not value:
        return None
    try:
        return date.fromisoformat(str(value))
    except ValueError:
        return None


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


def _daily_metric_with_original_fallback(
    daily: dict[tuple[str, str], dict[str, Any]],
    original_daily: dict[tuple[str, str], dict[str, Any]],
    period: str,
    field: str,
) -> Any:
    value = _daily_metric(daily, period, field)
    if value not in (None, ""):
        return value
    return _daily_metric(original_daily, period, field)


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


def _normalized_terms(query: str | None) -> list[str]:
    return [
        term.strip()
        for term in (query or "").replace("\n", ",").split(",")
        if term.strip()
    ]


def _prefix_search_condition(table, prefixes: list[str]):
    search_conditions = []
    for prefix in prefixes:
        like = f"{prefix}%"
        search_conditions.extend([
            table.c.sku.ilike(like),
            table.c.original_sku.ilike(like),
        ])
    return or_(*search_conditions)


def _gj_product_row(row: dict[str, Any], brand: BrandKey) -> dict[str, Any]:
    raw_payload = row.get("raw_payload")
    goods_code = str(row.get("goods_code") or "").strip()
    original_goods_code = str(row.get("original_goods_code") or "").strip() or goods_code
    product = {
        "id": -int(row["id"]),
        "source_workbook": row.get("source_workbook") or "",
        "source_sheet": row.get("source_sheet") or "",
        "source_row_number": row.get("source_row_number") or "",
        "raw_payload": raw_payload if isinstance(raw_payload, dict) else {},
        "image_path": None,
        "sku": goods_code,
        "original_sku": original_goods_code,
        "group_name": None,
        "cost": None,
        "factory_sku": row.get("factory_code"),
        "color": None,
        "season_category": None,
        "year": None,
        "upper_material": row.get("upper_material"),
        "lining_material": row.get("lining_material"),
        "outsole_material": row.get("outsole_material"),
        "insole_material": row.get("insole_material"),
        "execution_standard": row.get("execution_standard"),
        "heel_height": None,
        "shoe_width": None,
        "shoe_length": None,
        "shaft_circumference": None,
        "shaft_height": None,
        "internal_height_increase": None,
        "internal_height_note": None,
        "upper_height": None,
        "toe_shape": None,
        "closure_type": None,
        "shoe_box_spec": row.get("shoe_box_spec"),
        "first_order_time": None,
        "size_range": None,
        "product_model": row.get("product_name"),
        "supplier_name": row.get("primary_supplier"),
        "color_code": None,
        "launch_date": row.get("launch_date"),
        "extra_fields": row.get("extra_fields"),
        "brand": brand,
    }
    for field in PRODUCT_FIELDS:
        product.setdefault(field.name, None)
    return dict(apply_product_defaults(brand, product))


def _merge_gj_product_row(gj_row: dict[str, Any], archive_row: dict[str, Any] | None, brand: BrandKey) -> dict[str, Any]:
    product = _gj_product_row(gj_row, brand)
    if archive_row is None:
        return product

    for field in PRODUCT_FIELDS:
        if field.name in {"sku", "original_sku"}:
            continue
        if product.get(field.name) in (None, ""):
            product[field.name] = archive_row.get(field.name)
    return product


def _hydrate_snapshot_image_urls(
    *,
    connection,
    items: list[dict[str, Any]],
    brand: BrandKey,
    settings,
) -> None:
    product_table = PRODUCT_TABLES.get(brand)
    if product_table is None:
        return

    missing_items = [item for item in items if not item.get("image_url")]
    if not missing_items:
        return

    codes = {
        code
        for item in missing_items
        for code in (
            str(item.get("sku") or "").strip(),
            str(item.get("original_sku") or "").strip(),
        )
        if code
    }
    if not codes:
        return

    image_by_sku: dict[str, str] = {}
    image_by_original_sku: dict[str, str] = {}
    for row in connection.execute(
        select(product_table.c.sku, product_table.c.original_sku, product_table.c.image_path)
        .where(or_(
            product_table.c.sku.in_(codes),
            product_table.c.original_sku.in_(codes),
        ))
        .where(product_table.c.image_path.isnot(None))
        .where(product_table.c.image_path != "")
        .order_by(desc(product_table.c.id))
    ).mappings():
        image_path = str(row.get("image_path") or "").strip()
        if not image_path:
            continue
        sku = str(row.get("sku") or "").strip()
        original_sku = str(row.get("original_sku") or "").strip()
        if sku:
            image_by_sku.setdefault(sku, image_path)
        if original_sku:
            image_by_original_sku.setdefault(original_sku, image_path)

    for item in missing_items:
        image_path = (
            str(item.get("image_path") or "").strip()
            or image_by_sku.get(str(item.get("sku") or "").strip())
            or image_by_original_sku.get(str(item.get("sku") or "").strip())
            or image_by_sku.get(str(item.get("original_sku") or "").strip())
            or image_by_original_sku.get(str(item.get("original_sku") or "").strip())
        )
        if image_path:
            item["image_path"] = image_path
            item["image_url"] = image_url_for(brand, image_path, settings)


def _gj_fine_table_brand(brand: BrandKey) -> str | None:
    return brand if brand in {CBANNER_MENS_BRAND, CBANNER_WOMENS_BRAND} else None


def _fine_table_view_label(value: str | None) -> str:
    if value == "missingImage":
        return "暂无图片"
    if value == "stockRisk":
        return "缺货风险"
    return "全部"


@router.post("/fine-table/export-log")
def log_fine_table_export(request: Request, body: FineTableExportLogRequest):
    brand_label = (body.brand_label or str(body.brand)).strip()
    exported_rows = max(0, int(body.exported_rows or 0))
    total_rows = max(0, int(body.total_rows or 0)) if body.total_rows is not None else None
    filters = [f"视图：{_fine_table_view_label(body.view)}"]
    if body.query:
        filters.append(f"包含搜索：{body.query.strip()}")
    if body.sku_prefix:
        filters.append(f"货号前缀：{body.sku_prefix.strip()}")
    if body.history_date:
        filters.append(f"历史日期：{body.history_date.strip()}")

    total_text = f"，当前条件共 {total_rows} 行" if total_rows is not None else ""
    summary = f"导出商品精细表 {brand_label}，导出 {exported_rows} 行{total_text}（{'；'.join(filters)}）"
    write_operation_log(
        request,
        module="fine_table",
        action="export",
        entity_type="fine_table",
        entity_id=body.brand,
        entity_label=brand_label,
        summary=summary,
        after_data={
            "brand": body.brand,
            "brand_label": brand_label,
            "exported_rows": exported_rows,
            "total_rows": total_rows,
            "view": body.view,
            "query": body.query,
            "sku_prefix": body.sku_prefix,
            "history_date": body.history_date,
            "column_mode": body.column_mode,
            "column_count": body.column_count,
            "filename": body.filename,
        },
    )
    return {"message": "操作日志已记录"}


@router.post("/fine-table/snapshots")
def create_fine_table_snapshot(
    request: Request,
    brand: BrandKey = Query(DEFAULT_BRAND),
    snapshot_date: date | None = None,
):
    repository = request.app.state.repository
    _ensure_snapshot_tables(repository.engine)
    resolved_snapshot_date = snapshot_date or date.today()
    ensure_fine_table_snapshot_ref_table(repository.engine, resolved_snapshot_date)

    first_payload = list_fine_table(
        request,
        brand=brand,
        query=None,
        season=None,
        page=1,
        page_size=SNAPSHOT_PAGE_SIZE,
    )
    total = int(first_payload.get("total") or 0)
    latest_order_date = _parse_iso_date(first_payload.get("latest_order_date"))
    items = list(first_payload.get("items") or [])
    total_pages = ceil(total / SNAPSHOT_PAGE_SIZE) if total else 1

    for page_number in range(2, total_pages + 1):
        page_payload = list_fine_table(
            request,
            brand=brand,
            query=None,
            season=None,
            page=page_number,
            page_size=SNAPSHOT_PAGE_SIZE,
        )
        items.extend(page_payload.get("items") or [])

    row_payloads = [_json_payload(item) for item in items]

    with repository.engine.begin() as connection:
        existing = connection.execute(
            select(FINE_TABLE_SNAPSHOT_BATCH_TABLE)
            .where(FINE_TABLE_SNAPSHOT_BATCH_TABLE.c.brand == brand)
            .where(FINE_TABLE_SNAPSHOT_BATCH_TABLE.c.snapshot_date == resolved_snapshot_date)
        ).mappings().first()

        replaced = existing is not None
        if existing is None:
            batch = connection.execute(
                insert(FINE_TABLE_SNAPSHOT_BATCH_TABLE)
                .values(
                    brand=brand,
                    snapshot_date=resolved_snapshot_date,
                    total_rows=len(row_payloads),
                    latest_order_date=latest_order_date,
                )
                .returning(FINE_TABLE_SNAPSHOT_BATCH_TABLE)
            ).mappings().one()
            batch_id = batch["id"]
        else:
            batch_id = existing["id"]
            batch = connection.execute(
                update(FINE_TABLE_SNAPSHOT_BATCH_TABLE)
                .where(FINE_TABLE_SNAPSHOT_BATCH_TABLE.c.id == batch_id)
                .values(
                    total_rows=len(row_payloads),
                    latest_order_date=latest_order_date,
                    updated_at=func.date_trunc("minute", func.now()),
                )
                .returning(FINE_TABLE_SNAPSHOT_BATCH_TABLE)
            ).mappings().one()
        write_optimized_snapshot_rows(
            connection,
            brand=brand,
            snapshot_date=resolved_snapshot_date,
            batch_id=int(batch_id),
            payloads=row_payloads,
        )

    return {
        "item": _snapshot_batch_payload(dict(batch)),
        "rows": len(row_payloads),
        "replaced": replaced,
        "message": "快照已更新" if replaced else "快照已生成",
    }


@router.get("/fine-table/snapshots")
def list_fine_table_snapshots(
    request: Request,
    brand: BrandKey = Query(DEFAULT_BRAND),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
):
    repository = request.app.state.repository
    _ensure_snapshot_tables(repository.engine)
    conditions = [FINE_TABLE_SNAPSHOT_BATCH_TABLE.c.brand == brand]
    count_stmt = select(func.count()).select_from(FINE_TABLE_SNAPSHOT_BATCH_TABLE).where(and_(*conditions))
    items_stmt = (
        select(FINE_TABLE_SNAPSHOT_BATCH_TABLE)
        .where(and_(*conditions))
        .order_by(desc(FINE_TABLE_SNAPSHOT_BATCH_TABLE.c.snapshot_date), desc(FINE_TABLE_SNAPSHOT_BATCH_TABLE.c.id))
        .offset((page - 1) * page_size)
        .limit(page_size)
    )

    with repository.engine.connect() as connection:
        total = connection.execute(count_stmt).scalar_one()
        items = [_snapshot_batch_payload(dict(row)) for row in connection.execute(items_stmt).mappings()]

    return {"items": items, "total": total, "page": page, "page_size": page_size}


@router.get("/fine-table/snapshots/by-date")
def get_fine_table_snapshot_by_date(
    request: Request,
    brand: BrandKey = Query(DEFAULT_BRAND),
    snapshot_date: date = Query(...),
    query: str | None = None,
    sku_prefix: str | None = None,
    filters: str | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(80, ge=1, le=200),
):
    repository = request.app.state.repository
    _ensure_snapshot_tables(repository.engine)
    with repository.engine.connect() as connection:
        batch = connection.execute(
            select(FINE_TABLE_SNAPSHOT_BATCH_TABLE)
            .where(FINE_TABLE_SNAPSHOT_BATCH_TABLE.c.brand == brand)
            .where(FINE_TABLE_SNAPSHOT_BATCH_TABLE.c.snapshot_date == snapshot_date)
        ).mappings().first()
    if batch is None:
        raise HTTPException(status_code=404, detail="Snapshot not found")

    return get_fine_table_snapshot(
        request,
        batch_id=int(batch["id"]),
        query=query,
        sku_prefix=sku_prefix,
        filters=filters,
        page=page,
        page_size=page_size,
    )


@router.get("/fine-table/snapshots/{batch_id}")
def get_fine_table_snapshot(
    request: Request,
    batch_id: int,
    query: str | None = None,
    sku_prefix: str | None = None,
    filters: str | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(80, ge=1, le=200),
):
    settings = request.app.state.settings
    repository = request.app.state.repository
    _ensure_snapshot_tables(repository.engine)
    parsed_filters = _parse_fine_table_filters(filters)
    with repository.engine.connect() as connection:
        batch = connection.execute(
            select(FINE_TABLE_SNAPSHOT_BATCH_TABLE)
            .where(FINE_TABLE_SNAPSHOT_BATCH_TABLE.c.id == batch_id)
        ).mappings().first()
        if batch is None:
            raise HTTPException(status_code=404, detail="Snapshot not found")

        snapshot_date = batch["snapshot_date"]
        if not isinstance(snapshot_date, date):
            raise HTTPException(status_code=500, detail="Invalid snapshot date")
        if not fine_table_snapshot_year_table_exists(repository.engine, snapshot_date) and not fine_table_snapshot_ref_table_exists(repository.engine, snapshot_date):
            raise HTTPException(status_code=500, detail="Snapshot row table not found")
        if optimized_snapshot_available(repository.engine, snapshot_date, int(batch["id"])):
            if not parsed_filters:
                ref_table = fine_table_snapshot_ref_table_for_date(snapshot_date)
                conditions = [not_excluded_sku_condition(ref_table.c.sku, ref_table.c.original_sku)]
                query_terms = _normalized_terms(query)
                prefix_terms = _normalized_terms(sku_prefix)
                if query_terms:
                    search_conditions = []
                    for term in query_terms:
                        like = f"%{term}%"
                        search_conditions.extend([ref_table.c.sku.ilike(like), ref_table.c.original_sku.ilike(like)])
                    conditions.append(or_(*search_conditions))
                if prefix_terms:
                    conditions.append(_prefix_search_condition(ref_table, prefix_terms))
                items, total = load_optimized_snapshot_rows(
                    repository.engine,
                    snapshot_date,
                    int(batch_id),
                    conditions=conditions,
                    page=page,
                    page_size=page_size,
                )
                with repository.engine.connect() as connection:
                    _hydrate_snapshot_image_urls(
                        connection=connection,
                        items=items,
                        brand=batch["brand"],
                        settings=settings,
                    )
                return {
                    "items": items,
                    "total": total,
                    "page": page,
                    "page_size": page_size,
                    "snapshot": _snapshot_batch_payload(dict(batch)),
                }
            all_rows, _snapshot_total = load_optimized_snapshot_rows(
                repository.engine,
                snapshot_date,
                int(batch_id),
                conditions=[],
                page=1,
                page_size=1_000_000,
            )
            query_terms = _normalized_terms(query)
            prefix_terms = _normalized_terms(sku_prefix)
            filtered_rows = []
            for row in all_rows:
                sku = str(row.get("sku") or "")
                original_sku = str(row.get("original_sku") or "")
                if is_excluded_sku(sku, original_sku):
                    continue
                if query_terms and not any(term.lower() in sku.lower() or term.lower() in original_sku.lower() for term in query_terms):
                    continue
                if prefix_terms and not any(sku.lower().startswith(term.lower()) or original_sku.lower().startswith(term.lower()) for term in prefix_terms):
                    continue
                if parsed_filters and not all(_fine_table_row_matches_filter(row, condition) for condition in parsed_filters):
                    continue
                filtered_rows.append(row)
            total = len(filtered_rows) if (parsed_filters or query_terms or prefix_terms) else int(_snapshot_total)
            offset = (page - 1) * page_size
            items = filtered_rows[offset:offset + page_size]
            with repository.engine.connect() as connection:
                _hydrate_snapshot_image_urls(
                    connection=connection,
                    items=items,
                    brand=batch["brand"],
                    settings=settings,
                )
            return {
                "items": items,
                "total": total,
                "page": page,
                "page_size": page_size,
                "snapshot": _snapshot_batch_payload(dict(batch)),
            }

        snapshot_row_table = fine_table_snapshot_row_table_for_date(snapshot_date)
        all_rows = [dict(row["payload"] or {}) for row in connection.execute(
            select(snapshot_row_table.c.payload)
            .where(snapshot_row_table.c.batch_id == batch_id)
            .order_by(snapshot_row_table.c.row_index)
        ).mappings()]
        query_terms = _normalized_terms(query)
        prefix_terms = _normalized_terms(sku_prefix)
        filtered_rows = []
        for row in all_rows:
            sku = str(row.get("sku") or "")
            original_sku = str(row.get("original_sku") or "")
            if is_excluded_sku(sku, original_sku):
                continue
            if query_terms and not any(term.lower() in sku.lower() or term.lower() in original_sku.lower() for term in query_terms):
                continue
            if prefix_terms and not any(sku.lower().startswith(term.lower()) or original_sku.lower().startswith(term.lower()) for term in prefix_terms):
                continue
            if parsed_filters and not all(_fine_table_row_matches_filter(row, condition) for condition in parsed_filters):
                continue
            filtered_rows.append(row)
        total = len(filtered_rows)
        offset = (page - 1) * page_size
        items = filtered_rows[offset:offset + page_size]
        _hydrate_snapshot_image_urls(
            connection=connection,
            items=items,
            brand=batch["brand"],
            settings=settings,
        )

    return {
        "items": items,
        "total": total,
        "page": page,
        "page_size": page_size,
        "snapshot": _snapshot_batch_payload(dict(batch)),
    }


def _fine_table_options_from_rows(rows: list[dict[str, Any]], field: str) -> dict[str, Any]:
    counts: dict[str, int] = {}
    for row in rows:
        value = _fine_table_filter_option_text(_fine_table_filter_value(row, field))
        counts[value] = counts.get(value, 0) + 1
    sorted_options = sorted(counts.items(), key=lambda item: (-item[1], item[0].lower()))
    options = [{"value": value, "count": count} for value, count in sorted_options[:10_000]]
    return {
        "field": field,
        "total": len(sorted_options),
        "truncated": len(sorted_options) > len(options),
        "options": options,
    }


@router.get("/fine-table/filter-options")
def list_fine_table_filter_options(
    request: Request,
    field: str,
    brand: BrandKey = Query(DEFAULT_BRAND),
    filters: str | None = None,
    query: str | None = None,
    sku_prefix: str | None = None,
    snapshot_date: date | None = None,
):
    if not _is_supported_fine_table_filter_field(field):
        raise HTTPException(status_code=400, detail=f"不支持按 {field or '该字段'} 筛选")
    parsed_filters = _parse_fine_table_filters(filters)
    other_filters = tuple(item for item in parsed_filters if item.field != field)
    product_table = PRODUCT_TABLES[brand]
    terms = _normalized_terms(query)
    prefix_terms = _normalized_terms(sku_prefix)

    repository = request.app.state.repository
    if snapshot_date is not None:
        _ensure_snapshot_tables(repository.engine)
        with repository.engine.connect() as connection:
            batch = connection.execute(
                select(FINE_TABLE_SNAPSHOT_BATCH_TABLE)
                .where(FINE_TABLE_SNAPSHOT_BATCH_TABLE.c.brand == brand)
                .where(FINE_TABLE_SNAPSHOT_BATCH_TABLE.c.snapshot_date == snapshot_date)
            ).mappings().first()
        if batch is None:
            raise HTTPException(status_code=404, detail="Snapshot not found")
        if optimized_snapshot_available(repository.engine, snapshot_date, int(batch["id"])):
            rows, _snapshot_total = load_optimized_snapshot_rows(
                repository.engine,
                snapshot_date,
                int(batch["id"]),
                conditions=[],
                page=1,
                page_size=1_000_000,
            )
        else:
            snapshot_row_table = fine_table_snapshot_row_table_for_date(snapshot_date)
            with repository.engine.connect() as connection:
                rows = [dict(row["payload"] or {}) for row in connection.execute(
                    select(snapshot_row_table.c.payload)
                    .where(snapshot_row_table.c.batch_id == int(batch["id"]))
                    .order_by(snapshot_row_table.c.row_index)
                ).mappings()]
        filtered_rows = []
        for row in rows:
            sku = str(row.get("sku") or "")
            original_sku = str(row.get("original_sku") or "")
            if is_excluded_sku(sku, original_sku):
                continue
            if terms and not any(term.lower() in sku.lower() or term.lower() in original_sku.lower() for term in terms):
                continue
            if prefix_terms and not any(sku.lower().startswith(term.lower()) or original_sku.lower().startswith(term.lower()) for term in prefix_terms):
                continue
            if other_filters and not all(_fine_table_row_matches_filter(row, condition) for condition in other_filters):
                continue
            filtered_rows.append(row)
        return _fine_table_options_from_rows(filtered_rows, field)

    payload_filter_mode = (
        _gj_fine_table_brand(brand) is not None
        or field not in FINE_TABLE_SQL_FILTER_FIELDS
        or any(item.field not in FINE_TABLE_SQL_FILTER_FIELDS for item in other_filters)
    )
    if payload_filter_mode:
        encoded_filters = json.dumps([item.model_dump() for item in other_filters], ensure_ascii=False)
        response = list_fine_table(
            request,
            brand=brand,
            query=query,
            sku_prefix=sku_prefix,
            filters=encoded_filters if other_filters else None,
            page=1,
            page_size=200,
            include_all=True,
        )
        return _fine_table_options_from_rows(response["items"], field)

    conditions = [not_excluded_sku_condition(product_table.c.sku, product_table.c.original_sku)]
    if terms:
        search_conditions = []
        for term in terms:
            like = f"%{term}%"
            search_conditions.extend([product_table.c.sku.ilike(like), product_table.c.original_sku.ilike(like)])
        conditions.append(or_(*search_conditions))
    if prefix_terms:
        conditions.append(_prefix_search_condition(product_table, prefix_terms))
    conditions.extend(_fine_table_filter_conditions(
        product_table,
        brand,
        other_filters,
    ))
    column = _fine_table_filter_columns(product_table, brand)[field]
    value_expression = func.coalesce(func.trim(cast(column, Text)), "")
    statement = (
        select(value_expression.label("value"), func.count().label("count"))
        .select_from(product_table)
        .where(and_(*conditions))
        .group_by(value_expression)
        .order_by(desc(func.count()), value_expression)
        .limit(10_000)
    )
    total_statement = select(func.count(func.distinct(value_expression))).select_from(product_table).where(and_(*conditions))
    with repository.engine.connect() as connection:
        rows = connection.execute(statement).mappings().all()
        total = int(connection.execute(total_statement).scalar() or 0)
    return {
        "field": field,
        "total": total,
        "truncated": total > len(rows),
        "options": [{"value": str(row["value"] or ""), "count": int(row["count"] or 0)} for row in rows],
    }


@router.get("/fine-table")
def list_fine_table(
    request: Request,
    brand: BrandKey = Query(DEFAULT_BRAND),
    query: str | None = None,
    sku_prefix: str | None = None,
    season: str | None = None,
    filters: str | None = None,
    cache_bust: str | None = None,
    include_all: bool = False,
    page: int = Query(1, ge=1),
    page_size: int = Query(80, ge=1, le=200),
):
    settings = request.app.state.settings
    repository = request.app.state.repository
    product_table = PRODUCT_TABLES[brand]
    terms = _normalized_terms(query)
    prefix_terms = _normalized_terms(sku_prefix)
    normalized_query = ",".join(terms)
    normalized_sku_prefix = ",".join(prefix_terms)
    normalized_season = season if season and season != "all" else "all"
    parsed_filters = _parse_fine_table_filters(filters)
    payload_filters = parsed_filters if _gj_fine_table_brand(brand) is not None else tuple(
        item for item in parsed_filters if item.field not in FINE_TABLE_SQL_FILTER_FIELDS
    )
    fetch_all_rows = include_all or bool(payload_filters)
    normalized_filters = tuple(sorted((item.field, item.operator, tuple(item.values)) for item in parsed_filters))
    bypass_cache = bool(cache_bust) or include_all
    cache_key = (brand, normalized_query, normalized_sku_prefix, normalized_season, normalized_filters, page, page_size)
    total_cache_key = (brand, normalized_query, normalized_sku_prefix, normalized_season, normalized_filters, 0, 0)
    cached = None if bypass_cache else get_fine_table_cache(cache_key)
    if cached is not None:
        return cached
    cached_total_payload = None if bypass_cache else get_fine_table_cache(total_cache_key)
    cached_total = (
        int(cached_total_payload["total"])
        if cached_total_payload is not None and "total" in cached_total_payload
        else None
    )

    with repository.engine.connect() as conn:
        gj_fine_table_brand = _gj_fine_table_brand(brand)
        if gj_fine_table_brand is not None:
            latest_gj_product_info_date = conn.execute(
                select(func.max(GJ_MERGED_PRODUCT_INFO_TABLE.c.source_date_value))
            ).scalar()
            product_rows = []
            total = 0
            if latest_gj_product_info_date is not None:
                gj_conditions = [
                    GJ_MERGED_PRODUCT_INFO_TABLE.c.source_date_value == latest_gj_product_info_date,
                    GJ_MERGED_PRODUCT_INFO_TABLE.c.fine_table_brand == gj_fine_table_brand,
                    not_excluded_sku_condition(
                        GJ_MERGED_PRODUCT_INFO_TABLE.c.goods_code,
                        GJ_MERGED_PRODUCT_INFO_TABLE.c.original_goods_code,
                    ),
                ]
                if terms:
                    gj_search_conditions = []
                    for term in terms:
                        like = f"%{term}%"
                        gj_search_conditions.extend([
                            GJ_MERGED_PRODUCT_INFO_TABLE.c.goods_code.ilike(like),
                            GJ_MERGED_PRODUCT_INFO_TABLE.c.original_goods_code.ilike(like),
                        ])
                    gj_conditions.append(or_(*gj_search_conditions))
                if prefix_terms:
                    gj_prefix_conditions = []
                    for prefix in prefix_terms:
                        like = f"{prefix}%"
                        gj_prefix_conditions.extend([
                            GJ_MERGED_PRODUCT_INFO_TABLE.c.goods_code.ilike(like),
                            GJ_MERGED_PRODUCT_INFO_TABLE.c.original_goods_code.ilike(like),
                        ])
                    gj_conditions.append(or_(*gj_prefix_conditions))
                if normalized_season != "all":
                    gj_conditions.append(
                        select(product_table.c.id)
                        .where(or_(
                            product_table.c.sku == GJ_MERGED_PRODUCT_INFO_TABLE.c.goods_code,
                            product_table.c.sku == GJ_MERGED_PRODUCT_INFO_TABLE.c.original_goods_code,
                            product_table.c.original_sku == GJ_MERGED_PRODUCT_INFO_TABLE.c.goods_code,
                            product_table.c.original_sku == GJ_MERGED_PRODUCT_INFO_TABLE.c.original_goods_code,
                        ))
                        .where(product_table.c.season_category == normalized_season)
                        .exists()
                    )
                gj_criterion = and_(*gj_conditions)
                if fetch_all_rows:
                    total = 0
                elif cached_total is None:
                    total = conn.execute(
                        select(func.count()).select_from(GJ_MERGED_PRODUCT_INFO_TABLE).where(gj_criterion)
                    ).scalar_one()
                    set_fine_table_cache(total_cache_key, {"total": total})
                else:
                    total = cached_total
                gj_statement = (
                    select(GJ_MERGED_PRODUCT_INFO_TABLE)
                    .where(gj_criterion)
                    .order_by(desc(GJ_MERGED_PRODUCT_INFO_TABLE.c.id))
                )
                if not fetch_all_rows:
                    gj_statement = gj_statement.offset((page - 1) * page_size).limit(page_size)
                gj_rows = [dict(row) for row in conn.execute(gj_statement).mappings()]
                if fetch_all_rows:
                    total = len(gj_rows)
                gj_match_codes = {
                    code
                    for row in gj_rows
                    for code in (
                        str(row.get("goods_code") or "").strip(),
                        str(row.get("original_goods_code") or "").strip(),
                    )
                    if code
                }
                products_by_sku: dict[str, dict[str, Any]] = {}
                products_by_original_sku: dict[str, dict[str, Any]] = {}
                if gj_match_codes:
                    for row in conn.execute(
                        select(product_table)
                        .where(or_(
                            product_table.c.sku.in_(gj_match_codes),
                            product_table.c.original_sku.in_(gj_match_codes),
                        ))
                        .order_by(desc(product_table.c.id))
                    ).mappings():
                        sku = str(row.get("sku") or "").strip()
                        original_sku = str(row.get("original_sku") or "").strip()
                        if sku:
                            products_by_sku.setdefault(sku, dict(row))
                        if original_sku:
                            products_by_original_sku.setdefault(original_sku, dict(row))
                for gj_row in gj_rows:
                    sku = str(gj_row.get("goods_code") or "").strip()
                    original_sku = str(gj_row.get("original_goods_code") or "").strip()
                    if is_excluded_sku(sku, original_sku):
                        continue
                    archive_row = (
                        products_by_sku.get(sku)
                        or products_by_original_sku.get(sku)
                        or products_by_sku.get(original_sku)
                        or products_by_original_sku.get(original_sku)
                    )
                    product_rows.append(_merge_gj_product_row(gj_row, archive_row, brand))
        else:
            conditions = [not_excluded_sku_condition(product_table.c.sku, product_table.c.original_sku)]
            if terms:
                search_conditions = []
                for term in terms:
                    like = f"%{term}%"
                    search_conditions.extend([
                        product_table.c.sku.ilike(like),
                        product_table.c.original_sku.ilike(like),
                    ])
                conditions.append(or_(*search_conditions))
            if prefix_terms:
                conditions.append(_prefix_search_condition(product_table, prefix_terms))
            if normalized_season != "all":
                conditions.append(product_table.c.season_category == normalized_season)
            sql_filters = tuple(item for item in parsed_filters if item.field in FINE_TABLE_SQL_FILTER_FIELDS)
            conditions.extend(_fine_table_filter_conditions(product_table, brand, sql_filters))

            count_stmt = select(func.count()).select_from(product_table)
            items_base_stmt = select(product_table).order_by(desc(product_table.c.id))
            if conditions:
                criterion = and_(*conditions)
                count_stmt = count_stmt.where(criterion)
                items_base_stmt = items_base_stmt.where(criterion)

            if fetch_all_rows:
                total = 0
            elif cached_total is None:
                total = conn.execute(count_stmt).scalar_one()
                set_fine_table_cache(total_cache_key, {"total": total})
            else:
                total = cached_total
            items_statement = items_base_stmt if fetch_all_rows else items_base_stmt.offset((page - 1) * page_size).limit(page_size)
            product_rows = [dict(row) for row in conn.execute(items_statement).mappings()]
            if fetch_all_rows:
                total = len(product_rows)

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

        supplier_names = sorted({
            str(row.get("supplier_name") or "").strip()
            for row in product_rows
            if str(row.get("supplier_name") or "").strip()
        })
        supplier_factory_code_by_name: dict[str, str | None] = {}
        if supplier_names:
            supplier_factory_code_by_name = {
                str(row["name"]): row["factory_code"]
                for row in conn.execute(
                    select(SUPPLIER_TABLE.c.name, SUPPLIER_TABLE.c.factory_code)
                    .where(SUPPLIER_TABLE.c.name.in_(supplier_names))
                    .where(SUPPLIER_TABLE.c.brand == brand)
                ).mappings()
                if row["name"]
            }

        if original_skus:
            for row in conn.execute(
                select(product_table.c.sku, product_table.c.original_sku)
                .where(product_table.c.original_sku.in_(original_skus))
                .where(not_excluded_sku_condition(product_table.c.sku, product_table.c.original_sku))
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
            select(
                JST_PRICE_TABLE.c.goods_code,
                JST_PRICE_TABLE.c.cost_unit_price,
            )
            .where(JST_PRICE_TABLE.c.goods_code.in_(skus))
            .order_by(
                JST_PRICE_TABLE.c.goods_code,
                JST_PRICE_TABLE.c.source_date_value.desc().nulls_last(),
                desc(JST_PRICE_TABLE.c.updated_at),
                desc(JST_PRICE_TABLE.c.id),
            )
        ).mappings():
            cost_unit_price = row.get("cost_unit_price")
            if cost_unit_price is None:
                continue
            if isinstance(cost_unit_price, str) and not cost_unit_price.strip():
                continue
            price_by_sku.setdefault(str(row["goods_code"]), dict(row))

        daily_by_sku: dict[str, dict[tuple[str, str], dict[str, Any]]] = {sku: {} for sku in skus}
        daily_lookup_codes = sorted({*skus, *original_skus})
        for row in conn.execute(
            select(VIP_DAILY_TABLE)
            .where(VIP_DAILY_TABLE.c.goods_code.in_(daily_lookup_codes))
            .order_by(desc(VIP_DAILY_TABLE.c.report_end_date), desc(VIP_DAILY_TABLE.c.updated_at), desc(VIP_DAILY_TABLE.c.id))
        ).mappings():
            sku = str(row["goods_code"])
            key = _period_key(row.get("report_type"), row.get("period"))
            daily_by_sku.setdefault(sku, {}).setdefault(key, dict(row))

        stock_codes = sorted({*skus, *all_original_group_skus})
        size_stock_by_sku: dict[str, dict[str, int]] = {sku: {} for sku in stock_codes}
        for row in conn.execute(
            select(JST_SIZE_STOCK_TABLE.c.product_code, JST_SIZE_STOCK_TABLE.c.size, func.sum(JST_SIZE_STOCK_TABLE.c.stock_qty).label("qty"))
            .where(JST_SIZE_STOCK_TABLE.c.product_code.in_(stock_codes))
            .group_by(JST_SIZE_STOCK_TABLE.c.product_code, JST_SIZE_STOCK_TABLE.c.size)
        ).mappings():
            sku = str(row["product_code"])
            size = str(row["size"])
            label = SIZE_LABELS.get(size, size)
            size_stock_by_sku.setdefault(sku, {})[label] = _to_int(row["qty"])

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
        original_stock_qty_by_code: dict[str, int] = {}
        original_defect_in_transit_by_code: dict[str, int] = {}
        for original_sku, grouped_skus in original_skus_by_code.items():
            summary = {
                "defect_stock_qty": 0,
                "purchase_in_transit_qty": 0,
                "order_occupy_qty": 0,
            }
            stock_total = 0
            defect_in_transit_total = 0
            for grouped_sku in grouped_skus:
                stock_total += sum(size_stock_by_sku.get(grouped_sku, {}).values())
                stock_summary = stock_summary_by_sku.get(grouped_sku, {})
                summary["defect_stock_qty"] += stock_summary.get("defect_stock_qty", 0)
                summary["purchase_in_transit_qty"] += stock_summary.get("purchase_in_transit_qty", 0)
                summary["order_occupy_qty"] += stock_summary.get("order_occupy_qty", 0)
                defect_in_transit_total += defect_in_transit_by_sku.get(grouped_sku, 0)
            original_stock_summary_by_code[original_sku] = summary
            original_stock_qty_by_code[original_sku] = stock_total
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
        original_daily = daily_by_sku.get(original_sku, {})
        vip_30d_reject_count = _daily_metric_with_original_fallback(
            daily,
            original_daily,
            "30d",
            "reject_count",
        )
        vip_30d_reject_rate = _daily_metric_with_original_fallback(
            daily,
            original_daily,
            "30d",
            "reject_rate",
        )
        supplier_name = str(product.get("supplier_name") or "").strip()
        original_orders = original_orders_by_code.get(original_sku, {})
        size_stock = {label: size_stock_by_sku.get(sku, {}).get(label, 0) for label in SIZE_LABELS.values()}

        stock_qty = sum(size_stock.values())
        stock_summary = stock_summary_by_sku.get(sku, {})
        inbound_qty = stock_summary.get("purchase_in_transit_qty", 0)
        defect_in_transit_qty = defect_in_transit_by_sku.get(sku, 0)
        original_stock_summary = original_stock_summary_by_code.get(original_sku, {})
        original_inbound_qty = original_stock_summary.get("purchase_in_transit_qty", 0)
        original_defect_in_transit_qty = original_defect_in_transit_by_code.get(original_sku, 0)
        cost = _to_float(price.get("cost_unit_price")) or _to_float(product.get("cost"))
        final_price = _to_float(ops.get("final_price"))
        market_price = _to_float(ops.get("market_price"))
        vip_price = _to_float(ops.get("vip_price"))
        vip_3 = _to_int(_daily_metric(daily, "3d", "sales_volume"))
        vip_7 = _to_int(_daily_metric(daily, "7d", "sales_volume"))
        original_vip_7 = _to_int(_daily_metric_with_original_fallback(
            original_daily,
            daily,
            "7d",
            "sales_volume",
        ))
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
        original_other_7 = _to_int(original_orders.get("other_7"))
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
            "brand": brand,
            "image_url": image_url_for(brand, product.get("image_path"), settings),
            "factory_code": supplier_factory_code_by_name.get(supplier_name),
            "factory_name": supplier_name or None,
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
            "vip_30d_reject_count": _to_int(vip_30d_reject_count) if vip_30d_reject_count not in (None, "") else None,
            "vip_30d_reject_rate": vip_30d_reject_rate,
            "vip_daily_average_sales": vip_daily_average,
            "other_3d_sales": _to_int(orders.get("other_3")),
            "other_7d_sales": _to_int(orders.get("other_7")),
            "other_15d_sales": _to_int(orders.get("other_15")),
            "other_30d_sales": other_30,
            "original_other_3d_sales": _to_int(original_orders.get("other_3")),
            "original_other_7d_sales": original_other_7,
            "original_all_7d_sales": original_vip_7 + original_other_7,
            "original_other_15d_sales": _to_int(original_orders.get("other_15")),
            "original_other_30d_sales": _to_int(original_orders.get("other_30")),
            "shop_30d_sales": [
                {"shop_name": name, "quantity": qty}
                for name, qty in sorted((orders.get("shop_30") or {}).items(), key=lambda item: item[1], reverse=True)
            ][:12],
            "stock_qty": stock_qty,
            "original_stock_qty": original_stock_qty_by_code.get(original_sku, stock_qty),
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

    if payload_filters:
        items = _fine_table_rows_match_filters(items, payload_filters)
        total = len(items)
        if not include_all:
            offset = (page - 1) * page_size
            items = items[offset:offset + page_size]
    elif include_all:
        total = len(items)

    payload = {
        "items": items,
        "total": total,
        "page": page,
        "page_size": page_size,
        "latest_order_date": max_day.isoformat() if "max_day" in locals() else None,
    }
    set_fine_table_cache(cache_key, payload)
    return payload
