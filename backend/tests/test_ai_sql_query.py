import json

import pytest

from domain import ai_sql_query
from domain.ai_sql_query import (
    AiSqlQueryError,
    execute_readonly_sql,
    expand_permission_views,
    is_mutation_request,
    schema_for_question,
    table_allowed_for_permissions,
    validate_readonly_sql,
)


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
