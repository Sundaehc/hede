from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from sqlalchemy.exc import SQLAlchemyError

from domain.ai_sql_query import AiSqlPlan, AiSqlQueryError, AiSqlTimeoutError
from api.routes import ai_query
from api.routes.ai_query import (
    _can_use_ai_query,
    _current_inventory_summary_spec,
    _extract_brand,
    _extract_codes,
    _extract_year,
    _historical_order_summary_spec,
    _intent_for,
    _is_contextual_followup,
    _localize_ai_brand_values,
    _permission_set,
    _recent_sales_ranking_spec,
    _seasonal_category_sales_ranking_spec,
    _run_product_goods,
    _run_historical_order_summary,
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


def test_context_followup_detection_does_not_pollute_complete_new_queries():
    context = {
        "questions": ["查询千百度女鞋 QC153883D54 近7天销量和库存"],
        "brand": "cbanner_womens",
        "product_codes": ["QC153883D54"],
        "intent": "product_goods",
    }

    assert _is_contextual_followup("那库存呢", context)
    assert _is_contextual_followup("按供应商汇总", context)
    assert not _is_contextual_followup("查看今天定时任务执行情况", context)
    assert not _is_contextual_followup("查询千百度男鞋 C7763372D01 库存", context)


def test_product_goods_followup_inherits_brand_and_product_codes(monkeypatch):
    captured = {}

    class _HistoryRepository:
        def add_ai_query_history(self, user_id, question, *, limit):
            return None

    def _run_goods(request, question, payload, brand, codes):
        captured.update(question=question, brand=brand, codes=codes)
        return {
            **payload,
            "title": "库存查询",
            "rows": [{"goods_code": codes[0], "stock_total": 12}],
        }

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
    monkeypatch.setattr(ai_query, "_run_product_goods", _run_goods)
    monkeypatch.setattr(
        ai_query,
        "_run_ai_sql",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError("带货号的库存追问不应调用 AI SQL")
        ),
    )
    monkeypatch.setattr(ai_query, "write_operation_log", lambda *args, **kwargs: None)

    payload = query_with_natural_language(
        request,
        {
            "question": "那库存呢",
            "context": {
                "questions": ["查询千百度女鞋 QC153883D54 近7天销量"],
                "brand": "cbanner_womens",
                "product_codes": ["QC153883D54"],
                "year": 2026,
                "intent": "product_goods",
            },
        },
    )

    assert captured["brand"] == "cbanner_womens"
    assert captured["codes"] == ["QC153883D54"]
    assert "千百度女鞋" in captured["question"]
    assert "QC153883D54" in captured["question"]
    assert payload["question"] == "那库存呢"
    assert payload["context"] == {
        "questions": ["查询千百度女鞋 QC153883D54 近7天销量", "那库存呢"],
        "brand": "cbanner_womens",
        "product_codes": ["QC153883D54"],
        "year": 2026,
        "intent": "product_goods",
        "used_previous": True,
    }


def test_product_goods_context_can_switch_to_product_archive(monkeypatch):
    captured = {}

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

    def _run_archive(request, question, payload, brand, codes):
        captured.update(question=question, brand=brand, codes=codes)
        return {**payload, "title": "商品档案", "rows": [{"sku": codes[0]}]}

    monkeypatch.setattr(ai_query, "_run_product_archive", _run_archive)
    monkeypatch.setattr(
        ai_query,
        "_run_product_goods",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError("商品档案追问不应继续走货品表")
        ),
    )
    monkeypatch.setattr(ai_query, "write_operation_log", lambda *args, **kwargs: None)

    payload = query_with_natural_language(
        request,
        {
            "question": "查看这些商品的商品档案",
            "context": {
                "questions": ["查询千百度女鞋近7天销量前10"],
                "brand": "cbanner_womens",
                "product_codes": ["QC153883D54"],
                "year": 2026,
                "intent": "product_goods",
            },
        },
    )

    assert captured["brand"] == "cbanner_womens"
    assert captured["codes"] == ["QC153883D54"]
    assert payload["intent"] == "product_archive"


