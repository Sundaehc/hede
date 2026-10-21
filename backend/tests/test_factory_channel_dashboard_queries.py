from datetime import date
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine, event
from sqlalchemy.exc import OperationalError

from api import product_goods_cache
from api.product_goods_cache import clear_product_goods_cache
from api.routes import product_goods as goods_routes
from domain.daily_sales_schema import jst_daily_sales_table_for_year, vip_daily_sales_table_for_year
from domain.factory_channel_sales_summary_schema import FACTORY_CHANNEL_SALES_DAILY_SUMMARY_TABLE
from domain.inventory_schema import SUPPLIER_TABLE
from domain.product_goods_detail_snapshot_schema import product_goods_detail_snapshots_table_for_year
from domain.product_goods_historical_sales_schema import product_goods_historical_sales_table_for_year
from domain.schema import PRODUCT_TABLES


@pytest.fixture
def dashboard_request(monkeypatch):
    engine = create_engine("sqlite://")
    event.listen(engine, "connect", lambda connection, record: connection.create_function(
        "date_trunc", 2, lambda unit, value: value,
    ))
    historical = product_goods_historical_sales_table_for_year(2025)
    snapshots = product_goods_detail_snapshots_table_for_year(2025)
    for table in (PRODUCT_TABLES["cbanner_mens"], PRODUCT_TABLES["cbanner_womens"],
                  SUPPLIER_TABLE, historical, snapshots):
        table.create(engine)
    with engine.begin() as connection:
        for brand in ("cbanner_mens", "cbanner_womens"):
            connection.execute(PRODUCT_TABLES[brand].insert(), {
                "id": 1, "sku": "MEN001", "original_sku": "STYLE-M", "year": "2025",
                "season_category": "春夏", "supplier_name": "测试工厂",
                "source_workbook": "test", "source_sheet": "test", "source_row_number": "1",
                "raw_payload": {},
            })
        connection.execute(historical.insert(), [
            {"id": record_id, "brand": "cbanner_mens", "sales_year": 2025,
             "sales_date": sales_date, "product_code": "MEN001", "original_sku": "STYLE-M",
             "channel": "天猫", "sales_quantity": quantity, "source_workbook": "test",
             "source_sheet": "test", "source_row_number": record_id}
            for record_id, sales_date, quantity in (
                (1, date(2025, 1, 1), 8), (2, date(2025, 1, 2), 2),
            )
        ])
        connection.execute(snapshots.insert(), [
            {"id": record_id, "brand": "cbanner_mens", "snapshot_date": snapshot_date,
             "goods_code": "MEN001", "style_code": "STYLE-M", "source_workbook": "test",
             "source_sheet": "test", "source_row_number": record_id,
             "data": {"metrics": {"return_qty": quantity}, "unused": "x" * 20000}}
            for record_id, snapshot_date, quantity in (
                (1, date(2025, 1, 1), 2), (2, date(2025, 1, 2), 3),
            )
        ])
    monkeypatch.setattr(goods_routes, "_factory_dashboard_sales_date_coverage", lambda *args, **kwargs: {})
    clear_product_goods_cache()
    request = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(
        repository=SimpleNamespace(engine=engine),
    )))
    try:
        yield request
    finally:
        clear_product_goods_cache()
        engine.dispose()


def dashboard(request, **parameters):
    return goods_routes.get_factory_channel_dashboard(request, **{
        "brand": "cbanner_mens", "sales_year": 2025, **parameters,
    })


def test_cache_hit_skips_all_database_queries_including_year_discovery(dashboard_request):
    statements = []
    engine = dashboard_request.app.state.repository.engine
    event.listen(engine, "before_cursor_execute", lambda *args: statements.append(args[2]))
    first = dashboard(dashboard_request)
    assert first["summary"]["total_sales"] == 10
    assert first["summary"]["total_returns"] == 3
    assert first["summary"]["traditional_returns"] == 0
    assert statements
    statements.clear()
    assert dashboard(dashboard_request) == first
    assert statements == []


def test_filters_brands_and_automatic_year_use_separate_cache_entries(dashboard_request):
    assert dashboard(dashboard_request)["summary"]["total_sales"] == 10
    filtered = dashboard(dashboard_request, date_end=date(2025, 1, 1))
    assert filtered["summary"]["total_sales"] == 8
    assert filtered["summary"]["total_returns"] == 2
    assert dashboard(dashboard_request, brand="cbanner_womens")["summary"]["total_sales"] == 0
    assert dashboard(dashboard_request, product_year="2024")["summary"]["style_count"] == 0
    automatic = dashboard(dashboard_request, sales_year=None)
    assert automatic["sales_year"] == 2025
    assert automatic["available_sales_years"] == [2025]
    assert dashboard(dashboard_request, sales_year=None) == automatic


