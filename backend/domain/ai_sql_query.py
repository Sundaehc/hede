from __future__ import annotations

import json
import re
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import Engine, text
from sqlalchemy.exc import SQLAlchemyError
from sqlglot import exp, parse, parse_one
from sqlglot.errors import ParseError

from domain.ai_query_semantics import (
    SemanticQueryError,
    is_semantic_source_exposed,
    referenced_table_names,
    semantic_rules_for_question,
    validate_semantic_query,
    validate_staged_query_coverage,
)
from domain.ai_query_field_catalog import field_description, table_description


PROTECTED_TABLES = {
    "ai_query_history",
    "auth_users",
    "auth_sessions",
    "auth_roles",
    "auth_departments",
    "operation_logs",
}

PROTECTED_SQL_OBJECTS = re.compile(
    r"\b(?:pg_catalog|information_schema|ai_query_history|auth_users|auth_sessions|auth_roles|auth_departments|operation_logs)\b",
    re.IGNORECASE,
)

DANGEROUS_SQL_FUNCTIONS = re.compile(
    r"\b(?:pg_sleep|dblink|pg_read_file|pg_read_binary_file|pg_ls_dir|lo_import|lo_export|set_config|nextval|setval|pg_terminate_backend|pg_cancel_backend|pg_reload_conf)\s*\(",
    re.IGNORECASE,
)

MUTATION_REQUEST = re.compile(
    r"(?:新增|添加|创建|编辑|修改|删除|导入(?:数据|商品|单据)?|写入|覆盖|清空|批量更新|更新商品|更新库存|保存修改)",
)

READ_REQUEST = re.compile(
    r"(?:查询|查看|统计|列出|筛选|分析|汇总|对比|多少|哪些|是否|有没有|执行情况|最后修改时间)",
)

PRODUCT_ARCHIVE_TABLES = {
    "cbanner_mens_products",
    "cbanner_womens_products",
    "color_barcodes",
    "eblan_products",
    "gj_merged_product_info",
    "master_data_aliases",
    "master_data_entities",
    "ni_products",
    "product_code_mappings",
    "smiley_products",
    "v_master_data_aliases",
    "v_product_code_mappings",
    "yandou_products",
}

SIZE_GROUP_TABLES = {
    "product_size_group_mappings",
    "size_group_items",
    "size_groups",
}

SHARED_SUPPLIER_TABLES = {"supplier_brands", "suppliers"}

INVENTORY_TABLES = {
    "general_customer_brands",
    "general_customer_shops",
    "general_customer_sort_preferences",
    "general_customer_units",
    "inventory_account_subjects",
    "warehouse_brands",
    "warehouses",
}

SHARED_DOCUMENT_TABLES = {
    "inventory_details",
    "inventory_records",
    "v_inventory_records_normalized",
}

VIRTUAL_PURCHASE_RECORDS = "ai_purchase_records"
VIRTUAL_PURCHASE_DETAILS = "ai_purchase_details"

PURCHASE_TABLES = {"purchase_order_requirement_templates"}

SYSTEM_TABLES = {
    "data_governance_runs",
    "data_quality_issues",
}

INTERNAL_TABLES = {"alembic_version"}


class AiSqlQueryError(ValueError):
    pass


class AiProviderError(AiSqlQueryError):
    pass


class AiSqlTimeoutError(AiSqlQueryError):
    pass


@dataclass(frozen=True)
class AiSqlPlan:
    sql: str
    title: str
    summary: str
    warnings: list[str]


@dataclass(frozen=True)
class AiSqlStage:
    name: str
    sql: str


@dataclass(frozen=True)
class AiStagedPlan:
    stages: tuple[AiSqlStage, ...]
    join_keys: tuple[str, ...]
    title: str
    summary: str
    warnings: list[str]
    sort_by: str | None
    sort_descending: bool
    result_limit: int


@dataclass(frozen=True)
class AiSqlPlanEstimate:
    total_cost: float
    max_plan_rows: int
    max_nested_loop_rows: int


def is_mutation_request(question: str) -> bool:
    value = question.strip()
    if READ_REQUEST.search(value):
        return False
    return bool(MUTATION_REQUEST.search(value))


def required_permissions_for_table(table_name: str) -> set[str]:
    name = table_name.lower()
    if (
        name in INTERNAL_TABLES
        or name in PROTECTED_TABLES
        or not is_semantic_source_exposed(name)
    ):
        return set()
    if name in SYSTEM_TABLES:
        return {"system.admin"}
    if name == "scheduled_task_statuses":
        return {"ai_query.view"}
    if name in SHARED_SUPPLIER_TABLES:
        return {"purchase.view", "inventory.view", "supplier.create"}
    if name in SHARED_DOCUMENT_TABLES:
        return {"inventory.view"}
    if name in {VIRTUAL_PURCHASE_RECORDS, VIRTUAL_PURCHASE_DETAILS}:
        return {"purchase.view"}
    if name in INVENTORY_TABLES or name.startswith("general_customer_") or name.startswith("warehouse_"):
        return {"inventory.view"}
    if name in PURCHASE_TABLES or name.startswith("purchase_"):
        return {"purchase.view"}
    if (
        name in PRODUCT_ARCHIVE_TABLES
        or name.startswith("manual_product_archive_")
    ):
        return {"product.view"}
    if name in SIZE_GROUP_TABLES:
        return {"product.manage"}
    if (
        name == "smiley_fine_table"
        or name.startswith("fine_table_")
        or name.startswith("v_fine_table_")
    ):
        return {"fine_table.view"}
    if (
        name.startswith("product_goods_")
        or name.startswith("v_product_goods_")
        or name.startswith("product_order_detail_")
        or name.startswith("jst_")
        or name.startswith("v_jst_")
        or name.startswith("vip_")
        or name.startswith("v_vip_")
    ):
        return {"fine_table.view"}
    return set()