def test_product_goods_context_aggregation_uses_ai_sql(monkeypatch):
    captured = {}

    class _HistoryRepository:
        def add_ai_query_history(self, user_id, question, *, limit):
            return None

    request = SimpleNamespace(
        state=SimpleNamespace(
            current_user={
                "id": 7,
                "permissions": [
                    "product.view",
                    "fine_table.view",
                    "ai_query.view",
                ],
            }
        ),
        app=SimpleNamespace(
            state=SimpleNamespace(
                settings=SimpleNamespace(ai_sql_enabled=True),
                auth_repository=_HistoryRepository(),
            )
        ),
    )

    def _run_ai(request, question, permissions):
        captured.update(question=question, permissions=permissions)
        return {
            **ai_query._base_response(question, "ai_sql"),
            "query_mode": "ai_sql",
            "rows": [{"供应商": "测试工厂", "销量": 20}],
        }

    monkeypatch.setattr(ai_query, "_run_ai_sql", _run_ai)
    monkeypatch.setattr(
        ai_query,
        "_run_product_goods",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError("上下文聚合追问不应退化为货品明细")
        ),
    )
    monkeypatch.setattr(ai_query, "write_operation_log", lambda *args, **kwargs: None)

    payload = query_with_natural_language(
        request,
        {
            "question": "按供应商汇总",
            "context": {
                "questions": ["查询千百度女鞋近7天销量前10"],
                "brand": "cbanner_womens",
                "product_codes": ["QC153883D54", "QB652166W24"],
                "year": 2026,
                "intent": "product_goods",
            },
        },
    )

    assert "查询千百度女鞋近7天销量前10" in captured["question"]
    assert "货号=QC153883D54,QB652166W24" in captured["question"]
    assert payload["query_mode"] == "ai_sql"


def test_ai_sql_followup_receives_compact_conversation_context(monkeypatch):
    captured = {}

    class _HistoryRepository:
        def add_ai_query_history(self, user_id, question, *, limit):
            return None

    request = SimpleNamespace(
        state=SimpleNamespace(
            current_user={
                "id": 7,
                "permissions": ["purchase.view", "ai_query.view"],
            }
        ),
        app=SimpleNamespace(
            state=SimpleNamespace(
                settings=SimpleNamespace(ai_sql_enabled=True),
                auth_repository=_HistoryRepository(),
            )
        ),
    )

    def _run_ai(request, question, permissions):
        captured.update(question=question, permissions=permissions)
        return {
            **ai_query._base_response(question, "ai_sql"),
            "query_mode": "ai_sql",
            "title": "采购金额汇总",
            "rows": [{"供应商": "测试工厂", "金额": 100}],
        }

    monkeypatch.setattr(ai_query, "_run_ai_sql", _run_ai)
    monkeypatch.setattr(ai_query, "write_operation_log", lambda *args, **kwargs: None)

    payload = query_with_natural_language(
        request,
        {
            "question": "按供应商汇总",
            "context": {
                "questions": ["查询2026年采购单总金额"],
                "brand": None,
                "product_codes": [],
                "year": 2026,
                "intent": "product_archive",
            },
        },
    )

    assert "查询2026年采购单总金额" in captured["question"]
    assert "当前追问：按供应商汇总" in captured["question"]
    assert captured["permissions"] == {"purchase.view", "ai_query.view"}
    assert payload["question"] == "按供应商汇总"
    assert payload["context"]["used_previous"] is True


def test_natural_language_query_parser_identifies_factory_channel_question():
    question = "查询千百度男鞋2026年各工厂传统、直播、清仓销量"

    assert _extract_brand(question) == "cbanner_mens"
    assert _extract_year(question) == 2026
    assert _intent_for(question) == "factory_channel"


def test_natural_language_query_parser_identifies_historical_order_summary():
    question = "24-25年秋冬每个月各品类新款下单数量"

    assert _intent_for(question) == "historical_order_summary"
    assert _historical_order_summary_spec(question) == {
        "start_year": 2024,
        "end_year": 2025,
        "season_label": "秋冬",
        "season_keywords": ("秋", "冬"),
        "product_role": "新品",
    }


def test_historical_order_summary_uses_fixed_business_result(monkeypatch):
    calls = []

    def _summary(request, **kwargs):
        calls.append(kwargs)
        return {
            "items": [
                {"month": "2024-09", "category_l4": "板鞋", "order_quantity": 12}
            ],
            "total_order_quantity": 12,
            "matched_orders": 1,
            "unmatched_orders": 0,
            "sources": ["product_goods_historical_orders_2024"],
        }

    monkeypatch.setattr(ai_query, "get_historical_order_category_monthly_summary", _summary)
    request = SimpleNamespace(
        state=SimpleNamespace(
            current_user={"permissions": ["product.view", "fine_table.view"]}
        )
    )
    question = "24-25年秋冬每个月各品类新款下单数量"

    payload = _run_historical_order_summary(
        request,
        question,
        ai_query._base_response(question, "historical_order_summary"),
        "cbanner_womens",
    )

    assert calls == [
        {
            "start_year": 2024,
            "end_year": 2025,
            "brands": {"cbanner_womens"},
            "season_keywords": ("秋", "冬"),
            "product_role": "新品",
        }
    ]
    assert payload["rows"] == [
        {"month": "2024-09", "category_l4": "板鞋", "order_quantity": 12}
    ]
    assert payload["metrics"][0]["value"] == 12
    assert payload["sources"] == [
        "历史订单",
        "商品信息档案",
        "货品表手工字段",
        "product_goods_historical_orders_2024",
    ]


