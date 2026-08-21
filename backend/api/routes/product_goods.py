from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.encoders import jsonable_encoder
from pydantic import BaseModel, ConfigDict
from collections import defaultdict
from datetime import date, timedelta
import json
import re

from sqlalchemy import Text, and_, case, cast, delete, desc, false, func, inspect, or_, select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from api.product_goods_cache import (
    clear_product_goods_cache,
    get_product_goods_cache,
    get_product_goods_filter_options_cache,
    get_product_goods_risk_codes_cache,
    get_product_goods_snapshot_dates_cache,
    set_product_goods_cache,
    set_product_goods_filter_options_cache,
    set_product_goods_risk_codes_cache,
    set_product_goods_snapshot_dates_cache,
)
from api.operation_log_utils import write_operation_log
from api.routes.images import image_url_for
from domain.product_goods_schema import PRODUCT_GOODS_OVERRIDES_TABLE
from domain.product_goods_shop_channel_schema import PRODUCT_GOODS_SHOP_CHANNEL_MAPPINGS_TABLE
from domain.product_goods_historical_sales_schema import HISTORICAL_SALES_YEARS, product_goods_historical_sales_table_for_year
from domain.product_goods_historical_orders_schema import HISTORICAL_ORDER_START_YEAR, product_goods_historical_orders_table_for_year
from domain.product_goods_sales_period_schema import PRODUCT_GOODS_SALES_PERIODS_TABLE
from domain.product_goods_detail_snapshot_schema import (
    PRODUCT_GOODS_DETAIL_SNAPSHOT_BATCHES_TABLE,
    ensure_product_goods_detail_snapshot_tables,
    product_goods_detail_snapshots_table_for_year,
)
from domain.gj_schema import GJ_MERGED_PRODUCT_INFO_TABLE
from domain.schema import PRODUCT_TABLES
from domain.vip_schema import JST_SIZE_STOCK_TABLE, JST_STOCK_SUMMARY_TABLE
from domain.daily_sales_schema import jst_daily_sales_table_for_year, vip_daily_sales_table_for_year
from domain.factory_channel_sales import (
    channel_group as factory_channel_group,
    is_clearance_channel,
    platform_name,
    product_for_sale,
    product_index,
    sales_metrics,
    season_group,
    shop_channel_key,
)
from domain.factory_channel_sales_summary_schema import FACTORY_CHANNEL_SALES_DAILY_SUMMARY_TABLE
from domain.inventory_schema import SUPPLIER_TABLE
from domain.jst_full_stock_schema import JST_FULL_STOCK_TABLE
from domain.jst_stock_snapshot_schema import JST_SIZE_STOCK_SNAPSHOT_TABLE, JST_STOCK_SUMMARY_SNAPSHOT_TABLE


router = APIRouter()


def _consumer_sales_channel_condition(channel_column):
    channel = func.coalesce(channel_column, "")
    return and_(
        ~channel.ilike("%采购%"),
        ~channel.ilike("%-公司"),
        ~channel.ilike("%VMI%"),
    )


DEFAULT_BRAND = "cbanner_womens"
STANDARD_SIZE_COLUMNS = ["34", "35", "36", "37", "38", "39", "40", "41", "42", "43", "44"]
CLOG_SIZE_COLUMNS = ["225-230", "230-235", "235-240", "240-245", "245-250", "250-255"]
SIZE_COLUMNS = [*STANDARD_SIZE_COLUMNS, *CLOG_SIZE_COLUMNS]
SIZE_COLUMN_ORDER = {size: index for index, size in enumerate(SIZE_COLUMNS)}
PLATFORM_COLUMNS = ["唯品", "天猫", "得物", "拼多多", "京东", "商品卡", "直播赛道", "达播清仓", "拼多多清仓", "其他"]
SIZE_TO_STOCK_CODE = {str(size): str(50 + size * 5) for size in range(34, 45)}
STOCK_CODE_TO_SIZE = {value: key for key, value in SIZE_TO_STOCK_CODE.items()}
SALES_PERIOD_START_YEAR = 2024
LOW_STOCK_SALE_DAYS = 7
SHORTAGE_RISK_SALE_DAYS = 30
URGENT_SHORTAGE_RISK_SALE_DAYS = 20
HIGH_STOCK_SALE_DAYS = 90
CALCULATED_SNAPSHOT_FORMAT = "product_goods_calculated_snapshot_v1"
CALCULATED_SNAPSHOT_SOURCE_PATH = "database://product-goods/current"
CALCULATED_SNAPSHOT_SOURCE_WORKBOOK = "database_calculated_product_goods"
CALCULATED_SNAPSHOT_SOURCE_SHEET = "goods"
GJ_PRODUCT_GOODS_BRANDS = frozenset({"cbanner_mens", "cbanner_womens"})
GJ_PRODUCT_GOODS_FIELDS = (
    "goods_code",
    "original_goods_code",
    "factory_code",
    "product_name",
    "execution_standard",
    "launch_date",
    "insole_material",
    "outsole_material",
    "lining_material",
    "upper_material",
    "shoe_box_spec",
    "primary_supplier",
    "extra_fields",
)


class ProductGoodsUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    platform: str | None = None
    category_l4: str | None = None
    product_role: str | None = None
    product_type: str | None = None
    douyin_hot: str | None = None
    clearance: str | None = None
    remark: str | None = None
    expected_replenishment_stock: int | None = None
    replenishment_by_size: dict[str, int] | None = None
    replenishment_total: int | None = None
    post_replenishment_by_size: dict[str, int] | None = None
    post_replenishment_stock: int | None = None
    post_replenishment_total: int | None = None
    post_replenishment_turnover_days: float | None = None


class ProductGoodsExportLogRequest(BaseModel):
    brand: str
    brand_label: str | None = None
    exported_rows: int = 0
    total_rows: int | None = None
    view: Literal["goods", "style_summary"] = "goods"
    query: str | None = None
    filters: int = 0
    history_date: str | None = None
    column_count: int | None = None
    filename: str | None = None


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
    "expected_replenishment_stock",
    "replenishment_by_size",
    "replenishment_total",
    "post_replenishment_by_size",
    "post_replenishment_stock",
    "post_replenishment_total",
    "post_replenishment_turnover_days",
}


ProductGoodsFilterOperator = Literal["contains", "equals", "empty", "not_empty", "in", "not_in"]
PRODUCT_GOODS_FILTER_OPERATORS: set[str] = {"contains", "equals", "empty", "not_empty", "in", "not_in"}
PRODUCT_GOODS_FILTER_FIELDS = {
    "year",
    "season",
    "platform",
    "category_l4",
    "first_order_date",
    "factory_sku",
    "factory_code",
    "factory_name",
    "style_code",
    "goods_code",
    "color",
    "cost",
    "product_role",
    "product_type",
    "douyin_hot",
    "clearance",
    "remark",
}


class ProductGoodsFilter(BaseModel):
    model_config = ConfigDict(extra="forbid")

    field: str
    operator: ProductGoodsFilterOperator
    value: str | None = None
    values: list[str] | None = None


def _parse_product_goods_filters(raw_filters: str | None) -> tuple[ProductGoodsFilter, ...]:
    if not raw_filters:
        return ()
    try:
        payload = json.loads(raw_filters)
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=400, detail="筛选条件格式无效") from exc
    if not isinstance(payload, list) or len(payload) > 20:
        raise HTTPException(status_code=400, detail="筛选条件最多 20 条")
    filters: list[ProductGoodsFilter] = []
    for item in payload:
        if not isinstance(item, dict):
            raise HTTPException(status_code=400, detail="筛选条件格式无效")
        try:
            condition = ProductGoodsFilter.model_validate(item)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail="筛选条件格式无效") from exc
        condition.field = condition.field.strip()
        condition.value = condition.value.strip() if isinstance(condition.value, str) else None
        condition.values = [item.strip() for item in condition.values] if condition.values is not None else None
        if condition.field not in PRODUCT_GOODS_FILTER_FIELDS:
            raise HTTPException(status_code=400, detail=f"不支持按 {condition.field or '该字段'} 筛选")
        if condition.operator not in PRODUCT_GOODS_FILTER_OPERATORS:
            raise HTTPException(status_code=400, detail="筛选方式无效")
        if condition.operator in {"contains", "equals"} and not condition.value:
            raise HTTPException(status_code=400, detail="请输入筛选值")
        if condition.operator in {"in", "not_in"} and condition.values is None:
            raise HTTPException(status_code=400, detail="请选择筛选值")
        if condition.values is not None and len(condition.values) > 5_000:
            raise HTTPException(status_code=400, detail="单个字段最多选择 5000 个值")
        filters.append(condition)
    return tuple(filters)


def _product_goods_filter_condition(
    column,
    operator: ProductGoodsFilterOperator,
    value: str | None,
    values: list[str] | None = None,
):
    normalized = func.coalesce(func.trim(cast(column, Text)), "")
    if operator == "empty":
        return normalized == ""
    if operator == "not_empty":
        return normalized != ""
    if operator == "in":
        normalized_values = sorted({item.lower() for item in values or []})
        return func.lower(normalized).in_(normalized_values) if normalized_values else false()
    if operator == "not_in":
        normalized_values = sorted({item.lower() for item in values or []})
        return func.lower(normalized).not_in(normalized_values) if normalized_values else normalized == normalized
    if operator == "equals":
        return func.lower(normalized) == (value or "").lower()
    escaped_value = (value or "").replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return normalized.ilike(f"%{escaped_value}%", escape="\\")


def _uses_gj_product_goods_source(brand: str, snapshot_date: date | None) -> bool:
    return snapshot_date is None and brand in GJ_PRODUCT_GOODS_BRANDS


def _first_non_empty_expression(*columns):
    normalized_columns = [
        func.nullif(func.trim(cast(column, Text)), "")
        for column in columns
        if column is not None
    ]
    return func.coalesce(*normalized_columns, "")


def _product_goods_source_columns(product_table, gj_table=None) -> dict[str, Any]:
    if gj_table is None:
        return {
            "sku": product_table.c.sku,
            "original_sku": product_table.c.original_sku,
            "factory_sku": product_table.c.factory_sku,
            "supplier_name": product_table.c.supplier_name,
            "year": product_table.c.year,
            "season_category": product_table.c.season_category,
            "first_order_time": product_table.c.first_order_time,
            "color": product_table.c.color,
        }
    return {
        "sku": _first_non_empty_expression(gj_table.c.goods_code, product_table.c.sku),
        "original_sku": _first_non_empty_expression(
            gj_table.c.original_goods_code,
            gj_table.c.goods_code,
            product_table.c.original_sku,
            product_table.c.sku,
        ),
        "factory_sku": _first_non_empty_expression(gj_table.c.factory_code, product_table.c.factory_sku),
        "supplier_name": _first_non_empty_expression(gj_table.c.primary_supplier, product_table.c.supplier_name),
        "year": product_table.c.year,
        "season_category": product_table.c.season_category,
        "first_order_time": product_table.c.first_order_time,
        "color": product_table.c.color,
    }


def _product_goods_filter_columns(product_table, override, *, source_columns: dict[str, Any] | None = None):
    source = source_columns or _product_goods_source_columns(product_table)
    factory_code_column = (
        select(SUPPLIER_TABLE.c.factory_code)
        .where(SUPPLIER_TABLE.c.name == source["supplier_name"])
        .limit(1)
        .scalar_subquery()
    )
    return {
        "year": source["year"],
        "season": source["season_category"],
        "platform": override.c.platform,
        "category_l4": override.c.category_l4,
        "first_order_date": source["first_order_time"],
        "factory_sku": source["factory_sku"],
        "factory_code": factory_code_column,
        "factory_name": source["supplier_name"],
        "style_code": source["original_sku"],
        "goods_code": source["sku"],
        "color": source["color"],
        "cost": product_table.c.cost,
        "product_role": override.c.product_role,
        "product_type": _product_type_column(product_table, override, goods_code=source["sku"]),
        "douyin_hot": override.c.douyin_hot,
        "clearance": override.c.clearance,
        "remark": override.c.remark,
    }


def _product_type_column(product_table, override, *, goods_code=None):
    product_code = goods_code if goods_code is not None else product_table.c.sku
    return func.coalesce(
        func.nullif(func.trim(override.c.product_type), ""),
        case(
            (func.upper(func.trim(cast(product_code, Text))).like("KT%"), "洞洞鞋"),
            else_=None,
        ),
    )


def _product_type_value(value: object, goods_code: object) -> str | None:
    product_type = str(value or "").strip()
    if product_type:
        return product_type
    return "洞洞鞋" if str(goods_code or "").strip().upper().startswith("KT") else None


def _product_goods_conditions(
    product_table,
    override,
    *,
    query: str,
    platform: str,
    year: str,
    filters: tuple[ProductGoodsFilter, ...],
    source_columns: dict[str, Any] | None = None,
) -> list:
    source = source_columns or _product_goods_source_columns(product_table)
    conditions = []
    if query:
        query_terms = [
            term.strip()
            for term in re.split(r"[,，\n]+", query)
            if term.strip()
        ]
        if query_terms:
            conditions.append(or_(*(
                or_(
                    cast(source["sku"], Text).ilike(f"%{term}%"),
                    cast(source["original_sku"], Text).ilike(f"%{term}%"),
                    cast(source["factory_sku"], Text).ilike(f"%{term}%"),
                    cast(source["color"], Text).ilike(f"%{term}%"),
                )
                for term in query_terms
            )))
    if year:
        conditions.append(cast(source["year"], Text).ilike(f"%{year}%"))
    if platform:
        conditions.append(override.c.platform == platform)
    columns = _product_goods_filter_columns(product_table, override, source_columns=source)
    grouped_filters: dict[str, list] = defaultdict(list)
    for product_filter in filters:
        grouped_filters[product_filter.field].append(
            _product_goods_filter_condition(
                columns[product_filter.field],
                product_filter.operator,
                product_filter.value,
                product_filter.values,
            )
        )
    conditions.extend(or_(*field_conditions) for field_conditions in grouped_filters.values())
    return conditions


