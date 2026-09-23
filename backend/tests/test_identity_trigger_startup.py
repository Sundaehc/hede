from pathlib import Path
import os
from unittest.mock import Mock
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, event, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import OperationalError

from domain.product_archive_identity_schema import _ensure_trigger, ensure_product_archive_identity_schema


TRIGGER_ARGUMENTS = {
    "table_name": "archive_test",
    "trigger_name": "trg_hede_product_identity_sync",
    "function_name": "hede_sync_product_archive_identity",
    "trigger_type": 29,
    "columns": ("sku", "original_sku", "deleted_at"),
    "arguments": ("test_brand",),
    "definition": "CREATE TRIGGER expected_definition",
}


def matching_trigger():
    return {
        "tgtype": 29, "tgenabled": "O", "tgargs": b"test_brand\0", "unconditional": True,
        "ordinary": True, "no_transition_tables": True, "function_matches": True,
        "updated_columns": ["deleted_at", "original_sku", "sku"],
    }


def test_matching_trigger_does_not_execute_ddl():
    connection = Mock()
    connection.execute.return_value.mappings.return_value.first.return_value = matching_trigger()
    _ensure_trigger(connection, **TRIGGER_ARGUMENTS)
    assert connection.execute.call_count == 1
    assert "FROM pg_catalog.pg_trigger" in str(connection.execute.call_args.args[0])


@pytest.mark.parametrize("change", [
    {"tgtype": 23}, {"tgenabled": "D"}, {"tgargs": b"wrong_brand\0"},
    {"unconditional": False}, {"ordinary": False}, {"no_transition_tables": False},
    {"function_matches": False}, {"updated_columns": ["sku"]},
])
def test_changed_trigger_is_replaced(change):
    connection = Mock()
    connection.execute.return_value.mappings.return_value.first.return_value = {**matching_trigger(), **change}
    _ensure_trigger(connection, **TRIGGER_ARGUMENTS)
    statements = [str(call.args[0]) for call in connection.execute.call_args_list]
    assert statements[1:] == [
        "DROP TRIGGER trg_hede_product_identity_sync ON archive_test", "CREATE TRIGGER expected_definition",
    ]


def test_missing_trigger_is_created_without_drop():
    connection = Mock()
    connection.execute.return_value.mappings.return_value.first.return_value = None
    _ensure_trigger(connection, **TRIGGER_ARGUMENTS)
    assert connection.execute.call_count == 2
    assert str(connection.execute.call_args.args[0]) == "CREATE TRIGGER expected_definition"


@pytest.fixture(scope="module")
def isolated_database():
    value = os.getenv("IDENTITY_TRIGGER_TEST_DATABASE_URL")
    if not value:
        pytest.skip("Only runs with a dedicated local PostgreSQL test cluster")
    url = make_url(value)
    if url.host != "127.0.0.1" or url.port != 55439 or url.database != "postgres":
        raise RuntimeError("Refusing trigger tests outside isolated loopback cluster")
    admin = create_engine(value, isolation_level="AUTOCOMMIT")
    try:
        with admin.connect() as connection:
            directory = Path(connection.scalar(text("SHOW data_directory"))).resolve()
            logs = (Path(__file__).resolve().parents[1] / "logs").resolve()
            if not directory.is_relative_to(logs) or not directory.name.startswith("mcp-pg-test-trigger-"):
                raise RuntimeError("Refusing trigger tests outside isolated test directory")
            database_name = "identity_trigger_test_" + uuid4().hex
            connection.exec_driver_sql(f"CREATE DATABASE {database_name}")
        yield url.set(database=database_name)
    finally:
        admin.dispose()


@pytest.fixture
def trigger_engine(isolated_database):
    schema = "identity_test_" + uuid4().hex
    engine = create_engine(isolated_database)
    with engine.begin() as connection:
        connection.exec_driver_sql(f"CREATE SCHEMA {schema}")
    engine.dispose()
    engine = create_engine(isolated_database, connect_args={"options": f"-c search_path={schema},pg_catalog"})
    with engine.begin() as connection:
        for statement in (
            "CREATE TABLE inventory_records(id bigint PRIMARY KEY,document_type text,supplier text,raw_payload json,updated_at timestamptz)",
            "CREATE TABLE inventory_details(id bigint PRIMARY KEY,document_id bigint,product_code text,product_name text,color_barcode text,extra_fields json,updated_at timestamptz)",
            "CREATE TABLE suppliers(id bigint PRIMARY KEY,name text,brand text)",
            "CREATE TABLE archive_test(id bigint PRIMARY KEY,sku text,original_sku text,deleted_at timestamptz)",
        ):
            connection.exec_driver_sql(statement)
        ensure_product_archive_identity_schema(connection, table_specs=(("archive_test", "test_brand"),))
    try:
        yield engine
    finally:
        engine.dispose()


