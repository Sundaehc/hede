from __future__ import annotations

import re
from datetime import date
from uuid import uuid4

from fastapi import APIRouter, HTTPException, Request
from fastapi.encoders import jsonable_encoder
from sqlalchemy import desc, inspect, select
from sqlalchemy.exc import SQLAlchemyError

from api.operation_log_utils import write_operation_log
from api.routes.auth import user_has_permission
from api.routes.product_goods import (
    get_factory_channel_dashboard,
    get_historical_order_category_monthly_summary,
    get_recent_sales_ranking,
    get_seasonal_category_sales_ranking,
    list_product_goods,
)
from api.routes.products import list_products
from domain.task_status_schema import SCHEDULED_TASK_STATUS_TABLE
from domain.ai_query_semantics import referenced_table_names
from domain.ai_sql_query import (
    AiProviderError,
    AiSqlPlan,
    AiSqlQueryError,
    build_database_schema,
    execute_readonly_sql,
    generate_plan,
    is_mutation_request,
    schema_for_question,
    schema_table_names,
)


router = APIRouter(prefix="/ai-query", tags=["ai-query"])
MAX_QUERY_HISTORY_ITEMS = 8

BRAND_ALIASES = {
    "千百度男鞋": "cbanner_mens",
    "千百度男": "cbanner_mens",
    "男鞋": "cbanner_mens",
    "千百度女鞋": "cbanner_womens",
    "千百度女": "cbanner_womens",
    "女鞋": "cbanner_womens",
    "烟斗": "yandou",
    "名人烟斗": "yandou",
    "伊伴": "eblan",
    "笑脸": "smiley",
    "小莲": "smiley",
    "ni": "ni",
}
BRAND_LABELS = {
    "cbanner_mens": "千百度男鞋",
    "cbanner_womens": "千百度女鞋",
    "yandou": "烟斗",
    "eblan": "伊伴",
    "smiley": "笑脸",
    "ni": "NI",
    "ns": "NS",
}
GOODS_BRANDS = {"cbanner_mens", "cbanner_womens", "yandou", "eblan"}
CODE_PATTERN = re.compile(
    r"(?<![A-Za-z0-9])(?=[A-Za-z0-9-]{6,32}(?![A-Za-z0-9]))"
    r"(?=[A-Za-z0-9-]*[A-Za-z])(?=[A-Za-z0-9-]*\d)[A-Za-z0-9-]+"
)


def _clean_text(value: object) -> str:
    return str(value or "").strip()


def _current_user_id(request: Request) -> int:
    current_user = getattr(request.state, "current_user", None)
    if not isinstance(current_user, dict) or current_user.get("id") is None:
        raise HTTPException(status_code=401, detail="未登录")
    return int(current_user["id"])


def _contains(question: str, *terms: str) -> bool:
    return any(term in question for term in terms)


def _extract_brand(question: str) -> str | None:
    normalized = question.lower()
    for label, brand in sorted(BRAND_ALIASES.items(), key=lambda item: len(item[0]), reverse=True):
        if label.lower() in normalized:
            return brand
    return None


def _extract_codes(question: str) -> list[str]:
    return list(dict.fromkeys(match.upper() for match in CODE_PATTERN.findall(question)))


def _extract_year(question: str) -> int | None:
    match = re.search(r"(?:销售|销量|商品)?\s*(20\d{2})\s*(?:年)?", question)
    return int(match.group(1)) if match else None


def _historical_order_summary_spec(question: str) -> dict[str, object] | None:
    if not _contains(
        question,
        "订单量",
        "订单数量",
        "下单量",
        "下单数量",
        "订货量",
        "订货数量",
        "总订单量",
    ):
        return None
    if not _contains(question, "每个月", "每月", "月度", "按月", "月份"):
        return None
    if not _contains(question, "品类", "分类"):
        return None
    if not _contains(question, "新款", "新品"):
        return None
    range_match = re.search(
        r"(?<!\d)(20\d{2}|\d{2})\s*[-—~～至到]+\s*(20\d{2}|\d{2})\s*年?",
        question,
    )
    if range_match is None:
        return None

    def normalize_year(value: str) -> int:
        year = int(value)
        return year if year >= 2000 else 2000 + year

    start_year = normalize_year(range_match.group(1))
    end_year = normalize_year(range_match.group(2))
    if start_year > end_year:
        start_year, end_year = end_year, start_year
    season_label = ""
    season_keywords: tuple[str, ...] = ()
    for label, keywords in (
        ("秋冬", ("秋", "冬")),
        ("春夏", ("春", "夏")),
        ("春季", ("春",)),
        ("夏季", ("夏",)),
        ("秋季", ("秋",)),
        ("冬季", ("冬",)),
    ):
        if label in question:
            season_label = label
            season_keywords = keywords
            break
    if not season_keywords:
        return None
    return {
        "start_year": start_year,
        "end_year": end_year,
        "season_label": season_label,
        "season_keywords": season_keywords,
        "product_role": "新品",
    }


