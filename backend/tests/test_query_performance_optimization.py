from datetime import date
import json
from types import SimpleNamespace
from unittest.mock import MagicMock, Mock

import pytest
from sqlalchemy import Column, Date, Integer, MetaData, Table, UniqueConstraint, create_engine, insert, select
from sqlalchemy.dialects import postgresql
from sqlalchemy.schema import CreateIndex

from api.routes import fine_table, product_goods
from domain.daily_sales_schema import jst_daily_sales_table_for_year, vip_daily_sales_table_for_year
from domain.fine_table_snapshot_schema import fine_table_snapshot_ref_table_for_date
from domain.inventory_schema import INVENTORY_ACCOUNT_SUBJECT_TABLE, PURCHASE_ORDER_REQUIREMENT_TABLE
from domain.jst_stock_snapshot_schema import JST_STOCK_SUMMARY_SNAPSHOT_TABLE
from domain.product_goods_detail_snapshot_schema import PRODUCT_GOODS_DETAIL_SNAPSHOT_BATCHES_TABLE
from domain.vip_schema import JST_PRICE_TABLE
from scripts.optimize_query_performance import (
    OptimizationAction,
    REDUNDANT_INDEX_PATTERN,
    _index_action,
    _quote,
    execute_plan,
)
from storage import stock_snapshot_queries
from storage.fine_table_snapshot_dedup import load_optimized_snapshot_rows


def test_schema_does_not_recreate_verified_duplicate_indexes():
    tables = [
        fine_table_snapshot_ref_table_for_date(date(2026, 10, 13)),
        fine_table_snapshot_ref_table_for_date(date(2027, 1, 1)),
        JST_STOCK_SUMMARY_SNAPSHOT_TABLE,
        PRODUCT_GOODS_DETAIL_SNAPSHOT_BATCHES_TABLE,
        INVENTORY_ACCOUNT_SUBJECT_TABLE,
        PURCHASE_ORDER_REQUIREMENT_TABLE,
    ]
    for table in tables:
        assert not any(REDUNDANT_INDEX_PATTERN.fullmatch(index.name) for index in table.indexes)
        assert any(isinstance(constraint, UniqueConstraint) for constraint in table.constraints)


def test_price_index_preserves_nulls_last_query_order():
    index = next(index for index in JST_PRICE_TABLE.indexes if index.name == "idx_jst_price_code_date_nulls_last_updated")
    sql = str(CreateIndex(index).compile(dialect=postgresql.dialect()))
    assert "goods_code, source_date_value DESC NULLS LAST, updated_at DESC, id DESC" in sql


@pytest.mark.parametrize("table_factory", [jst_daily_sales_table_for_year, vip_daily_sales_table_for_year])
def test_daily_sales_index_matches_style_and_date_range(table_factory):
    table = table_factory(2026)
    index = next(index for index in table.indexes if index.name == f"idx_{table.name}_style_date")
    assert [column.name for column in index.columns] == ["style_code", "sales_date"]


def test_snapshot_dates_use_one_index_seek_per_distinct_date():
    connection = Mock()
    connection.dialect.name = "postgresql"
    connection.execute.return_value.scalars.return_value = [date(2026, 10, 12), date(2026, 10, 11)]
    assert stock_snapshot_queries.load_stock_snapshot_dates(connection) == [date(2026, 10, 12), date(2026, 10, 11)]
    statement = str(connection.execute.call_args.args[0])
    assert "WITH RECURSIVE" in statement
    assert "snapshot_date < previous.snapshot_date" in statement
    assert "DISTINCT" not in statement


