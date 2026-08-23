import json

import pytest

from domain import ai_sql_query
from domain.ai_sql_query import (
    AiStagedPlan,
    AiSqlQueryError,
    AiSqlStage,
    AiSqlTimeoutError,
    assess_readonly_sql_plan,
    build_database_schema,
    execute_readonly_sql,
    expand_permission_views,
    is_mutation_request,
    merge_staged_query_results,
    schema_for_staged_plan,
    schema_for_question,
    table_allowed_for_permissions,
    validate_readonly_sql,
)


class _SchemaResult:
    def __init__(self, rows):
        self.rows = rows

    def mappings(self):
        return self.rows


class _SchemaContext:
    def __init__(self, value):
        self.value = value

    def __enter__(self):
        return self.value

    def __exit__(self, exc_type, exc_value, traceback):
        return False


class _SchemaEngine:
    def __init__(self, rows):
        self.rows = rows

    def connect(self):
        engine = self

        class _Connection:
            def execute(self, statement):
                return _SchemaResult(engine.rows)

        return _SchemaContext(_Connection())


@pytest.mark.parametrize(
    "sql",
    [
        "SELECT sku, cost FROM products",
        "WITH sales AS (SELECT sku, quantity FROM jst_daily_sales) SELECT * FROM sales",
    ],
)
def test_validate_readonly_sql_accepts_select_queries(sql: str):
    assert validate_readonly_sql(sql) == sql


@pytest.mark.parametrize(
    "sql",
    [
        "UPDATE products SET cost = 0",
        "DELETE FROM products",
        "WITH changed AS (DELETE FROM products RETURNING *) SELECT * FROM changed",
        "SELECT * FROM products; DELETE FROM products",
        "SELECT * FROM auth_users",
        "SELECT pg_sleep(10)",
        "SELECT pg_read_file('/etc/passwd')",
        "SELECT nextval('some_sequence')",
        "SELECT * INTO copied_products FROM products",
    ],
)
def test_validate_readonly_sql_rejects_unsafe_queries(sql: str):
    with pytest.raises(AiSqlQueryError):
        validate_readonly_sql(sql)


def test_mutation_request_detection_does_not_block_status_queries():
    assert is_mutation_request("删除商品 QC153883D54") is True
    assert is_mutation_request("修改这双鞋的成本") is True
    assert is_mutation_request("查看今天定时任务有没有更新") is False
    assert is_mutation_request("查询今天新增了多少商品") is False
    assert is_mutation_request("查看采购单最后修改时间") is False


def test_schema_for_question_limits_product_sales_and_stock_tables():
    schema = "\n".join(
        [
            "public.cbanner_womens_products (sku text, deleted_at timestamp)",
            "public.cbanner_mens_products (sku text, deleted_at timestamp)",
            "public.v_jst_daily_sales (sales_date date, product_code text)",
            "public.v_vip_daily_sales (sales_date date, goods_code text)",
            "public.product_goods_shop_channel_mappings (brand text, shop_name text)",
            "public.jst_full_stock (sync_date date, product_code text)",
            "public.inventory_records (id bigint, deleted_at timestamp)",
            "public.scheduled_task_statuses (task_name text)",
        ]
    )

    filtered = schema_for_question(
        schema,
        "查询千百度女鞋 QC153883D54 近7天销量和库存",
    )

    assert "cbanner_womens_products" in filtered
    assert "cbanner_mens_products" not in filtered
    assert "v_jst_daily_sales" in filtered
    assert "v_vip_daily_sales" in filtered
    assert "product_goods_shop_channel_mappings" in filtered
    assert "jst_full_stock" in filtered
    assert "inventory_records" not in filtered
    assert "scheduled_task_statuses" not in filtered