def _intent_for(question: str) -> str:
    if _contains(question, "定时任务", "任务执行", "任务情况", "更新任务", "任务有没有", "任务是否"):
        return "task_status"
    if _contains(question, "工厂渠道", "传统赛道", "直播赛道", "清仓赛道", "传统", "直播", "清仓") and _contains(question, "工厂", "渠道", "赛道"):
        return "factory_channel"
    if _historical_order_summary_spec(question) is not None:
        return "historical_order_summary"
    if _contains(question, "销量", "销售", "库存", "在途", "缺货", "断码", "补单", "周转", "货品表"):
        return "product_goods"
    return "product_archive"


def _view_for(question: str) -> str:
    if _contains(question, "缺货风险", "缺货", "断码", "库存健康"):
        return "shortage_risk"
    if _contains(question, "款号汇总", "按款号", "款号汇总"):
        return "style_summary"
    return "goods"


def _positive_number(value: str) -> int | None:
    normalized = value.strip().lower()
    if normalized.isdigit():
        return int(normalized)
    digits = {
        "一": 1,
        "二": 2,
        "两": 2,
        "三": 3,
        "四": 4,
        "五": 5,
        "六": 6,
        "七": 7,
        "八": 8,
        "九": 9,
    }
    if normalized == "十":
        return 10
    if "十" in normalized:
        left, right = normalized.split("十", 1)
        tens = digits.get(left, 1 if not left else 0)
        ones = digits.get(right, 0 if not right else -1)
        return tens * 10 + ones if tens > 0 and ones >= 0 else None
    return digits.get(normalized)


def _ranking_limit(question: str) -> int | None:
    normalized = question.lower()
    rank_match = re.search(r"(?:top\s*|前\s*)(\d+|[一二两三四五六七八九十]+)", normalized)
    if rank_match is None:
        rank_match = re.search(r"(?:最高|最多)(?:的)?\s*(\d+|[一二两三四五六七八九十]+)", normalized)
    if rank_match is not None:
        return _positive_number(rank_match.group(1))
    if _contains(normalized, "排行", "排名", "榜单", "最高", "最多"):
        return 10
    return None


def _recent_sales_ranking_spec(question: str) -> tuple[int, int] | None:
    normalized = question.lower()
    if not _contains(normalized, "销量", "销售量", "销售数量"):
        return None
    limit = _ranking_limit(normalized)
    if limit is None:
        return None
    period_match = re.search(r"近\s*(\d+|[一二两三四五六七八九十]+)\s*[天日]", normalized)
    if period_match is not None:
        days = _positive_number(period_match.group(1))
    elif _contains(normalized, "近一周", "最近一周", "近7天", "近七天", "周销量", "周销售量"):
        days = 7
    else:
        return None
    if days is None or limit is None or not 1 <= days <= 31 or not 1 <= limit <= 100:
        return None
    return days, limit


def _seasonal_category_sales_ranking_spec(question: str) -> dict[str, object] | None:
    normalized = question.lower()
    if not _contains(normalized, "销量", "销售量", "销售数量"):
        return None
    if not _contains(normalized, "品类", "分类"):
        return None
    limit = _ranking_limit(normalized)
    if limit is None or not 1 <= limit <= 100:
        return None
    for season_label, season_keywords in (
        ("秋冬", ("秋", "冬")),
        ("春夏", ("春", "夏")),
        ("春季", ("春",)),
        ("夏季", ("夏",)),
        ("秋季", ("秋",)),
        ("冬季", ("冬",)),
    ):
        if season_label in normalized:
            return {
                "limit": limit,
                "season_label": season_label,
                "season_keywords": season_keywords,
                "sales_year": _extract_year(question),
            }
    return None


def _should_use_business_rules(
    question: str,
    intent: str,
    brand: str | None,
    codes: list[str],
) -> bool:
    if intent == "task_status":
        return True
    if intent == "factory_channel":
        return brand in GOODS_BRANDS
    if intent == "historical_order_summary":
        return _historical_order_summary_spec(question) is not None
    if intent == "product_goods":
        return brand in GOODS_BRANDS and (
            bool(codes)
            or _view_for(question) != "goods"
            or _recent_sales_ranking_spec(question) is not None
            or _seasonal_category_sales_ranking_spec(question) is not None
        )
    if intent == "product_archive":
        return bool(brand and codes)
    return False


def _condition(label: str, value: object) -> dict[str, str]:
    return {"label": label, "value": _clean_text(value)}


def _base_response(question: str, intent: str) -> dict[str, object]:
    return {
        "query_id": uuid4().hex,
        "question": question,
        "intent": intent,
        "supported": True,
        "needs_clarification": False,
        "title": "智能查询",
        "summary": "",
        "conditions": [],
        "metrics": [],
        "columns": [],
        "rows": [],
        "data_as_of": [],
        "sources": [],
        "warnings": [],
        "link": None,
        "suggestions": [],
        "query_mode": "business_rules",
        "generated_sql": None,
    }


def _clarification(question: str, message: str, *, intent: str = "unknown") -> dict[str, object]:
    payload = _base_response(question, intent)
    payload.update(
        {
            "supported": False,
            "needs_clarification": True,
            "title": "需要补充条件",
            "summary": message,
            "suggestions": [
                "查询千百度女鞋 QC153883D54 近7天销量和库存",
                "查询千百度女鞋近7天无销量的缺货风险商品",
                "查询千百度男鞋2026年各工厂传统、直播、清仓销量",
                "查看今天定时任务执行情况",
            ],
        }
    )
    return payload


