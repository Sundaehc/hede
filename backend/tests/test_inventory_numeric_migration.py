import os
from decimal import Decimal
from pathlib import Path

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url

from scripts.expand_inventory_numeric import MIGRATION_PATH, expand, snapshot


@pytest.fixture
def migration_engine():
    value = os.getenv("INVENTORY_NUMERIC_TEST_DATABASE_URL")
    if not value:
        pytest.skip("Requires a dedicated local PostgreSQL test cluster")
    url = make_url(value)
    if url.host != "127.0.0.1" or url.port != 55441 or url.database != "postgres":
        raise RuntimeError("Refusing numeric migration tests outside isolated loopback cluster")
    engine = create_engine(value)
    with engine.begin() as connection:
        directory = Path(connection.scalar(text("SHOW data_directory"))).resolve()
        test_root = (Path(__file__).resolve().parents[1] / "tmp").resolve()
        if not directory.is_relative_to(test_root) or not directory.name.startswith("pg-inventory-numeric-"):
            raise RuntimeError("Refusing numeric migration tests outside isolated test directory")
        connection.exec_driver_sql("DROP SCHEMA IF EXISTS mcp_readonly CASCADE")
        connection.exec_driver_sql("DROP SCHEMA public CASCADE")
        connection.exec_driver_sql("CREATE SCHEMA public")
        connection.exec_driver_sql("CREATE SCHEMA mcp_readonly")
        connection.exec_driver_sql("""DO $$ BEGIN
            IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'numeric_test_reader') THEN
                CREATE ROLE numeric_test_reader;
            END IF;
        END $$""")
        connection.exec_driver_sql("CREATE TABLE public.inventory_records(id bigint PRIMARY KEY, total_count numeric(10,2), amount numeric(10,2))")
        connection.exec_driver_sql("CREATE TABLE public.inventory_details(id bigint PRIMARY KEY, quantity numeric(10,2), unit_price numeric(10,2), amount numeric(10,2))")
        connection.exec_driver_sql("CREATE TABLE public.inventory_import_tasks(id text PRIMARY KEY, status text)")
        connection.exec_driver_sql("CREATE INDEX detail_page ON public.inventory_details(id) INCLUDE(quantity, amount)")
        connection.exec_driver_sql("CREATE INDEX missing_amount ON public.inventory_details(id) WHERE amount IS NULL OR amount=0")
        connection.exec_driver_sql("INSERT INTO public.inventory_records VALUES (1, 2.25, 99.99)")
        connection.exec_driver_sql("INSERT INTO public.inventory_details VALUES (1, 2.25, 44.44, 99.99)")
        connection.exec_driver_sql("CREATE VIEW public.v_inventory_records_normalized AS SELECT * FROM public.inventory_records")
        connection.exec_driver_sql("CREATE VIEW mcp_readonly.inventory_records WITH (security_barrier=true) AS SELECT * FROM public.inventory_records")
        connection.exec_driver_sql("CREATE VIEW mcp_readonly.inventory_details WITH (security_barrier=true) AS SELECT * FROM public.inventory_details")
        connection.exec_driver_sql("CREATE VIEW mcp_readonly.purchase_orders WITH (security_barrier=true) AS SELECT * FROM public.inventory_records WHERE id > 0")
        connection.exec_driver_sql("GRANT SELECT ON mcp_readonly.inventory_records TO numeric_test_reader WITH GRANT OPTION")
        connection.exec_driver_sql("COMMENT ON VIEW mcp_readonly.inventory_records IS '测试视图'")
        connection.exec_driver_sql("COMMENT ON COLUMN mcp_readonly.inventory_records.amount IS '金额'")
    try:
        yield engine
    finally:
        engine.dispose()


