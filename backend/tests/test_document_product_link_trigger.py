from __future__ import annotations

from unittest.mock import Mock

import pytest
from sqlalchemy import create_engine, text

from domain.product_archive_identity_schema import (
    _install_functions,
    install_document_product_link_function,
)


def test_document_product_link_function_compares_payloads_as_jsonb() -> None:
    connection = Mock()

    install_document_product_link_function(connection)

    connection.execute.assert_called_once()
    statement = str(connection.execute.call_args.args[0])
    assert "NEW.raw_payload::jsonb IS DISTINCT FROM OLD.raw_payload::jsonb" in statement
    assert "NEW.raw_payload IS DISTINCT FROM OLD.raw_payload" not in statement


def test_identity_schema_installation_includes_fixed_document_function() -> None:
    connection = Mock()

    _install_functions(connection)

    statements = [str(call.args[0]) for call in connection.execute.call_args_list]
    document_functions = [
        statement for statement in statements
        if "CREATE OR REPLACE FUNCTION hede_refresh_document_product_links()" in statement
    ]
    assert len(document_functions) == 1
    assert "NEW.raw_payload::jsonb IS DISTINCT FROM OLD.raw_payload::jsonb" in document_functions[0]


@pytest.fixture
def document_trigger_connection(test_database_url: str):
    engine = create_engine(test_database_url)
    if engine.dialect.name != "postgresql":
        engine.dispose()
        pytest.skip("PostgreSQL is required for trigger regression tests")

    try:
        with engine.connect() as connection:
            transaction = connection.begin()
            try:
                connection.execute(text("SET LOCAL search_path TO pg_temp"))
                connection.execute(text("""
                    CREATE TEMP TABLE inventory_records (
                        id bigint PRIMARY KEY,
                        document_type text,
                        supplier text,
                        raw_payload json,
                        additional_note text
                    ) ON COMMIT DROP
                """))
                connection.execute(text("""
                    CREATE TEMP TABLE inventory_details (
                        id bigint PRIMARY KEY,
                        document_id bigint,
                        product_identity_id bigint,
                        product_code text,
                        refresh_count integer NOT NULL DEFAULT 0
                    ) ON COMMIT DROP
                """))
                install_document_product_link_function(connection)
                connection.execute(text("""
                    CREATE FUNCTION pg_temp.count_detail_refresh() RETURNS trigger
                    LANGUAGE plpgsql AS $$
                    BEGIN
                        NEW.refresh_count := OLD.refresh_count + 1;
                        RETURN NEW;
                    END;
                    $$
                """))
                connection.execute(text("""
                    CREATE TRIGGER count_detail_refresh
                    BEFORE UPDATE ON inventory_details
                    FOR EACH ROW EXECUTE FUNCTION pg_temp.count_detail_refresh()
                """))
                connection.execute(text("""
                    CREATE TRIGGER refresh_document_product_links
                    AFTER UPDATE OF document_type, supplier, raw_payload ON inventory_records
                    FOR EACH ROW EXECUTE FUNCTION pg_temp.hede_refresh_document_product_links()
                """))
                yield connection
            finally:
                transaction.rollback()
    finally:
        engine.dispose()


def _insert_purchase_order(connection, raw_payload: str | None = "{}") -> None:
    connection.execute(text("""
        INSERT INTO inventory_records (id, document_type, supplier, raw_payload)
        VALUES (1, '进货订单', '测试供应商', CAST(:raw_payload AS json))
    """), {"raw_payload": raw_payload})
    connection.execute(text("""
        INSERT INTO inventory_details (id, document_id, product_identity_id, product_code)
        VALUES (1, 1, 42, 'TEST-SKU')
    """))


def test_purchase_order_metadata_edit_preserves_product_links(document_trigger_connection) -> None:
    connection = document_trigger_connection
    _insert_purchase_order(connection)

    connection.execute(text("""
        UPDATE inventory_records
        SET document_type = document_type, supplier = supplier, additional_note = '1234'
        WHERE id = 1
    """))

    assert connection.execute(text(
        "SELECT additional_note FROM inventory_records WHERE id = 1"
    )).scalar_one() == "1234"
    assert connection.execute(text(
        "SELECT product_identity_id, product_code, refresh_count FROM inventory_details WHERE id = 1"
    )).one() == (42, "TEST-SKU", 0)


@pytest.mark.parametrize(("old_payload", "new_payload", "expected_refreshes"), [
    ('{"brand":"cbanner_mens","nested":{"a":1,"b":2}}',
     '{ "nested": {"b": 2, "a": 1}, "brand": "cbanner_mens" }', 0),
    ('{"sizes":[38,39]}', '{ "sizes": [38, 39] }', 0),
    (None, None, 0),
    ("null", "null", 0),
    ('{"brand":"cbanner_mens"}', '{"brand":"cbanner_womens"}', 1),
    ('{"sizes":[38,39]}', '{"sizes":[39,38]}', 1),
    (None, "{}", 1),
    ("{}", None, 1),
    (None, "null", 1),
])
def test_purchase_order_payload_changes_refresh_only_when_distinct(
    document_trigger_connection,
    old_payload: str | None,
    new_payload: str | None,
    expected_refreshes: int,
) -> None:
    connection = document_trigger_connection
    _insert_purchase_order(connection, old_payload)

    connection.execute(text("""
        UPDATE inventory_records
        SET raw_payload = CAST(:raw_payload AS json)
        WHERE id = 1
    """), {"raw_payload": new_payload})

    identity_id = None if expected_refreshes else 42
    assert connection.execute(text(
        "SELECT product_identity_id, product_code, refresh_count FROM inventory_details WHERE id = 1"
    )).one() == (identity_id, "TEST-SKU", expected_refreshes)


@pytest.mark.parametrize(("document_type", "supplier"), [
    ("进货订单", "其他供应商"),
    ("进货单", "测试供应商"),
])
def test_purchase_order_scope_changes_still_clear_product_links(
    document_trigger_connection,
    document_type: str,
    supplier: str,
) -> None:
    connection = document_trigger_connection
    _insert_purchase_order(connection)

    connection.execute(text("""
        UPDATE inventory_records
        SET document_type = :document_type, supplier = :supplier
        WHERE id = 1
    """), {"document_type": document_type, "supplier": supplier})

    assert connection.execute(text(
        "SELECT product_identity_id, product_code, refresh_count FROM inventory_details WHERE id = 1"
    )).one() == (None, "TEST-SKU", 1)