def _archive_row(row: dict[str, object]) -> dict[str, object]:
    return {
        "brand": BRAND_LABELS.get(_clean_text(row.get("brand")), _clean_text(row.get("brand"))),
        "goods_code": row.get("sku"),
        "original_sku": row.get("original_sku"),
        "product_name": row.get("product_name"),
        "color": row.get("color"),
        "year": row.get("year"),
        "season": row.get("season_category"),
        "factory_name": row.get("supplier_name"),
        "cost": row.get("cost"),
        "upper_material": row.get("upper_material"),
        "lining_material": row.get("lining_material"),
        "outsole_material": row.get("outsole_material"),
        "insole_material": row.get("insole_material"),
        "size_range": row.get("size_range"),
        "image_url": row.get("image_url"),
    }


def _goods_row(row: dict[str, object]) -> dict[str, object]:
    metrics = row.get("metrics") if isinstance(row.get("metrics"), dict) else {}
    return {
        "goods_code": row.get("goods_code"),
        "style_code": row.get("style_code"),
        "color": row.get("color"),
        "year": row.get("year"),
        "season": row.get("season"),
        "factory_name": row.get("factory_name"),
        "cost": row.get("cost"),
        "yesterday_sales": metrics.get("yesterday_sales"),
        "week_sales": metrics.get("week_sales"),
        "month_sales": metrics.get("month_sales"),
        "total_sales": metrics.get("total_sales"),
        "stock_total": row.get("stock_total"),
        "in_transit_total": row.get("in_transit_total"),
        "inventory_total": row.get("inventory_total"),
        "shortage_total": metrics.get("shortage_total"),
        "stock_health": metrics.get("stock_health"),
    }


def _allowed(user: dict[str, object] | None, permission: str) -> bool:
    return user_has_permission(user, permission)


def _permission_set(user: dict[str, object] | None) -> set[str]:
    if not user:
        return set()
    permissions = user.get("permissions")
    if not isinstance(permissions, list):
        return set()
    return {str(item) for item in permissions if str(item).strip()}


def _can_use_ai_query(user: dict[str, object] | None) -> bool:
    return any(
        _allowed(user, permission)
        for permission in (
            "ai_query.view",
            "product.view",
            "fine_table.view",
            "purchase.view",
            "inventory.view",
        )
    )


def _resolve_brand(request: Request, question: str, code: str | None, brand: str | None) -> tuple[str | None, dict[str, object] | None]:
    if brand:
        return brand, None
    if not code or not _allowed(getattr(request.state, "current_user", None), "product.view"):
        return None, _clarification(question, "请在问题中指定品牌，例如“千百度男鞋”或“伊伴”。")
    result = list_products(request, brand="all", query=code, page=1, page_size=20)
    brands = list(dict.fromkeys(_clean_text(item.get("brand")) for item in result.get("items", []) if _clean_text(item.get("brand"))))
    if len(brands) == 1:
        return brands[0], None
    if len(brands) > 1:
        labels = "、".join(BRAND_LABELS.get(item, item) for item in brands)
        return None, _clarification(question, f"货号 {code} 在多个品牌中有匹配，请指定品牌：{labels}。")
    return None, _clarification(question, f"没有根据货号 {code} 自动匹配到品牌，请补充品牌后重试。")


def _run_product_archive(request: Request, question: str, payload: dict[str, object], brand: str | None, codes: list[str]) -> dict[str, object]:
    if not _allowed(getattr(request.state, "current_user", None), "product.view"):
        raise HTTPException(status_code=403, detail="当前账户没有商品档案查询权限")
    if not brand:
        return _clarification(question, "商品档案查询需要指定品牌或唯一货号。", intent="product_archive")
    query = codes[0] if codes else None
    result = list_products(request, brand=brand, query=query, page=1, page_size=50)
    rows = [_archive_row(dict(item)) for item in result.get("items", [])]
    payload.update(
        {
            "title": f"{BRAND_LABELS.get(brand, brand)}商品档案",
            "summary": f"共匹配 {result.get('total', 0)} 条商品档案。",
            "conditions": [_condition("品牌", BRAND_LABELS.get(brand, brand))] + ([_condition("货号", query)] if query else []),
            "metrics": [{"label": "匹配商品", "value": result.get("total", 0), "tone": "blue"}],
            "columns": [
                {"key": "goods_code", "label": "货号"},
                {"key": "original_sku", "label": "原始货号"},
                {"key": "product_name", "label": "品名"},
                {"key": "color", "label": "颜色"},
                {"key": "year", "label": "年份"},
                {"key": "season", "label": "季节"},
                {"key": "factory_name", "label": "供应商"},
                {"key": "cost", "label": "成本", "type": "number"},
                {"key": "upper_material", "label": "鞋面材质"},
                {"key": "size_range", "label": "尺码组"},
            ],
            "rows": rows,
            "sources": ["商品信息档案"],
            "link": {"label": "打开商品信息档案", "href": f"/products?brand={brand}&query={query or ''}"},
            "suggestions": ["查看这批商品近7天销量", "查看这些商品的库存和在途"],
        }
    )
    return payload