def _shortage_risk_product_codes(
    connection,
    product_table,
    *,
    brand: str,
    snapshot_date: date | None = None,
) -> set[str]:
    cached_codes = get_product_goods_risk_codes_cache(brand, snapshot_date)
    if cached_codes is not None:
        return set(cached_codes)
    product_codes = {
        str(product_code).strip()
        for product_code in connection.execute(select(product_table.c.sku)).scalars()
        if str(product_code or "").strip()
    }
    if not product_codes:
        return set()

    # Historical views are rendered from the immutable product-goods snapshot.
    # Do the risk filtering from that same payload so a row marked as broken-size
    # in the table is not excluded by the current inventory source.
    if snapshot_date is not None:
        snapshot_table = product_goods_detail_snapshots_table_for_year(snapshot_date.year)
        if inspect(connection).has_table(snapshot_table.name):
            matched_codes: set[str] = set()
            rows = connection.execute(
                select(snapshot_table.c.goods_code, snapshot_table.c.data)
                .where(snapshot_table.c.brand == brand)
                .where(snapshot_table.c.snapshot_date == snapshot_date)
                .where(snapshot_table.c.goods_code.in_(product_codes))
            ).mappings()
            for row in rows:
                product_code = str(row["goods_code"] or "").strip()
                data = row["data"] if isinstance(row["data"], dict) else {}
                metrics = data.get("metrics") if isinstance(data.get("metrics"), dict) else {}
                inventory_by_size = data.get("inventory_by_size") if isinstance(data.get("inventory_by_size"), dict) else {}
                shortage_by_size = data.get("shortage_by_size") if isinstance(data.get("shortage_by_size"), dict) else {}
                shortage_total = int(metrics.get("shortage_total") or sum(int(value or 0) for value in shortage_by_size.values()))
                broken_size, biased_size = _size_inventory_risk_flags(inventory_by_size)
                zero_inventory = bool(inventory_by_size) and sum(int(value or 0) for value in inventory_by_size.values()) <= 0
                stock_sale_days = metrics.get("stock_sale_days")
                if (
                    shortage_total > 0
                    or (isinstance(stock_sale_days, (int, float)) and stock_sale_days <= SHORTAGE_RISK_SALE_DAYS)
                    or broken_size
                    or biased_size
                    or zero_inventory
                ):
                    matched_codes.add(product_code)
            set_product_goods_risk_codes_cache(brand, matched_codes, snapshot_date)
            return matched_codes

    code_lengths = sorted({len(product_code) for product_code in product_codes}, reverse=True)
    attributes: dict[str, dict[str, Any]] = {}
    if inspect(connection).has_table(JST_FULL_STOCK_TABLE.name):
        source_rows = connection.execute(
            select(
                JST_FULL_STOCK_TABLE.c.product_code,
                JST_FULL_STOCK_TABLE.c.size,
                JST_FULL_STOCK_TABLE.c.available_qty,
                JST_FULL_STOCK_TABLE.c.stock_sale_days,
                JST_FULL_STOCK_TABLE.c.actual_stock_qty,
                JST_FULL_STOCK_TABLE.c.purchase_warehouse_stock_qty,
                JST_FULL_STOCK_TABLE.c.purchase_in_transit_qty,
                JST_FULL_STOCK_TABLE.c.transfer_in_transit_qty,
                JST_FULL_STOCK_TABLE.c.return_in_transit_qty,
            )
        ).mappings()
        for row in source_rows:
            source_code = str(row["product_code"] or "").strip()
            matched_code = next(
                (source_code[:length] for length in code_lengths if source_code[:length] in product_codes),
                None,
            )
            if matched_code is None:
                continue
            attribute = attributes.setdefault(
                matched_code,
                {"has_shortage": False, "stock_sale_days": [], "inventory_by_size": {}},
            )
            if int(row["available_qty"] or 0) < 0:
                attribute["has_shortage"] = True
            if row["stock_sale_days"] is not None:
                attribute["stock_sale_days"].append(float(row["stock_sale_days"]))
            size = _full_stock_size(row["size"])
            if size is not None:
                inventory_quantity = (
                    int(row["actual_stock_qty"] or 0)
                    + int(row["purchase_warehouse_stock_qty"] or 0)
                    + int(row["purchase_in_transit_qty"] or 0)
                    + int(row["transfer_in_transit_qty"] or 0)
                    + int(row["return_in_transit_qty"] or 0)
                )
                inventory_by_size = attribute["inventory_by_size"]
                inventory_by_size[size] = inventory_by_size.get(size, 0) + inventory_quantity

    # Some goods have no row in jst_full_stock, while jst_size_stock still
    # contains zero-valued size rows. Those rows are exactly what the goods list
    # uses as its fallback and must participate in the same risk filter.
    fallback_codes = [code for code in product_codes if code not in attributes]
    if fallback_codes and inspect(connection).has_table(JST_SIZE_STOCK_TABLE.name):
        size_rows = connection.execute(
            select(
                JST_SIZE_STOCK_TABLE.c.product_code,
                JST_SIZE_STOCK_TABLE.c.size,
                JST_SIZE_STOCK_TABLE.c.stock_qty,
            )
            .where(JST_SIZE_STOCK_TABLE.c.product_code.in_(fallback_codes))
        ).mappings()
        for row in size_rows:
            product_code = str(row["product_code"] or "").strip()
            size = STOCK_CODE_TO_SIZE.get(str(row["size"] or "").strip()) or _size_from_color_spec(row["size"])
            if not product_code or not size:
                continue
            attribute = attributes.setdefault(
                product_code,
                {"has_shortage": False, "stock_sale_days": [], "inventory_by_size": {}},
            )
            inventory_by_size = attribute["inventory_by_size"]
            inventory_by_size[size] = inventory_by_size.get(size, 0) + int(row["stock_qty"] or 0)

    matched_codes: set[str] = set()
    for product_code, attribute in attributes.items():
        stock_sale_days = attribute["stock_sale_days"]
        broken_size, biased_size = _size_inventory_risk_flags(attribute["inventory_by_size"])
        zero_inventory = bool(attribute["inventory_by_size"]) and sum(attribute["inventory_by_size"].values()) <= 0
        if (
            attribute["has_shortage"]
            or (stock_sale_days and min(stock_sale_days) <= SHORTAGE_RISK_SALE_DAYS)
            or broken_size
            or biased_size
            or zero_inventory
        ):
            matched_codes.add(product_code)
    set_product_goods_risk_codes_cache(brand, matched_codes, snapshot_date)
    return matched_codes


def _style_summary_expression(product_table, *, source_columns: dict[str, Any] | None = None):
    source = source_columns or _product_goods_source_columns(product_table)
    style_code = _first_non_empty_expression(source["original_sku"], source["sku"])
    return func.regexp_replace(style_code, r".{2}$", "")


def _gj_product_goods_select_columns():
    return [
        GJ_MERGED_PRODUCT_INFO_TABLE.c[field].label(f"_gj_{field}")
        for field in GJ_PRODUCT_GOODS_FIELDS
    ]


def _merge_gj_product_goods_row(row: dict[str, Any]) -> dict[str, Any]:
    merged = dict(row)

    def gj_value(field: str) -> Any:
        value = merged.get(f"_gj_{field}")
        return value if value not in (None, "") else None

    goods_code = gj_value("goods_code")
    original_goods_code = gj_value("original_goods_code") or goods_code
    field_mapping = {
        "sku": goods_code,
        "original_sku": original_goods_code,
        "factory_sku": gj_value("factory_code"),
        "product_model": gj_value("product_name"),
        "execution_standard": gj_value("execution_standard"),
        "launch_date": gj_value("launch_date"),
        "insole_material": gj_value("insole_material"),
        "outsole_material": gj_value("outsole_material"),
        "lining_material": gj_value("lining_material"),
        "upper_material": gj_value("upper_material"),
        "shoe_box_spec": gj_value("shoe_box_spec"),
        "supplier_name": gj_value("primary_supplier"),
        "extra_fields": gj_value("extra_fields"),
    }
    for field, value in field_mapping.items():
        if value is not None:
            merged[field] = value
    return merged


def _base_style_code(value: object) -> str:
    style_code = str(value or "").strip()
    return style_code[:-2] if len(style_code) > 2 else style_code


def _style_summary_key(row: dict[str, Any]) -> str:
    return _base_style_code(row.get("style_code") or row.get("goods_code"))


def _sum_mapping_values(items: list[dict[str, Any]], field: str) -> dict[str, int]:
    totals: dict[str, int] = {}
    for item in items:
        values = item.get(field)
        if not isinstance(values, dict):
            continue
        for key, raw_value in values.items():
            try:
                numeric_value = int(raw_value or 0)
            except (TypeError, ValueError):
                continue
            totals[str(key)] = totals.get(str(key), 0) + numeric_value
    return totals


def _sum_metric_values(items: list[dict[str, Any]], key: str) -> int | float | None:
    values: list[int | float] = []
    for item in items:
        raw_value = (item.get("metrics") or {}).get(key)
        if isinstance(raw_value, bool) or not isinstance(raw_value, (int, float)):
            continue
        values.append(raw_value)
    return sum(values) if values else None


def _first_distinct_value(items: list[dict[str, Any]], field: str) -> Any:
    values = []
    for item in items:
        value = item.get(field)
        if value is None or value == "":
            continue
        if value not in values:
            values.append(value)
    if not values:
        return None
    return values[0] if len(values) == 1 else "、".join(str(value) for value in values)


