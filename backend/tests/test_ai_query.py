from types import SimpleNamespace

from sqlalchemy.exc import SQLAlchemyError

from domain.ai_sql_query import AiSqlPlan, AiSqlQueryError
from api.routes import ai_query
from api.routes.ai_query import (
    _can_use_ai_query,
    _extract_brand,
    _extract_codes,
    _extract_year,
    _intent_for,
    _localize_ai_brand_values,
    _permission_set,
    _recent_sales_ranking_spec,
    _run_product_goods,
    _should_use_business_rules,
    _view_for,
    clear_query_history,
    list_query_history,
    query_with_natural_language,
)


def test_natural_language_query_parser_identifies_product_goods_question():
    question = "查询千百度女鞋 QC153883D54 近7天销量和库存"

    assert _extract_brand(question) == "cbanner_womens"
    assert _extract_codes(question) == ["QC153883D54"]
    assert _intent_for(question) == "product_goods"
    assert _view_for(question) == "goods"


def test_natural_language_query_parser_identifies_factory_channel_question():
    question = "查询千百度男鞋2026年各工厂传统、直播、清仓销量"

    assert _extract_brand(question) == "cbanner_mens"
    assert _extract_year(question) == 2026
    assert _intent_for(question) == "factory_channel"


def test_natural_language_query_parser_identifies_task_and_risk_views():
    assert _intent_for("查看今天定时任务执行情况") == "task_status"
    assert _view_for("查询千百度女鞋缺货风险商品") == "shortage_risk"


def test_standard_queries_use_fast_business_rules_and_complex_queries_use_ai():
    standard_question = "查询千百度女鞋 QC153883D54 近7天销量和库存"
    assert _should_use_business_rules(
        standard_question,
        _intent_for(standard_question),
        _extract_brand(standard_question),
        _extract_codes(standard_question),
    )
    assert _should_use_business_rules(
        "查看今天定时任务执行情况",
        "task_status",
        None,
        [],
    )
    ranking_question = "查询千百度女鞋近7天销量前十的商品"
    assert _recent_sales_ranking_spec(ranking_question) == (7, 10)
    assert _should_use_business_rules(
        ranking_question,
        "product_goods",
        "cbanner_womens",
        [],
    )
    assert not _should_use_business_rules(
        "统计2026年采购单按供应商汇总金额",
        "product_archive",
        None,
        [],
    )


def test_recent_sales_ranking_supports_numeric_and_default_limits():
    assert _recent_sales_ranking_spec("千百度女鞋近14天销量前20") == (14, 20)
    assert _recent_sales_ranking_spec("千百度女鞋周销量排行") == (7, 10)
    assert _recent_sales_ranking_spec("千百度女鞋月销量前十") is None


def test_product_goods_uses_recent_sales_ranking_fast_path(monkeypatch):
    calls = []

    def _get_recent_sales_ranking(request, *, brand, days, limit):
        calls.append((brand, days, limit))
        return {
            "items": [
                {
                    "rank": 1,
                    "goods_code": "QC153883D54",
                    "style_code": "QC153883",
                    "recent_sales": 36,
                }
            ],
            "date_start": "2026-08-09",
            "date_end": "2026-08-15",
            "sales_product_count": 25,
            "period_sales": 180,
            "sources": ["jst_daily_sales_2026", "vip_daily_sales_2026"],
        }

    monkeypatch.setattr(ai_query, "get_recent_sales_ranking", _get_recent_sales_ranking)
    monkeypatch.setattr(
        ai_query,
        "list_product_goods",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError("排行查询不应加载完整货品表")
        ),
    )
    request = SimpleNamespace(
        state=SimpleNamespace(current_user={"permissions": ["product.view"]})
    )

    payload = _run_product_goods(
        request,
        "查询千百度女鞋近7天销量前十的商品",
        ai_query._base_response("查询千百度女鞋近7天销量前十的商品", "product_goods"),
        "cbanner_womens",
        [],
    )

    assert calls == [("cbanner_womens", 7, 10)]
    assert payload["title"] == "千百度女鞋近7天销量排行"
    assert payload["rows"][0]["recent_sales"] == 36
    assert payload["data_as_of"] == [{"label": "最新销售日期", "value": "2026-08-15"}]
    assert payload["link"]["href"] == (
        "/product-goods?brand=cbanner_womens&query=QC153883D54&view=goods"
    )