def _run_product_goods(request: Request, question: str, payload: dict[str, object], brand: str | None, codes: list[str]) -> dict[str, object]:
    if not _allowed(getattr(request.state, "current_user", None), "product.view"):
        raise HTTPException(status_code=403, detail="当前账户没有货品表查询权限")
    if brand not in GOODS_BRANDS:
        return _clarification(question, "货品表初版支持千百度男鞋、千百度女鞋、烟斗和伊伴，请指定其中一个品牌。", intent="product_goods")
    seasonal_ranking_spec = _seasonal_category_sales_ranking_spec(question)
    if seasonal_ranking_spec is not None and not codes:
        result = get_seasonal_category_sales_ranking(
            request,
            brand=brand,
            season_keywords=seasonal_ranking_spec["season_keywords"],
            season_label=str(seasonal_ranking_spec["season_label"]),
            limit=int(seasonal_ranking_spec["limit"]),
            sales_year=seasonal_ranking_spec["sales_year"],
        )
        rows = list(result.get("items") or [])
        result_codes = ",".join(
            _clean_text(row.get("goods_code"))
            for row in rows
            if isinstance(row, dict) and _clean_text(row.get("goods_code"))
        )
        resolved_sales_year = result.get("sales_year")
        season_label = str(seasonal_ranking_spec["season_label"])
        limit = int(seasonal_ranking_spec["limit"])
        payload.update(
            {
                "title": f"{BRAND_LABELS.get(brand, brand)}{season_label}款销量前{limit}单品",
                "summary": f"按商品季节筛选{season_label}款，并结合四级分类统计 {resolved_sales_year or '最新年度'} 销量，当前展示前 {len(rows)} 名。",
                "conditions": [
                    _condition("品牌", BRAND_LABELS.get(brand, brand)),
                    _condition("商品季节", season_label),
                    _condition("销量年度", resolved_sales_year or "暂无"),
                    _condition("排行范围", f"前{limit}名"),
                ],
                "metrics": [
                    {"label": f"{season_label}款销量", "value": result.get("period_sales", 0), "tone": "violet"},
                    {"label": "有销量单品", "value": result.get("sales_product_count", 0), "tone": "blue"},
                    {"label": "最高销量", "value": rows[0].get("sales_quantity", 0) if rows else 0, "tone": "emerald"},
                ],
                "columns": [
                    {"key": "rank", "label": "排名", "type": "number"},
                    {"key": "category_l4", "label": "细分品类"},
                    {"key": "goods_code", "label": "货号"},
                    {"key": "style_code", "label": "原始货号"},
                    {"key": "product_name", "label": "品名"},
                    {"key": "color", "label": "颜色"},
                    {"key": "season", "label": "季节"},
                    {"key": "sales_quantity", "label": f"{resolved_sales_year or ''}年销量", "type": "number"},
                ],
                "rows": rows,
                "data_as_of": ([{"label": "销量数据截至", "value": result["source_as_of_date"]}] if result.get("source_as_of_date") else []),
                "sources": ["商品信息档案", "货品表四级分类", "年度销量", *(result.get("sources") or [])],
                "link": {
                    "label": "打开商品货品表",
                    "href": f"/product-goods?brand={brand}&query={result_codes}&view=goods",
                },
                "suggestions": ["查看这批商品的商品档案"],
            }
        )
        return payload
    ranking_spec = _recent_sales_ranking_spec(question)
    if ranking_spec is not None and not codes:
        days, limit = ranking_spec
        result = get_recent_sales_ranking(
            request,
            brand=brand,
            days=days,
            limit=limit,
        )
        rows = list(result.get("items") or [])
        result_codes = ",".join(
            _clean_text(row.get("goods_code"))
            for row in rows
            if isinstance(row, dict) and _clean_text(row.get("goods_code"))
        )
        date_start = _clean_text(result.get("date_start"))
        date_end = _clean_text(result.get("date_end"))
        period_label = f"{date_start} 至 {date_end}" if date_start and date_end else f"近{days}天"
        payload.update(
            {
                "title": f"{BRAND_LABELS.get(brand, brand)}近{days}天销量排行",
                "summary": f"按 {period_label} 的净销量排序，共有 {result.get('sales_product_count', 0)} 个商品产生销量，当前展示前 {len(rows)} 名。",
                "conditions": [
                    _condition("品牌", BRAND_LABELS.get(brand, brand)),
                    _condition("统计周期", period_label),
                    _condition("排行范围", f"前{limit}名"),
                ],
                "metrics": [
                    {"label": f"近{days}天销量", "value": result.get("period_sales", 0), "tone": "violet"},
                    {"label": "有销量商品", "value": result.get("sales_product_count", 0), "tone": "blue"},
                    {"label": "最高销量", "value": rows[0].get("recent_sales", 0) if rows else 0, "tone": "emerald"},
                ],
                "columns": [
                    {"key": "rank", "label": "排名", "type": "number"},
                    {"key": "goods_code", "label": "货号"},
                    {"key": "style_code", "label": "款号"},
                    {"key": "color", "label": "颜色"},
                    {"key": "factory_sku", "label": "工厂货号"},
                    {"key": "factory_name", "label": "工厂"},
                    {"key": "recent_sales", "label": f"近{days}天销量", "type": "number"},
                ],
                "rows": rows,
                "data_as_of": ([{"label": "最新销售日期", "value": date_end}] if date_end else []),
                "sources": ["商品信息档案", "聚水潭日销", "唯品日销", *(result.get("sources") or [])],
                "link": {
                    "label": "打开商品货品表",
                    "href": f"/product-goods?brand={brand}&query={result_codes}&view=goods",
                },
                "suggestions": ["查看这批商品的商品档案"],
            }
        )
        return payload
    view = _view_for(question)
    queries = codes or [None]
    result_items: list[dict[str, object]] = []
    daily_dates: list[object] = []
    source_total = 0
    seen_goods_codes: set[str] = set()
    for query in queries:
        result = list_product_goods(
            request,
            brand=brand,
            view=view,
            query=query,
            page=1,
            page_size=50,
        )
        source_total += int(result.get("total") or 0)
        daily_dates.extend(result.get("daily_dates") or [])
        for item in result.get("items", []):
            item_dict = dict(item)
            goods_code = _clean_text(item_dict.get("goods_code"))
            if goods_code and goods_code in seen_goods_codes:
                continue
            if goods_code:
                seen_goods_codes.add(goods_code)
            result_items.append(item_dict)
    rows = [_goods_row(item) for item in result_items]
    matched_total = len(result_items) if codes else source_total
    latest_date = max((_clean_text(item) for item in daily_dates), default="")
    metrics_rows = [
        {"label": "匹配商品", "value": matched_total, "tone": "blue"},
        {"label": "近7天销量", "value": sum(int((row.get("week_sales") or 0)) for row in rows), "tone": "violet"},
        {"label": "在仓合计", "value": sum(int((row.get("stock_total") or 0)) for row in rows), "tone": "emerald"},
        {"label": "在途合计", "value": sum(int((row.get("in_transit_total") or 0)) for row in rows), "tone": "orange"},
    ]
    payload.update(
        {
            "title": f"{BRAND_LABELS.get(brand, brand)}货品表",
            "summary": f"共匹配 {matched_total} 条商品，当前结果按货号明细展示。" if view == "goods" else f"共匹配 {matched_total} 条结果。",
            "conditions": [_condition("品牌", BRAND_LABELS.get(brand, brand)), _condition("视图", {"goods": "货号明细", "style_summary": "款号汇总", "shortage_risk": "缺货风险"}[view])] + ([_condition("货号", "、".join(codes))] if codes else []),
            "metrics": metrics_rows,
            "columns": [
                {"key": "goods_code", "label": "货号"},
                {"key": "style_code", "label": "款号"},
                {"key": "color", "label": "颜色"},
                {"key": "factory_name", "label": "工厂"},
                {"key": "yesterday_sales", "label": "昨日销量", "type": "number"},
                {"key": "week_sales", "label": "近7天销量", "type": "number"},
                {"key": "month_sales", "label": "月销量", "type": "number"},
                {"key": "stock_total", "label": "在仓合计", "type": "number"},
                {"key": "in_transit_total", "label": "在途合计", "type": "number"},
                {"key": "inventory_total", "label": "整体库存", "type": "number"},
                {"key": "shortage_total", "label": "缺货合计", "type": "number"},
                {"key": "stock_health", "label": "库存健康度"},
            ],
            "rows": rows,
            "data_as_of": ([{"label": "最新销售日期", "value": latest_date}] if latest_date else []),
            "sources": ["商品货品表", "聚水潭日销", "唯品日销", "库存与在途数据"],
            "link": {"label": "打开商品货品表", "href": f"/product-goods?brand={brand}&query={','.join(codes)}&view={view}"},
            "suggestions": ["查看这批商品的商品档案"],
        }
    )
    return payload