def table_allowed_for_permissions(table_name: str, permissions: set[str]) -> bool:
    required = required_permissions_for_table(table_name)
    if not required:
        return False
    return "*" in permissions or bool(required & permissions)


def build_database_schema(
    engine: Engine, *, permissions: set[str] | None = None
) -> str:
    statement = text(
        """
        SELECT table_schema, table_name, column_name, data_type
        FROM information_schema.columns
        WHERE table_schema NOT IN ('pg_catalog', 'information_schema')
          AND table_schema NOT LIKE 'pg_toast%'
        ORDER BY table_schema, table_name, ordinal_position
        """
    )
    grouped: dict[tuple[str, str], list[str]] = {}
    with engine.connect() as connection:
        rows = connection.execute(statement).mappings()
        for row in rows:
            table_name = str(row["table_name"])
            if table_name in PROTECTED_TABLES:
                continue
            output_table_name = table_name
            if permissions is not None and table_name in SHARED_DOCUMENT_TABLES:
                has_inventory_access = "*" in permissions or "inventory.view" in permissions
                has_purchase_access = "purchase.view" in permissions
                if not has_inventory_access and has_purchase_access:
                    if table_name == "v_inventory_records_normalized":
                        continue
                    output_table_name = (
                        VIRTUAL_PURCHASE_RECORDS
                        if table_name == "inventory_records"
                        else VIRTUAL_PURCHASE_DETAILS
                    )
                elif not has_inventory_access:
                    continue
            elif permissions is not None and not table_allowed_for_permissions(
                table_name, permissions
            ):
                continue
            key = (str(row["table_schema"]), output_table_name)
            column_name = str(row["column_name"])
            description = field_description(output_table_name, column_name)
            column_schema = f"{column_name} {row['data_type']}"
            if description:
                column_schema += f" [含义：{description}]"
            grouped.setdefault(key, []).append(column_schema)

    lines = []
    for (schema_name, table_name), columns in grouped.items():
        purpose = table_description(table_name)
        purpose_suffix = f" [表用途：{purpose}]" if purpose else ""
        lines.append(
            f"{schema_name}.{table_name} ({', '.join(columns)}){purpose_suffix}"
        )
    if not lines:
        raise AiSqlQueryError("数据库中没有可供查询的业务表结构")
    return "\n".join(lines)


def schema_table_names(schema: str) -> set[str]:
    names: set[str] = set()
    for line in schema.splitlines():
        qualified_name = line.split(" (", 1)[0].strip().lower()
        if not qualified_name:
            continue
        names.add(qualified_name)
        names.add(qualified_name.rsplit(".", 1)[-1])
    return names


def schema_for_question(schema: str, question: str) -> str:
    """Keep only the business tables relevant to a question.

    The full permission-filtered schema remains the source of truth. This
    second pass only reduces the prompt and the SQL allowlist for one query.
    """

    normalized = question.strip().lower()
    lines_by_table: dict[str, str] = {}
    for line in schema.splitlines():
        qualified_name = line.split(" (", 1)[0].strip().lower()
        if not qualified_name:
            continue
        lines_by_table[qualified_name.rsplit(".", 1)[-1]] = line

    selected: set[str] = set()

    def include(*table_names: str) -> None:
        selected.update(name.lower() for name in table_names)

    def include_prefix(*prefixes: str) -> None:
        selected.update(
            name
            for name in lines_by_table
            if any(name.startswith(prefix) for prefix in prefixes)
        )

    brand_archives = {
        label: table
        for label, table in (
            ("千百度男鞋", "cbanner_mens_products"),
            ("千百度女鞋", "cbanner_womens_products"),
            ("名人烟斗", "yandou_products"),
            ("烟斗", "yandou_products"),
            ("伊伴", "eblan_products"),
            ("笑脸", "smiley_products"),
            ("小莲", "smiley_products"),
            ("ni", "ni_products"),
        )
        if label in normalized
    }
    archive_tables = set(brand_archives.values()) or {
        name for name in PRODUCT_ARCHIVE_TABLES if name in lines_by_table
    }

    task_request = any(
        term in normalized for term in ("定时任务", "任务执行", "任务状态")
    )
    sales_request = any(
        term in normalized
        for term in (
            "销量",
            "销售",
            "卖出",
            "售出",
            "平台",
            "渠道",
            "传统",
            "直播",
            "清仓",
        )
    )
    historical_order_request = any(
        term in normalized
        for term in (
            "订单量",
            "订单数量",
            "下单量",
            "下单数量",
            "订货量",
            "订货数量",
            "总订单量",
        )
    )
    stock_request = any(
        term in normalized
        for term in (
            "库存",
            "在仓",
            "在途",
            "缺货",
            "断码",
            "周转",
        )
    )
    archive_request = any(
        term in normalized
        for term in (
            "商品",
            "货号",
            "款号",
            "档案",
            "成本",
            "材质",
            "颜色",
            "年份",
            "季节",
            "上市",
            "工厂",
            "品类",
            "分类",
            "新款",
            "新品",
            "秋冬",
            "春夏",
        )
    )
    document_request = any(
        term in normalized
        for term in (
            "经营历程",
            "单据",
            "进货",
            "采购单",
            "退货单",
            "调拨单",
            "报溢",
            "报损",
        )
    )

    if task_request:
        include("scheduled_task_statuses")
    if archive_request or sales_request or stock_request:
        selected.update(archive_tables)
    if archive_request and any(
        term in normalized for term in ("档案", "成本", "材质", "颜色", "尺码段")
    ):
        include(
            "color_barcodes",
            "gj_merged_product_info",
            "product_code_mappings",
            "v_product_code_mappings",
        )
        include_prefix("manual_product_archive_")
    if sales_request:
        include(
            "v_jst_daily_sales",
            "v_vip_daily_sales",
            "product_goods_shop_channel_mappings",
        )
        if any(
            term in normalized
            for term in ("历史", "历年", "年度", "2022", "2023", "2024", "2025")
        ):
            include(
                "v_product_goods_historical_sales",
                "product_goods_sales_periods",
            )
    if historical_order_request:
        include(
            "v_product_goods_historical_orders",
            "product_goods_overrides",
        )
        selected.update(archive_tables)
    if stock_request:
        include("jst_full_stock", "jst_stock_summary")
        if "尺码" in normalized or "断码" in normalized:
            include("jst_size_stock")
        if any(term in normalized for term in ("历史", "快照", "对比", "趋势")):
            include(
                "jst_size_stock_snapshots",
                "jst_stock_summary_snapshots",
                "v_jst_daily_stock_normalized",
                "v_product_goods_detail_snapshots",
            )
    if "精细表" in normalized:
        include_prefix("v_fine_table_")
    if any(term in normalized for term in ("唯品罗盘", "拒退", "uv", "ctr")):
        include("v_vip_product_daily_normalized")
    if any(term in normalized for term in ("尺码组", "尺码段")):
        selected.update(SIZE_GROUP_TABLES)
    if document_request:
        include(
            "inventory_records",
            "inventory_details",
            "v_inventory_records_normalized",
            VIRTUAL_PURCHASE_RECORDS,
            VIRTUAL_PURCHASE_DETAILS,
            "purchase_order_requirement_templates",
        )
    if "供应商" in normalized:
        selected.update(SHARED_SUPPLIER_TABLES)
    if any(term in normalized for term in ("仓库", "一般客户", "科目")):
        selected.update(INVENTORY_TABLES)
        include_prefix("general_customer_", "warehouse_")
    if any(term in normalized for term in ("数据质量", "治理任务")):
        selected.update(SYSTEM_TABLES)

    filtered_lines = [
        line for name, line in lines_by_table.items() if name in selected
    ]
    return "\n".join(filtered_lines) if filtered_lines else schema