def test_product_goods_queries_every_detected_product_code(monkeypatch):
    calls = []

    def _list_product_goods(request, *, brand, view, query, page, page_size):
        calls.append(query)
        in_transit = 60 if query == "C7763372D01" else 80
        return {
            "total": 1,
            "daily_dates": ["2026-08-15"],
            "items": [
                {
                    "goods_code": query,
                    "style_code": query,
                    "metrics": {"week_sales": 0},
                    "stock_total": 0,
                    "in_transit_total": in_transit,
                    "inventory_total": in_transit,
                }
            ],
        }

    monkeypatch.setattr(ai_query, "list_product_goods", _list_product_goods)
    request = SimpleNamespace(
        state=SimpleNamespace(current_user={"permissions": ["product.view"]})
    )

    payload = _run_product_goods(
        request,
        "查询两个货号近7天销量和库存",
        ai_query._base_response("查询两个货号近7天销量和库存", "product_goods"),
        "cbanner_mens",
        ["C7763372D01", "C7763373D24"],
    )

    assert calls == ["C7763372D01", "C7763373D24"]
    assert [row["goods_code"] for row in payload["rows"]] == calls
    assert [row["in_transit_total"] for row in payload["rows"]] == [60, 80]
    assert payload["metrics"][0]["value"] == 2
    assert payload["link"]["href"].endswith(
        "query=C7763372D01,C7763373D24&view=goods"
    )
    assert payload["suggestions"] == ["查看这批商品的商品档案"]


def test_brandless_product_codes_resolve_brand_before_ai_sql(monkeypatch):
    class _HistoryRepository:
        def add_ai_query_history(self, user_id, question, *, limit):
            return None

    request = SimpleNamespace(
        state=SimpleNamespace(
            current_user={
                "id": 7,
                "permissions": ["product.view", "ai_query.view"],
            }
        ),
        app=SimpleNamespace(
            state=SimpleNamespace(
                settings=SimpleNamespace(ai_sql_enabled=True),
                auth_repository=_HistoryRepository(),
            )
        ),
    )
    monkeypatch.setattr(
        ai_query,
        "_resolve_brand",
        lambda request, question, code, brand: ("cbanner_mens", None),
    )
    monkeypatch.setattr(
        ai_query,
        "_run_product_goods",
        lambda request, question, payload, brand, codes: {
            **payload,
            "title": "货品表结果",
            "rows": [{"goods_code": code} for code in codes],
            "query_mode": "business_rules",
        },
    )
    monkeypatch.setattr(
        ai_query,
        "_run_ai_sql",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError("不应调用 AI SQL")
        ),
    )
    monkeypatch.setattr(ai_query, "write_operation_log", lambda *args, **kwargs: None)

    payload = query_with_natural_language(
        request,
        {"question": "查询C7763373D24,C7763372D01近7天的销量和库存"},
    )

    assert payload["query_mode"] == "business_rules"
    assert [row["goods_code"] for row in payload["rows"]] == [
        "C7763373D24",
        "C7763372D01",
    ]


def test_ai_sql_brand_columns_return_chinese_labels():
    rows = [
        {"品牌": "cbanner_mens", "货号": "C7763372D01"},
        {"品牌": "cbanner_womens", "货号": "QC153883D54"},
    ]

    _localize_ai_brand_values(["品牌", "货号"], rows)

    assert [row["品牌"] for row in rows] == ["千百度男鞋", "千百度女鞋"]


def test_query_history_is_scoped_to_current_user():
    class _HistoryRepository:
        def __init__(self):
            self.items = {
                7: ["用户七的查询"],
                8: ["用户八的查询"],
            }

        def list_ai_query_history(self, user_id, *, limit):
            return self.items.get(user_id, [])[:limit]

        def clear_ai_query_history(self, user_id):
            self.items[user_id] = []

    repository = _HistoryRepository()
    request = SimpleNamespace(
        state=SimpleNamespace(current_user={"id": 7}),
        app=SimpleNamespace(state=SimpleNamespace(auth_repository=repository)),
    )

    assert list_query_history(request) == {"items": ["用户七的查询"]}
    assert clear_query_history(request) == {"message": "最近查询已清空"}
    assert list_query_history(request) == {"items": []}
    assert repository.items[8] == ["用户八的查询"]


def test_all_read_departments_can_use_ai_with_their_existing_permissions():
    finance_user = {
        "permissions": ["inventory.view", "purchase.view", "ai_query.view"]
    }
    design_user = {"permissions": ["product.view", "ai_query.view"]}

    assert _can_use_ai_query(finance_user)
    assert _can_use_ai_query(design_user)
    assert _permission_set(finance_user) == {
        "inventory.view",
        "purchase.view",
        "ai_query.view",
    }


