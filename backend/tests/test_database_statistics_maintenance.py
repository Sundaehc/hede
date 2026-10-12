from unittest.mock import MagicMock, Mock

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.dialects import postgresql

from domain.database_statistics import STALE_LARGE_TABLES_SQL
from scripts import maintain_database
from scripts.review_missing_data import Review, YELLOW


def test_maintenance_adds_stale_large_tables_and_deduplicates_fixed_tables(monkeypatch):
    engine = MagicMock()
    inspector = Mock()
    inspector.has_table.side_effect = lambda name, schema: name == "vip_daily_sales_2026" and schema == "public"
    monkeypatch.setattr(maintain_database, "inspect", lambda selected_engine: inspector)
    connection = engine.connect.return_value.__enter__.return_value
    connection.execute.return_value.mappings.return_value = [
        {"table_name": "fine_table_snapshot_payloads"},
        {"table_name": "vip_daily_sales_2026"},
        {"table_name": "jst_size_stock_snapshots"},
    ]
    assert maintain_database._existing_analyze_tables(engine) == (
        "vip_daily_sales_2026", "fine_table_snapshot_payloads", "jst_size_stock_snapshots",
    )
    statement = str(connection.execute.call_args.args[0])
    assert STALE_LARGE_TABLES_SQL in statement
    assert "last_autoanalyze" in statement
    assert "relation.relkind = 'r'" in statement


def test_maintenance_keeps_fixed_tables_when_no_large_table_is_stale(monkeypatch):
    engine = MagicMock()
    inspector = Mock()
    inspector.has_table.return_value = True
    monkeypatch.setattr(maintain_database, "inspect", lambda selected_engine: inspector)
    connection = engine.connect.return_value.__enter__.return_value
    connection.execute.return_value.mappings.return_value = []
    assert maintain_database._existing_analyze_tables(engine) == maintain_database.ANALYZE_TABLES


def test_analyze_uses_autocommit_timeouts_and_quoted_identifiers():
    engine = MagicMock()
    engine.dialect = postgresql.dialect()
    connection = engine.connect.return_value.execution_options.return_value.__enter__.return_value
    maintain_database._analyze_tables(engine, ('fine_table_snapshot_payloads', 'unusual"table'))
    engine.connect.return_value.execution_options.assert_called_once_with(isolation_level="AUTOCOMMIT")
    statements = [str(call.args[0]) for call in connection.execute.call_args_list]
    assert statements == [
        "SET lock_timeout = '10s'",
        "SET statement_timeout = '5min'",
        'ANALYZE "public"."fine_table_snapshot_payloads"',
        'ANALYZE "public"."unusual""table"',
    ]


def test_operations_review_uses_the_same_stale_table_definition():
    review = Review(Mock(), 90, {})
    review.scalar = Mock(side_effect=["120 GB", 14])
    review.rows_of = Mock(return_value=[])
    review.check_operations()
    assert not review.failures
    statement = review.scalar.call_args_list[1].args[0]
    assert STALE_LARGE_TABLES_SQL in statement
    result = next(row for row in review.rows if row["key"] == "ops.stale_stats")
    assert result["status"] == YELLOW
    assert result["detail"] == "14 张"
    assert "自动 ANALYZE" in result["note"]


@pytest.mark.parametrize(("manual_days", "automatic_days", "stale"), [
    (None, None, True),
    (None, 1, False),
    (20, 1, False),
    (1, 20, False),
    (8, None, True),
    (None, 8, True),
    (20, 8, True),
])
def test_staleness_uses_latest_manual_or_automatic_analysis(test_database_url, manual_days, automatic_days, stale):
    engine = create_engine(test_database_url)
    if engine.dialect.name != "postgresql":
        engine.dispose()
        pytest.skip("PostgreSQL statistics timestamp semantics required")
    try:
        with engine.connect() as connection:
            result = connection.scalar(text("""
                WITH timestamps AS (
                    SELECT now() - CAST(:manual_days AS integer) * interval '1 day' AS last_analyze,
                           now() - CAST(:automatic_days AS integer) * interval '1 day' AS last_autoanalyze
                )
                SELECT GREATEST(last_analyze, last_autoanalyze) IS NULL
                    OR GREATEST(last_analyze, last_autoanalyze) < now() - interval '7 days'
                FROM timestamps
            """), {"manual_days": manual_days, "automatic_days": automatic_days})
            assert result is stale
    finally:
        engine.dispose()