def test_historical_order_summary_bypasses_ai_sql(monkeypatch):
    class _HistoryRepository:
        def add_ai_query_history(self, user_id, question, *, limit):
            return None

    request = SimpleNamespace(
        state=SimpleNamespace(
            current_user={
                "id": 7,
                "permissions": [
                    "product.view",
                    "fine_table.view",
                    "ai_query.view",
                ],
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
        "get_historical_order_category_monthly_summary",
        lambda *args, **kwargs: {
            "items": [],
            "total_order_quantity": 0,
            "matched_orders": 0,
            "unmatched_orders": 0,
            "sources": [],
        },
    )
    monkeypatch.setattr(
        ai_query,
        "_run_ai_sql",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError("固定历史订单汇总不应调用 AI SQL")
        ),
    )
    monkeypatch.setattr(ai_query, "write_operation_log", lambda *args, **kwargs: None)

    payload = query_with_natural_language(
        request,
        {"question": "24-25年秋冬每个月各品类新款下单数量"},
    )

    assert payload["intent"] == "historical_order_summary"
    assert payload["query_mode"] == "business_rules"
    assert payload["generated_sql"] is None


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

    inventory_question = "2026年千百度女鞋春季款的库存数量"
    assert _current_inventory_summary_spec(inventory_question) == {
        "year": 2026,
        "season_label": "春季款",
        "year_label": "26年春季款",
    }
    assert _should_use_business_rules(
        inventory_question,
        "product_goods",
        "cbanner_womens",
        [],
    )


def test_recent_sales_ranking_supports_numeric_and_default_limits():
    assert _recent_sales_ranking_spec("千百度女鞋近14天销量前20") == (14, 20)
    assert _recent_sales_ranking_spec("千百度女鞋周销量排行") == (7, 10)
    assert _recent_sales_ranking_spec("千百度女鞋月销量前十") is None


def test_current_inventory_summary_uses_fast_business_path(monkeypatch):
    calls = []

    def _get_summary(request, **kwargs):
        calls.append(kwargs)
        return {
            "year_label": "26年春季款",
            "product_count": 2058,
            "matched_product_count": 1495,
            "stock_total": 72524,
            "in_transit_total": 1857,
            "inventory_total": 74381,
            "source_as_of_date": "2026-07-23",
        }

    monkeypatch.setattr(ai_query, "get_current_inventory_summary", _get_summary)
    monkeypatch.setattr(
        ai_query,
        "list_product_goods",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError("季节款库存汇总不应加载完整货品表")
        ),
    )
    request = SimpleNamespace(
        state=SimpleNamespace(current_user={"permissions": ["product.view"]})
    )

    payload = _run_product_goods(
        request,
        "2026年千百度女鞋春季款的库存数量",
        ai_query._base_response(
            "2026年千百度女鞋春季款的库存数量",
            "product_goods",
        ),
        "cbanner_womens",
        [],
    )

    assert calls == [
        {"brand": "cbanner_womens", "year_label": "26年春季款"}
    ]
    assert payload["query_mode"] == "business_rules"
    assert payload["metrics"][2]["value"] == 74381
    assert payload["data_as_of"] == [
        {"label": "库存数据日期", "value": "2026-07-23"}
    ]
    assert payload["warnings"] == [
        "库存源最新成功更新日期为 2026-07-23，并非今天数据。"
    ]


def test_seasonal_category_sales_ranking_supports_compact_top_wording():
    assert _seasonal_category_sales_ranking_spec(
        "千百度女鞋细分品类top前10单品是什么款式，秋冬销量是多少"
    ) == {
        "limit": 10,
        "season_label": "秋冬",
        "season_keywords": ("秋", "冬"),
        "sales_year": None,
    }
    assert _seasonal_category_sales_ranking_spec(
        "千百度女鞋2025年春夏分类销量前20"
    ) == {
        "limit": 20,
        "season_label": "春夏",
        "season_keywords": ("春", "夏"),
        "sales_year": 2025,
    }