STAGED_ARCHIVE_COLUMNS = {
    "id",
    "sku",
    "original_sku",
    "product_name",
    "product_model",
    "year",
    "season_category",
    "color",
    "factory_sku",
    "supplier_name",
    "deleted_at",
}

STAGED_TABLE_COLUMNS = {
    "product_goods_overrides": {
        "brand",
        "product_id",
        "platform",
        "category_l4",
        "product_role",
        "product_type",
        "clearance",
    },
    "product_goods_shop_channel_mappings": {"brand", "shop_name", "channel"},
    "product_goods_sales_periods": {
        "brand",
        "product_code",
        "style_code",
        "period_type",
        "period_start",
        "sales_quantity",
        "source_as_of_date",
    },
    "v_jst_daily_sales": {
        "sales_date",
        "channel",
        "product_code",
        "style_code",
        "sales_quantity",
        "return_quantity",
        "net_sales_quantity",
        "sales_amount",
        "net_sales_amount",
    },
    "v_vip_daily_sales": {
        "sales_date",
        "goods_code",
        "style_code",
        "size_name",
        "sales_quantity",
        "sales_amount",
    },
    "v_product_goods_historical_sales": {
        "brand",
        "sales_year",
        "sales_date",
        "channel",
        "style_code",
        "product_code",
        "original_sku",
        "size",
        "sales_quantity",
        "sales_amount",
    },
    "v_product_goods_historical_orders": {
        "brand",
        "order_date",
        "original_sku",
        "channel",
        "order_quantity",
        "source_workbook",
        "source_sheet",
        "source_row_number",
    },
    "jst_full_stock": {
        "sync_date",
        "product_code",
        "style_code",
        "size",
        "actual_stock_qty",
        "purchase_warehouse_stock_qty",
        "purchase_in_transit_qty",
        "transfer_in_transit_qty",
        "return_in_transit_qty",
        "available_qty",
        "stock_sale_days",
    },
    "jst_size_stock": {"product_code", "size", "stock_qty"},
    "jst_stock_summary": {
        "stock_date_value",
        "product_code",
        "defect_stock_qty",
        "purchase_in_transit_qty",
        "off_shelf_qty",
        "order_occupy_qty",
    },
    "inventory_records": {
        "id",
        "date_value",
        "supplier",
        "total_count",
        "amount",
        "warehouse",
        "document_type",
        "summary",
        "handler",
        "document_number",
        "deleted_at",
    },
    "v_inventory_records_normalized": {
        "id",
        "business_date",
        "supplier",
        "total_count",
        "amount",
        "warehouse",
        "document_type",
        "summary",
        "handler",
        "document_number",
        "deleted_at",
    },
    "ai_purchase_records": {
        "id",
        "date_value",
        "supplier",
        "total_count",
        "amount",
        "warehouse",
        "document_number",
    },
    "inventory_details": {
        "document_id",
        "product_code",
        "quantity",
        "unit_price",
        "amount",
        "size_quantities",
    },
    "ai_purchase_details": {
        "document_id",
        "product_code",
        "quantity",
        "unit_price",
        "amount",
        "size_quantities",
    },
    "v_vip_product_daily_normalized": {
        "goods_code",
        "style_code",
        "detail_uv",
        "ctr",
        "fav_count",
        "sales_amount",
        "sales_volume",
        "customer_count",
        "purchase_conversion",
        "reject_count",
        "reject_rate",
        "report_type",
        "period",
        "report_start_date",
        "report_end_date",
    },
}