def test_snapshot_dates_sqlite_fallback_preserves_unique_descending_dates(monkeypatch):
    engine = create_engine("sqlite://")
    table = Table("stock_snapshots", MetaData(), Column("id", Integer, primary_key=True), Column("snapshot_date", Date))
    table.create(engine)
    monkeypatch.setattr(stock_snapshot_queries, "JST_SIZE_STOCK_SNAPSHOT_TABLE", table)
    try:
        with engine.begin() as connection:
            assert stock_snapshot_queries.load_stock_snapshot_dates(connection) == []
            connection.execute(insert(table), [
                {"snapshot_date": date(2026, 10, 11)}, {"snapshot_date": date(2026, 10, 12)},
                {"snapshot_date": date(2026, 10, 11)},
            ])
            assert stock_snapshot_queries.load_stock_snapshot_dates(connection) == [date(2026, 10, 12), date(2026, 10, 11)]
    finally:
        engine.dispose()


def test_product_goods_dates_merge_stock_and_successful_detail_batches(monkeypatch):
    monkeypatch.setattr(product_goods, "get_product_goods_snapshot_dates_cache", lambda brand: None)
    monkeypatch.setattr(product_goods, "load_stock_snapshot_dates", lambda connection: [date(2026, 10, 11)])
    monkeypatch.setattr(product_goods, "_detail_snapshot_dates", lambda connection, *, brand: [date(2026, 10, 12), date(2026, 10, 11)])
    saved = Mock()
    monkeypatch.setattr(product_goods, "set_product_goods_snapshot_dates_cache", saved)
    assert product_goods._product_goods_snapshot_dates(Mock(), brand="cbanner_mens") == [date(2026, 10, 12), date(2026, 10, 11)]
    saved.assert_called_once_with("cbanner_mens", ["2026-10-12", "2026-10-11"])


@pytest.mark.parametrize("field,values", [
    ("cost", ["100"]), ("platform", ["唯品"]), ("risk", ["正常"]),
    ("year", ["2026"]), ("factory_sku", ["00123"]), ("style_code", ["10%"]),
])
def test_snapshot_numeric_and_derived_filters_keep_original_semantics(field, values):
    filters = (fine_table.FineTableFilter(field=field, operator="in", values=values),)
    assert fine_table._snapshot_payload_filter_conditions(filters) is None


def test_snapshot_text_filters_use_correct_payload_and_null_safe_exclusion():
    filters = (
        fine_table.FineTableFilter(field="factory_name", operator="not_in", values=[""]),
        fine_table.FineTableFilter(field="sales_tag", operator="in", values=["畅销"]),
    )
    conditions = fine_table._snapshot_payload_filter_conditions(filters)
    sql = str(select(1).where(*conditions).compile(dialect=postgresql.dialect()))
    assert "fine_table_snapshot_payloads.payload" in sql
    assert "fine_table_snapshot_metrics.payload" in sql
    assert "coalesce" in sql and "NOT IN" in sql


def test_snapshot_text_filters_paginate_in_database(monkeypatch):
    batch = {"id": 42, "brand": "cbanner_mens", "snapshot_date": date(2026, 10, 12), "total_rows": 20000}
    connection = Mock()
    connection.execute.return_value.mappings.return_value.first.return_value = batch
    engine = MagicMock()
    engine.dialect.name = "postgresql"
    engine.connect.return_value.__enter__.return_value = connection
    request = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(
        repository=SimpleNamespace(engine=engine), settings=SimpleNamespace(),
    )))
    monkeypatch.setattr(fine_table, "_ensure_snapshot_tables", lambda engine: None)
    monkeypatch.setattr(fine_table, "fine_table_snapshot_year_table_exists", lambda *args: False)
    monkeypatch.setattr(fine_table, "fine_table_snapshot_ref_table_exists", lambda *args: True)
    monkeypatch.setattr(fine_table, "optimized_snapshot_available", lambda *args: True)
    loader = Mock(return_value=([{"sku": "A_1"}], 7))
    monkeypatch.setattr(fine_table, "load_optimized_snapshot_rows", loader)
    for helper in ("_hydrate_snapshot_archive_costs", "_hydrate_snapshot_image_urls", "_hydrate_fine_table_platforms"):
        monkeypatch.setattr(fine_table, helper, lambda **kwargs: None)
    response = fine_table.get_fine_table_snapshot(
        request, batch_id=42, query="A_1", sku_prefix="A_",
        filters='[{"field":"factory_name","operator":"in","values":["工厂A"]}]', page=2, page_size=80,
    )
    assert response["total"] == 7
    arguments = loader.call_args.kwargs
    assert arguments["page"] == 2 and arguments["page_size"] == 80
    assert len(arguments["payload_conditions"]) == 1
    assert any("%A!_1%" in condition.compile(dialect=postgresql.dialect()).params.values() for condition in arguments["conditions"])
    assert any("A!_%" in condition.compile(dialect=postgresql.dialect()).params.values() for condition in arguments["conditions"])