def _run_factory_channel(request: Request, question: str, payload: dict[str, object], brand: str | None, year: int | None) -> dict[str, object]:
    if not _allowed(getattr(request.state, "current_user", None), "product.view"):
        raise HTTPException(status_code=403, detail="当前账户没有工厂渠道看板查询权限")
    if not brand:
        return _clarification(question, "工厂渠道查询需要指定品牌，例如“千百度男鞋”。", intent="factory_channel")
    if brand not in GOODS_BRANDS:
        return _clarification(question, "工厂渠道看板初版支持千百度男鞋、千百度女鞋、烟斗和伊伴。", intent="factory_channel")
    result = get_factory_channel_dashboard(request, brand=brand, sales_year=year)
    rows = []
    for season in result.get("seasons", []):
        for item in season.get("items", []):
            rows.append({
                "season": season.get("label"),
                "factory_name": item.get("factory_name"),
                "factory_code": item.get("factory_code"),
                "style_count": item.get("style_count"),
                "total_sales": item.get("total_sales"),
                "traditional_sales": item.get("traditional_sales"),
                "live_sales": item.get("live_sales"),
                "clearance_sales": item.get("clearance_sales"),
            })
    summary = result.get("summary") if isinstance(result.get("summary"), dict) else {}
    payload.update(
        {
            "title": f"{BRAND_LABELS.get(brand, brand)}工厂渠道看板",
            "summary": f"共 {summary.get('factory_count', 0)} 家工厂，销量 {summary.get('total_sales', 0)} 件。",
            "conditions": [_condition("品牌", BRAND_LABELS.get(brand, brand)), _condition("销售年份", result.get("sales_year"))],
            "metrics": [
                {"label": "工厂数", "value": summary.get("factory_count", 0), "tone": "blue"},
                {"label": "款数", "value": summary.get("style_count", 0), "tone": "slate"},
                {"label": "传统销量", "value": summary.get("traditional_sales", 0), "tone": "blue"},
                {"label": "直播 / 清仓", "value": f"{summary.get('live_sales', 0)} / {summary.get('clearance_sales', 0)}", "tone": "orange"},
            ],
            "columns": [
                {"key": "season", "label": "季节"},
                {"key": "factory_name", "label": "工厂"},
                {"key": "factory_code", "label": "工厂代码"},
                {"key": "style_count", "label": "款数", "type": "number"},
                {"key": "total_sales", "label": "销量", "type": "number"},
                {"key": "traditional_sales", "label": "传统", "type": "number"},
                {"key": "live_sales", "label": "直播", "type": "number"},
                {"key": "clearance_sales", "label": "清仓", "type": "number"},
            ],
            "rows": rows,
            "data_as_of": ([{"label": "最新销售日期", "value": result.get("latest_sales_date")}] if result.get("latest_sales_date") else []),
            "sources": ["工厂渠道看板", "商品档案", "聚水潭日销", "唯品日销"],
            "link": {"label": "打开工厂渠道看板", "href": f"/factory-channel-dashboard?brand={brand}&sales_year={result.get('sales_year')}"},
            "suggestions": ["按工厂筛选", "比较直播和清仓占比", "查看工厂对应商品"],
        }
    )
    return payload