def schema_for_staged_plan(schema: str, question: str) -> str:
    normalized = question.lower()
    archive_columns = set(STAGED_ARCHIVE_COLUMNS)
    if "材质" in normalized:
        archive_columns.update(
            {"upper_material", "lining_material", "outsole_material", "insole_material"}
        )
    if "成本" in normalized:
        archive_columns.add("cost")
    if "颜色" in normalized:
        archive_columns.add("color_code")
    if "尺码" in normalized:
        archive_columns.add("size_range")
    if "上市" in normalized:
        archive_columns.add("launch_date")

    compact_lines: list[str] = []
    for line in schema.splitlines():
        qualified_name = line.split(" (", 1)[0].strip()
        table_name = qualified_name.rsplit(".", 1)[-1].lower()
        desired_columns = STAGED_TABLE_COLUMNS.get(table_name)
        if table_name in {
            "cbanner_mens_products",
            "cbanner_womens_products",
            "yandou_products",
            "eblan_products",
            "smiley_products",
            "ni_products",
        } or table_name.startswith("manual_product_archive_"):
            desired_columns = archive_columns
        if desired_columns is None or " (" not in line:
            compact_lines.append(line)
            continue

        remainder = line.split(" (", 1)[1]
        purpose_marker = ") [表用途："
        if purpose_marker in remainder:
            columns_text, purpose_text = remainder.split(purpose_marker, 1)
            suffix = f") [表用途：{purpose_text}"
        else:
            closing_index = remainder.rfind(")")
            if closing_index < 0:
                compact_lines.append(line)
                continue
            columns_text = remainder[:closing_index]
            suffix = remainder[closing_index:]
        columns = [
            item
            for item in columns_text.split(", ")
            if item.split(" ", 1)[0].lower() in desired_columns
        ]
        compact_lines.append(f"{qualified_name} ({', '.join(columns)}{suffix}")
    return "\n".join(compact_lines)


def _extract_json(content: str) -> dict[str, Any]:
    value = content.strip()
    if value.startswith("```"):
        value = re.sub(r"^```(?:json)?\s*", "", value, flags=re.IGNORECASE)
        value = re.sub(r"\s*```$", "", value)
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError as exc:
        match = re.search(r"\{.*\}", value, flags=re.DOTALL)
        if not match:
            raise AiSqlQueryError("AI 返回的查询计划不是有效 JSON") from exc
        try:
            parsed = json.loads(match.group(0))
        except json.JSONDecodeError as nested_exc:
            raise AiSqlQueryError("AI 返回的查询计划不是有效 JSON") from nested_exc
    if not isinstance(parsed, dict):
        raise AiSqlQueryError("AI 返回的查询计划格式不正确")
    return parsed


def _message_content(response: dict[str, Any]) -> str:
    choices = response.get("choices")
    if not isinstance(choices, list) or not choices:
        raise AiSqlQueryError("AI 没有返回查询计划")
    message = choices[0].get("message") if isinstance(choices[0], dict) else None
    content = message.get("content") if isinstance(message, dict) else None
    if isinstance(content, list):
        content = "".join(
            item.get("text", "") for item in content if isinstance(item, dict)
        )
    if not isinstance(content, str) or not content.strip():
        raise AiSqlQueryError("AI 没有返回有效查询计划")
    return content


def _provider_error_message(body: str) -> str:
    try:
        payload = json.loads(body)
    except json.JSONDecodeError:
        return "AI 服务未返回可识别的错误信息"
    error = payload.get("error") if isinstance(payload, dict) else None
    if isinstance(error, dict):
        code = str(error.get("code") or "").strip()
        message = str(error.get("message") or "").strip()
        if code and message:
            return f"{code}：{message[:300]}"
        if message:
            return message[:300]
    return "AI 服务请求失败"