def test_automatic_and_latest_year_share_cache_and_refresh(dashboard_request):
    engine = dashboard_request.app.state.repository.engine
    statements = []
    event.listen(engine, "before_cursor_execute", lambda *args: statements.append(args[2]))
    dashboard(dashboard_request, sales_year=None)
    statements.clear()
    assert dashboard(dashboard_request)["summary"]["total_sales"] == 10
    assert statements == []
    historical = product_goods_historical_sales_table_for_year(2025)
    with engine.begin() as connection:
        connection.execute(historical.update().where(historical.c.id == 1).values(sales_quantity=18))
    dashboard(dashboard_request, cache_bust="refresh")
    statements.clear()
    assert dashboard(dashboard_request, sales_year=None)["summary"]["total_sales"] == 20
    assert statements == []


def test_cross_day_requests_and_new_year_tables_are_not_hidden_by_cache(dashboard_request, monkeypatch):
    engine = dashboard_request.app.state.repository.engine

    class QueryDate(date):
        current = date(2026, 1, 1)

        @classmethod
        def today(cls):
            return cls.current

    monkeypatch.setattr(goods_routes, "date", QueryDate)
    monkeypatch.setattr(goods_routes, "_factory_dashboard_sales_rows", lambda *args, **kwargs: ([], None))
    assert dashboard(dashboard_request, sales_year=None)["sales_year"] == 2025
    jst_daily_sales_table_for_year(2026).create(engine)
    assert dashboard(dashboard_request, sales_year=None)["sales_year"] == 2025
    QueryDate.current = date(2026, 1, 2)
    assert dashboard(dashboard_request, sales_year=None)["sales_year"] == 2026


def test_refresh_clear_and_expiry_reload_changed_sales(dashboard_request, monkeypatch):
    assert dashboard(dashboard_request)["summary"]["total_sales"] == 10
    engine = dashboard_request.app.state.repository.engine
    historical = product_goods_historical_sales_table_for_year(2025)
    with engine.begin() as connection:
        connection.execute(historical.update().where(historical.c.id == 1).values(sales_quantity=18))
    assert dashboard(dashboard_request)["summary"]["total_sales"] == 10
    assert dashboard(dashboard_request, cache_bust="refresh")["summary"]["total_sales"] == 20
    assert dashboard(dashboard_request)["summary"]["total_sales"] == 20
    with engine.begin() as connection:
        connection.execute(historical.update().where(historical.c.id == 1).values(sales_quantity=28))
    clock = product_goods_cache.monotonic()
    monkeypatch.setattr(product_goods_cache, "monotonic", lambda: clock + 301)
    assert dashboard(dashboard_request)["summary"]["total_sales"] == 30
    clear_product_goods_cache()
    assert dashboard(dashboard_request)["summary"]["total_sales"] == 30


def test_cached_results_do_not_cross_database_engines(dashboard_request):
    dashboard(dashboard_request)
    other_engine = create_engine("sqlite://")
    other_request = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(
        repository=SimpleNamespace(engine=other_engine),
    )))
    try:
        with pytest.raises(OperationalError, match="no such table"):
            dashboard(other_request)
    finally:
        other_engine.dispose()


@pytest.mark.parametrize("parameters", [
    {"sales_year": 2023}, {"sales_year": 0}, {"sales_year": date.today().year + 1},
    {"date_start": date(2025, 1, 2), "date_end": date(2025, 1, 1)},
])
def test_invalid_filters_are_rejected_before_querying(dashboard_request, parameters):
    with pytest.raises(HTTPException) as error:
        dashboard(dashboard_request, **parameters)
    assert error.value.status_code == 400


