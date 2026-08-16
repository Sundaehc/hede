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
from sqlglot import exp, parse, parse_one
from sqlglot.errors import ParseError

from domain.ai_query_semantics import (
    SemanticQueryError,
    is_semantic_source_exposed,
    referenced_table_names,
    semantic_rules_for_question,
    validate_semantic_query,
)


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


@dataclass(frozen=True)
class AiSqlPlan:
    sql: str
    title: str
    summary: str
    warnings: list[str]


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
            grouped.setdefault(key, []).append(
                f"{row['column_name']} {row['data_type']}"
            )

    lines = []
    for (schema_name, table_name), columns in grouped.items():
        lines.append(f"{schema_name}.{table_name} ({', '.join(columns)})")
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
9. 聚水潭销量优先使用 v_jst_daily_sales，唯品销量优先使用 v_vip_daily_sales；title 和 summary 只描述查询口径，不要捏造查询结果。
10. 结果字段尽量使用简短、明确的中文别名，聚合字段必须提供别名。

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

    data = _extract_json(_message_content(result))
    return AiSqlPlan(
        sql=str(data.get("sql") or "").strip(),
        title=str(data.get("title") or "AI 数据查询").strip()[:80],
        summary=str(data.get("summary") or "").strip()[:300],
        warnings=[str(item) for item in data.get("warnings", []) if str(item).strip()],
    )


def validate_readonly_sql(
    sql: str,
    *,
    allowed_tables: set[str] | None = None,
    question: str | None = None,
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
            validate_semantic_query(question, value)
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


def execute_readonly_sql(
    engine: Engine,
    sql: str,
    *,
    max_rows: int,
    timeout_seconds: int,
    allowed_tables: set[str] | None = None,
    question: str | None = None,
) -> tuple[list[str], list[dict[str, Any]], bool]:
    checked_sql = validate_readonly_sql(
        sql,
        allowed_tables=allowed_tables,
        question=question,
    )
    executable_sql = expand_permission_views(checked_sql)
    bounded_sql = f"SELECT * FROM ({executable_sql}) AS ai_query_result LIMIT {int(max_rows) + 1}"
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
    truncated = len(fetched_rows) > max_rows
    return columns, fetched_rows[:max_rows], truncated