def _request_ai_json(
    *,
    system_prompt: str,
    user_prompt: str,
    api_key: str,
    provider: str,
    base_url: str,
    model: str,
    timeout_seconds: int,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "model": model,
        "temperature": 0,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
    }
    if provider != "custom":
        payload["response_format"] = {"type": "json_object"}
    normalized_base_url = base_url.rstrip("/")
    endpoint = (
        normalized_base_url
        if normalized_base_url.endswith("/chat/completions")
        else normalized_base_url + "/chat/completions"
    )
    request = urllib.request.Request(
        endpoint,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
            response_body = response.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        detail = _provider_error_message(body)
        raise AiProviderError(f"AI 服务请求失败（HTTP {exc.code}）：{detail}") from exc
    except (urllib.error.URLError, TimeoutError) as exc:
        raise AiProviderError("AI 服务连接失败，请检查地址、网络或超时配置") from exc
    try:
        result = json.loads(response_body)
    except json.JSONDecodeError as exc:
        raise AiSqlQueryError("AI 服务返回了无法解析的结果") from exc
    return _extract_json(_message_content(result))


def generate_plan(
    *,
    question: str,
    schema: str,
    api_key: str,
    provider: str,
    base_url: str,
    model: str,
    timeout_seconds: int,
    max_rows: int,
    previous_sql: str | None = None,
    correction_error: str | None = None,
) -> AiSqlPlan:
    system_prompt = f"""
你是企业商品数据库的只读查询规划器。根据用户问题生成 PostgreSQL 查询计划。

严格规则：
1. 只能生成单条 SELECT 或 WITH 查询，禁止 INSERT、UPDATE、DELETE、MERGE、DDL、事务控制、函数调用副作用和多条语句。
2. SQL 中不得出现分号、注释、pg_catalog、information_schema 或任何 auth_* 表。
3. 只能使用下方给出的表和字段，不得猜测不存在的字段；无法确定时返回空 sql，并在 warnings 说明原因。
4. 只返回 JSON，不要 Markdown。格式必须是：{{"sql":"...","title":"...","summary":"...","warnings":["..."]}}。
5. SQL 不要以分号结尾；不要在 SQL 中写 LIMIT，服务端会统一限制最多 {max_rows} 行。
6. 用户要求新增、编辑、删除、导入、更新或其他写入动作时，返回空 sql，并说明只支持查询。
7. 优先使用 v_ 开头的标准化视图或统一父表，不要同时查询统一父表和它的年度分表，避免重复统计。
8. 商品档案按品牌分别存放在 cbanner_mens_products、cbanner_womens_products、yandou_products、eblan_products、smiley_products、ni_products。
9. 历史订单按商品属性统计时，v_product_goods_historical_orders 的年度表 id 可能重复；最长基础货号匹配优先使用 LATERAL。若使用 ROW_NUMBER 或 DISTINCT ON，必须按 original_sku、source_workbook、source_sheet、source_row_number 等来源复合键分组，不能只按 orders.id 去重。
10. 聚水潭销量优先使用 v_jst_daily_sales，唯品销量优先使用 v_vip_daily_sales；title 和 summary 只描述查询口径，不要捏造查询结果。
11. 结果字段尽量使用简短、明确的中文别名，聚合字段必须提供别名。
12. 临时复杂分析必须分层处理：先用 product_scope CTE 按品牌、年份、季节、货号等缩小商品范围；再在每个销量、库存、订单事实来源内部按日期过滤并聚合到最终需要的粒度；最后才关联各聚合结果。禁止把两个未聚合的大事实表直接 JOIN，也禁止让完整库存/销量表对商品档案逐行做前缀匹配。
13. 只选择回答问题需要的字段。跨年度时优先在各年度或统一视图内先聚合再 UNION ALL；只需要汇总结果时不能先展开全部明细后再聚合。
14. 数据库结构中的“[含义：...]”和“[表用途：...]”是业务注释，不是字段名；生成 SQL 时只能引用注释前实际存在的英文字段名。

数据库结构：
{schema}

{semantic_rules_for_question(question)}
""".strip()
    user_prompt = f"用户问题：{question}"
    if correction_error:
        user_prompt += (
            "\n\n上一次查询计划未通过后端只读或业务口径校验。"
            "请根据错误原因修正 SQL，仍只返回规定的 JSON，不要解释。"
            f"\n上一次 SQL：{previous_sql or '(空)'}"
            f"\n校验错误：{correction_error[:500]}"
        )
    data = _request_ai_json(
        system_prompt=system_prompt,
        user_prompt=user_prompt,
        api_key=api_key,
        provider=provider,
        base_url=base_url,
        model=model,
        timeout_seconds=timeout_seconds,
    )
    return AiSqlPlan(
        sql=str(data.get("sql") or "").strip(),
        title=str(data.get("title") or "AI 数据查询").strip()[:80],
        summary=str(data.get("summary") or "").strip()[:300],
        warnings=[str(item) for item in data.get("warnings", []) if str(item).strip()],
    )


def generate_staged_plan(
    *,
    question: str,
    schema: str,
    api_key: str,
    provider: str,
    base_url: str,
    model: str,
    timeout_seconds: int,
    max_rows: int,
    failed_sql: str,
    failure_reason: str,
    previous_plan: AiStagedPlan | None = None,
) -> AiStagedPlan:
    system_prompt = f"""
你是企业商品数据库的分阶段只读查询规划器。单条跨表 SQL 已因执行计划过大而失败，请把用户问题拆成 2 至 6 个可独立执行的 PostgreSQL 聚合阶段，再由后端合并结果。

严格规则：
1. 每个阶段只能生成单条 SELECT 或 WITH 查询，禁止写入、DDL、多语句、分号、注释、系统表和副作用函数。
2. 只能使用下方开放的真实表和字段。数据库结构中的“[含义：...]”和“[表用途：...]”只是注释。
3. 每个阶段最多读取一个大事实领域：销量、库存、订单、经营单据或唯品指标。商品档案、人工字段和渠道映射可以作为该阶段的维度表。
4. 每个事实阶段都要先在 product_scope CTE 中按品牌、日期、年份、季节、货号等缩小商品范围，再在事实表内部聚合到最终粒度；禁止完整事实表之间直接 JOIN。
5. 所有阶段必须返回完全相同的 join_keys 字段别名，并保证每个阶段中 join_keys 组合唯一。非键指标别名在不同阶段之间不得重复。
6. join_keys 为空时，每个阶段只能返回一行汇总结果；需要按货号、月份、平台等展示多行时必须把这些中文别名写入 join_keys。
7. 不要在 SQL 中写 LIMIT，服务端会统一限制阶段最多 2000 行、最终最多 {max_rows} 行。只返回回答问题需要的字段。
8. 结果需要排序时填写 sort_by 和 sort_direction；sort_by 必须是阶段输出的非键指标别名。result_limit 为 1 至 {max_rows}。
9. 只查询年度、月度或跨年总销量且不需要平台、尺码、每日趋势时，销量阶段优先使用 product_goods_sales_periods，按 period_type 和 period_start 过滤后聚合；不能再混入逐日销量。只有问题明确要求平台、渠道、尺码或逐日趋势时才展开历史销量和日销来源。
10. 只返回 JSON，不要 Markdown。格式：
{{"title":"...","summary":"...","warnings":["..."],"join_keys":["货号"],"sort_by":"总销量","sort_direction":"desc","result_limit":100,"stages":[{{"name":"商品销量","sql":"WITH product_scope AS (...) SELECT ..."}},{{"name":"商品库存","sql":"WITH product_scope AS (...) SELECT ..."}}]}}

数据库结构：
{schema}

{semantic_rules_for_question(question)}
""".strip()
    user_prompt = (
        f"用户问题：{question}\n"
        f"失败的单 SQL：{failed_sql[:12000]}\n"
        f"失败原因：{failure_reason[:1000]}"
    )
    if previous_plan is not None:
        previous_payload = {
            "join_keys": list(previous_plan.join_keys),
            "stages": [
                {"name": stage.name, "sql": stage.sql}
                for stage in previous_plan.stages
            ],
        }
        user_prompt += (
            "\n上一次分阶段计划仍未通过校验，请继续修正，不要退回单条跨事实表 SQL。"
            f"\n上一次分阶段计划：{json.dumps(previous_payload, ensure_ascii=False)[:12000]}"
        )
    data = _request_ai_json(
        system_prompt=system_prompt,
        user_prompt=user_prompt,
        api_key=api_key,
        provider=provider,
        base_url=base_url,
        model=model,
        timeout_seconds=timeout_seconds,
    )
    raw_stages = data.get("stages")
    if not isinstance(raw_stages, list) or not 2 <= len(raw_stages) <= 6:
        raise AiSqlQueryError("AI 分阶段计划必须包含 2 至 6 个查询阶段")
    stages: list[AiSqlStage] = []
    stage_names: set[str] = set()
    for index, item in enumerate(raw_stages, start=1):
        if not isinstance(item, dict):
            raise AiSqlQueryError("AI 分阶段计划格式不正确")
        name = str(item.get("name") or f"阶段{index}").strip()[:40]
        sql = str(item.get("sql") or "").strip()
        if not sql:
            raise AiSqlQueryError(f"AI 分阶段计划中的{name}没有 SQL")
        if name in stage_names:
            name = f"{name}{index}"
        stage_names.add(name)
        stages.append(AiSqlStage(name=name, sql=sql))

    raw_join_keys = data.get("join_keys")
    if raw_join_keys is None:
        raw_join_keys = []
    if not isinstance(raw_join_keys, list) or len(raw_join_keys) > 4:
        raise AiSqlQueryError("AI 分阶段计划的关联键格式不正确")
    join_keys = tuple(
        dict.fromkeys(
            str(item).strip()[:80]
            for item in raw_join_keys
            if str(item).strip()
        )
    )
    try:
        result_limit = int(data.get("result_limit") or max_rows)
    except (TypeError, ValueError):
        result_limit = max_rows
    result_limit = min(max(result_limit, 1), max_rows)
    sort_by = str(data.get("sort_by") or "").strip()[:80] or None
    sort_direction = str(data.get("sort_direction") or "desc").strip().lower()
    return AiStagedPlan(
        stages=tuple(stages),
        join_keys=join_keys,
        title=str(data.get("title") or "AI 复杂数据分析").strip()[:80],
        summary=str(data.get("summary") or "").strip()[:300],
        warnings=[
            str(item) for item in data.get("warnings", []) if str(item).strip()
        ],
        sort_by=sort_by,
        sort_descending=sort_direction != "asc",
        result_limit=result_limit,
    )


def validate_readonly_sql(
    sql: str,
    *,
    allowed_tables: set[str] | None = None,
    question: str | None = None,
    partial_stage: bool = False,
) -> str:
    value = sql.strip()
    if not value:
        raise AiSqlQueryError("AI 没有生成可执行的查询 SQL")
    if len(value) > 12000:
        raise AiSqlQueryError("查询 SQL 过长，已拒绝执行")
    if ";" in value or "--" in value or "/*" in value or "*/" in value:
        raise AiSqlQueryError("只允许执行单条无注释的查询 SQL")
    if not re.match(r"^(?:SELECT|WITH)\b", value, flags=re.IGNORECASE):
        raise AiSqlQueryError("只允许执行 SELECT 或 WITH 查询")
    if re.search(r"\b(?:FOR\s+UPDATE|FOR\s+NO\s+KEY\s+UPDATE|FOR\s+SHARE|FOR\s+KEY\s+SHARE|LOCK\s+TABLE)\b", value, flags=re.IGNORECASE):
        raise AiSqlQueryError("查询中包含被禁止的锁定或副作用操作")
    if DANGEROUS_SQL_FUNCTIONS.search(value):
        raise AiSqlQueryError("查询中包含被禁止的系统或副作用函数")
    try:
        expressions = parse(value, read="postgres")
    except ParseError as exc:
        raise AiSqlQueryError("AI 生成的 SQL 语法无法解析") from exc
    if len(expressions) != 1:
        raise AiSqlQueryError("只允许执行单条查询 SQL")
    expression = expressions[0]
    if expression.find(exp.Select) is None:
        raise AiSqlQueryError("只允许执行 SELECT 或 WITH 查询")

    forbidden_nodes = {
        "insert",
        "update",
        "delete",
        "merge",
        "truncate",
        "alter",
        "drop",
        "create",
        "grant",
        "revoke",
        "command",
        "transaction",
        "copy",
        "into",
    }
    if any(node.key in forbidden_nodes for node in expression.walk()):
        raise AiSqlQueryError("查询中包含被禁止的写入或结构变更操作")

    cte_names = {
        cte.alias_or_name.lower()
        for cte in expression.find_all(exp.CTE)
        if cte.alias_or_name
    }
    for table in expression.find_all(exp.Table):
        table_name = table.name.lower()
        if not table.db and not table.catalog and table_name in cte_names:
            continue
        qualified_name = ".".join(
            part.lower()
            for part in (table.catalog, table.db, table.name)
            if part
        )
        if table_name in PROTECTED_TABLES or PROTECTED_SQL_OBJECTS.search(qualified_name):
            raise AiSqlQueryError("不允许查询系统表和账户安全表")
        if allowed_tables is not None and not (
            qualified_name in allowed_tables or table_name in allowed_tables
        ):
            raise AiSqlQueryError(f"查询引用了未开放的数据表：{qualified_name}")
    if question:
        try:
            validate_semantic_query(
                question,
                value,
                partial_stage=partial_stage,
            )
        except SemanticQueryError as exc:
            raise AiSqlQueryError(str(exc)) from exc
    return value


def _json_value(value: Any) -> Any:
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return value


def expand_permission_views(sql: str) -> str:
    expression = parse_one(sql, read="postgres")

    def _replace(node: exp.Expression) -> exp.Expression:
        if not isinstance(node, exp.Table):
            return node
        table_name = node.name.lower()
        if table_name == VIRTUAL_PURCHASE_RECORDS:
            query = parse_one(
                "SELECT * FROM public.inventory_records "
                "WHERE document_type = '进货订单' AND deleted_at IS NULL",
                read="postgres",
            )
            return query.subquery(alias=node.alias_or_name)
        if table_name == VIRTUAL_PURCHASE_DETAILS:
            query = parse_one(
                "SELECT detail.* FROM public.inventory_details AS detail "
                "JOIN public.inventory_records AS record ON record.id = detail.document_id "
                "WHERE record.document_type = '进货订单' AND record.deleted_at IS NULL",
                read="postgres",
            )
            return query.subquery(alias=node.alias_or_name)
        return node

    return expression.transform(_replace).sql(dialect="postgres")


def assess_readonly_sql_plan(
    engine: Engine,
    sql: str,
    *,
    max_rows: int,
    timeout_seconds: int,
    max_plan_cost: int,
    max_plan_rows: int,
    allowed_tables: set[str] | None = None,
    question: str | None = None,
    partial_stage: bool = False,
) -> AiSqlPlanEstimate:
    checked_sql = validate_readonly_sql(
        sql,
        allowed_tables=allowed_tables,
        question=question,
        partial_stage=partial_stage,
    )
    executable_sql = expand_permission_views(checked_sql)
    bounded_sql = (
        f"SELECT * FROM ({executable_sql}) AS ai_query_result "
        f"LIMIT {int(max_rows) + 1}"
    )
    try:
        with engine.connect() as connection:
            with connection.begin():
                connection.exec_driver_sql("SET TRANSACTION READ ONLY")
                connection.exec_driver_sql(
                    f"SET LOCAL statement_timeout = {int(timeout_seconds * 1000)}"
                )
                raw_plan = connection.execute(
                    text(f"EXPLAIN (FORMAT JSON) {bounded_sql}")
                ).scalar_one()
    except SQLAlchemyError as exc:
        raise AiSqlQueryError(
            "查询计划分析失败，请缩小日期范围或减少同时关联的数据来源"
        ) from exc

    if isinstance(raw_plan, str):
        try:
            raw_plan = json.loads(raw_plan)
        except json.JSONDecodeError as exc:
            raise AiSqlQueryError("数据库返回了无法识别的查询计划") from exc
    try:
        root = raw_plan[0]["Plan"]
    except (KeyError, IndexError, TypeError) as exc:
        raise AiSqlQueryError("数据库返回了无法识别的查询计划") from exc

    total_cost = float(root.get("Total Cost") or 0)
    largest_node_rows = 0
    largest_nested_loop_rows = 0
    pending = [root]
    while pending:
        node = pending.pop()
        node_rows = max(int(node.get("Plan Rows") or 0), 0)
        largest_node_rows = max(largest_node_rows, node_rows)
        child_plans = [
            child
            for child in (node.get("Plans") or [])
            if isinstance(child, dict)
        ]
        if node.get("Node Type") == "Nested Loop" and len(child_plans) >= 2:
            nested_rows = 1
            for child in child_plans:
                nested_rows *= max(int(child.get("Plan Rows") or 0), 1)
            largest_nested_loop_rows = max(largest_nested_loop_rows, nested_rows)
        pending.extend(child_plans)

    estimate = AiSqlPlanEstimate(
        total_cost=total_cost,
        max_plan_rows=largest_node_rows,
        max_nested_loop_rows=largest_nested_loop_rows,
    )
    if (
        total_cost > max_plan_cost
        or largest_node_rows > max_plan_rows
        or largest_nested_loop_rows > max_plan_rows
    ):
        raise AiSqlQueryError(
            "查询计划预计处理的数据量过大"
            f"（成本 {total_cost:,.0f}，最大节点 {largest_node_rows:,} 行，"
            f"嵌套循环候选 {largest_nested_loop_rows:,} 行）。"
            "请先按品牌、日期和商品范围建立 product_scope，"
            "再分别聚合销量、库存或订单来源，最后关联聚合结果；"
            "不要在完整事实表之间逐行关联。"
        )
    return estimate


def execute_readonly_sql(
    engine: Engine,
    sql: str,
    *,
    max_rows: int,
    timeout_seconds: int,
    allowed_tables: set[str] | None = None,
    question: str | None = None,
    partial_stage: bool = False,
) -> tuple[list[str], list[dict[str, Any]], bool]:
    checked_sql = validate_readonly_sql(
        sql,
        allowed_tables=allowed_tables,
        question=question,
        partial_stage=partial_stage,
    )
    executable_sql = expand_permission_views(checked_sql)
    bounded_sql = f"SELECT * FROM ({executable_sql}) AS ai_query_result LIMIT {int(max_rows) + 1}"
    try:
        with engine.connect() as connection:
            with connection.begin():
                connection.exec_driver_sql("SET TRANSACTION READ ONLY")
                connection.exec_driver_sql(
                    f"SET LOCAL statement_timeout = {int(timeout_seconds * 1000)}"
                )
                result = connection.execute(text(bounded_sql))
                columns = list(result.keys())
                fetched_rows = [
                    {key: _json_value(value) for key, value in row.items()}
                    for row in result.mappings()
                ]
    except SQLAlchemyError as exc:
        current: BaseException | None = exc
        is_timeout = False
        visited: set[int] = set()
        while current is not None and id(current) not in visited:
            visited.add(id(current))
            sqlstate = str(getattr(current, "sqlstate", "") or "")
            message = str(current).lower()
            if sqlstate == "57014" or "statement timeout" in message:
                is_timeout = True
                break
            current = (
                getattr(current, "orig", None)
                or getattr(current, "__cause__", None)
            )
        if is_timeout:
            raise AiSqlTimeoutError(
                f"查询执行超过 {timeout_seconds} 秒，系统已停止本次查询。"
                "请缩小日期范围、指定品牌或货号，或改为按月/按品牌分段查询。"
            ) from exc
        raise
    truncated = len(fetched_rows) > max_rows
    return columns, fetched_rows[:max_rows], truncated


def _hashable_join_value(value: Any) -> Any:
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False, sort_keys=True)
    return value