def test_snapshot_count_applies_the_same_payload_filters_as_page():
    connection = Mock()
    connection.execute.side_effect = [SimpleNamespace(mappings=lambda: []), SimpleNamespace(scalar_one=lambda: 3)]
    engine = MagicMock()
    engine.connect.return_value.__enter__.return_value = connection
    conditions = fine_table._snapshot_payload_filter_conditions((
        fine_table.FineTableFilter(field="factory_name", operator="in", values=["工厂A"]),
    ))
    rows, total = load_optimized_snapshot_rows(
        engine, date(2026, 10, 12), 42, conditions=[], payload_conditions=conditions, page=2, page_size=80,
    )
    assert rows == [] and total == 3
    statements = [str(call.args[0].compile(dialect=postgresql.dialect())) for call in connection.execute.call_args_list]
    assert all("JOIN fine_table_snapshot_payloads" in statement and "lower(coalesce" in statement for statement in statements)
    assert "LIMIT" in statements[0] and "OFFSET" in statements[0]
    assert "LIMIT" not in statements[1] and "OFFSET" not in statements[1]


def test_snapshot_unfiltered_count_does_not_join_large_payload_tables():
    connection = Mock()
    connection.execute.side_effect = [SimpleNamespace(mappings=lambda: []), SimpleNamespace(scalar_one=lambda: 0)]
    engine = MagicMock()
    engine.connect.return_value.__enter__.return_value = connection
    load_optimized_snapshot_rows(engine, date(2026, 10, 12), 42, conditions=[], page=1, page_size=80)
    assert "JOIN" not in str(connection.execute.call_args_list[1].args[0])


def test_optimization_refuses_unsafe_identifiers():
    with pytest.raises(ValueError):
        _quote("table; DROP TABLE business_data")


@pytest.mark.parametrize("valid,definition", [(False, "CREATE INDEX x"), (True, "unexpected definition")])
def test_optimization_refuses_invalid_or_mismatched_existing_indexes(valid, definition):
    connection = Mock()
    connection.execute.return_value.mappings.return_value.first.return_value = {"indisvalid": valid, "definition": definition}
    with pytest.raises(ValueError):
        _index_action(connection, "jst_product_price", "idx_test", "goods_code")


def test_optimization_persists_progress_and_stops_before_dropping_when_build_fails(tmp_path):
    connection = Mock()
    connection.execute.side_effect = [None, None, None, RuntimeError("build failed")]
    actions = [
        OptimizationAction("create_index", "prices", "CREATE INDEX CONCURRENTLY new_price_index ON prices (code)"),
        OptimizationAction("drop_replaced_index", "prices", "DROP INDEX CONCURRENTLY old_price_index"),
    ]
    report = {"completed": []}
    with pytest.raises(RuntimeError):
        execute_plan(connection, actions, report, tmp_path / "report.json")
    assert not any("DROP INDEX" in str(call.args[0]) for call in connection.execute.call_args_list)
    assert report["completed"] == []


def test_optimization_saves_rollback_after_each_successful_operation(tmp_path):
    connection = Mock()
    action = OptimizationAction("create_index", "prices", "CREATE INDEX CONCURRENTLY new_price_index ON prices (code)", "DROP INDEX CONCURRENTLY new_price_index")
    report = {"completed": []}
    output = tmp_path / "report.json"
    execute_plan(connection, [action], report, output)
    assert json.loads(output.read_text(encoding="utf-8"))["completed"][0]["rollback"] == action.rollback