@pytest.mark.parametrize("data, expected", [
    ({"metrics": {"return_qty": "7"}}, 7),
    ({"metrics": {"return_qty": 3.5}}, 3),
    ({"metrics": {"return_qty": -1}}, 0),
    ({"metrics": {"return_qty": "invalid"}}, 0),
    ({"metrics": {"return_qty": {"invalid": 3}}}, 0),
    ({"metrics": {"return_qty": None}}, 0),
    ({"metrics": []}, 0), ({"metrics": None}, 0), ({}, 0), ([], 0), (None, 0),
])
def test_historical_returns_project_only_required_json_metric(dashboard_request, data, expected):
    engine = dashboard_request.app.state.repository.engine
    snapshots = product_goods_detail_snapshots_table_for_year(2025)
    with engine.begin() as connection:
        connection.execute(snapshots.update().where(snapshots.c.id == 2).values(data=data))
    statements = []
    event.listen(engine, "before_cursor_execute", lambda *args: statements.append(args[2]))
    with engine.connect() as connection:
        rows = goods_routes._factory_dashboard_historical_detail_returns(
            connection, engine, brand="cbanner_mens", sales_year=2025, date_start=None, date_end=None,
        )
    assert sum(row["return_quantity"] for row in rows) == expected
    projection = next(statement for statement in statements if "AS return_quantity" in statement)
    assert "JSON_EXTRACT" in projection
    assert f"{snapshots.name}.data \nFROM" not in projection
    assert all(row["return_total_only"] and row["quantity"] == 0 for row in rows)


def test_daily_summary_and_raw_fallback_keep_the_same_sales_totals(dashboard_request):
    engine = dashboard_request.app.state.repository.engine
    jst = jst_daily_sales_table_for_year(2026)
    vip = vip_daily_sales_table_for_year(2026)
    summary = FACTORY_CHANNEL_SALES_DAILY_SUMMARY_TABLE
    for table in (jst, vip, summary):
        table.create(engine)
    sales_date = date(2026, 1, 1)
    source = {"id": 1, "sales_date": sales_date, "source_workbook": "test",
              "source_sheet": "test", "source_row_number": 1, "raw_payload": {}}
    with engine.begin() as connection:
        connection.execute(jst.insert(), {**source, "channel": "天猫", "product_code": "MEN00134",
                           "sales_quantity": 8, "net_sales_quantity": 5, "return_quantity": 3})
        connection.execute(vip.insert(), {**source, "goods_code": "MEN001", "goods_id": "1",
                           "sales_quantity": 2})
        connection.execute(summary.insert(), [
            {"id": 1, "brand": "cbanner_mens", "sales_date": sales_date, "product_code": "",
             "channel_group": "", "match_status": "date_marker", "quantity": 0,
             "gross_quantity": 0, "return_quantity": 0},
            {"id": 2, "brand": "cbanner_mens", "sales_date": sales_date, "product_code": "MEN001",
             "channel_group": "traditional", "match_status": "matched", "quantity": 7,
             "gross_quantity": 10, "return_quantity": 3},
        ])
    summarized = dashboard(dashboard_request, sales_year=2026)
    assert summarized["summary"]["total_sales"] == 10
    assert summarized["summary"]["total_net_sales"] == 7
    assert summarized["summary"]["total_returns"] == 3
    summary.drop(engine)
    fallback = dashboard(dashboard_request, sales_year=2026, cache_bust="fallback")
    assert fallback == summarized


def test_matching_is_reused_across_channels_dates_and_snapshot_returns(dashboard_request, monkeypatch):
    engine = dashboard_request.app.state.repository.engine
    historical = product_goods_historical_sales_table_for_year(2025)
    with engine.begin() as connection:
        connection.execute(historical.insert(), [
            {"id": record_id, "brand": "cbanner_mens", "sales_year": 2025,
             "sales_date": date(2025, 1, 2), "product_code": code, "original_sku": style,
             "channel": channel, "sales_quantity": 1, "source_workbook": "test",
             "source_sheet": "test", "source_row_number": record_id}
            for record_id, code, style, channel in (
                (3, "MEN001", "STYLE-M", "直播"), (4, "UNKNOWN", "", "天猫"),
                (5, "UNKNOWN", "", "直播"), (6, "UNKNOWN", "STYLE-M", "清仓"),
            )
        ])
    original_resolver = goods_routes._factory_dashboard_product_for_sale
    resolved_keys = []

    def resolve(*args, **kwargs):
        resolved_keys.append(args)
        return original_resolver(*args, **kwargs)

    monkeypatch.setattr(goods_routes, "_factory_dashboard_product_for_sale", resolve)
    payload = dashboard(dashboard_request)
    assert payload["summary"]["total_sales"] == 12
    assert payload["summary"]["total_returns"] == 3
    assert payload["summary"]["unmatched_sales"] == 2
    assert payload["summary"]["live_sales"] == 1
    assert payload["summary"]["clearance_sales"] == 1
    assert sorted(resolved_keys) == [("MEN001", "STYLE-M"), ("UNKNOWN", ""), ("UNKNOWN", "STYLE-M")]