def merge_staged_query_results(
    plan: AiStagedPlan,
    stage_results: list[
        tuple[AiSqlStage, list[str], list[dict[str, Any]], bool]
    ],
    *,
    max_rows: int,
) -> tuple[list[str], list[dict[str, Any]], bool]:
    output_columns = list(plan.join_keys)
    merged_by_key: dict[tuple[Any, ...], dict[str, Any]] = {}
    ordered_keys: list[tuple[Any, ...]] = []
    scalar_row: dict[str, Any] = {}
    any_stage_rows = False
    stage_truncated = False

    for stage, columns, rows, truncated in stage_results:
        stage_truncated = stage_truncated or truncated
        missing_keys = [key for key in plan.join_keys if key not in columns]
        if missing_keys:
            raise AiSqlQueryError(
                f"分阶段查询“{stage.name}”缺少关联字段：{', '.join(missing_keys)}"
            )
        if not plan.join_keys and len(rows) > 1:
            raise AiSqlQueryError(
                f"分阶段查询“{stage.name}”未声明关联键，但返回了多行结果"
            )

        column_aliases: dict[str, str] = {}
        for column in columns:
            if column in plan.join_keys:
                continue
            output_column = column
            if output_column in output_columns:
                output_column = f"{stage.name}_{column}"
            suffix = 2
            while output_column in output_columns:
                output_column = f"{stage.name}_{column}_{suffix}"
                suffix += 1
            output_columns.append(output_column)
            column_aliases[column] = output_column

        seen_stage_keys: set[tuple[Any, ...]] = set()
        for row in rows:
            any_stage_rows = True
            if plan.join_keys:
                key = tuple(
                    _hashable_join_value(row.get(column))
                    for column in plan.join_keys
                )
                if key in seen_stage_keys:
                    raise AiSqlQueryError(
                        f"分阶段查询“{stage.name}”的关联键不是唯一结果"
                    )
                seen_stage_keys.add(key)
                target = merged_by_key.get(key)
                if target is None:
                    target = {
                        column: row.get(column)
                        for column in plan.join_keys
                    }
                    merged_by_key[key] = target
                    ordered_keys.append(key)
            else:
                target = scalar_row
            for column, output_column in column_aliases.items():
                target[output_column] = row.get(column)

    if not any_stage_rows:
        return output_columns, [], stage_truncated
    rows = (
        [merged_by_key[key] for key in ordered_keys]
        if plan.join_keys
        else [scalar_row]
    )
    for row in rows:
        for column in output_columns:
            row.setdefault(column, None)

    if plan.sort_by and plan.sort_by in output_columns:
        present_rows = [row for row in rows if row.get(plan.sort_by) is not None]
        missing_rows = [row for row in rows if row.get(plan.sort_by) is None]

        def sort_value(row: dict[str, Any]) -> tuple[int, Any]:
            value = row.get(plan.sort_by)
            if isinstance(value, (int, float, Decimal)):
                return (0, float(value))
            return (1, str(value))

        present_rows.sort(key=sort_value, reverse=plan.sort_descending)
        rows = present_rows + missing_rows

    result_limit = min(plan.result_limit, max_rows)
    final_truncated = stage_truncated or len(rows) > result_limit
    return output_columns, rows[:result_limit], final_truncated