def test_database_schema_includes_field_meanings_and_keeps_permission_filtering():
    engine = _SchemaEngine(
        [
            {
                "table_schema": "public",
                "table_name": "cbanner_womens_products",
                "column_name": "sku",
                "data_type": "text",
            },
            {
                "table_schema": "public",
                "table_name": "cbanner_womens_products",
                "column_name": "unknown_field",
                "data_type": "text",
            },
            {
                "table_schema": "public",
                "table_name": "inventory_records",
                "column_name": "document_number",
                "data_type": "text",
            },
        ]
    )

    schema = build_database_schema(
        engine,
        permissions={"product.view", "ai_query.view"},
    )

    assert "sku text [含义：商品档案当前基础货号" in schema
    assert "unknown_field text" in schema
    assert "unknown_field text [含义" not in schema
    assert "[表用途：千百度女鞋商品档案" in schema
    assert "inventory_records" not in schema


def test_database_schema_descriptions_survive_question_level_trimming():
    engine = _SchemaEngine(
        [
            {
                "table_schema": "public",
                "table_name": "v_jst_daily_sales",
                "column_name": "net_sales_quantity",
                "data_type": "integer",
            },
            {
                "table_schema": "public",
                "table_name": "scheduled_task_statuses",
                "column_name": "status",
                "data_type": "text",
            },
        ]
    )
    full_schema = build_database_schema(engine, permissions={"*"})

    filtered = schema_for_question(full_schema, "查询近7天销量")

    assert "净销量" in filtered
    assert "v_jst_daily_sales" in filtered
    assert "scheduled_task_statuses" not in filtered


def test_schema_for_task_question_includes_run_history() -> None:
    schema = "\n".join(
        [
            "public.scheduled_task_statuses (task_name text, business_date date, status text)",
            "public.scheduled_task_runs (task_name text, started_at timestamp, status text, error_summary text)",
            "public.inventory_records (id bigint)",
        ]
    )

    filtered = schema_for_question(schema, "查看今天所有定时任务执行情况")

    assert "scheduled_task_runs" in filtered
    assert "scheduled_task_statuses" in filtered
    assert "inventory_records" not in filtered


def test_schema_for_question_includes_historical_order_attribute_sources():
    schema = "\n".join(
        [
            "public.cbanner_womens_products (id bigint, sku text, year text, season_category text, deleted_at timestamp)",
            "public.cbanner_mens_products (id bigint, sku text, year text, season_category text, deleted_at timestamp)",
            "public.product_goods_overrides (brand text, product_id bigint, category_l4 text, product_role text)",
            "public.v_product_goods_historical_orders (brand text, order_date date, original_sku text, order_quantity integer)",
            "public.v_jst_daily_sales (sales_date date, net_sales_quantity integer)",
        ]
    )

    filtered = schema_for_question(
        schema,
        "24-25年秋冬每个月各品类新款下单数量",
    )

    assert "v_product_goods_historical_orders" in filtered
    assert "product_goods_overrides" in filtered
    assert "cbanner_womens_products" in filtered
    assert "cbanner_mens_products" in filtered
    assert "v_jst_daily_sales" not in filtered


def test_staged_schema_keeps_only_question_relevant_business_columns():
    schema = "\n".join(
        [
            "public.cbanner_womens_products (id bigint, sku text, year text, season_category text, upper_material text, shoe_box_spec text, deleted_at timestamp) [表用途：千百度女鞋商品档案]",
            "public.jst_full_stock (sync_date date, product_code text, actual_stock_qty integer, purchase_in_transit_qty integer, live_warehouse_qty integer) [表用途：当前库存]",
        ]
    )

    compact = schema_for_staged_plan(schema, "按货号查询年份、销量和库存")

    assert "sku text" in compact
    assert "year text" in compact
    assert "actual_stock_qty integer" in compact
    assert "shoe_box_spec" not in compact
    assert "upper_material" not in compact
    assert "live_warehouse_qty" not in compact
    assert "[表用途：当前库存]" in compact