def _run_historical_order_summary(
    request: Request,
    question: str,
    payload: dict[str, object],
    brand: str | None,
) -> dict[str, object]:
    current_user = getattr(request.state, "current_user", None)
    if not _allowed(current_user, "product.view") or not _allowed(
        current_user, "fine_table.view"
    ):
        raise HTTPException(status_code=403, detail="当前账户没有历史订单商品属性查询权限")
    spec = _historical_order_summary_spec(question)
    if spec is None:
        return _clarification(
            question,
            "请明确年份范围、季节、按月、品类和新款条件。",
            intent="historical_order_summary",
        )
    selected_brands = {brand} if brand in GOODS_BRANDS else set(GOODS_BRANDS)
    result = get_historical_order_category_monthly_summary(
        request,
        start_year=int(spec["start_year"]),
        end_year=int(spec["end_year"]),
        brands=selected_brands,
        season_keywords=tuple(spec["season_keywords"]),
        product_role=str(spec["product_role"]),
    )
    rows = list(result.get("items") or [])
    brand_label = BRAND_LABELS.get(brand, brand) if brand else "全部货品表品牌"
    period_label = f"{spec['start_year']} 至 {spec['end_year']} 年"
    payload.update(
        {
            "title": f"{period_label}{spec['season_label']}新品月度品类下单数量",
            "summary": f"按历史订单日期汇总 {period_label}各月、各四级品类的{spec['season_label']}新品下单数量，共返回 {len(rows)} 行数据。",
            "conditions": [
                _condition("品牌", brand_label),
                _condition("订单年份", period_label),
                _condition("季节", spec["season_label"]),
                _condition("商品角色", spec["product_role"]),
            ],
            "metrics": [
                {"label": "下单数量", "value": result.get("total_order_quantity", 0), "tone": "violet"},
                {"label": "月份数", "value": len({row.get("month") for row in rows}), "tone": "blue"},
                {"label": "品类数", "value": len({row.get("category_l4") for row in rows}), "tone": "emerald"},
            ],
            "columns": [
                {"key": "month", "label": "月份", "type": "date"},
                {"key": "category_l4", "label": "四级品类"},
                {"key": "order_quantity", "label": "下单数量", "type": "number"},
            ],
            "rows": rows,
            "sources": ["历史订单", "商品信息档案", "货品表手工字段", *(result.get("sources") or [])],
            "warnings": (
                [f"有 {result.get('unmatched_orders', 0)} 条订单未匹配到已维护品类的{spec['season_label']}新品。"]
                if result.get("unmatched_orders")
                else []
            ),
            "link": None,
            "suggestions": [],
        }
    )
    return payload


def _run_task_status(request: Request, question: str, payload: dict[str, object]) -> dict[str, object]:
    if not inspect(request.app.state.repository.engine).has_table(SCHEDULED_TASK_STATUS_TABLE.name):
        return _clarification(question, "当前数据库还没有定时任务状态记录。", intent="task_status")
    table = SCHEDULED_TASK_STATUS_TABLE
    today_only = _contains(question, "今天", "今日")
    statement = select(table).order_by(desc(table.c.business_date), desc(table.c.last_started_at)).limit(100)
    if today_only:
        statement = statement.where(table.c.business_date == date.today())
    with request.app.state.repository.engine.connect() as connection:
        rows = [dict(row) for row in connection.execute(statement).mappings()]
    result_rows = [
        {
            "task_name": row.get("task_name"),
            "business_date": row.get("business_date"),
            "status": row.get("status"),
            "attempts": row.get("attempts"),
            "last_started_at": row.get("last_started_at"),
            "finished_at": row.get("finished_at"),
            "message": row.get("message"),
        }
        for row in rows
    ]
    failed = sum(1 for row in result_rows if row.get("status") == "failed")
    payload.update(
        {
            "title": "定时任务执行情况",
            "summary": f"查询到 {len(result_rows)} 条任务记录，其中失败 {failed} 条。",
            "conditions": [_condition("日期", "今天" if today_only else "最近记录")],
            "metrics": [
                {"label": "任务记录", "value": len(result_rows), "tone": "blue"},
                {"label": "失败", "value": failed, "tone": "orange"},
                {"label": "成功", "value": sum(1 for row in result_rows if row.get("status") == "success"), "tone": "emerald"},
            ],
            "columns": [
                {"key": "task_name", "label": "任务"},
                {"key": "business_date", "label": "业务日期", "type": "date"},
                {"key": "status", "label": "状态"},
                {"key": "attempts", "label": "尝试次数", "type": "number"},
                {"key": "last_started_at", "label": "开始时间"},
                {"key": "finished_at", "label": "完成时间"},
                {"key": "message", "label": "结果"},
            ],
            "rows": jsonable_encoder(result_rows),
            "sources": ["scheduled_task_statuses"],
            "link": None,
            "suggestions": ["查看失败任务", "查看今天唯品日销任务", "查看今天聚水潭日销任务"],
        }
    )
    return payload


