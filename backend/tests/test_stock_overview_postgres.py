"""Run only against an isolated test database with TEST_STOCK_OVERVIEW_DATABASE_URL."""
from datetime import date, timedelta
import os
from uuid import uuid4

import pytest
from sqlalchemy import Column, Integer, MetaData, Table, Text, create_engine, event, text

from domain.size_group_schema import SIZE_GROUPS_TABLE, SIZE_GROUP_ITEMS_TABLE
from domain.stock_overview import build_overview
from storage.stock_alert_facts import load_stock_alert_facts
from storage.stock_alert_tasks import TASK_KIND_CHECK, StockAlertTaskRepository
from storage.stock_overview import load_stock_overview, weekly_observations
from storage.stock_replenishment_facts import load_replenishment_facts


def test_overview_postgres_sources_and_old_task_constraint():
    url = os.getenv("TEST_STOCK_OVERVIEW_DATABASE_URL")
    if not url:
        pytest.skip("requires an isolated PostgreSQL integration database")
    schema = f"stock_overview_test_{uuid4().hex}"
    admin = create_engine(url)
    with admin.begin() as conn:
        conn.exec_driver_sql(f'CREATE SCHEMA "{schema}"')
    engine = create_engine(url, connect_args={"options": f"-c search_path={schema}"})
    brand, today = "cbanner_womens", date(2026, 11, 20)
    archive = Table("test_archive", MetaData(), Column("id", Integer, primary_key=True), *[
        Column(name, Text) for name in ("sku", "original_sku", "product_name", "color", "color_code", "barcode_build_rule",
            "size_range", "supplier_name", "launch_date", "year", "season_category", "upper_material", "deleted_at")])

    class Repository:
        def __init__(self):
            self.engine = engine

        def product_archive_brands(self):
            return [brand]

        def _table_for_brand(self, _):
            return archive

    try:
        archive.create(engine)
        SIZE_GROUPS_TABLE.create(engine)
        SIZE_GROUP_ITEMS_TABLE.create(engine)
        repo = StockAlertTaskRepository(engine)
        repo.create_tables()
        with engine.begin() as conn:
            conn.exec_driver_sql(f"ALTER TABLE stock_alert_tasks DROP CONSTRAINT {TASK_KIND_CHECK}")
            conn.exec_driver_sql("ALTER TABLE stock_alert_tasks ADD CHECK (kind IN ('zero', 'slow'))")
        actor = {"id": 1, "username": "operator"}
        snapshot = {"id": 1, "brand": brand, "sku": "TEST01"}
        args = dict(snapshot=snapshot, assignee=actor, due_date=today, measures="check", actor=actor)
        original = repo.create(kind="slow", **args)
        repo.create_tables()
        assert repo.get(original["id"])["kind"] == "slow"
        assert repo.create(kind="clearance", **args)["kind"] == "clearance"

        end, launch = today - timedelta(days=1), today - timedelta(days=29)
        first = today - timedelta(days=today.weekday() + 7)
        last = first + timedelta(days=6)
        with engine.begin() as conn:
            conn.execute(archive.insert(), [dict(id=1, sku="TEST01", launch_date=launch.isoformat(), year="2024", season_category="WINTER"),
                dict(id=2, sku="TEST02", launch_date=launch.isoformat(), year="2024", season_category="WINTER"),
                dict(id=3, sku="TEST03", launch_date=launch.isoformat(), year="2024", season_category="WINTER")])
            for sql in (
                "CREATE TABLE jst_full_stock (sync_date date, product_code text, style_code text, size text, available_qty int, purchase_in_transit_qty int)",
                "CREATE TABLE jst_daily_sales (sales_date date, product_code text, style_code text, channel text, sales_quantity int)",
                "CREATE TABLE vip_daily_sales (sales_date date, goods_code text, style_code text, sales_quantity int)",
                "CREATE TABLE factory_channel_sales_daily_summaries (sales_date date, brand text, product_code text, channel_group text, match_status text, quantity int, gross_quantity int, return_quantity int)",
                "CREATE TABLE jst_size_stock_snapshots (snapshot_date date, product_code text, size text, stock_qty int)",
            ):
                conn.exec_driver_sql(sql)
            conn.execute(text("INSERT INTO jst_full_stock VALUES (:day,'TEST01','TEST01','37',100,0),(:day,'TEST02','TEST02','37',10,0),(:day,'TEST03','TEST03','37',21,0)"), {"day": today})
            for source in ("jst_daily_sales", "vip_daily_sales"):
                conn.execute(text(f"INSERT INTO {source} (sales_date) SELECT CAST(d AS date) FROM generate_series(CAST(:first AS date), CAST(:last AS date), interval '1 day') d"), {"first": today - timedelta(days=31), "last": end})
            # A raw sale identified only by its style still disproves zero sales.
            # A purchase-channel row and a pre-launch VIP sale do not.
            conn.execute(text("""INSERT INTO jst_daily_sales VALUES
                (:day,'unmapped','TEST02','shop',1),(:day,'TEST03','TEST03','采购',1)"""), {"day": first})
            conn.execute(text("INSERT INTO vip_daily_sales VALUES (:day,'TEST03','TEST03',1)"),
                         {"day": launch - timedelta(days=1)})
            conn.execute(text("INSERT INTO factory_channel_sales_daily_summaries (sales_date,brand,match_status) SELECT CAST(d as date), :brand, 'date_marker' FROM generate_series(CAST(:first AS date), CAST(:last AS date), interval '1 day') d"), {"first": today-timedelta(days=30), "last": end, "brand": brand})
            conn.execute(text("INSERT INTO factory_channel_sales_daily_summaries VALUES (:day,:brand,'TEST01','clearance','matched',3,3,0),(:day,:brand,'TEST01','traditional','matched',10,10,0)"), {"day": first, "brand": brand})
            conn.execute(text("INSERT INTO jst_size_stock_snapshots VALUES (:before,'TEST01','37',110),(:after,'TEST01','37',101)"), {"before": first-timedelta(days=1), "after": last})

        adapter = Repository()
        recent = load_replenishment_facts(adapter, brand, today=today, overview=True)
        historic = load_stock_alert_facts(adapter, brand, today=today, verify_zero=True)
        assert len(recent["items"]) == 3
        assert load_replenishment_facts(adapter, brand, today=today, overview=True) == recent
        assert historic["items"] and all(item.get("zero_confirmed") == (item["id"] == 3) for item in historic["items"] if item["id"] != 1)
        result = build_overview(recent, historic, {}, {}, {}, today)
        assert result["inventory"]["available"] == 131
        assert result["inventory"]["total_30"] == 13
        assert result["inventory"]["clearance_30"] == 3
        assert [(row["id"], row["kind"]) for row in result["recommendations"] if row["kind"] == "zero"] == [(3, "zero")]
        statements = []

        @event.listens_for(engine, "before_cursor_execute")
        def record_statement(conn, cursor, statement, params, context, executemany):
            statements.append(" ".join(statement.lower().split()))

        def read_rules():
            return {}, {}, {}

        actual, _ = load_stock_overview(adapter, brand, today, refresh=False, read_rules=read_rules)
        assert actual == result
        cold_queries = len(statements)
        assert sum("from test_archive" in query for query in statements) == 1
        assert sum("from jst_full_stock where sync_date" in query for query in statements) == 1
        assert sum("group by product_code" in query and "as net30" in query for query in statements) == 1
        statements.clear()
        again, _ = load_stock_overview(adapter, brand, today, refresh=False, read_rules=read_rules)
        assert again == actual
        assert not statements
        _, _ = load_stock_overview(adapter, brand, today, refresh=True, read_rules=read_rules)
        assert len(statements) == cold_queries

        # A late inventory snapshot preserves the historical sales cutoff instead
        # of falsely aligning it to the per-stock forecast cutoff.
        with engine.begin() as conn:
            conn.execute(text("UPDATE jst_full_stock SET sync_date = :day"), {"day": today - timedelta(days=1)})
        stale_recent = load_replenishment_facts(adapter, brand, today=today, overview=True, refresh=True)
        stale_history = load_stock_alert_facts(adapter, brand, today=today, verify_zero=True, refresh=True)
        stale, _ = load_stock_overview(adapter, brand, today, refresh=True, read_rules=read_rules)
        assert stale == build_overview(stale_recent, stale_history, {}, {}, {}, today)
        assert not stale["sources"]["history_aligned"]
        assert weekly_observations(adapter, brand, first, last, {1}, {1}) == {
            "net_sales": 13, "clearance_net_sales": 3, "stock_change": -9}
    finally:
        engine.dispose()
        with admin.begin() as conn:
            conn.exec_driver_sql(f'DROP SCHEMA "{schema}" CASCADE')
        admin.dispose()