def test_validate_readonly_sql_enforces_open_table_list_and_allows_cte_aliases():
    sql = "WITH sales AS (SELECT sku FROM public.jst_daily_sales) SELECT * FROM sales"
    assert validate_readonly_sql(
        sql,
        allowed_tables={"public.jst_daily_sales", "jst_daily_sales"},
    ) == sql

    with pytest.raises(AiSqlQueryError):
        validate_readonly_sql(
            "SELECT * FROM hidden_table",
            allowed_tables={"public.jst_daily_sales", "jst_daily_sales"},
        )


def test_operation_logs_are_protected_from_ai_sql():
    with pytest.raises(AiSqlQueryError):
        validate_readonly_sql("SELECT * FROM operation_logs")
    with pytest.raises(AiSqlQueryError):
        validate_readonly_sql("SELECT * FROM ai_query_history")


def test_custom_provider_uses_chat_completions_without_response_format(monkeypatch):
    captured: dict[str, object] = {}

    class _Response:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc_value, traceback):
            return False

        def read(self):
            return json.dumps({
                "choices": [{
                    "message": {
                        "content": json.dumps({
                            "sql": "SELECT 1 AS count",
                            "title": "测试",
                            "summary": "测试查询",
                            "warnings": [],
                        })
                    }
                }]
            }).encode("utf-8")

    def _urlopen(request, timeout):
        captured["url"] = request.full_url
        captured["payload"] = json.loads(request.data.decode("utf-8"))
        captured["timeout"] = timeout
        return _Response()

    monkeypatch.setattr(ai_sql_query.urllib.request, "urlopen", _urlopen)
    plan = ai_sql_query.generate_plan(
        question="查询数量",
        schema="public.products (id integer)",
        api_key="test-key",
        provider="custom",
        base_url="https://example.test/v1",
        model="custom-model",
        timeout_seconds=20,
        max_rows=100,
    )

    assert plan.sql == "SELECT 1 AS count"
    assert captured["url"] == "https://example.test/v1/chat/completions"
    assert "response_format" not in captured["payload"]


def test_staged_plan_parser_accepts_independent_aggregate_queries(monkeypatch):
    class _Response:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc_value, traceback):
            return False

        def read(self):
            content = {
                "title": "销量库存分析",
                "summary": "按货号合并销量和库存",
                "warnings": [],
                "join_keys": ["货号"],
                "sort_by": "总销量",
                "sort_direction": "desc",
                "result_limit": 100,
                "stages": [
                    {
                        "name": "销量",
                        "sql": "SELECT product_code AS 货号, SUM(net_sales_quantity) AS 总销量 FROM v_jst_daily_sales GROUP BY product_code",
                    },
                    {
                        "name": "库存",
                        "sql": "SELECT product_code AS 货号, SUM(actual_stock_qty) AS 在仓库存 FROM jst_full_stock GROUP BY product_code",
                    },
                ],
            }
            return json.dumps({
                "choices": [{"message": {"content": json.dumps(content, ensure_ascii=False)}}]
            }).encode("utf-8")

    monkeypatch.setattr(ai_sql_query.urllib.request, "urlopen", lambda *args, **kwargs: _Response())

    plan = ai_sql_query.generate_staged_plan(
        question="按货号查询销量和库存",
        schema="public.v_jst_daily_sales (product_code text)\npublic.jst_full_stock (product_code text)",
        api_key="test-key",
        provider="custom",
        base_url="https://example.test/v1",
        model="custom-model",
        timeout_seconds=20,
        max_rows=500,
        failed_sql="SELECT 1",
        failure_reason="查询计划预计处理的数据量过大",
    )

    assert plan.join_keys == ("货号",)
    assert len(plan.stages) == 2
    assert plan.sort_by == "总销量"
    assert plan.sort_descending is True