def _ai_column_type(rows: list[dict[str, object]], key: str) -> str:
    for row in rows:
        value = row.get(key)
        if value is None:
            continue
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            return "number"
        if isinstance(value, str) and re.fullmatch(r"\d{4}-\d{2}-\d{2}(?:T.*)?", value):
            return "date"
        break
    return "text"


def _localize_ai_brand_values(
    columns: list[str],
    rows: list[dict[str, object]],
) -> None:
    brand_columns = [
        column
        for column in columns
        if "brand" in column.strip().lower() or "品牌" in column
    ]
    for row in rows:
        for column in brand_columns:
            value = _clean_text(row.get(column))
            row[column] = BRAND_LABELS.get(value.lower(), value)


def _run_ai_sql(
    request: Request,
    question: str,
    permissions: set[str],
) -> dict[str, object]:
    settings = request.app.state.settings
    api_key = str(getattr(settings, "ai_api_key", None) or "").strip()
    if not api_key:
        raise HTTPException(
            status_code=503,
            detail="AI SQL 查询尚未配置 AI_API_KEY",
        )

    engine = request.app.state.repository.engine
    schema_cache = getattr(request.app.state, "ai_sql_schema_cache", None)
    if not isinstance(schema_cache, dict):
        schema_cache = {}
        request.app.state.ai_sql_schema_cache = schema_cache
    cache_key = tuple(sorted(permissions))
    full_schema = schema_cache.get(cache_key)
    if not full_schema:
        try:
            full_schema = build_database_schema(engine, permissions=permissions)
        except (AiSqlQueryError, SQLAlchemyError) as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc
        schema_cache[cache_key] = full_schema
    schema = schema_for_question(full_schema, question)

    max_rows = int(getattr(settings, "ai_sql_max_rows", 500))
    timeout_seconds = int(getattr(settings, "ai_timeout_seconds", 30))
    plan_cache = getattr(request.app.state, "ai_sql_plan_cache", None)
    if not isinstance(plan_cache, dict):
        plan_cache = {}
        request.app.state.ai_sql_plan_cache = plan_cache
    plan_cache_key = (
        cache_key,
        re.sub(r"\s+", " ", question.strip().lower()),
        hash(schema),
    )
    plan = plan_cache.get(plan_cache_key)
    used_cached_plan = isinstance(plan, AiSqlPlan)
    if not used_cached_plan:
        plan = None
    previous_sql = None
    correction_error = None
    corrected = False
    try:
        if used_cached_plan:
            try:
                columns, rows, truncated = execute_readonly_sql(
                    engine,
                    plan.sql,
                    max_rows=max_rows,
                    timeout_seconds=timeout_seconds,
                    allowed_tables=schema_table_names(schema),
                    question=question,
                )
            except (AiSqlQueryError, SQLAlchemyError):
                plan_cache.pop(plan_cache_key, None)
                plan = None
                used_cached_plan = False
        if plan is None:
            for attempt in range(2):
                plan = generate_plan(
                    question=question,
                    schema=schema,
                    api_key=api_key,
                    provider=str(getattr(settings, "ai_provider", "openai")),
                    base_url=str(getattr(settings, "ai_base_url", "https://api.openai.com/v1")),
                    model=str(getattr(settings, "ai_model", "gpt-4.1-mini")),
                    timeout_seconds=timeout_seconds,
                    max_rows=max_rows,
                    previous_sql=previous_sql,
                    correction_error=correction_error,
                )
                try:
                    if not plan.sql:
                        detail = plan.warnings[0] if plan.warnings else "AI 无法根据当前问题生成查询 SQL"
                        raise AiSqlQueryError(detail)
                    columns, rows, truncated = execute_readonly_sql(
                        engine,
                        plan.sql,
                        max_rows=max_rows,
                        timeout_seconds=timeout_seconds,
                        allowed_tables=schema_table_names(schema),
                        question=question,
                    )
                    corrected = attempt > 0
                    plan_cache[plan_cache_key] = plan
                    while len(plan_cache) > 128:
                        plan_cache.pop(next(iter(plan_cache)))
                    break
                except (AiSqlQueryError, SQLAlchemyError) as exc:
                    if attempt > 0:
                        raise
                    previous_sql = plan.sql
                    if isinstance(exc, SQLAlchemyError):
                        database_error = getattr(exc, "orig", None) or exc
                        correction_error = f"数据库执行失败：{str(database_error)[:500]}"
                    else:
                        correction_error = str(exc)
    except AiProviderError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except AiSqlQueryError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except SQLAlchemyError as exc:
        raise HTTPException(
            status_code=422,
            detail="AI 生成的查询无法执行，请换一种描述后重试",
        ) from exc

    if plan is None:
        raise HTTPException(status_code=422, detail="AI 无法生成查询计划")

    _localize_ai_brand_values(columns, rows)
    payload = _base_response(question, "ai_sql")
    summary = plan.summary or "AI 已按自然语言条件完成数据库查询"
    summary = f"{summary}，共返回 {len(rows)} 行数据。"
    warnings = list(plan.warnings)
    if used_cached_plan:
        warnings.append("已复用校验通过的查询计划，数据已按当前数据库重新查询。")
    if corrected:
        warnings.append("首次 SQL 未通过业务口径校验，系统已自动修正后执行。")
    if truncated:
        warnings.append(f"结果超过 {max_rows} 行，当前仅展示前 {max_rows} 行。")
    warnings.append(f"数据库执行超时为 {timeout_seconds} 秒。")
    payload.update(
        {
            "query_mode": "ai_sql",
            "generated_sql": plan.sql,
            "title": plan.title or "AI 数据查询",
            "summary": summary,
            "conditions": [
                _condition("查询模式", "AI 只读 SQL"),
                _condition("数据范围", "当前账户已有权限"),
            ],
            "metrics": [
                {"label": "返回行数", "value": len(rows), "tone": "blue"},
                {"label": "字段数", "value": len(columns), "tone": "slate"},
            ],
            "columns": [
                {"key": key, "label": key, "type": _ai_column_type(rows, key)}
                for key in columns
            ],
            "rows": rows,
            "sources": [
                "规范化业务查询",
                *sorted(referenced_table_names(plan.sql)),
            ],
            "warnings": warnings,
        }
    )
    return payload