def trigger_oids(connection):
    return dict(connection.execute(text("""SELECT tgname,oid FROM pg_trigger
        WHERE tgrelid IN (to_regclass('archive_test'),to_regclass('inventory_details'),to_regclass('inventory_records'))
        AND NOT tgisinternal ORDER BY tgname""")).all())


@pytest.mark.parametrize(("relation", "trigger_name"), [
    ("archive_test", "trg_hede_product_identity_sync"),
    ("inventory_details", "trg_hede_purchase_detail_product_link"),
    ("inventory_records", "trg_hede_inventory_record_product_links"),
])
def test_startup_succeeds_with_concurrent_reader_without_dropping_trigger(trigger_engine, relation, trigger_name):
    with trigger_engine.connect() as reader, trigger_engine.begin() as startup:
        reader.exec_driver_sql(f"SELECT * FROM {relation} LIMIT 0")
        startup.exec_driver_sql("SET LOCAL lock_timeout='150ms'")
        startup.exec_driver_sql("SET LOCAL statement_timeout='5s'")
        with pytest.raises(OperationalError) as error:
            with startup.begin_nested():
                startup.exec_driver_sql(f"DROP TRIGGER IF EXISTS {trigger_name} ON {relation}")
        assert error.value.orig.sqlstate == "55P03"
        before = trigger_oids(startup)
        statements = []
        def capture(connection, cursor, statement, parameters, context, executemany):
            statements.append(statement)
        event.listen(startup, "before_cursor_execute", capture)
        ensure_product_archive_identity_schema(startup, table_specs=(("archive_test", "test_brand"),))
        assert trigger_oids(startup) == before
        assert not any("DROP TRIGGER" in statement or "CREATE TRIGGER" in statement for statement in statements)
        reader.rollback()


@pytest.mark.parametrize("alteration", [
    "ALTER TABLE archive_test DISABLE TRIGGER trg_hede_product_identity_sync",
    "DROP TRIGGER trg_hede_product_identity_sync ON archive_test",
    "CREATE OR REPLACE TRIGGER trg_hede_product_identity_sync AFTER INSERT OR DELETE OR UPDATE OF sku,original_sku,deleted_at ON archive_test FOR EACH ROW EXECUTE FUNCTION hede_sync_product_archive_identity('wrong_brand')",
    "CREATE OR REPLACE TRIGGER trg_hede_product_identity_sync AFTER INSERT OR DELETE OR UPDATE OF sku ON archive_test FOR EACH ROW EXECUTE FUNCTION hede_sync_product_archive_identity('test_brand')",
])
def test_startup_repairs_missing_or_stale_trigger(trigger_engine, alteration):
    with trigger_engine.begin() as connection:
        connection.exec_driver_sql(alteration)
        ensure_product_archive_identity_schema(connection, table_specs=(("archive_test", "test_brand"),))
        connection.exec_driver_sql("INSERT INTO archive_test VALUES(1,'BEFORE','ORIGINAL',NULL)")
        assert connection.execute(text("SELECT brand,sku FROM product_archive_identities")).one() == ("test_brand", "BEFORE")
        connection.exec_driver_sql("UPDATE archive_test SET original_sku='CHANGED' WHERE id=1")
        assert connection.scalar(text("SELECT original_sku FROM product_archive_identities")) == "CHANGED"


def test_second_startup_preserves_revoked_function_privileges_and_business_links(trigger_engine):
    with trigger_engine.begin() as connection:
        connection.exec_driver_sql("REVOKE EXECUTE ON FUNCTION hede_sync_product_archive_identity() FROM PUBLIC")
        ensure_product_archive_identity_schema(connection, table_specs=(("archive_test", "test_brand"),))
        public_execute = connection.scalar(text("""SELECT count(*) FROM pg_proc routine,
            LATERAL aclexplode(COALESCE(routine.proacl,acldefault('f',routine.proowner))) permission
            WHERE routine.oid=to_regprocedure('hede_sync_product_archive_identity()') AND permission.grantee=0"""))
        assert public_execute == 0
        connection.exec_driver_sql("INSERT INTO archive_test VALUES(1,'OLD','ORIGINAL',NULL)")
        connection.exec_driver_sql("INSERT INTO inventory_records VALUES(1,'purchase',NULL,'{\"brand\":\"test_brand\"}',NULL)")
        connection.exec_driver_sql("INSERT INTO inventory_details(id,document_id,product_code,extra_fields) VALUES(1,1,'OLD','{\"image_code\":\"OLD\"}')")
        identity = connection.scalar(text("SELECT product_identity_id FROM inventory_details WHERE id=1"))
        assert identity is not None
        connection.exec_driver_sql("UPDATE archive_test SET sku='NEW' WHERE id=1")
        row = connection.execute(text("SELECT product_identity_id,product_code,extra_fields->>'image_code' FROM inventory_details WHERE id=1")).one()
        assert row == (identity, "NEW", "NEW")