def test_staged_results_outer_join_and_sort_without_fact_table_cross_join():
    sales_stage = AiSqlStage(name="销量", sql="SELECT 1")
    stock_stage = AiSqlStage(name="库存", sql="SELECT 1")
    plan = AiStagedPlan(
        stages=(sales_stage, stock_stage),
        join_keys=("货号",),
        title="销量库存",
        summary="",
        warnings=[],
        sort_by="总销量",
        sort_descending=True,
        result_limit=10,
    )

    columns, rows, truncated = merge_staged_query_results(
        plan,
        [
            (
                sales_stage,
                ["货号", "总销量"],
                [
                    {"货号": "B", "总销量": 8},
                    {"货号": "A", "总销量": 12},
                ],
                False,
            ),
            (
                stock_stage,
                ["货号", "在仓库存"],
                [
                    {"货号": "A", "在仓库存": 20},
                    {"货号": "C", "在仓库存": 5},
                ],
                False,
            ),
        ],
        max_rows=500,
    )

    assert columns == ["货号", "总销量", "在仓库存"]
    assert rows == [
        {"货号": "A", "总销量": 12, "在仓库存": 20},
        {"货号": "B", "总销量": 8, "在仓库存": None},
        {"货号": "C", "总销量": None, "在仓库存": 5},
    ]
    assert truncated is False


def test_correction_feedback_is_sent_to_provider(monkeypatch):
    captured: dict[str, object] = {}

    class _Response:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc_value, traceback):
            return False

        def read(self):
            return json.dumps({
                "choices": [{
                    "message": {
                        "content": json.dumps({
                            "sql": "SELECT net_sales_quantity FROM v_jst_daily_sales",
                            "title": "测试",
                            "summary": "测试查询",
                            "warnings": [],
                        })
                    }
                }]
            }).encode("utf-8")

    def _urlopen(request, timeout):
        captured["payload"] = json.loads(request.data.decode("utf-8"))
        return _Response()

    monkeypatch.setattr(ai_sql_query.urllib.request, "urlopen", _urlopen)
    ai_sql_query.generate_plan(
        question="查询销量",
        schema="public.v_jst_daily_sales (net_sales_quantity integer)",
        api_key="test-key",
        provider="custom",
        base_url="https://example.test/v1",
        model="custom-model",
        timeout_seconds=20,
        max_rows=100,
        previous_sql="SELECT sales_quantity FROM v_jst_daily_sales",
        correction_error="聚水潭销量必须默认使用 net_sales_quantity 净销量",
    )

    user_prompt = captured["payload"]["messages"][1]["content"]
    assert "上一次 SQL" in user_prompt
    assert "聚水潭销量必须默认使用 net_sales_quantity" in user_prompt


def test_execute_sql_with_percent_literal_uses_sqlalchemy_text():
    executed_statements = []

    class _Result:
        def keys(self):
            return ["渠道"]

        def mappings(self):
            return [{"渠道": "唯品"}]

    class _Context:
        def __init__(self, value):
            self.value = value

        def __enter__(self):
            return self.value

        def __exit__(self, exc_type, exc_value, traceback):
            return False

    class _Connection:
        def begin(self):
            return _Context(None)

        def exec_driver_sql(self, statement):
            executed_statements.append(statement)

        def execute(self, statement):
            executed_statements.append(statement)
            assert "%唯品%" in statement.text
            return _Result()

    class _Engine:
        def connect(self):
            return _Context(_Connection())

    columns, rows, truncated = execute_readonly_sql(
        _Engine(),
        "SELECT '唯品' AS 渠道 WHERE '唯品' ILIKE '%唯品%'",
        max_rows=10,
        timeout_seconds=5,
    )

    assert columns == ["渠道"]
    assert rows == [{"渠道": "唯品"}]
    assert truncated is False


def test_execute_sql_converts_database_statement_timeout_to_query_timeout():
    class _Context:
        def __init__(self, value):
            self.value = value

        def __enter__(self):
            return self.value

        def __exit__(self, exc_type, exc_value, traceback):
            return False

    class _Connection:
        def begin(self):
            return _Context(None)

        def exec_driver_sql(self, statement):
            return None

        def execute(self, statement):
            raise ai_sql_query.SQLAlchemyError(
                "canceling statement due to statement timeout"
            )

    class _Engine:
        def connect(self):
            return _Context(_Connection())

    with pytest.raises(AiSqlTimeoutError, match="超过 5 秒"):
        execute_readonly_sql(
            _Engine(),
            "SELECT 1",
            max_rows=10,
            timeout_seconds=5,
        )