def test_ai_sql_retries_once_with_validation_feedback(monkeypatch):
    settings = SimpleNamespace(
        ai_api_key="test-key",
        ai_provider="custom",
        ai_base_url="https://example.test/v1",
        ai_model="custom-model",
        ai_sql_max_rows=100,
        ai_timeout_seconds=10,
    )
    permissions = {"fine_table.view", "ai_query.view"}
    cache_key = tuple(sorted(permissions))
    state = SimpleNamespace(
        settings=settings,
        repository=SimpleNamespace(engine=object()),
        ai_sql_schema_cache={
            cache_key: "public.v_jst_daily_sales (net_sales_quantity integer)"
        },
    )
    request = SimpleNamespace(app=SimpleNamespace(state=state))
    generated_calls = []
    plans = iter([
        AiSqlPlan(
            sql="SELECT sales_quantity FROM v_jst_daily_sales",
            title="首次",
            summary="首次",
            warnings=[],
        ),
        AiSqlPlan(
            sql="SELECT net_sales_quantity FROM v_jst_daily_sales",
            title="修正",
            summary="已修正",
            warnings=[],
        ),
    ])

    def _generate_plan(**kwargs):
        generated_calls.append(kwargs)
        return next(plans)

    execution_calls = []

    def _execute_readonly_sql(engine, sql, **kwargs):
        execution_calls.append(sql)
        if len(execution_calls) == 1:
            raise AiSqlQueryError("聚水潭销量必须默认使用 net_sales_quantity 净销量")
        return ["销量"], [{"销量": 12}], False

    monkeypatch.setattr(ai_query, "generate_plan", _generate_plan)
    monkeypatch.setattr(ai_query, "execute_readonly_sql", _execute_readonly_sql)

    payload = ai_query._run_ai_sql(request, "查询销量", permissions)

    assert len(generated_calls) == 2
    assert generated_calls[0]["correction_error"] is None
    assert generated_calls[1]["previous_sql"] == execution_calls[0]
    assert "net_sales_quantity" in generated_calls[1]["correction_error"]
    assert payload["generated_sql"] == execution_calls[1]
    assert any("自动修正" in warning for warning in payload["warnings"])


def test_ai_sql_retries_once_when_database_execution_fails(monkeypatch):
    settings = SimpleNamespace(
        ai_api_key="test-key",
        ai_provider="custom",
        ai_base_url="https://example.test/v1",
        ai_model="custom-model",
        ai_sql_max_rows=100,
        ai_timeout_seconds=10,
    )
    permissions = {"fine_table.view", "ai_query.view"}
    cache_key = tuple(sorted(permissions))
    state = SimpleNamespace(
        settings=settings,
        repository=SimpleNamespace(engine=object()),
        ai_sql_schema_cache={
            cache_key: "public.v_jst_daily_sales (net_sales_quantity integer)"
        },
    )
    request = SimpleNamespace(app=SimpleNamespace(state=state))
    generated_calls = []
    plans = iter(
        [
            AiSqlPlan(
                sql="SELECT missing_column FROM v_jst_daily_sales",
                title="首次",
                summary="首次",
                warnings=[],
            ),
            AiSqlPlan(
                sql="SELECT net_sales_quantity FROM v_jst_daily_sales",
                title="修正",
                summary="已修正",
                warnings=[],
            ),
        ]
    )

    def _generate_plan(**kwargs):
        generated_calls.append(kwargs)
        return next(plans)

    execution_calls = []

    def _execute_readonly_sql(engine, sql, **kwargs):
        execution_calls.append(sql)
        if len(execution_calls) == 1:
            raise SQLAlchemyError('column "missing_column" does not exist')
        return ["销量"], [{"销量": 12}], False

    monkeypatch.setattr(ai_query, "generate_plan", _generate_plan)
    monkeypatch.setattr(ai_query, "execute_readonly_sql", _execute_readonly_sql)

    payload = ai_query._run_ai_sql(request, "查询销量", permissions)

    assert len(generated_calls) == 2
    assert generated_calls[1]["previous_sql"] == execution_calls[0]
    assert "数据库执行失败" in generated_calls[1]["correction_error"]
    assert "missing_column" in generated_calls[1]["correction_error"]
    assert payload["generated_sql"] == execution_calls[1]
    assert any("自动修正" in warning for warning in payload["warnings"])


def test_ai_sql_reuses_validated_plan_and_requeries_current_data(monkeypatch):
    settings = SimpleNamespace(
        ai_api_key="test-key",
        ai_provider="custom",
        ai_base_url="https://example.test/v1",
        ai_model="custom-model",
        ai_sql_max_rows=100,
        ai_timeout_seconds=10,
    )
    permissions = {"fine_table.view", "ai_query.view"}
    cache_key = tuple(sorted(permissions))
    state = SimpleNamespace(
        settings=settings,
        repository=SimpleNamespace(engine=object()),
        ai_sql_schema_cache={
            cache_key: "public.v_jst_daily_sales (net_sales_quantity integer)"
        },
    )
    request = SimpleNamespace(app=SimpleNamespace(state=state))
    generated_calls = []
    execution_calls = []

    def _generate_plan(**kwargs):
        generated_calls.append(kwargs)
        return AiSqlPlan(
            sql="SELECT net_sales_quantity FROM v_jst_daily_sales",
            title="销量",
            summary="销量查询",
            warnings=[],
        )

    def _execute_readonly_sql(engine, sql, **kwargs):
        execution_calls.append(sql)
        return ["销量"], [{"销量": len(execution_calls)}], False

    monkeypatch.setattr(ai_query, "generate_plan", _generate_plan)
    monkeypatch.setattr(ai_query, "execute_readonly_sql", _execute_readonly_sql)

    first = ai_query._run_ai_sql(request, "查询销量", permissions)
    second = ai_query._run_ai_sql(request, "查询销量", permissions)

    assert len(generated_calls) == 1
    assert len(execution_calls) == 2
    assert first["rows"] == [{"销量": 1}]
    assert second["rows"] == [{"销量": 2}]
    assert any("复用校验通过" in warning for warning in second["warnings"])
