from datetime import date, datetime
import re
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine, event, select, text
from sqlalchemy.dialects import postgresql

from api.product_goods_cache import clear_product_goods_cache
from api.routes import product_goods as goods_routes
from api.routes.fine_table import _latest_daily_snapshot_day
from domain import excluded_skus
from domain.gj_schema import GJ_MERGED_PRODUCT_INFO_TABLE
from domain.inventory_schema import SUPPLIER_TABLE
from domain.product_goods_schema import PRODUCT_GOODS_OVERRIDES_TABLE
from domain.schema import PRODUCT_TABLES
from domain.vip_schema import JST_STOCK_SUMMARY_TABLE
from scripts.optimize_product_pagination import PARENT_INDEX, build_index_plan, normalize_index_definition


@pytest.fixture
def goods_request(monkeypatch):
    engine = create_engine("sqlite://")
    event.listen(engine, "connect", lambda connection, record: connection.create_function("date_trunc", 2, lambda unit, value: value))
    event.listen(engine, "connect", lambda connection, record: connection.create_function("regexp_replace", 3, lambda value, pattern, replacement: re.sub(pattern, replacement, value)))
    product_table = PRODUCT_TABLES["cbanner_womens"]
    for table in (product_table, PRODUCT_GOODS_OVERRIDES_TABLE, GJ_MERGED_PRODUCT_INFO_TABLE,
                  JST_STOCK_SUMMARY_TABLE, SUPPLIER_TABLE):
        table.create(engine)
    with engine.begin() as connection:
        connection.execute(product_table.insert(), [
            {"id": record_id, "sku": sku, "original_sku": sku, "year": year,
             "source_workbook": "test", "source_sheet": "test", "source_row_number": str(record_id),
             "raw_payload": {}, "deleted_at": datetime(2026, 10, 1) if record_id == 5 else None}
            for record_id, sku, year in [(1, "B", "2026"), (2, "A", "2026"), (3, "C", "2025"),
                                         (4, "D", None), (5, "E", "2026")]
        ])
        connection.execute(GJ_MERGED_PRODUCT_INFO_TABLE.insert(), [
            {"id": record_id, "goods_code": sku, "original_goods_code": sku,
             "fine_table_brand": "cbanner_womens", "source_date": "2026-10-14",
             "source_date_value": date(2026, 10, 14)}
            for record_id, sku in [(1, "A"), (2, "B"), (3, "C"), (4, "D"), (5, "E")]
        ])
        connection.execute(PRODUCT_GOODS_OVERRIDES_TABLE.insert(), {
            "id": 1, "brand": "cbanner_womens", "product_id": 2, "platform": "唯品",
        })
    empty_helpers = ("_current_full_stock_payload", "_size_stock_payload", "_aftersale_return_quantities",
                     "_detail_snapshot_payload", "_historical_order_counts")
    for name in empty_helpers:
        monkeypatch.setattr(goods_routes, name, lambda *args, **kwargs: {})
    monkeypatch.setattr(goods_routes, "_product_goods_snapshot_dates", lambda *args, **kwargs: [])
    monkeypatch.setattr(goods_routes, "_sales_matrix_payload", lambda *args, **kwargs: ([], {}, {}, {}, {}))
    monkeypatch.setattr(goods_routes, "_sales_period_payload", lambda *args, **kwargs: ([], [], {}, {}))
    clear_product_goods_cache()
    request = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(
        repository=SimpleNamespace(engine=engine), settings=SimpleNamespace(image_roots={}),
    )))
    try:
        yield request
    finally:
        clear_product_goods_cache()
        engine.dispose()


def list_goods(request, **kwargs):
    parameters = {"brand": "cbanner_womens", "view": "goods", "query": None, "platform": None,
                  "year": None, "filters": None, "snapshot_date": None, "cache_bust": None,
                  "page": 1, "page_size": 2}
    parameters.update(kwargs)
    return goods_routes.list_product_goods(request, **parameters)


def test_goods_paginates_before_loading_full_rows_and_reuses_matching_total(goods_request):
    statements = []
    event.listen(goods_request.app.state.repository.engine, "before_cursor_execute",
                 lambda connection, cursor, statement, parameters, context, executemany: statements.append(statement))
    first = list_goods(goods_request)
    second = list_goods(goods_request, page=2)
    assert [item["goods_code"] for item in first["items"]] == ["A", "B"]
    assert [item["goods_code"] for item in second["items"]] == ["C", "D"]
    assert first["total"] == second["total"] == 4
    assert first["items"][0]["platform"] == "唯品"
    assert len([statement for statement in statements if "SELECT count(*)" in statement]) == 1
    page_queries = [statement for statement in statements if "AS goods_page" in statement]
    assert len(page_queries) == 2
    assert all(statement.index("LIMIT") < statement.index("AS goods_page") for statement in page_queries)
    assert list_goods(goods_request, query="A")["total"] == 1
    assert list_goods(goods_request, cache_bust="refresh")["total"] == 4
    assert len([statement for statement in statements if "SELECT count(*)" in statement]) == 3