def test_query_plan_preflight_accepts_bounded_plan():
    class _Result:
        def scalar_one(self):
            return [{
                "Plan": {
                    "Node Type": "Limit",
                    "Total Cost": 1200,
                    "Plan Rows": 101,
                    "Plans": [
                        {
                            "Node Type": "Seq Scan",
                            "Total Cost": 1100,
                            "Plan Rows": 200_000,
                        }
                    ],
                }
            }]

    class _Context:
        def __init__(self, value):
            self.value = value

        def __enter__(self):
            return self.value

        def __exit__(self, exc_type, exc_value, traceback):
            return False

    class _Connection:
        def begin(self):
            return _Context(None)

        def exec_driver_sql(self, statement):
            return None

        def execute(self, statement):
            assert statement.text.startswith("EXPLAIN (FORMAT JSON)")
            return _Result()

    class _Engine:
        def connect(self):
            return _Context(_Connection())

    estimate = assess_readonly_sql_plan(
        _Engine(),
        "SELECT 1 AS value",
        max_rows=100,
        timeout_seconds=5,
        max_plan_cost=2_000_000,
        max_plan_rows=10_000_000,
    )

    assert estimate.total_cost == 1200
    assert estimate.max_plan_rows == 200_000
    assert estimate.max_nested_loop_rows == 0


def test_query_plan_preflight_rejects_large_nested_loop():
    class _Result:
        def scalar_one(self):
            return [{
                "Plan": {
                    "Node Type": "Nested Loop",
                    "Total Cost": 8_000_000,
                    "Plan Rows": 2_000_000,
                    "Plans": [
                        {"Node Type": "Seq Scan", "Plan Rows": 2058},
                        {"Node Type": "Seq Scan", "Plan Rows": 239_613},
                    ],
                }
            }]

    class _Context:
        def __init__(self, value):
            self.value = value

        def __enter__(self):
            return self.value

        def __exit__(self, exc_type, exc_value, traceback):
            return False

    class _Connection:
        def begin(self):
            return _Context(None)

        def exec_driver_sql(self, statement):
            return None

        def execute(self, statement):
            return _Result()

    class _Engine:
        def connect(self):
            return _Context(_Connection())

    with pytest.raises(AiSqlQueryError, match="查询计划预计处理的数据量过大"):
        assess_readonly_sql_plan(
            _Engine(),
            "SELECT 1 AS value",
            max_rows=100,
            timeout_seconds=5,
            max_plan_cost=2_000_000,
            max_plan_rows=10_000_000,
        )


def test_table_permissions_follow_existing_module_permissions():
    product_permissions = {"product.view", "ai_query.view"}
    finance_permissions = {"inventory.view", "purchase.view", "ai_query.view"}
    fine_table_permissions = {"fine_table.view", "ai_query.view"}

    assert table_allowed_for_permissions("cbanner_womens_products", product_permissions)
    assert not table_allowed_for_permissions("inventory_records", product_permissions)
    assert table_allowed_for_permissions("inventory_records", finance_permissions)
    assert not table_allowed_for_permissions("cbanner_womens_products", finance_permissions)
    assert table_allowed_for_permissions("v_jst_daily_sales", fine_table_permissions)
    assert not table_allowed_for_permissions("v_jst_daily_sales", product_permissions)


def test_purchase_permission_view_is_expanded_to_purchase_orders_only():
    sql = (
        "SELECT record.id FROM public.ai_purchase_records AS record "
        "JOIN public.ai_purchase_details AS detail ON detail.document_id = record.id"
    )
    expanded = expand_permission_views(sql)

    assert "document_type = '进货订单'" in expanded
    assert "inventory_records" in expanded
    assert "inventory_details" in expanded