@router.get("/history")
def list_query_history(request: Request):
    user_id = _current_user_id(request)
    repository = request.app.state.auth_repository
    return {
        "items": repository.list_ai_query_history(
            user_id,
            limit=MAX_QUERY_HISTORY_ITEMS,
        )
    }


@router.delete("/history")
def clear_query_history(request: Request):
    user_id = _current_user_id(request)
    request.app.state.auth_repository.clear_ai_query_history(user_id)
    return {"message": "最近查询已清空"}


@router.post("/query")
def query_with_natural_language(request: Request, body: dict):
    question = _clean_text(body.get("question"))
    if not question:
        raise HTTPException(status_code=400, detail="请输入查询问题")
    if is_mutation_request(question):
        raise HTTPException(
            status_code=400,
            detail="智能查询仅允许读取数据，不支持新增、编辑、删除、导入或更新操作",
        )

    intent = _intent_for(question)
    brand = _extract_brand(question)
    codes = _extract_codes(question)
    year = _extract_year(question)
    current_user = getattr(request.state, "current_user", None)
    brand_clarification = None
    if intent in {"product_goods", "product_archive"} and codes and not brand:
        brand, brand_clarification = _resolve_brand(
            request,
            question,
            codes[0],
            brand,
        )
    use_business_rules = _should_use_business_rules(
        question,
        intent,
        brand,
        codes,
    )
    if brand_clarification:
        payload = brand_clarification
    elif (
        bool(getattr(request.app.state.settings, "ai_sql_enabled", False))
        and _can_use_ai_query(current_user)
        and not use_business_rules
    ):
        payload = _run_ai_sql(request, question, _permission_set(current_user))
    else:
        payload = _base_response(question, intent)
        payload["conditions"] = ([ _condition("品牌", BRAND_LABELS.get(brand, brand)) ] if brand else [])

        if intent == "task_status":
            payload = _run_task_status(request, question, payload)
        elif intent == "historical_order_summary":
            payload = _run_historical_order_summary(
                request,
                question,
                payload,
                brand,
            )
        elif intent == "factory_channel":
            payload = _run_factory_channel(request, question, payload, brand, year)
        else:
            resolved_brand, clarification = _resolve_brand(request, question, codes[0] if codes else None, brand)
            if clarification:
                payload = clarification
            elif intent == "product_goods":
                payload = _run_product_goods(request, question, payload, resolved_brand, codes)
            else:
                payload = _run_product_archive(request, question, payload, resolved_brand, codes)

    payload = jsonable_encoder(payload)
    request.app.state.auth_repository.add_ai_query_history(
        _current_user_id(request),
        question,
        limit=MAX_QUERY_HISTORY_ITEMS,
    )
    write_operation_log(
        request,
        module="ai_query",
        action="query",
        entity_type="ai_query",
        entity_id=payload.get("query_id"),
        entity_label=str(payload.get("title") or "智能查询"),
        summary=f"智能查询：{question[:120]}",
        after_data={
            "intent": payload.get("intent"),
            "supported": payload.get("supported"),
            "row_count": len(payload.get("rows") or []),
            "query_mode": payload.get("query_mode"),
            "generated_sql": payload.get("generated_sql"),
        },
    )
    return payload