def test_seasonal_category_sales_ranking_uses_fast_business_path(monkeypatch):
    calls = []

    def _get_ranking(request, **kwargs):
        calls.append(kwargs)
        return {
            "items": [
                {
                    "rank": 1,
                    "category_l4": "老爹鞋",
                    "goods_code": "RI861599D25",
                    "style_code": "RI861599",
                    "product_name": "女休闲鞋",
                    "season": "秋冬",
                    "sales_quantity": 8717,
                }
            ],
            "sales_year": 2026,
            "source_as_of_date": "2026-08-16",
            "sales_product_count": 4686,
            "period_sales": 471968,
            "sources": [
                "product_goods_sales_periods",
                "jst_daily_sales_2026",
                "vip_daily_sales_2026",
            ],
        }

    class _HistoryRepository:
        def add_ai_query_history(self, user_id, question, *, limit):
            return None

    monkeypatch.setattr(
        ai_query,
        "get_seasonal_category_sales_ranking",
        _get_ranking,
    )
    monkeypatch.setattr(
        ai_query,
        "list_product_goods",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError("季节品类排行不应加载完整货品表")
        ),
    )
    monkeypatch.setattr(
        ai_query,
        "_run_ai_sql",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError("季节品类排行不应调用 AI SQL")
        ),
    )
    monkeypatch.setattr(ai_query, "write_operation_log", lambda *args, **kwargs: None)
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
    question = "千百度女鞋细分品类top前10单品是什么款式，秋冬销量是多少"

    payload = query_with_natural_language(request, {"question": question})

    assert calls == [
        {
            "brand": "cbanner_womens",
            "season_keywords": ("秋", "冬"),
            "season_label": "秋冬",
            "limit": 10,
            "sales_year": None,
        }
    ]
    assert payload["query_mode"] == "business_rules"
    assert payload["rows"][0]["goods_code"] == "RI861599D25"
    assert payload["data_as_of"] == [
        {"label": "销量数据截至", "value": "2026-08-16"}
    ]


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


def test_ai_sql_preflight_optimizes_before_database_execution(monkeypatch):
    settings = SimpleNamespace(
        ai_api_key="test-key",
        ai_provider="custom",
        ai_base_url="https://example.test/v1",
        ai_model="custom-model",
        ai_sql_max_rows=100,
        ai_timeout_seconds=180,
        ai_sql_preflight_enabled=True,
        ai_sql_explain_timeout_seconds=5,
        ai_sql_max_plan_cost=2_000_000,
        ai_sql_max_plan_rows=10_000_000,
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
                sql="SELECT * FROM v_jst_daily_sales",
                title="首次",
                summary="首次",
                warnings=[],
            ),
            AiSqlPlan(
                sql="SELECT SUM(net_sales_quantity) AS 销量 FROM v_jst_daily_sales",
                title="优化",
                summary="优化",
                warnings=[],
            ),
        ]
    )
    assessed_sql = []
    executed_sql = []

    def _generate_plan(**kwargs):
        generated_calls.append(kwargs)
        return next(plans)

    def _assess_plan(engine, sql, **kwargs):
        assessed_sql.append(sql)
        if len(assessed_sql) == 1:
            raise AiSqlQueryError("查询计划预计处理的数据量过大")
        return SimpleNamespace()

    def _execute_readonly_sql(engine, sql, **kwargs):
        executed_sql.append(sql)
        return ["销量"], [{"销量": 12}], False

    monkeypatch.setattr(ai_query, "generate_plan", _generate_plan)
    monkeypatch.setattr(ai_query, "assess_readonly_sql_plan", _assess_plan)
    monkeypatch.setattr(ai_query, "execute_readonly_sql", _execute_readonly_sql)

    payload = ai_query._run_ai_sql(request, "查询复杂销量汇总", permissions)

    assert len(generated_calls) == 2
    assert len(assessed_sql) == 2
    assert executed_sql == [assessed_sql[1]]
    assert "查询计划预计处理的数据量过大" in generated_calls[1]["correction_error"]
    assert any("查询计划优化" in warning for warning in payload["warnings"])


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


def test_ai_sql_timeout_stops_without_second_generation(monkeypatch):
    settings = SimpleNamespace(
        ai_api_key="test-key",
        ai_provider="custom",
        ai_base_url="https://example.test/v1",
        ai_model="custom-model",
        ai_sql_max_rows=100,
        ai_timeout_seconds=180,
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
        raise AiSqlTimeoutError("查询执行超过 180 秒")

    monkeypatch.setattr(ai_query, "generate_plan", _generate_plan)
    monkeypatch.setattr(ai_query, "execute_readonly_sql", _execute_readonly_sql)

    with pytest.raises(HTTPException) as error:
        ai_query._run_ai_sql(request, "查询复杂销量汇总", permissions)

    assert error.value.status_code == 408
    assert "超过 180 秒" in error.value.detail
    assert len(generated_calls) == 1
    assert len(execution_calls) == 1


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