def _style_summary_item(style_code: str, items: list[dict[str, Any]]) -> dict[str, Any]:
    representative = items[0]
    metrics = dict(representative.get("metrics") or {})
    metric_keys = set().union(*(set((item.get("metrics") or {}).keys()) for item in items))
    summed_metric_keys = {
        "total_order_count",
        "total_sales",
        "stock_plus_purchase",
        "in_transit_total",
        "return_qty",
        "post_replenishment_stock",
        "day_over_day",
        "yesterday_sales",
        "normal_shelf_sales",
        "clearance_sales",
        "week_sales",
        "normal_shelf_week_sales",
        "clearance_week_sales",
        "last_week_sales",
        "same_week_sales",
        "same_week_non_douyin_sales",
        "shortage_total",
        "sales_size_total",
        "replenishment_total",
        "post_replenishment_total",
        "three_day_change",
        "sales_2024",
        "sales_2025",
        "year_sales",
        "month_sales",
    }
    for key in metric_keys.intersection(summed_metric_keys):
        metrics[key] = _sum_metric_values(items, key)

    stock_total = sum(int(item.get("stock_total") or 0) for item in items)
    in_transit_total = sum(int(item.get("in_transit_total") or 0) for item in items)
    inventory_total = sum(int(item.get("inventory_total") or 0) for item in items)
    shortage_total = int(metrics.get("shortage_total") or 0)
    metrics["stock_plus_purchase"] = stock_total
    metrics["in_transit_total"] = in_transit_total
    metrics["shortage_total"] = shortage_total
    metrics["post_replenishment_turnover_days"] = None
    metrics["stock_health"] = _stock_health_label(
        None,
        shortage_total,
    )
    metrics["broken_size_sku"] = None

    return {
        **representative,
        "id": representative["id"],
        "is_style_summary": True,
        "style_code": style_code,
        "goods_code": style_code,
        "color": None,
        "year": _first_distinct_value(items, "year"),
        "season": _first_distinct_value(items, "season"),
        "platform": _first_distinct_value(items, "platform"),
        "category_l4": _first_distinct_value(items, "category_l4"),
        "first_order_date": _first_distinct_value(items, "first_order_date"),
        "factory_sku": _first_distinct_value(items, "factory_sku"),
        "factory_code": _first_distinct_value(items, "factory_code"),
        "factory_name": _first_distinct_value(items, "factory_name"),
        "cost": _first_distinct_value(items, "cost"),
        "product_role": _first_distinct_value(items, "product_role"),
        "product_type": _first_distinct_value(items, "product_type"),
        "douyin_hot": _first_distinct_value(items, "douyin_hot"),
        "clearance": _first_distinct_value(items, "clearance"),
        "remark": _first_distinct_value(items, "remark"),
        "stock_by_size": _sum_mapping_values(items, "stock_by_size"),
        "stock_total": stock_total,
        "in_transit_total": in_transit_total,
        "inventory_total": inventory_total,
        "daily_sales_by_date": _sum_mapping_values(items, "daily_sales_by_date"),
        "annual_sales": _sum_mapping_values(items, "annual_sales"),
        "monthly_sales": _sum_mapping_values(items, "monthly_sales"),
        "platform_sales": _sum_mapping_values(items, "platform_sales"),
        "daily_platform_sales": _sum_mapping_values(items, "daily_platform_sales"),
        "weekly_platform_sales": _sum_mapping_values(items, "weekly_platform_sales"),
        "monthly_platform_sales": _sum_mapping_values(items, "monthly_platform_sales"),
        "in_transit_by_size": _sum_mapping_values(items, "in_transit_by_size"),
        "inventory_by_size": _sum_mapping_values(items, "inventory_by_size"),
        "shortage_by_size": _sum_mapping_values(items, "shortage_by_size"),
        "sales_by_size": _sum_mapping_values(items, "sales_by_size"),
        "replenishment_by_size": _sum_mapping_values(items, "replenishment_by_size"),
        "post_replenishment_by_size": _sum_mapping_values(items, "post_replenishment_by_size"),
        "metrics": metrics,
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
        raw_size = str(row["size"] or "").strip()
        size = STOCK_CODE_TO_SIZE.get(raw_size) or _size_from_color_spec(raw_size) or raw_size
        if code and size:
            result.setdefault(code, {})[size] = int(row["quantity"] or 0)
    return result


def _full_stock_size(value: object) -> str | None:
    """Return a display size only when the source value maps to one exact size."""
    normalized = str(value or "").strip()
    if normalized.endswith(".0") and normalized[:-2].isdigit():
        normalized = normalized[:-2]
    return STOCK_CODE_TO_SIZE.get(normalized) or _size_from_color_spec(normalized)


def _stock_health_label(
    stock_sale_days: float | None,
    shortage_total: int,
    broken_size: bool = False,
    biased_size: bool = False,
) -> str | None:
    labels: list[str] = []
    if shortage_total > 0:
        labels.append("缺货")
    if broken_size:
        labels.append("断码")
    if biased_size:
        labels.append("偏码")
    if stock_sale_days is not None:
        if stock_sale_days <= URGENT_SHORTAGE_RISK_SALE_DAYS:
            labels.append("周转≤20天")
        elif stock_sale_days <= SHORTAGE_RISK_SALE_DAYS:
            labels.append("周转≤30天")
    if labels:
        return "、".join(labels)
    if stock_sale_days is None:
        return None
    if stock_sale_days >= HIGH_STOCK_SALE_DAYS:
        return "积压风险"
    return "正常"


def _size_inventory_risk_flags(
    inventory_by_size: dict[str, int],
) -> tuple[bool, bool]:
    values = [
        int(quantity or 0)
        for size, quantity in sorted(
            inventory_by_size.items(),
            key=lambda item: SIZE_COLUMN_ORDER.get(item[0], len(SIZE_COLUMNS)),
        )
        if size in SIZE_COLUMNS
    ]
    if not values:
        return False, False
    broken_size = any(quantity < 2 for quantity in values)
    total = sum(values)
    if total <= 0:
        return broken_size, False
    first_three = sum(values[:3])
    last_three = sum(values[-3:])
    biased_size = first_three / total > 0.7 or last_three / total > 0.7
    return broken_size, biased_size


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


def _product_goods_snapshot_dates(connection, *, brand: str) -> list[date]:
    cached = get_product_goods_snapshot_dates_cache(brand)
    if cached is not None:
        return [date.fromisoformat(item) for item in cached]

    stock_snapshot_dates = [
        item
        for item in connection.execute(
            select(JST_SIZE_STOCK_SNAPSHOT_TABLE.c.snapshot_date)
            .distinct()
            .order_by(desc(JST_SIZE_STOCK_SNAPSHOT_TABLE.c.snapshot_date))
        ).scalars()
        if isinstance(item, date)
    ]
    snapshot_dates = sorted({*stock_snapshot_dates, *_detail_snapshot_dates(connection, brand=brand)}, reverse=True)
    set_product_goods_snapshot_dates_cache(brand, [item.isoformat() for item in snapshot_dates])
    return snapshot_dates


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


def get_current_inventory_summary(
    request: Request,
    *,
    brand: str,
    year_label: str,
) -> dict[str, object]:
    """Summarize current stock without joining every stock row to every product."""
    if brand not in PRODUCT_TABLES:
        raise HTTPException(status_code=400, detail=f"Invalid brand: {brand}")
    normalized_year_label = str(year_label or "").strip()
    if not normalized_year_label:
        raise HTTPException(status_code=400, detail="商品年份季节不能为空")

    product_table = PRODUCT_TABLES[brand]
    repository = request.app.state.repository
    with repository.engine.connect() as connection:
        stock_date = connection.execute(
            select(func.max(JST_FULL_STOCK_TABLE.c.sync_date))
        ).scalar()
        cache_key = (
            "current-inventory-summary-v1",
            brand,
            normalized_year_label,
            stock_date.isoformat() if isinstance(stock_date, date) else None,
        )
        cached = get_product_goods_cache(cache_key)
        if cached is not None:
            return cached

        product_codes = sorted(
            {
                str(value or "").strip()
                for value in connection.execute(
                    select(product_table.c.sku).where(
                        product_table.c.deleted_at.is_(None),
                        product_table.c.year == normalized_year_label,
                    )
                ).scalars()
                if str(value or "").strip()
            }
        )
        stock_by_product = _current_full_stock_payload(connection, product_codes)

    stock_total = sum(int(item.get("stock_total") or 0) for item in stock_by_product.values())
    in_transit_total = sum(
        int(item.get("in_transit_total") or 0)
        for item in stock_by_product.values()
    )
    payload: dict[str, object] = {
        "year_label": normalized_year_label,
        "product_count": len(product_codes),
        "matched_product_count": len(stock_by_product),
        "stock_total": stock_total,
        "in_transit_total": in_transit_total,
        "inventory_total": stock_total + in_transit_total,
        "source_as_of_date": stock_date.isoformat() if isinstance(stock_date, date) else None,
    }
    set_product_goods_cache(cache_key, payload)
    return payload


def _manual_size_quantities(
    value: object,
    *,
    allow_negative: bool = False,
) -> dict[str, int]:
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
        if allow_negative or normalized_quantity >= 0:
            quantities[normalized_size] = normalized_quantity
    return quantities


def _manual_number(value: object) -> int | float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return value if value >= 0 else None


def _allocate_replenishment_by_sales(
    expected_replenishment_stock: int | float | None,
    post_replenishment_total: int,
    inventory_by_size: dict[str, int],
    sales_by_size: dict[str, int],
) -> dict[str, int]:
    if expected_replenishment_stock is None:
        return {}
    weights = [
        (size, int(quantity))
        for size, quantity in sales_by_size.items()
        if size in SIZE_COLUMNS and int(quantity) > 0
    ]
    total_sales = sum(quantity for _, quantity in weights)
    if total_sales == 0:
        return {}

    target_by_size: dict[str, int] = {}
    remainders: list[tuple[int, int, str]] = []
    targeted = 0
    for size, quantity in weights:
        target_quantity, remainder = divmod(
            post_replenishment_total * quantity,
            total_sales,
        )
        target_by_size[size] = target_quantity
        targeted += target_quantity
        remainders.append((remainder, -SIZE_COLUMN_ORDER[size], size))
    for _, _, size in sorted(remainders, reverse=True)[: post_replenishment_total - targeted]:
        target_by_size[size] += 1
    return {
        size: target_by_size.get(size, 0) - int(inventory_by_size.get(size, 0))
        for size in sorted(
            set(inventory_by_size) | set(target_by_size),
            key=lambda size: SIZE_COLUMN_ORDER.get(size, len(SIZE_COLUMNS)),
        )
    }


def _post_replenishment_inventory_by_size(
    inventory_by_size: dict[str, int],
    replenishment_by_size: dict[str, int],
) -> dict[str, int]:
    return {
        size: int(inventory_by_size.get(size, 0))
        + int(replenishment_by_size.get(size, 0))
        for size in sorted(
            set(inventory_by_size) | set(replenishment_by_size),
            key=lambda size: SIZE_COLUMN_ORDER.get(size, len(SIZE_COLUMNS)),
        )
    }


def _post_replenishment_turnover_days(
    post_replenishment_total: int | None,
    recent_14_day_sales: int | None,
) -> float | None:
    if post_replenishment_total is None or recent_14_day_sales is None or recent_14_day_sales <= 0:
        return None
    return round(post_replenishment_total * 14 / recent_14_day_sales, 1)


def _snapshot_value(values: dict[str, object], key: str, fallback: object) -> object:
    return values[key] if key in values and values[key] is not None else fallback


def _size_from_color_spec(value: object) -> str | None:
    text = str(value or "")
    matched = re.search(r"(?<!\d)(3[4-9]|4[0-4])(?!\d)", text)
    if matched:
        return matched.group(1)
    normalized = re.sub(r"[\s~\u301c\u2014\u2013/\u81f3]+", "-", text)
    for size in CLOG_SIZE_COLUMNS:
        if re.search(rf"(?<!\d){re.escape(size)}(?!\d)", normalized):
            return size
    return None


def _shop_channel_key(value: object) -> str:
    return shop_channel_key(value)


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
    return platform_name(channel, shop_channel_mappings)


def _is_clearance_channel(channel: object, platform: str) -> bool:
    return is_clearance_channel(channel, platform)


def _factory_dashboard_season(value: object) -> str | None:
    return season_group(value)


def _factory_dashboard_channel_group(channel: object, shop_channel_mappings: dict[str, str]) -> str:
    return factory_channel_group(channel, shop_channel_mappings)


def _factory_dashboard_product_index(rows: list[dict[str, object]]) -> tuple[
    dict[str, dict[str, object]],
    dict[str, list[dict[str, object]]],
    dict[str, str],
]:
    return product_index(rows)


def _factory_dashboard_product_for_sale(
    product_code: object,
    style_code: object,
    *,
    by_sku: dict[str, dict[str, object]],
    by_prefix: dict[str, list[dict[str, object]]],
    unique_style_matches: dict[str, str],
) -> dict[str, object] | None:
    return product_for_sale(
        product_code,
        style_code,
        by_sku=by_sku,
        by_prefix=by_prefix,
        unique_style_matches=unique_style_matches,
    )


def _factory_dashboard_available_sales_years(engine) -> list[int]:
    inspector = inspect(engine)
    available_years: list[int] = []
    for sales_year in range(SALES_PERIOD_START_YEAR, date.today().year + 1):
        historical_table = product_goods_historical_sales_table_for_year(sales_year)
        jst_table = jst_daily_sales_table_for_year(sales_year)
        vip_table = vip_daily_sales_table_for_year(sales_year)
        if any(inspector.has_table(table.name) for table in (historical_table, jst_table, vip_table)):
            available_years.append(sales_year)
    return available_years


def _factory_dashboard_sales_rows(
    connection,
    engine,
    *,
    brand: str,
    sales_year: int,
    date_start: date | None,
    date_end: date | None,
) -> tuple[list[dict[str, object]], date | None]:
    inspector = inspect(engine)
    historical_table = product_goods_historical_sales_table_for_year(sales_year)
    jst_table = jst_daily_sales_table_for_year(sales_year)
    vip_table = vip_daily_sales_table_for_year(sales_year)
    rows: list[dict[str, object]] = []
    latest_date: date | None = None

    def collect(statement, *, source: str) -> None:
        nonlocal latest_date
        for row in connection.execute(statement).mappings():
            sales_date = row["sales_date"]
            if isinstance(sales_date, date) and (latest_date is None or sales_date > latest_date):
                latest_date = sales_date
            rows.append({**dict(row), "source": source})

    # Historical workbooks cover 2024/2025 in full. Prefer them over any partial
    # daily-table backfill for the same year so annual sales are not double counted.
    if inspector.has_table(historical_table.name):
        statement = (
            select(
                historical_table.c.product_code,
                historical_table.c.original_sku.label("style_code"),
                historical_table.c.channel,
                func.max(historical_table.c.sales_date).label("sales_date"),
                func.sum(historical_table.c.sales_quantity).label("quantity"),
                func.sum(historical_table.c.sales_quantity).label("gross_quantity"),
                func.sum(historical_table.c.sales_quantity * 0).label("return_quantity"),
            )
            .where(historical_table.c.brand == brand)
            .group_by(
                historical_table.c.product_code,
                historical_table.c.original_sku,
                historical_table.c.channel,
            )
        )
        if date_start is not None:
            statement = statement.where(historical_table.c.sales_date >= date_start)
        if date_end is not None:
            statement = statement.where(historical_table.c.sales_date <= date_end)
        collect(statement, source="historical")
        return rows, latest_date

    if inspector.has_table(FACTORY_CHANNEL_SALES_DAILY_SUMMARY_TABLE.name):
        summary_conditions = [
            FACTORY_CHANNEL_SALES_DAILY_SUMMARY_TABLE.c.brand == brand,
            FACTORY_CHANNEL_SALES_DAILY_SUMMARY_TABLE.c.sales_date >= date(sales_year, 1, 1),
            FACTORY_CHANNEL_SALES_DAILY_SUMMARY_TABLE.c.sales_date <= date(sales_year, 12, 31),
        ]
        if date_start is not None:
            summary_conditions.append(FACTORY_CHANNEL_SALES_DAILY_SUMMARY_TABLE.c.sales_date >= date_start)
        if date_end is not None:
            summary_conditions.append(FACTORY_CHANNEL_SALES_DAILY_SUMMARY_TABLE.c.sales_date <= date_end)
        summary_bounds = connection.execute(
            select(
                func.min(FACTORY_CHANNEL_SALES_DAILY_SUMMARY_TABLE.c.sales_date),
                func.max(FACTORY_CHANNEL_SALES_DAILY_SUMMARY_TABLE.c.sales_date),
            )
            .where(*summary_conditions)
            .where(FACTORY_CHANNEL_SALES_DAILY_SUMMARY_TABLE.c.match_status == "date_marker")
        ).one()
        raw_bounds: list[tuple[date, date]] = []
        for raw_table in (jst_table, vip_table):
            if not inspector.has_table(raw_table.name):
                continue
            raw_conditions = [
                raw_table.c.sales_date >= date(sales_year, 1, 1),
                raw_table.c.sales_date <= date(sales_year, 12, 31),
            ]
            if date_start is not None:
                raw_conditions.append(raw_table.c.sales_date >= date_start)
            if date_end is not None:
                raw_conditions.append(raw_table.c.sales_date <= date_end)
            raw_min, raw_max = connection.execute(
                select(func.min(raw_table.c.sales_date), func.max(raw_table.c.sales_date)).where(*raw_conditions)
            ).one()
            if isinstance(raw_min, date) and isinstance(raw_max, date):
                raw_bounds.append((raw_min, raw_max))
        expected_bounds = (
            min(bounds[0] for bounds in raw_bounds),
            max(bounds[1] for bounds in raw_bounds),
        ) if raw_bounds else (None, None)
        if tuple(summary_bounds) == expected_bounds and isinstance(summary_bounds[1], date):
            latest_date = summary_bounds[1]
            statement = (
                select(
                    FACTORY_CHANNEL_SALES_DAILY_SUMMARY_TABLE.c.product_code,
                    FACTORY_CHANNEL_SALES_DAILY_SUMMARY_TABLE.c.channel_group,
                    FACTORY_CHANNEL_SALES_DAILY_SUMMARY_TABLE.c.match_status,
                    func.max(FACTORY_CHANNEL_SALES_DAILY_SUMMARY_TABLE.c.sales_date).label("sales_date"),
                    func.sum(FACTORY_CHANNEL_SALES_DAILY_SUMMARY_TABLE.c.quantity).label("quantity"),
                    func.sum(FACTORY_CHANNEL_SALES_DAILY_SUMMARY_TABLE.c.gross_quantity).label("gross_quantity"),
                    func.sum(FACTORY_CHANNEL_SALES_DAILY_SUMMARY_TABLE.c.return_quantity).label("return_quantity"),
                )
                .where(*summary_conditions)
                .where(FACTORY_CHANNEL_SALES_DAILY_SUMMARY_TABLE.c.match_status != "date_marker")
                .group_by(
                    FACTORY_CHANNEL_SALES_DAILY_SUMMARY_TABLE.c.product_code,
                    FACTORY_CHANNEL_SALES_DAILY_SUMMARY_TABLE.c.channel_group,
                    FACTORY_CHANNEL_SALES_DAILY_SUMMARY_TABLE.c.match_status,
                )
            )
            for row in connection.execute(statement).mappings():
                rows.append({**dict(row), "source": "summary", "preaggregated": True})
            return rows, latest_date

    if inspector.has_table(jst_table.name):
        statement = (
            select(
                jst_table.c.product_code,
                jst_table.c.style_code,
                jst_table.c.channel,
                jst_table.c.sales_date,
                func.sum(func.coalesce(jst_table.c.net_sales_quantity, 0)).label("quantity"),
                func.sum(func.coalesce(jst_table.c.sales_quantity, 0)).label("gross_quantity"),
                func.sum(func.coalesce(jst_table.c.return_quantity, 0)).label("return_quantity"),
            )
            .group_by(
                jst_table.c.product_code,
                jst_table.c.style_code,
                jst_table.c.channel,
                jst_table.c.sales_date,
            )
            .where(_consumer_sales_channel_condition(jst_table.c.channel))
            .where(func.coalesce(jst_table.c.net_sales_quantity, 0) != 0)
        )
        if date_start is not None:
            statement = statement.where(jst_table.c.sales_date >= date_start)
        if date_end is not None:
            statement = statement.where(jst_table.c.sales_date <= date_end)
        collect(statement, source="jst")

    if inspector.has_table(vip_table.name):
        statement = (
            select(
                vip_table.c.goods_code.label("product_code"),
                vip_table.c.style_code,
                vip_table.c.sales_date,
                func.sum(func.coalesce(vip_table.c.sales_quantity, 0)).label("quantity"),
                func.sum(func.coalesce(vip_table.c.sales_quantity, 0)).label("gross_quantity"),
                func.sum(func.coalesce(vip_table.c.sales_quantity, 0) * 0).label("return_quantity"),
            )
            .group_by(
                vip_table.c.goods_code,
                vip_table.c.style_code,
                vip_table.c.sales_date,
            )
            .where(func.coalesce(vip_table.c.sales_quantity, 0) != 0)
        )
        if date_start is not None:
            statement = statement.where(vip_table.c.sales_date >= date_start)
        if date_end is not None:
            statement = statement.where(vip_table.c.sales_date <= date_end)
        for row in connection.execute(statement).mappings():
            sales_date = row["sales_date"]
            if isinstance(sales_date, date) and (latest_date is None or sales_date > latest_date):
                latest_date = sales_date
            rows.append({**dict(row), "channel": "唯品", "source": "vip"})
    return rows, latest_date


@router.get("/product-goods/factory-channel-dashboard")
def get_factory_channel_dashboard(
    request: Request,
    brand: str = Query("cbanner_mens"),
    sales_year: int | None = None,
    product_year: str | None = None,
    date_start: date | None = None,
    date_end: date | None = None,
):
    """Aggregate seasonal factory styles and sales by traditional, live and clearance channels."""
    if brand not in PRODUCT_TABLES:
        raise HTTPException(status_code=400, detail=f"Invalid brand: {brand}")
    if date_start is not None and date_end is not None and date_start > date_end:
        raise HTTPException(status_code=400, detail="开始日期不能晚于结束日期")

    repository = request.app.state.repository
    available_sales_years = _factory_dashboard_available_sales_years(repository.engine)
    selected_sales_year = sales_year or (available_sales_years[-1] if available_sales_years else date.today().year)
    if selected_sales_year < SALES_PERIOD_START_YEAR or selected_sales_year > date.today().year:
        raise HTTPException(status_code=400, detail="销售年份无效")
    normalized_product_year = str(product_year or "").strip()
    cache_key = (
        "factory-channel-dashboard-v2",
        brand,
        selected_sales_year,
        normalized_product_year,
        date_start.isoformat() if date_start else "",
        date_end.isoformat() if date_end else "",
    )
    cached = get_product_goods_cache(cache_key)
    if cached is not None:
        return cached

    product_table = PRODUCT_TABLES[brand]
    with repository.engine.connect() as connection:
        product_statement = select(
            product_table.c.sku,
            product_table.c.original_sku,
            product_table.c.supplier_name,
            product_table.c.season_category,
            product_table.c.year,
        ).where(product_table.c.deleted_at.is_(None)).where(product_table.c.sku.is_not(None))
        if normalized_product_year:
            product_statement = product_statement.where(product_table.c.year.ilike(f"%{normalized_product_year}%"))
        product_rows = [dict(row) for row in connection.execute(product_statement).mappings()]
        product_year_rows = connection.execute(
            select(product_table.c.year)
            .where(product_table.c.year.is_not(None))
            .where(func.trim(product_table.c.year) != "")
            .distinct()
            .order_by(product_table.c.year.desc())
        ).scalars().all()
        supplier_names = sorted({str(row.get("supplier_name") or "").strip() for row in product_rows if str(row.get("supplier_name") or "").strip()})
        supplier_codes = {
            str(row["name"]): str(row["factory_code"] or "").strip() or None
            for row in connection.execute(
                select(SUPPLIER_TABLE.c.name, SUPPLIER_TABLE.c.factory_code)
                .where(SUPPLIER_TABLE.c.name.in_(supplier_names))
            ).mappings()
        } if supplier_names else {}
        sales_rows, latest_sales_date = _factory_dashboard_sales_rows(
            connection,
            repository.engine,
            brand=brand,
            sales_year=selected_sales_year,
            date_start=date_start,
            date_end=date_end,
        )
        shop_channel_mappings = _shop_channel_mapping_payload(connection, brand)

    by_sku, by_prefix, unique_style_matches = _factory_dashboard_product_index(product_rows)
    season_items: dict[str, dict[tuple[str, str | None], dict[str, object]]] = {
        "spring_summer": {},
        "autumn_winter": {},
    }
    unclassified_style_codes: set[str] = set()
    for product in product_rows:
        factory_name = str(product.get("supplier_name") or "").strip() or "未维护工厂"
        factory_code = supplier_codes.get(factory_name)
        factory_key = (factory_name, factory_code)
        season = _factory_dashboard_season(product.get("season_category"))
        style_code = _base_style_code(product.get("original_sku") or product.get("sku"))
        if not season:
            if style_code:
                unclassified_style_codes.add(style_code)
            continue
        item = season_items[season].setdefault(factory_key, {
            "factory_name": factory_name,
            "factory_code": factory_code,
            "style_codes": set(),
            "total_sales": 0,
            "total_net_sales": 0,
            "total_returns": 0,
            "traditional_sales": 0,
            "traditional_net_sales": 0,
            "traditional_returns": 0,
            "live_sales": 0,
            "live_net_sales": 0,
            "live_returns": 0,
            "clearance_sales": 0,
            "clearance_net_sales": 0,
            "clearance_returns": 0,
        })
        if style_code:
            item["style_codes"].add(style_code)

    resolved_sales: list[tuple[dict[str, object], dict[str, object]]] = []
    vip_product_dates: set[tuple[str, date]] = set()
    unmatched_sales = 0
    unclassified_sales = 0
    for sale in sales_rows:
        net_quantity, gross_quantity, return_quantity = sales_metrics(sale)
        if sale.get("preaggregated") and sale.get("match_status") == "unmatched":
            unmatched_sales += gross_quantity
            continue
        product = (
            by_sku.get(str(sale.get("product_code") or "").strip())
            if sale.get("preaggregated")
            else _factory_dashboard_product_for_sale(
                sale.get("product_code"),
                sale.get("style_code"),
                by_sku=by_sku,
                by_prefix=by_prefix,
                unique_style_matches=unique_style_matches,
            )
        )
        if product is None:
            unmatched_sales += gross_quantity
            continue
        resolved_sales.append((sale, product))
        if sale.get("source") == "vip" and isinstance(sale.get("sales_date"), date):
            vip_product_dates.add((str(product.get("sku") or ""), sale["sales_date"]))

    for sale, product in resolved_sales:
        net_quantity, gross_quantity, return_quantity = sales_metrics(sale)
        season = _factory_dashboard_season(product.get("season_category"))
        if not season:
            unclassified_sales += gross_quantity
            continue
        if sale.get("preaggregated") and sale.get("match_status") == "duplicate_vip":
            continue
        platform = _platform_name(sale.get("channel"), shop_channel_mappings)
        if not sale.get("preaggregated"):
            if (
                sale.get("source") == "jst"
                and platform == "唯品"
                and isinstance(sale.get("sales_date"), date)
                and (str(product.get("sku") or ""), sale["sales_date"]) in vip_product_dates
            ):
                continue
        factory_name = str(product.get("supplier_name") or "").strip() or "未维护工厂"
        factory_code = supplier_codes.get(factory_name)
        item = season_items[season].setdefault((factory_name, factory_code), {
            "factory_name": factory_name,
            "factory_code": factory_code,
            "style_codes": set(),
            "total_sales": 0,
            "total_net_sales": 0,
            "total_returns": 0,
            "traditional_sales": 0,
            "traditional_net_sales": 0,
            "traditional_returns": 0,
            "live_sales": 0,
            "live_net_sales": 0,
            "live_returns": 0,
            "clearance_sales": 0,
            "clearance_net_sales": 0,
            "clearance_returns": 0,
        })
        channel_group = (
            str(sale.get("channel_group"))
            if sale.get("preaggregated")
            else "clearance" if _is_clearance_channel(sale.get("channel"), platform) else "live" if platform == "直播赛道" else "traditional"
        )
        item["total_sales"] = int(item["total_sales"]) + gross_quantity
        item["total_net_sales"] = int(item["total_net_sales"]) + net_quantity
        item["total_returns"] = int(item["total_returns"]) + return_quantity
        item[f"{channel_group}_sales"] = int(item[f"{channel_group}_sales"]) + gross_quantity
        item[f"{channel_group}_net_sales"] = int(item[f"{channel_group}_net_sales"]) + net_quantity
        item[f"{channel_group}_returns"] = int(item[f"{channel_group}_returns"]) + return_quantity

    total_factory_keys: set[tuple[str, str | None]] = set()
    totals = {
        "factory_count": 0,
        "style_count": 0,
        "total_sales": 0,
        "total_net_sales": 0,
        "total_returns": 0,
        "traditional_sales": 0,
        "traditional_net_sales": 0,
        "traditional_returns": 0,
        "live_sales": 0,
        "live_net_sales": 0,
        "live_returns": 0,
        "clearance_sales": 0,
        "clearance_net_sales": 0,
        "clearance_returns": 0,
    }
    seasons = []
    for season_key, label in (("spring_summer", "春夏款"), ("autumn_winter", "秋冬款")):
        items = []
        for item in season_items[season_key].values():
            total_sales = int(item["total_sales"])
            style_count = len(item["style_codes"])
            payload = {
                "factory_name": item["factory_name"],
                "factory_code": item["factory_code"],
                "style_count": style_count,
                "total_sales": total_sales,
                "total_net_sales": int(item["total_net_sales"]),
                "total_returns": int(item["total_returns"]),
                "traditional_sales": int(item["traditional_sales"]),
                "traditional_net_sales": int(item["traditional_net_sales"]),
                "traditional_returns": int(item["traditional_returns"]),
                "live_sales": int(item["live_sales"]),
                "live_net_sales": int(item["live_net_sales"]),
                "live_returns": int(item["live_returns"]),
                "clearance_sales": int(item["clearance_sales"]),
                "clearance_net_sales": int(item["clearance_net_sales"]),
                "clearance_returns": int(item["clearance_returns"]),
                "traditional_ratio": round(int(item["traditional_sales"]) / total_sales * 100, 1) if total_sales else 0,
                "live_ratio": round(int(item["live_sales"]) / total_sales * 100, 1) if total_sales else 0,
                "clearance_ratio": round(int(item["clearance_sales"]) / total_sales * 100, 1) if total_sales else 0,
            }
            items.append(payload)
            total_factory_keys.add((str(payload["factory_name"]), payload["factory_code"]))
            totals["style_count"] += style_count
            totals["total_sales"] += total_sales
            totals["total_net_sales"] += payload["total_net_sales"]
            totals["total_returns"] += payload["total_returns"]
            totals["traditional_sales"] += payload["traditional_sales"]
            totals["traditional_net_sales"] += payload["traditional_net_sales"]
            totals["traditional_returns"] += payload["traditional_returns"]
            totals["live_sales"] += payload["live_sales"]
            totals["live_net_sales"] += payload["live_net_sales"]
            totals["live_returns"] += payload["live_returns"]
            totals["clearance_sales"] += payload["clearance_sales"]
            totals["clearance_net_sales"] += payload["clearance_net_sales"]
            totals["clearance_returns"] += payload["clearance_returns"]
        items.sort(key=lambda item: (-item["total_sales"], item["factory_name"]))
        seasons.append({"key": season_key, "label": label, "items": items})

    totals["factory_count"] = len(total_factory_keys)

    payload = {
        "brand": brand,
        "sales_year": selected_sales_year,
        "product_year": normalized_product_year or None,
        "date_start": date_start.isoformat() if date_start else None,
        "date_end": date_end.isoformat() if date_end else None,
        "latest_sales_date": latest_sales_date.isoformat() if latest_sales_date else None,
        "available_sales_years": available_sales_years,
        "available_product_years": [str(value).strip() for value in product_year_rows if str(value).strip()],
        "summary": {
            **totals,
            "unmatched_sales": unmatched_sales,
            "unclassified_style_count": len(unclassified_style_codes),
            "unclassified_sales": unclassified_sales,
        },
        "seasons": seasons,
    }
    set_product_goods_cache(cache_key, payload)
    return payload


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
            .where(_consumer_sales_channel_condition(table.c.channel))
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


def _recent_sales_payload(
    connection,
    engine,
    product_sales_codes: dict[str, str],
    *,
    brand: str,
    as_of_date: date | None = None,
) -> tuple[
    dict[str, dict[str, int]],
    dict[str, dict[str, int]],
    dict[str, int],
    dict[str, int],
]:
    if not product_sales_codes:
        return {}, {}, {}, {}
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
    inspector = inspect(engine)
    jst_tables = []
    vip_tables = []
    current_year = date.today().year
    jst_table = jst_daily_sales_table_for_year(current_year)
    vip_table = vip_daily_sales_table_for_year(current_year)
    if inspector.has_table(jst_table.name):
        jst_tables.append(jst_table)
    if inspector.has_table(vip_table.name):
        vip_tables.append(vip_table)
    tables = [*jst_tables, *vip_tables]
    if not tables:
        return {}, {}, {}, {}
    latest_candidates = [
        connection.execute(
            select(func.max(table.c.sales_date)).where(table.c.sales_date <= as_of_date)
            if as_of_date is not None
            else select(func.max(table.c.sales_date))
        ).scalar()
        for table in tables
    ]
    latest = as_of_date or max(
        (item for item in latest_candidates if isinstance(item, date)),
        default=None,
    )
    if not isinstance(latest, date):
        return {}, {}, {}, {}
    start_30_date = latest - timedelta(days=29)
    start_14_date = latest - timedelta(days=13)
    recent_14_day_sales_by_size: dict[str, dict[str, int]] = {}
    recent_30_day_sales_by_size: dict[str, dict[str, int]] = {}
    recent_14_day_sales: dict[str, int] = {}
    recent_30_day_sales: dict[str, int] = {}
    vip_product_dates: set[tuple[str, date]] = set()

    def add_sale(code: str, sales_date: date, quantity: int, size: str | None) -> None:
        recent_30_day_sales[code] = recent_30_day_sales.get(code, 0) + quantity
        if size is not None:
            values = recent_30_day_sales_by_size.setdefault(code, {})
            values[size] = values.get(size, 0) + quantity
        if sales_date < start_14_date:
            return
        recent_14_day_sales[code] = recent_14_day_sales.get(code, 0) + quantity
        if size is not None:
            values = recent_14_day_sales_by_size.setdefault(code, {})
            values[size] = values.get(size, 0) + quantity

    for table in vip_tables:
        code_conditions = [table.c.goods_code.startswith(product_code) for product_code in product_codes]
        if unique_style_codes:
            code_conditions.append(table.c.style_code.in_(unique_style_codes))
        rows = connection.execute(
            select(
                table.c.goods_code,
                table.c.style_code,
                table.c.sales_date,
                table.c.size_name,
                table.c.size_id,
                func.sum(func.coalesce(table.c.sales_quantity, 0)).label("quantity"),
            )
            .where(or_(*code_conditions))
            .where(table.c.sales_date.between(start_30_date, latest))
            .where(_consumer_sales_channel_condition(table.c.channel))
            .group_by(
                table.c.goods_code,
                table.c.style_code,
                table.c.sales_date,
                table.c.size_name,
                table.c.size_id,
            )
        ).mappings()
        for row in rows:
            code = _resolve_jst_product_code(
                row["goods_code"],
                row["style_code"],
                product_codes,
                unique_style_codes,
            )
            sales_date = row["sales_date"]
            size = _size_from_color_spec(row["size_name"]) or _size_from_color_spec(row["size_id"])
            if code is None or not isinstance(sales_date, date):
                continue
            vip_product_dates.add((code, sales_date))
            add_sale(code, sales_date, int(row["quantity"] or 0), size)

    shop_channel_mappings = _shop_channel_mapping_payload(connection, brand)
    for table in jst_tables:
        code_conditions = [table.c.product_code.startswith(product_code) for product_code in product_codes]
        if unique_style_codes:
            code_conditions.append(table.c.style_code.in_(unique_style_codes))
        rows = connection.execute(
            select(
                table.c.product_code,
                table.c.style_code,
                table.c.sales_date,
                table.c.channel,
                table.c.color_spec,
                func.sum(func.coalesce(table.c.net_sales_quantity, 0)).label("quantity"),
            )
            .where(or_(*code_conditions))
            .where(table.c.sales_date.between(start_30_date, latest))
            .group_by(
                table.c.product_code,
                table.c.style_code,
                table.c.sales_date,
                table.c.channel,
                table.c.color_spec,
            )
        ).mappings()
        for row in rows:
            code = _resolve_jst_product_code(
                row["product_code"],
                row["style_code"],
                product_codes,
                unique_style_codes,
            )
            sales_date = row["sales_date"]
            size = _size_from_color_spec(row["color_spec"])
            if code is None or not isinstance(sales_date, date):
                continue
            if (
                _platform_name(row["channel"], shop_channel_mappings) == "唯品"
                and (code, sales_date) in vip_product_dates
            ):
                continue
            add_sale(code, sales_date, int(row["quantity"] or 0), size)
    return (
        recent_14_day_sales_by_size,
        recent_30_day_sales_by_size,
        recent_14_day_sales,
        recent_30_day_sales,
    )


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


def _risk_same_season_monthly_sales_payload(
    connection,
    engine,
    product_sales_codes: dict[str, str],
    *,
    brand: str,
    as_of_date: date | None = None,
) -> dict[str, dict[str, int]]:
    if not product_sales_codes or not inspect(engine).has_table(PRODUCT_GOODS_SALES_PERIODS_TABLE.name):
        return {}
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
    current_month = date.today().month
    target_periods = {
        date(year + (current_month + offset - 1) // 12, (current_month + offset - 1) % 12 + 1, 1)
        for year in (2024, 2025, 2026)
        for offset in (-1, 0, 1)
    }
    conditions = [PRODUCT_GOODS_SALES_PERIODS_TABLE.c.product_code.startswith(product_code) for product_code in product_codes]
    if unique_style_codes:
        conditions.append(PRODUCT_GOODS_SALES_PERIODS_TABLE.c.style_code.in_(unique_style_codes))
    statement = (
        select(
            PRODUCT_GOODS_SALES_PERIODS_TABLE.c.product_code,
            PRODUCT_GOODS_SALES_PERIODS_TABLE.c.style_code,
            PRODUCT_GOODS_SALES_PERIODS_TABLE.c.period_start,
            PRODUCT_GOODS_SALES_PERIODS_TABLE.c.sales_quantity,
        )
        .where(PRODUCT_GOODS_SALES_PERIODS_TABLE.c.brand == brand)
        .where(PRODUCT_GOODS_SALES_PERIODS_TABLE.c.period_type == "month")
        .where(PRODUCT_GOODS_SALES_PERIODS_TABLE.c.period_start.in_(target_periods))
        .where(or_(*conditions))
    )
    if as_of_date is not None:
        statement = statement.where(
            or_(
                PRODUCT_GOODS_SALES_PERIODS_TABLE.c.source_as_of_date.is_(None),
                PRODUCT_GOODS_SALES_PERIODS_TABLE.c.source_as_of_date <= as_of_date,
            )
        )
    monthly_by_sku: dict[str, dict[str, int]] = {}
    for row in connection.execute(statement).mappings():
        code = _resolve_jst_product_code(
            row["product_code"],
            row["style_code"],
            product_codes,
            unique_style_codes,
        )
        period_start = row["period_start"]
        if code is None or not isinstance(period_start, date):
            continue
        key = f"{period_start.year % 100:02d}-{period_start.month}"
        monthly_by_sku.setdefault(code, {})[key] = int(row["sales_quantity"] or 0)
    return monthly_by_sku


@router.get("/product-goods/filter-options")
def list_product_goods_filter_options(
    request: Request,
    field: str,
    brand: str = Query(DEFAULT_BRAND),
    filters: str | None = None,
    query: str | None = None,
    search: str | None = None,
    platform: str | None = None,
    year: str | None = None,
):
    if brand not in PRODUCT_TABLES:
        raise HTTPException(status_code=400, detail=f"Invalid brand: {brand}")
    if field not in PRODUCT_GOODS_FILTER_FIELDS:
        raise HTTPException(status_code=400, detail=f"不支持按 {field or '该字段'} 筛选")
    parsed_filters = _parse_product_goods_filters(filters)
    other_field_filters = tuple(item for item in parsed_filters if item.field != field)
    normalized_query = (query or "").strip()
    normalized_search = (search or "").strip()
    normalized_platform = (platform or "").strip()
    normalized_year = (year or "").strip()
    normalized_filters = tuple(
        sorted(
            (
                item.field,
                item.operator,
                item.value or "",
                tuple(sorted(item.values or [])),
            )
            for item in other_field_filters
        )
    )
    cache_key = (
        "filter-options-v2",
        brand,
        field,
        normalized_query,
        normalized_search,
        normalized_platform,
        normalized_year,
        normalized_filters,
    )
    cached = get_product_goods_filter_options_cache(cache_key)
    if cached is not None:
        return cached
    product_table = PRODUCT_TABLES[brand]
    override = PRODUCT_GOODS_OVERRIDES_TABLE
    repository = request.app.state.repository
    with repository.engine.connect() as connection:
        gj_table = None
        latest_gj_product_info_date = None
        if _uses_gj_product_goods_source(brand, None):
            latest_gj_product_info_date = connection.execute(
                select(func.max(GJ_MERGED_PRODUCT_INFO_TABLE.c.source_date_value))
            ).scalar()
            if latest_gj_product_info_date is not None:
                gj_table = GJ_MERGED_PRODUCT_INFO_TABLE

        source_columns = _product_goods_source_columns(product_table, gj_table)
        conditions = _product_goods_conditions(
            product_table,
            override,
            query=normalized_query,
            platform=normalized_platform,
            year=normalized_year,
            filters=other_field_filters,
            source_columns=source_columns,
        )
        if gj_table is not None:
            conditions.extend([
                gj_table.c.source_date_value == latest_gj_product_info_date,
                gj_table.c.fine_table_brand == brand,
            ])
            join = gj_table.join(product_table, (product_table.c.sku == gj_table.c.goods_code) & product_table.c.deleted_at.is_(None)).outerjoin(
                override,
                (override.c.brand == brand) & (override.c.product_id == product_table.c.id),
            )
        else:
            join = product_table.outerjoin(
                override,
                (override.c.brand == brand) & (override.c.product_id == product_table.c.id),
            )

        column = _product_goods_filter_columns(
            product_table,
            override,
            source_columns=source_columns,
        )[field]
        value_expression = func.coalesce(func.trim(cast(column, Text)), "")
        if normalized_search:
            escaped_query = normalized_search.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
            conditions.append(value_expression.ilike(f"%{escaped_query}%", escape="\\"))
        statement = (
            select(
                value_expression.label("value"),
                func.count().label("count"),
                func.count().over().label("total"),
            )
            .select_from(join)
            .where(*conditions)
            .group_by(value_expression)
            .order_by(desc(func.count()), value_expression)
            .limit(10_000)
        )
        rows = connection.execute(statement).mappings().all()
    total = int(rows[0]["total"] or 0) if rows else 0
    payload = {
        "field": field,
        "total": total,
        "truncated": total > len(rows),
        "options": [{"value": str(row["value"] or ""), "count": int(row["count"] or 0)} for row in rows],
    }
    set_product_goods_filter_options_cache(cache_key, payload)
    return payload


def get_recent_sales_ranking(
    request: Request,
    *,
    brand: str,
    days: int = 7,
    limit: int = 10,
) -> dict[str, object]:
    if brand not in PRODUCT_TABLES:
        raise HTTPException(status_code=400, detail=f"Invalid brand: {brand}")
    days = min(max(int(days), 1), 31)
    limit = min(max(int(limit), 1), 100)
    repository = request.app.state.repository
    engine = repository.engine
    inspector = inspect(engine)
    sales_tables_by_year: dict[int, tuple[object | None, object | None]] = {}
    with engine.connect() as connection:
        latest_candidates: list[date] = []
        for sales_year in range(SALES_PERIOD_START_YEAR, date.today().year + 1):
            jst_table = jst_daily_sales_table_for_year(sales_year)
            vip_table = vip_daily_sales_table_for_year(sales_year)
            available_jst_table = jst_table if inspector.has_table(jst_table.name) else None
            available_vip_table = vip_table if inspector.has_table(vip_table.name) else None
            if available_jst_table is None and available_vip_table is None:
                continue
            sales_tables_by_year[sales_year] = (available_jst_table, available_vip_table)
            for table in (available_jst_table, available_vip_table):
                if table is None:
                    continue
                latest_value = connection.execute(select(func.max(table.c.sales_date))).scalar()
                if isinstance(latest_value, date):
                    latest_candidates.append(latest_value)
        latest_sales_date = max(latest_candidates, default=None)
        if latest_sales_date is None:
            return {
                "items": [],
                "days": days,
                "limit": limit,
                "date_start": None,
                "date_end": None,
                "sales_product_count": 0,
                "period_sales": 0,
                "sources": [],
            }

        date_start = latest_sales_date - timedelta(days=days - 1)
        cache_key = (
            "recent-sales-ranking-v2",
            brand,
            days,
            limit,
            date_start.isoformat(),
            latest_sales_date.isoformat(),
        )
        cached = get_product_goods_cache(cache_key)
        if cached is not None:
            return cached

        product_table = PRODUCT_TABLES[brand]
        product_rows = [
            dict(row)
            for row in connection.execute(
                select(
                    product_table.c.sku,
                    product_table.c.original_sku,
                    product_table.c.color,
                    product_table.c.factory_sku,
                    product_table.c.supplier_name,
                ).where(product_table.c.deleted_at.is_(None))
            ).mappings()
            if str(row.get("sku") or "").strip()
        ]
        by_sku, by_prefix, unique_style_matches = _factory_dashboard_product_index(product_rows)
        sales_by_sku: dict[str, int] = defaultdict(int)
        vip_product_dates: set[tuple[str, date]] = set()
        sources: set[str] = set()

        for sales_year, (_, vip_table) in sales_tables_by_year.items():
            if vip_table is None or sales_year < date_start.year or sales_year > latest_sales_date.year:
                continue
            sources.add(vip_table.name)
            rows = connection.execute(
                select(
                    vip_table.c.goods_code,
                    vip_table.c.style_code,
                    vip_table.c.sales_date,
                    func.sum(func.coalesce(vip_table.c.sales_quantity, 0)).label("quantity"),
                )
                .where(vip_table.c.sales_date.between(date_start, latest_sales_date))
                .group_by(vip_table.c.goods_code, vip_table.c.style_code, vip_table.c.sales_date)
            ).mappings()
            for row in rows:
                product = _factory_dashboard_product_for_sale(
                    row["goods_code"],
                    row["style_code"],
                    by_sku=by_sku,
                    by_prefix=by_prefix,
                    unique_style_matches=unique_style_matches,
                )
                sales_date = row["sales_date"]
                if product is None or not isinstance(sales_date, date):
                    continue
                sku = str(product.get("sku") or "").strip()
                vip_product_dates.add((sku, sales_date))
                sales_by_sku[sku] += int(row["quantity"] or 0)

        shop_channel_mappings = _shop_channel_mapping_payload(connection, brand)
        for sales_year, (jst_table, _) in sales_tables_by_year.items():
            if jst_table is None or sales_year < date_start.year or sales_year > latest_sales_date.year:
                continue
            sources.add(jst_table.name)
            rows = connection.execute(
                select(
                    jst_table.c.product_code,
                    jst_table.c.style_code,
                    jst_table.c.sales_date,
                    jst_table.c.channel,
                    func.sum(func.coalesce(jst_table.c.net_sales_quantity, 0)).label("quantity"),
                )
                .where(jst_table.c.sales_date.between(date_start, latest_sales_date))
                .where(_consumer_sales_channel_condition(jst_table.c.channel))
                .group_by(
                    jst_table.c.product_code,
                    jst_table.c.style_code,
                    jst_table.c.sales_date,
                    jst_table.c.channel,
                )
            ).mappings()
            for row in rows:
                product = _factory_dashboard_product_for_sale(
                    row["product_code"],
                    row["style_code"],
                    by_sku=by_sku,
                    by_prefix=by_prefix,
                    unique_style_matches=unique_style_matches,
                )
                sales_date = row["sales_date"]
                if product is None or not isinstance(sales_date, date):
                    continue
                sku = str(product.get("sku") or "").strip()
                if (
                    _platform_name(row["channel"], shop_channel_mappings) == "唯品"
                    and (sku, sales_date) in vip_product_dates
                ):
                    continue
                sales_by_sku[sku] += int(row["quantity"] or 0)

    ranked_sales = sorted(sales_by_sku.items(), key=lambda item: (-item[1], item[0]))
    items = []
    for rank, (sku, quantity) in enumerate(ranked_sales[:limit], start=1):
        product = by_sku[sku]
        items.append(
            {
                "rank": rank,
                "goods_code": sku,
                "style_code": product.get("original_sku"),
                "color": product.get("color"),
                "factory_sku": product.get("factory_sku"),
                "factory_name": product.get("supplier_name"),
                "recent_sales": quantity,
            }
        )
    payload = {
        "items": items,
        "days": days,
        "limit": limit,
        "date_start": date_start.isoformat(),
        "date_end": latest_sales_date.isoformat(),
        "sales_product_count": len(ranked_sales),
        "period_sales": sum(sales_by_sku.values()),
        "sources": sorted(sources),
    }
    set_product_goods_cache(cache_key, payload)
    return payload


def get_seasonal_category_sales_ranking(
    request: Request,
    *,
    brand: str,
    season_keywords: tuple[str, ...],
    season_label: str,
    limit: int = 10,
    sales_year: int | None = None,
    archive_year_label: str | None = None,
    require_category: bool = True,
) -> dict[str, object]:
    if brand not in PRODUCT_TABLES:
        raise HTTPException(status_code=400, detail=f"Invalid brand: {brand}")
    limit = min(max(int(limit), 1), 100)
    repository = request.app.state.repository
    engine = repository.engine
    if not inspect(engine).has_table(PRODUCT_GOODS_SALES_PERIODS_TABLE.name):
        return {
            "items": [],
            "sales_year": sales_year,
            "source_as_of_date": None,
            "sales_product_count": 0,
            "period_sales": 0,
            "sources": [],
        }

    product_table = PRODUCT_TABLES[brand]
    override = PRODUCT_GOODS_OVERRIDES_TABLE
    sales_table = PRODUCT_GOODS_SALES_PERIODS_TABLE
    inspector = inspect(engine)
    with engine.connect() as connection:
        period_statement = select(func.max(sales_table.c.period_start)).where(
            sales_table.c.brand == brand,
            sales_table.c.period_type == "year",
        )
        if sales_year is not None:
            period_statement = period_statement.where(
                sales_table.c.period_start == date(sales_year, 1, 1)
            )
        period_start = connection.execute(period_statement).scalar()
        if not isinstance(period_start, date):
            return {
                "items": [],
                "sales_year": sales_year,
                "source_as_of_date": None,
                "sales_product_count": 0,
                "period_sales": 0,
                "sources": [],
            }

        source_as_of_date = connection.execute(
            select(func.max(sales_table.c.source_as_of_date)).where(
                sales_table.c.brand == brand,
                sales_table.c.period_type == "year",
                sales_table.c.period_start == period_start,
            )
        ).scalar()
        daily_sales_tables: tuple[object | None, object | None] = (None, None)
        latest_daily_sales_date: date | None = None
        if period_start.year == date.today().year:
            jst_table = jst_daily_sales_table_for_year(period_start.year)
            vip_table = vip_daily_sales_table_for_year(period_start.year)
            available_jst_table = jst_table if inspector.has_table(jst_table.name) else None
            available_vip_table = vip_table if inspector.has_table(vip_table.name) else None
            daily_sales_tables = (available_jst_table, available_vip_table)
            latest_daily_candidates: list[date] = []
            for table in daily_sales_tables:
                if table is None:
                    continue
                latest_value = connection.execute(select(func.max(table.c.sales_date))).scalar()
                if isinstance(latest_value, date):
                    latest_daily_candidates.append(latest_value)
            latest_daily_sales_date = max(latest_daily_candidates, default=None)
        cache_key = (
            "seasonal-category-sales-ranking-v4",
            brand,
            tuple(season_keywords),
            season_label,
            limit,
            period_start.isoformat(),
            source_as_of_date.isoformat() if isinstance(source_as_of_date, date) else None,
            latest_daily_sales_date.isoformat() if latest_daily_sales_date else None,
            archive_year_label,
            require_category,
        )
        cached = get_product_goods_cache(cache_key)
        if cached is not None:
            return cached

        product_statement = (
            select(
                product_table.c.id,
                product_table.c.sku,
                product_table.c.original_sku,
                product_table.c.product_name,
                product_table.c.color,
                product_table.c.season_category,
                product_table.c.year,
                override.c.category_l4,
            )
            .select_from(
                product_table.outerjoin(
                    override,
                    (override.c.brand == brand)
                    & (override.c.product_id == product_table.c.id),
                )
            )
            .where(product_table.c.deleted_at.is_(None))
        )
        if require_category:
            product_statement = product_statement.where(
                func.nullif(func.btrim(override.c.category_l4), "").is_not(None)
            )
        if archive_year_label:
            product_statement = product_statement.where(
                product_table.c.year.contains(archive_year_label)
            )
        else:
            product_statement = product_statement.where(or_(*(
                product_table.c.season_category.contains(keyword)
                for keyword in season_keywords
            )))
        product_rows = [
            dict(row)
            for row in connection.execute(
                product_statement
            ).mappings()
            if str(row.get("sku") or "").strip()
        ]
        by_sku, by_prefix, unique_style_matches = _factory_dashboard_product_index(product_rows)
        sales_by_sku: dict[str, int] = defaultdict(int)
        sales_rows = connection.execute(
            select(
                sales_table.c.product_code,
                sales_table.c.style_code,
                func.max(sales_table.c.sales_quantity).label("sales_quantity"),
            )
            .where(
                sales_table.c.brand == brand,
                sales_table.c.period_type == "year",
                sales_table.c.period_start == period_start,
            )
            .group_by(sales_table.c.product_code, sales_table.c.style_code)
        ).mappings()
        for row in sales_rows:
            product = _factory_dashboard_product_for_sale(
                row["product_code"],
                row["style_code"],
                by_sku=by_sku,
                by_prefix=by_prefix,
                unique_style_matches=unique_style_matches,
            )
            if product is None:
                continue
            sku = str(product.get("sku") or "").strip()
            sales_by_sku[sku] += int(row["sales_quantity"] or 0)

        sources = {PRODUCT_GOODS_SALES_PERIODS_TABLE.name}
        combined_as_of_date = source_as_of_date if isinstance(source_as_of_date, date) else None
        if (
            combined_as_of_date is not None
            and latest_daily_sales_date is not None
            and latest_daily_sales_date > combined_as_of_date
        ):
            incremental_start = max(combined_as_of_date + timedelta(days=1), period_start)
            jst_table, vip_table = daily_sales_tables
            vip_product_dates: set[tuple[str, date]] = set()

            if vip_table is not None:
                sources.add(vip_table.name)
                rows = connection.execute(
                    select(
                        vip_table.c.goods_code,
                        vip_table.c.style_code,
                        vip_table.c.sales_date,
                        func.sum(func.coalesce(vip_table.c.sales_quantity, 0)).label("quantity"),
                    )
                    .where(vip_table.c.sales_date.between(incremental_start, latest_daily_sales_date))
                    .group_by(vip_table.c.goods_code, vip_table.c.style_code, vip_table.c.sales_date)
                ).mappings()
                for row in rows:
                    product = _factory_dashboard_product_for_sale(
                        row["goods_code"],
                        row["style_code"],
                        by_sku=by_sku,
                        by_prefix=by_prefix,
                        unique_style_matches=unique_style_matches,
                    )
                    sales_date = row["sales_date"]
                    if product is None or not isinstance(sales_date, date):
                        continue
                    sku = str(product.get("sku") or "").strip()
                    vip_product_dates.add((sku, sales_date))
                    sales_by_sku[sku] += int(row["quantity"] or 0)

            if jst_table is not None:
                sources.add(jst_table.name)
                shop_channel_mappings = _shop_channel_mapping_payload(connection, brand)
                rows = connection.execute(
                    select(
                        jst_table.c.product_code,
                        jst_table.c.style_code,
                        jst_table.c.sales_date,
                        jst_table.c.channel,
                        func.sum(func.coalesce(jst_table.c.net_sales_quantity, 0)).label("quantity"),
                    )
                    .where(jst_table.c.sales_date.between(incremental_start, latest_daily_sales_date))
                    .where(_consumer_sales_channel_condition(jst_table.c.channel))
                    .group_by(
                        jst_table.c.product_code,
                        jst_table.c.style_code,
                        jst_table.c.sales_date,
                        jst_table.c.channel,
                    )
                ).mappings()
                for row in rows:
                    product = _factory_dashboard_product_for_sale(
                        row["product_code"],
                        row["style_code"],
                        by_sku=by_sku,
                        by_prefix=by_prefix,
                        unique_style_matches=unique_style_matches,
                    )
                    sales_date = row["sales_date"]
                    if product is None or not isinstance(sales_date, date):
                        continue
                    sku = str(product.get("sku") or "").strip()
                    if (
                        _platform_name(row["channel"], shop_channel_mappings) == "唯品"
                        and (sku, sales_date) in vip_product_dates
                    ):
                        continue
                    sales_by_sku[sku] += int(row["quantity"] or 0)

            combined_as_of_date = latest_daily_sales_date

    ranked_sales = sorted(
        ((sku, quantity) for sku, quantity in sales_by_sku.items() if quantity > 0),
        key=lambda item: (-item[1], item[0]),
    )
    items = []
    for rank, (sku, quantity) in enumerate(ranked_sales[:limit], start=1):
        product = by_sku[sku]
        items.append(
            {
                "rank": rank,
                "category_l4": product.get("category_l4"),
                "goods_code": sku,
                "style_code": product.get("original_sku"),
                "product_name": product.get("product_name"),
                "color": product.get("color"),
                "season": (
                    product.get("year")
                    if archive_year_label
                    else product.get("season_category")
                ),
                "sales_quantity": quantity,
            }
        )
    payload = {
        "items": items,
        "sales_year": period_start.year,
        "source_as_of_date": combined_as_of_date.isoformat() if combined_as_of_date else None,
        "sales_product_count": len(ranked_sales),
        "period_sales": sum(sales_by_sku.values()),
        "sources": sorted(sources),
    }
    set_product_goods_cache(cache_key, payload)
    return payload


def get_historical_order_category_monthly_summary(
    request: Request,
    *,
    start_year: int,
    end_year: int,
    brands: set[str] | None = None,
    season_keywords: tuple[str, ...] = (),
    product_role: str = "新品",
) -> dict[str, object]:
    start_year = max(start_year, HISTORICAL_ORDER_START_YEAR)
    end_year = min(end_year, date.today().year)
    selected_brands = sorted((brands or set(PRODUCT_TABLES)) & set(PRODUCT_TABLES))
    if start_year > end_year or not selected_brands:
        return {"items": [], "total_order_quantity": 0, "matched_orders": 0, "sources": []}
    cache_key = (
        "historical-order-category-monthly-v1",
        start_year,
        end_year,
        tuple(selected_brands),
        season_keywords,
        product_role,
    )
    cached = get_product_goods_cache(cache_key)
    if cached is not None:
        return cached

    repository = request.app.state.repository
    inspector = inspect(repository.engine)
    candidates_by_prefix: dict[tuple[str, str], list[dict[str, object]]] = defaultdict(list)
    monthly_category_quantity: dict[tuple[str, str], int] = defaultdict(int)
    matched_orders = 0
    unmatched_orders = 0
    sources: set[str] = set()
    with repository.engine.connect() as connection:
        override_rows = connection.execute(
            select(
                PRODUCT_GOODS_OVERRIDES_TABLE.c.brand,
                PRODUCT_GOODS_OVERRIDES_TABLE.c.product_id,
                PRODUCT_GOODS_OVERRIDES_TABLE.c.category_l4,
            )
            .where(PRODUCT_GOODS_OVERRIDES_TABLE.c.brand.in_(selected_brands))
            .where(PRODUCT_GOODS_OVERRIDES_TABLE.c.product_role == product_role)
        ).mappings()
        overrides_by_brand: dict[str, dict[int, str]] = defaultdict(dict)
        for row in override_rows:
            category = str(row["category_l4"] or "").strip()
            if not category or category == "#N/A":
                continue
            overrides_by_brand[str(row["brand"])][int(row["product_id"])] = category

        for brand in selected_brands:
            eligible_products = overrides_by_brand.get(brand, {})
            if not eligible_products:
                continue
            product_table = PRODUCT_TABLES[brand]
            product_rows = connection.execute(
                select(
                    product_table.c.id,
                    product_table.c.sku,
                    product_table.c.season_category,
                )
                .where(product_table.c.id.in_(eligible_products))
                .where(product_table.c.deleted_at.is_(None))
            ).mappings()
            for row in product_rows:
                sku = str(row["sku"] or "").strip()
                season = str(row["season_category"] or "").strip()
                if not sku or (
                    season_keywords
                    and not any(keyword in season for keyword in season_keywords)
                ):
                    continue
                candidates_by_prefix[(brand, sku[:4])].append(
                    {
                        "sku": sku,
                        "category": eligible_products[int(row["id"])],
                    }
                )
        for candidates in candidates_by_prefix.values():
            candidates.sort(key=lambda item: len(str(item["sku"])), reverse=True)

        for order_year in range(start_year, end_year + 1):
            order_table = product_goods_historical_orders_table_for_year(order_year)
            if not inspector.has_table(order_table.name):
                continue
            sources.add(order_table.name)
            order_start = max(date(start_year, 1, 1), date(order_year, 1, 1))
            order_end = min(date(end_year + 1, 1, 1), date(order_year + 1, 1, 1))
            rows = connection.execute(
                select(
                    order_table.c.brand,
                    order_table.c.order_date,
                    order_table.c.original_sku,
                    order_table.c.order_quantity,
                )
                .where(order_table.c.brand.in_(selected_brands))
                .where(order_table.c.order_date >= order_start)
                .where(order_table.c.order_date < order_end)
            ).mappings()
            for row in rows:
                brand = str(row["brand"] or "").strip()
                order_code = str(row["original_sku"] or "").strip()
                order_date = row["order_date"]
                if not order_code or not isinstance(order_date, date):
                    unmatched_orders += 1
                    continue
                product = next(
                    (
                        candidate
                        for candidate in candidates_by_prefix.get((brand, order_code[:4]), [])
                        if order_code.startswith(str(candidate["sku"]))
                    ),
                    None,
                )
                if product is None:
                    unmatched_orders += 1
                    continue
                matched_orders += 1
                month = order_date.strftime("%Y-%m")
                monthly_category_quantity[(month, str(product["category"]))] += int(
                    row["order_quantity"] or 0
                )

    items = [
        {"month": month, "category_l4": category, "order_quantity": quantity}
        for (month, category), quantity in sorted(monthly_category_quantity.items())
    ]
    payload = {
        "items": items,
        "total_order_quantity": sum(monthly_category_quantity.values()),
        "matched_orders": matched_orders,
        "unmatched_orders": unmatched_orders,
        "sources": sorted(sources),
    }
    set_product_goods_cache(cache_key, payload)
    return payload


@router.get("/product-goods")
def list_product_goods(
    request: Request,
    brand: str = Query(DEFAULT_BRAND),
    view: Literal["goods", "style_summary", "shortage_risk"] = Query("goods"),
    query: str | None = None,
    platform: str | None = None,
    year: str | None = None,
    filters: str | None = None,
    snapshot_date: date | None = None,
    cache_bust: str | None = None,
    page: int = 1,
    page_size: int = 50,
):
    if brand not in PRODUCT_TABLES:
        raise HTTPException(status_code=400, detail=f"Invalid brand: {brand}")
    repository = request.app.state.repository
    page = max(page, 1)
    page_size = min(max(page_size, 1), 500)
    normalized_query = (query or "").strip()
    normalized_platform = (platform or "").strip()
    normalized_year = (year or "").strip()
    normalized_snapshot_date = snapshot_date.isoformat() if snapshot_date else ""
    parsed_filters = _parse_product_goods_filters(filters)
    normalized_filters = tuple(sorted((item.field, item.operator, item.value or "", tuple(sorted(item.values or []))) for item in parsed_filters))
    cache_key = (brand, view, "style-summary-v3" if view == "style_summary" else "shortage-risk-v3" if view == "shortage_risk" else "goods-v2", normalized_query, normalized_platform, normalized_year, normalized_filters, normalized_snapshot_date, page, page_size)
    if not cache_bust:
        cached = get_product_goods_cache(cache_key)
        if cached is not None:
            return cached
    product_table = PRODUCT_TABLES[brand]
    override = PRODUCT_GOODS_OVERRIDES_TABLE
    style_codes: list[str] = []
    settings = request.app.state.settings
    with repository.engine.connect() as connection:
        snapshot_dates = _product_goods_snapshot_dates(connection, brand=brand)
        if snapshot_date is not None and snapshot_date not in snapshot_dates:
            raise HTTPException(status_code=404, detail=f"未找到 {snapshot_date.isoformat()} 的货品表快照")

        gj_table = None
        latest_gj_product_info_date = None
        if _uses_gj_product_goods_source(brand, snapshot_date):
            latest_gj_product_info_date = connection.execute(
                select(func.max(GJ_MERGED_PRODUCT_INFO_TABLE.c.source_date_value))
            ).scalar()
            if latest_gj_product_info_date is not None:
                gj_table = GJ_MERGED_PRODUCT_INFO_TABLE

        source_columns = _product_goods_source_columns(product_table, gj_table)
        conditions = _product_goods_conditions(
            product_table,
            override,
            query=normalized_query,
            platform=normalized_platform,
            year=normalized_year,
            filters=parsed_filters,
            source_columns=source_columns,
        )
        if view == "shortage_risk":
            risk_product_codes = _shortage_risk_product_codes(
                connection,
                product_table,
                brand=brand,
                snapshot_date=snapshot_date,
            )
            conditions.append(
                cast(source_columns["sku"], Text).in_(risk_product_codes)
                if risk_product_codes
                else false()
            )

        if gj_table is not None:
            conditions.extend([
                gj_table.c.source_date_value == latest_gj_product_info_date,
                gj_table.c.fine_table_brand == brand,
            ])
            join = gj_table.join(product_table, (product_table.c.sku == gj_table.c.goods_code) & product_table.c.deleted_at.is_(None)).outerjoin(
                override,
                (override.c.brand == brand) & (override.c.product_id == product_table.c.id),
            )
            selected_columns = [product_table, override, *_gj_product_goods_select_columns()]
        else:
            join = product_table.outerjoin(
                override,
                (override.c.brand == brand) & (override.c.product_id == product_table.c.id),
            )
            selected_columns = [product_table, override]

        if view == "style_summary":
            style_expression = _style_summary_expression(product_table, source_columns=source_columns)
            style_statement = select(style_expression.label("style_code")).select_from(join)
            count_statement = select(func.count(func.distinct(style_expression))).select_from(join)
            for condition in conditions:
                style_statement = style_statement.where(condition)
                count_statement = count_statement.where(condition)
            style_statement = (
                style_statement
                .group_by(style_expression)
                .order_by(style_expression)
                .offset((page - 1) * page_size)
                .limit(page_size)
            )
            statement = select(*selected_columns).select_from(join)
            for condition in conditions:
                statement = statement.where(condition)
            statement = statement.where(style_expression.in_(select(style_statement.subquery().c.style_code)))
            statement = statement.order_by(
                cast(source_columns["year"], Text).desc().nulls_last(),
                cast(source_columns["sku"], Text),
            )
        else:
            statement = select(*selected_columns).select_from(join)
            count_statement = select(func.count()).select_from(join)
            for condition in conditions:
                statement = statement.where(condition)
                count_statement = count_statement.where(condition)
            statement = statement.order_by(
                cast(source_columns["year"], Text).desc().nulls_last(),
                cast(source_columns["sku"], Text),
            ).offset((page - 1) * page_size).limit(page_size)

        total = int(connection.execute(count_statement).scalar() or 0)
        if view == "style_summary":
            style_codes = [
                str(item or "").strip()
                for item in connection.execute(style_statement).scalars()
            ]
        rows = [dict(row) for row in connection.execute(statement).mappings()]
        if gj_table is not None:
            rows = [_merge_gj_product_goods_row(row) for row in rows]
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
        if view == "shortage_risk":
            daily_dates = []
            daily_sales = {}
            platform_sales = {}
            (
                sales_by_size,
                recent_30_day_sales_by_size,
                recent_14_day_sales,
                recent_30_day_sales,
            ) = _recent_sales_payload(
                connection,
                repository.engine,
                product_sales_codes,
                brand=brand,
                as_of_date=snapshot_date,
            )
            sales_summary = {}
            historical_order_counts = {}
            annual_sales_columns = []
            monthly_sales_columns = []
            annual_sales = {}
            monthly_sales = _risk_same_season_monthly_sales_payload(
                connection,
                repository.engine,
                product_sales_codes,
                brand=brand,
                as_of_date=snapshot_date,
            )
        else:
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
            recent_30_day_sales_by_size = {}
            recent_14_day_sales = {}
            recent_30_day_sales = {}
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
        is_calculated_snapshot = detail_snapshot.get("snapshot_format") == CALCULATED_SNAPSHOT_FORMAT
        full_stock = full_stocks.get(sku)
        stock_by_size = dict(detail_snapshot.get("stock_by_size") or (full_stock["stock_by_size"] if full_stock else size_stocks.get(sku, {})))
        in_transit_by_size = dict(detail_snapshot.get("in_transit_by_size") or (full_stock["in_transit_by_size"] if full_stock else {}))
        shortage_by_size = dict(detail_snapshot.get("shortage_by_size") or (full_stock["shortage_by_size"] if full_stock else {}))
        shortage_total = int(
            _snapshot_value(
                snapshot_metrics,
                "shortage_total",
                full_stock["shortage_total"] if full_stock else sum(shortage_by_size.values()),
            )
            or 0
        )
        stock_total = int(_snapshot_value(snapshot_metrics, "stock_total", full_stock["stock_total"] if full_stock else sum(stock_by_size.values())) or 0)
        summary = summaries.get(sku, {})
        in_transit_total = int(_snapshot_value(snapshot_metrics, "in_transit_total", full_stock["in_transit_total"] if full_stock else int(summary.get("purchase_in_transit_qty") or 0)) or 0)
        inventory_by_size = dict(detail_snapshot.get("inventory_by_size") or {
            size: int(stock_by_size.get(size, 0)) + int(in_transit_by_size.get(size, 0))
            for size in sorted(
                set(stock_by_size) | set(in_transit_by_size),
                key=lambda value: SIZE_COLUMN_ORDER.get(value, len(SIZE_COLUMNS)),
            )
        })
        inventory_total = int(_snapshot_value(snapshot_metrics, "inventory_total", stock_total + in_transit_total) or 0)
        broken_size, biased_size = _size_inventory_risk_flags(inventory_by_size)
        sales = sales_summary.get(sku, {})
        extra_fields = row.get("extra_fields") if isinstance(row.get("extra_fields"), dict) else {}
        sales_by_size_values = dict(detail_snapshot.get("sales_by_size") or sales_by_size.get(sku, {}))
        recent_14_day_sales_value = int(
            recent_14_day_sales.get(sku, sum(sales_by_size_values.values()))
        )
        recent_30_day_sales_value = int(recent_30_day_sales.get(sku, 0))
        recent_30_day_sales_by_size_values = dict(
            recent_30_day_sales_by_size.get(sku, {})
        )
        replenishment_sales_by_size = (
            recent_30_day_sales_by_size_values
            if view == "shortage_risk"
            else sales_by_size_values
        )
        expected_replenishment_stock = _manual_number(
            _snapshot_value(
                snapshot_metrics,
                "expected_replenishment_stock",
                extra_fields.get("expected_replenishment_stock"),
            )
        )
        if is_calculated_snapshot:
            replenishment_by_size = dict(detail_snapshot.get("replenishment_by_size") or {})
            post_replenishment_by_size = dict(detail_snapshot.get("post_replenishment_by_size") or {})
            post_replenishment_stock = _manual_number(snapshot_metrics.get("post_replenishment_stock"))
            post_replenishment_total = _manual_number(snapshot_metrics.get("post_replenishment_total"))
            post_replenishment_turnover_days = _manual_number(snapshot_metrics.get("post_replenishment_turnover_days"))
        else:
            manual_replenishment_value = extra_fields.get("replenishment_by_size")
            has_manual_replenishment = isinstance(manual_replenishment_value, dict)
            manual_replenishment_by_size = _manual_size_quantities(
                manual_replenishment_value,
                allow_negative=True,
            )
            if has_manual_replenishment:
                replenishment_by_size = manual_replenishment_by_size
                expected_replenishment_stock = sum(replenishment_by_size.values())
                post_replenishment_stock = stock_total + expected_replenishment_stock
                post_replenishment_total = inventory_total + expected_replenishment_stock
                post_replenishment_by_size = _post_replenishment_inventory_by_size(
                    inventory_by_size,
                    replenishment_by_size,
                )
                post_replenishment_turnover_days = _post_replenishment_turnover_days(
                    post_replenishment_total,
                    recent_14_day_sales_value,
                )
            elif expected_replenishment_stock is None:
                replenishment_by_size = dict(detail_snapshot.get("replenishment_by_size") or _manual_size_quantities(extra_fields.get("replenishment_by_size")))
                post_replenishment_by_size = dict(detail_snapshot.get("post_replenishment_by_size") or _manual_size_quantities(extra_fields.get("post_replenishment_by_size")))
                post_replenishment_stock = _manual_number(extra_fields.get("post_replenishment_stock"))
                post_replenishment_total = _manual_number(extra_fields.get("post_replenishment_total"))
                post_replenishment_turnover_days = _manual_number(extra_fields.get("post_replenishment_turnover_days"))
            else:
                expected_replenishment_stock = int(expected_replenishment_stock)
                post_replenishment_stock = stock_total + expected_replenishment_stock
                post_replenishment_total = inventory_total + expected_replenishment_stock
                replenishment_by_size = _allocate_replenishment_by_sales(
                    expected_replenishment_stock,
                    post_replenishment_total,
                    inventory_by_size,
                    replenishment_sales_by_size,
                )
                post_replenishment_by_size = _post_replenishment_inventory_by_size(
                    inventory_by_size,
                    replenishment_by_size,
                )
                post_replenishment_turnover_days = _post_replenishment_turnover_days(
                    post_replenishment_total,
                    recent_14_day_sales_value,
                )
        yesterday_sales = int(sales.get("yesterday_sales") or 0)
        previous_day_sales = int(sales.get("previous_day_sales") or 0)
        total_order_count = historical_order_counts.get(sku, sales.get("total_order_count"))
        metrics = {
            "total_order_count": total_order_count,
            "total_sales": sales.get("total_sales"),
            "stock_plus_purchase": stock_total,
            "in_transit_total": in_transit_total,
            "return_qty": sales.get("return_qty"),
            "expected_replenishment_stock": expected_replenishment_stock,
            "post_replenishment_stock": post_replenishment_stock,
            "post_replenishment_turnover_days": post_replenishment_turnover_days,
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
            "stock_health": _stock_health_label(full_stock["stock_sale_days"], shortage_total, broken_size, biased_size) if full_stock else _stock_health_label(None, shortage_total, broken_size, biased_size),
            "broken_size_sku": "是" if broken_size else None,
            "sales_size_total": recent_14_day_sales_value if view == "shortage_risk" else sum(sales_by_size_values.values()) if sales_by_size_values else None,
            "recent_14_day_sales": recent_14_day_sales_value if view == "shortage_risk" else None,
            "recent_30_day_sales": recent_30_day_sales_value if view == "shortage_risk" else None,
            "replenishment_total": expected_replenishment_stock if expected_replenishment_stock is not None else _manual_number(extra_fields.get("replenishment_total")),
            "post_replenishment_total": post_replenishment_total,
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
            "color": detail_snapshot.get("color") or row.get("color"), "image_url": detail_snapshot.get("image_url") or image_url_for(brand, row.get("image_path"), settings),
            "cost": detail_snapshot.get("cost") or (str(row["cost"]) if row.get("cost") is not None else None),
            "product_role": detail_snapshot.get("product_role") or row.get("product_role"), "product_type": _product_type_value(detail_snapshot.get("product_type") or row.get("product_type"), row.get("sku")),
            "douyin_hot": detail_snapshot.get("douyin_hot") or row.get("douyin_hot"), "clearance": detail_snapshot.get("clearance") or row.get("clearance"), "remark": detail_snapshot.get("remark") or row.get("remark"),
            "stock_by_size": stock_by_size, "stock_total": stock_total,
            "in_transit_total": in_transit_total,
            "inventory_total": inventory_total,
            "recent_14_day_sales": recent_14_day_sales_value if view == "shortage_risk" else None,
            "recent_30_day_sales": recent_30_day_sales_value if view == "shortage_risk" else None,
            "recent_30_day_sales_by_size": recent_30_day_sales_by_size_values if view == "shortage_risk" else {},
            "daily_sales_by_date": detail_snapshot.get("daily_sales_by_date") or daily_sales.get(sku, {}),
            "annual_sales": detail_snapshot.get("annual_sales") or annual_sales.get(sku, {}),
            "monthly_sales": detail_snapshot.get("monthly_sales") or monthly_sales.get(sku, {}),
            "platform_sales": platform_sales.get(sku, {}),
            "daily_platform_sales": detail_snapshot.get("daily_platform_sales") or platform_sales.get(sku, {}).get("daily", {}),
            "weekly_platform_sales": detail_snapshot.get("weekly_platform_sales") or platform_sales.get(sku, {}).get("weekly", {}),
            "monthly_platform_sales": detail_snapshot.get("monthly_platform_sales") or platform_sales.get(sku, {}).get("monthly", {}),
            "in_transit_by_size": in_transit_by_size, "inventory_by_size": inventory_by_size, "shortage_by_size": shortage_by_size,
            "sales_by_size": sales_by_size_values, "replenishment_by_size": replenishment_by_size, "post_replenishment_by_size": post_replenishment_by_size,
            "metrics": metrics,
        })
    if view == "style_summary":
        items_by_style: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for row, item in zip(rows, items):
            items_by_style[_base_style_code(row.get("original_sku") or row.get("sku"))].append(item)
        items = [
            _style_summary_item(style_code, items_by_style[style_code])
            for style_code in style_codes
            if items_by_style.get(style_code)
        ]

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


def _calculated_snapshot_data(item: dict[str, Any]) -> dict[str, object]:
    metrics = dict(item.get("metrics") or {})
    metrics.update(
        {
            "stock_total": item.get("stock_total"),
            "in_transit_total": item.get("in_transit_total"),
            "inventory_total": item.get("inventory_total"),
        }
    )
    return jsonable_encoder(
        {
            "snapshot_format": CALCULATED_SNAPSHOT_FORMAT,
            "year": item.get("year"),
            "season": item.get("season"),
            "platform": item.get("platform"),
            "category_l4": item.get("category_l4"),
            "first_order_date": item.get("first_order_date"),
            "factory_sku": item.get("factory_sku"),
            "factory_code": item.get("factory_code"),
            "factory_name": item.get("factory_name"),
            "style_code": item.get("style_code"),
            "color": item.get("color"),
            "image_url": item.get("image_url"),
            "cost": item.get("cost"),
            "product_role": item.get("product_role"),
            "product_type": item.get("product_type"),
            "douyin_hot": item.get("douyin_hot"),
            "clearance": item.get("clearance"),
            "remark": item.get("remark"),
            "metrics": metrics,
            "stock_by_size": item.get("stock_by_size") or {},
            "in_transit_by_size": item.get("in_transit_by_size") or {},
            "inventory_by_size": item.get("inventory_by_size") or {},
            "shortage_by_size": item.get("shortage_by_size") or {},
            "sales_by_size": item.get("sales_by_size") or {},
            "replenishment_by_size": item.get("replenishment_by_size") or {},
            "post_replenishment_by_size": item.get("post_replenishment_by_size") or {},
            "daily_sales_by_date": item.get("daily_sales_by_date") or {},
            "annual_sales": item.get("annual_sales") or {},
            "monthly_sales": item.get("monthly_sales") or {},
            "daily_platform_sales": item.get("daily_platform_sales") or {},
            "weekly_platform_sales": item.get("weekly_platform_sales") or {},
            "monthly_platform_sales": item.get("monthly_platform_sales") or {},
        }
    )


def create_product_goods_calculated_snapshot(
    request: Request,
    *,
    brand: str,
    snapshot_date: date | None = None,
) -> dict[str, object]:
    """Persist the current product-goods calculation as one immutable daily view."""
    if brand not in PRODUCT_TABLES:
        raise ValueError(f"Invalid brand: {brand}")

    target_date = snapshot_date or date.today()
    page = 1
    page_size = 500
    items: list[dict[str, Any]] = []
    total: int | None = None
    while total is None or len(items) < total:
        payload = list_product_goods(
            request,
            brand=brand,
            view="goods",
            cache_bust=f"calculated-snapshot-{target_date.isoformat()}-{brand}-{page}",
            page=page,
            page_size=page_size,
        )
        page_items = payload["items"]
        if not isinstance(page_items, list):
            raise ValueError(f"Invalid product-goods payload for {brand}")
        if total is None:
            total = int(payload["total"])
        if not page_items and len(items) < total:
            raise ValueError(f"Incomplete product-goods payload for {brand}: expected {total}, got {len(items)}")
        items.extend(page_items)
        page += 1

    if not items:
        raise ValueError(f"No product-goods rows available for {brand}")

    repository = request.app.state.repository
    table = ensure_product_goods_detail_snapshot_tables(repository.engine, target_date.year)
    records = [
        {
            "brand": brand,
            "snapshot_date": target_date,
            "goods_code": str(item["goods_code"]),
            "style_code": str(item.get("style_code") or "") or None,
            "source_workbook": CALCULATED_SNAPSHOT_SOURCE_WORKBOOK,
            "source_sheet": CALCULATED_SNAPSHOT_SOURCE_SHEET,
            "source_row_number": index,
            "data": _calculated_snapshot_data(item),
        }
        for index, item in enumerate(items, start=1)
    ]
    batch_values = {
        "brand": brand,
        "snapshot_date": target_date,
        "source_path": CALCULATED_SNAPSHOT_SOURCE_PATH,
        "source_workbook": CALCULATED_SNAPSHOT_SOURCE_WORKBOOK,
        "status": "running",
        "row_count": None,
        "message": None,
    }
    try:
        with repository.engine.begin() as connection:
            statement = pg_insert(PRODUCT_GOODS_DETAIL_SNAPSHOT_BATCHES_TABLE).values(batch_values)
            connection.execute(
                statement.on_conflict_do_update(
                    index_elements=["brand", "snapshot_date"],
                    set_={key: value for key, value in batch_values.items() if key not in {"brand", "snapshot_date"}},
                )
            )
            connection.execute(
                delete(table).where(
                    (table.c.brand == brand)
                    & (table.c.snapshot_date == target_date)
                )
            )
            for start in range(0, len(records), 1_000):
                connection.execute(table.insert(), records[start:start + 1_000])
            connection.execute(
                PRODUCT_GOODS_DETAIL_SNAPSHOT_BATCHES_TABLE.update()
                .where(
                    (PRODUCT_GOODS_DETAIL_SNAPSHOT_BATCHES_TABLE.c.brand == brand)
                    & (PRODUCT_GOODS_DETAIL_SNAPSHOT_BATCHES_TABLE.c.snapshot_date == target_date)
                )
                .values(
                    status="success",
                    row_count=len(records),
                    message=CALCULATED_SNAPSHOT_FORMAT,
                )
            )
    except Exception as exc:
        failed_values = {
            **batch_values,
            "status": "failed",
            "message": f"{type(exc).__name__}: {exc}",
        }
        with repository.engine.begin() as connection:
            statement = pg_insert(PRODUCT_GOODS_DETAIL_SNAPSHOT_BATCHES_TABLE).values(failed_values)
            connection.execute(
                statement.on_conflict_do_update(
                    index_elements=["brand", "snapshot_date"],
                    set_={key: value for key, value in failed_values.items() if key not in {"brand", "snapshot_date"}},
                )
            )
        raise

    clear_product_goods_cache()
    return {
        "brand": brand,
        "snapshot_date": target_date.isoformat(),
        "rows": len(records),
        "message": CALCULATED_SNAPSHOT_FORMAT,
    }


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
        if (
            "expected_replenishment_stock" in manual_replenishment_fields
            and "replenishment_by_size" not in manual_replenishment_fields
        ):
            extra_fields.pop("replenishment_by_size", None)
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


@router.post("/product-goods/export-log")
def log_product_goods_export(request: Request, body: ProductGoodsExportLogRequest):
    if body.brand not in PRODUCT_TABLES:
        raise HTTPException(status_code=400, detail=f"Invalid brand: {body.brand}")

    brand_label = (body.brand_label or body.brand).strip()
    exported_rows = max(0, int(body.exported_rows or 0))
    total_rows = max(0, int(body.total_rows or 0)) if body.total_rows is not None else None
    view_label = "款号汇总" if body.view == "style_summary" else "货号明细"
    filters = [f"视图：{view_label}"]
    if body.query:
        filters.append(f"包含搜索：{body.query.strip()}")
    if body.filters:
        filters.append(f"筛选条件：{max(0, int(body.filters))} 项")
    if body.history_date:
        filters.append(f"历史日期：{body.history_date.strip()}")

    total_text = f"，当前条件共 {total_rows} 行" if total_rows is not None else ""
    write_operation_log(
        request,
        module="product_goods",
        action="export",
        entity_type="product_goods",
        entity_id=body.brand,
        entity_label=brand_label,
        summary=f"导出商品货品表 {brand_label}，导出 {exported_rows} 行{total_text}（{'；'.join(filters)}）",
        after_data={
            "brand": body.brand,
            "brand_label": brand_label,
            "exported_rows": exported_rows,
            "total_rows": total_rows,
            "view": body.view,
            "query": body.query,
            "filters": max(0, int(body.filters)),
            "history_date": body.history_date,
            "column_count": body.column_count,
            "filename": body.filename,
        },
    )
    return {"message": "操作日志已记录"}