def test_numeric_migration_preserves_data_views_permissions_and_avoids_rewrite(migration_engine):
    with migration_engine.begin() as connection:
        index_query = text("SELECT relation.relname, pg_get_indexdef(indexrelid) AS definition, relation.relfilenode, indisvalid FROM pg_index JOIN pg_class relation ON relation.oid=indexrelid WHERE indrelid='public.inventory_details'::regclass ORDER BY definition")
        indexes_before = connection.execute(index_query).all()
        before, after = expand(connection)
        assert all(row["numeric_precision"] == 10 for row in before["columns"])
        assert all(row["numeric_precision"] == 18 for row in after["columns"])
        assert before["tables"] == after["tables"]
        assert before["views"] == after["views"]
        indexes_after = connection.execute(index_query).all()
        assert [(row.relname, row.definition) for row in indexes_after] == [(row.relname, row.definition) for row in indexes_before]
        assert all(row.indisvalid for row in indexes_after)
        assert next(row.relfilenode for row in indexes_after if row.relname == "detail_page") == next(row.relfilenode for row in indexes_before if row.relname == "detail_page")
        assert connection.scalar(text("SELECT amount FROM public.inventory_records WHERE id=1")) == Decimal("99.99")
        assert connection.scalar(text("SELECT obj_description('mcp_readonly.inventory_records'::regclass)")) == "测试视图"
        assert connection.scalar(text("SELECT col_description('mcp_readonly.inventory_records'::regclass, 3)")) == "金额"
        connection.exec_driver_sql("INSERT INTO public.inventory_records VALUES (2, 100000000, 9999999999999999.99)")
        connection.exec_driver_sql("INSERT INTO public.inventory_details VALUES (2, 100000000, 200, 20000000000)")
        assert connection.scalar(text("SELECT count(*) FROM mcp_readonly.inventory_records")) == 2
        second_before, second_after = expand(connection)
        assert second_before == second_after


@pytest.mark.parametrize("reason", ["active_batch", "downstream_view", "unknown_view", "column_permission"])
def test_numeric_migration_refuses_unsafe_dependencies_and_active_imports(migration_engine, reason):
    with migration_engine.begin() as connection:
        if reason == "active_batch":
            connection.exec_driver_sql("INSERT INTO public.inventory_import_tasks VALUES ('batch', 'running')")
        elif reason == "downstream_view":
            connection.exec_driver_sql("CREATE VIEW public.child_view AS SELECT * FROM mcp_readonly.inventory_records")
        elif reason == "unknown_view":
            connection.exec_driver_sql("CREATE VIEW public.extra_view AS SELECT amount FROM public.inventory_records")
        else:
            connection.exec_driver_sql("GRANT SELECT(amount) ON mcp_readonly.inventory_records TO numeric_test_reader")
    expected = "后台导入" if reason == "active_batch" else "下游依赖" if reason == "downstream_view" else "未支持的视图依赖或列级权限"
    with pytest.raises(Exception, match=expected):
        with migration_engine.begin() as connection:
            expand(connection)
    with migration_engine.connect() as connection:
        assert all(row["numeric_precision"] == 10 for row in snapshot(connection)["columns"])
        assert connection.scalar(text("SELECT count(*) FROM mcp_readonly.inventory_records")) == 1


def test_numeric_migration_does_not_wait_for_busy_table(migration_engine):
    with migration_engine.begin() as holder:
        holder.exec_driver_sql("LOCK TABLE public.inventory_details IN ROW EXCLUSIVE MODE")
        with pytest.raises(Exception, match="lock|锁"):
            with migration_engine.begin() as connection:
                expand(connection)


def test_numeric_migration_rolls_back_when_view_recreation_fails(migration_engine):
    statement = MIGRATION_PATH.read_text(encoding="utf-8").replace(
        "EXECUTE format('CREATE VIEW", "RAISE EXCEPTION 'test rollback';\n        EXECUTE format('CREATE VIEW", 1,
    )
    with pytest.raises(Exception, match="test rollback"):
        with migration_engine.begin() as connection:
            connection.execute(text(statement))
    with migration_engine.connect() as connection:
        result = snapshot(connection)
        assert len(result["views"]) == 4
        assert all(row["numeric_precision"] == 10 for row in result["columns"])


def test_numeric_migration_does_not_wait_for_import_advisory_lock(migration_engine):
    with migration_engine.begin() as holder:
        holder.exec_driver_sql("SELECT pg_advisory_xact_lock(42917001)")
        with pytest.raises(Exception, match="单据导入正在写入"):
            with migration_engine.begin() as connection:
                expand(connection)