def test_goods_archive_source_keeps_order_and_empty_page_total(goods_request, monkeypatch):
    monkeypatch.setattr(goods_routes, "_uses_gj_product_goods_source", lambda *args: False)
    first = list_goods(goods_request)
    missing = list_goods(goods_request, page=4)
    assert [item["goods_code"] for item in first["items"]] == ["A", "B"]
    assert missing["items"] == [] and missing["total"] == 5


def test_goods_filters_style_summary_and_cache_clear_keep_separate_totals(goods_request):
    first = list_goods(goods_request)
    selected = list_goods(goods_request, platform="唯品")
    summary = list_goods(goods_request, view="style_summary", page_size=3)
    assert first["total"] == 4
    assert selected["total"] == 1
    assert [item["goods_code"] for item in selected["items"]] == ["A"]
    assert summary["total"] == 4
    assert [item["style_code"] for item in summary["items"]] == ["A", "B", "C"]
    with goods_request.app.state.repository.engine.begin() as connection:
        connection.execute(GJ_MERGED_PRODUCT_INFO_TABLE.delete().where(GJ_MERGED_PRODUCT_INFO_TABLE.c.goods_code == "D"))
    clear_product_goods_cache()
    assert list_goods(goods_request, page=2)["total"] == 3


def test_fine_latest_snapshot_date_uses_only_requested_goods_and_report_period():
    engine = create_engine("sqlite://")
    try:
        with engine.begin() as connection:
            connection.execute(text("CREATE TABLE vip_product_daily_snapshots (goods_code TEXT, snapshot_date DATE, report_type TEXT, period TEXT)"))
            connection.execute(text("""
                INSERT INTO vip_product_daily_snapshots VALUES
                ('A', '2026-10-10', '罗盘', '1d'), ('B', '2026-10-12', '罗盘', '1d'),
                ('A', '2026-10-14', '罗盘', '7d'), ('A', '2026-10-13', '环比', '1d'),
                ('OTHER', '2026-10-14', '罗盘', '1d')
            """))
            assert _latest_daily_snapshot_day(connection, ["A", "B"]) == date(2026, 10, 12)
            assert _latest_daily_snapshot_day(connection, ["MISSING"]) is None
            assert _latest_daily_snapshot_day(connection, []) is None
    finally:
        engine.dispose()


def test_excluded_sku_condition_passes_one_escaped_array_and_uses_noncorrelated_membership(monkeypatch):
    values = frozenset({"A,B", 'A"B', "A\\B", "中文"})
    monkeypatch.setattr(excluded_skus, "EXCLUDED_SKUS", values)
    condition = excluded_skus.not_excluded_sku_condition(PRODUCT_TABLES["cbanner_womens"].c.sku)
    compiled = select(PRODUCT_TABLES["cbanner_womens"].c.id).where(condition).compile(dialect=postgresql.dialect())
    assert "NOT IN (SELECT unnest(CAST(" in str(compiled)
    assert isinstance(compiled.params["excluded_skus"], str)
    assert compiled.params["excluded_skus"] == '{"A\\"B","A,B","A\\\\B","中文"}'
    assert 'sku IS NULL' in str(compiled)
    assert excluded_skus.is_excluded_sku("A,B", "OTHER")
    assert not excluded_skus.is_excluded_sku("OTHER", "A,B")


def test_partition_index_plan_builds_leaf_indexes_concurrently_before_parent_attachment():
    plan = build_index_plan(["jst_aftersale_returns_2026", "jst_aftersale_returns_default"], partitioned=True)
    assert len(plan) == 5
    assert all(action["statement"].startswith("CREATE INDEX CONCURRENTLY") for action in plan[:-1])
    assert plan[-1]["name"] == PARENT_INDEX
    assert "ON ONLY public.jst_aftersale_returns" in plan[-1]["statement"]
    assert len(plan[-1]["attachments"]) == 2
    assert normalize_index_definition(plan[0]["statement"]) == normalize_index_definition(plan[0]["definition"])
    with pytest.raises(ValueError):
        build_index_plan(["unsafe;DROP TABLE products"], partitioned=True)


def test_nonpartitioned_index_plan_does_not_attach_leaf_indexes():
    plan = build_index_plan([], partitioned=False)
    assert len(plan) == 3
    assert plan[-1]["name"] == PARENT_INDEX
    assert all("CONCURRENTLY" in action["statement"] for action in plan)
    assert all("attachments" not in action for action in plan)