def execute_staged_readonly_plan(
    engine: Engine,
    plan: AiStagedPlan,
    *,
    max_rows: int,
    timeout_seconds: int,
    preflight_enabled: bool,
    explain_timeout_seconds: int,
    max_plan_cost: int,
    max_plan_rows: int,
    allowed_tables: set[str],
    question: str,
) -> tuple[list[str], list[dict[str, Any]], bool]:
    stage_max_rows = min(max(max_rows * 4, max_rows), 2000)
    try:
        validate_staged_query_coverage(
            question,
            [stage.sql for stage in plan.stages],
        )
    except SemanticQueryError as exc:
        raise AiSqlQueryError(str(exc)) from exc
    stage_results: list[
        tuple[AiSqlStage, list[str], list[dict[str, Any]], bool]
    ] = []
    for stage in plan.stages:
        if preflight_enabled:
            assess_readonly_sql_plan(
                engine,
                stage.sql,
                max_rows=stage_max_rows,
                timeout_seconds=explain_timeout_seconds,
                max_plan_cost=max_plan_cost,
                max_plan_rows=max_plan_rows,
                allowed_tables=allowed_tables,
                question=question,
                partial_stage=True,
            )
        columns, rows, truncated = execute_readonly_sql(
            engine,
            stage.sql,
            max_rows=stage_max_rows,
            timeout_seconds=timeout_seconds,
            allowed_tables=allowed_tables,
            question=question,
            partial_stage=True,
        )
        stage_results.append((stage, columns, rows, truncated))
    return merge_staged_query_results(
        plan,
        stage_results,
        max_rows=max_rows,
    )
