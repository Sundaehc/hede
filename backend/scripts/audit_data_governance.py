"""Normalize typed business fields and record invalid source values without blocking imports."""
from __future__ import annotations

import argparse
import json
import traceback

from sqlalchemy import create_engine, text

from config import load_settings
from domain import data_governance_schema  # noqa: F401 - register governance tables
from domain import master_data_schema  # noqa: F401 - register master-data tables
from domain.schema import METADATA
from storage.migrations import apply_core_database_optimizations


ISSUE_SPECS = (
    ("inventory_records", "date", "id", "date_value", r"^\d{4}-\d{2}-\d{2}$", "invalid_date"),
    ("jst_daily_stock", "stock_date", "id", "stock_date_value", r"^\d{1,2}\.\d{1,2}$", "invalid_month_day"),
    ("vip_product_daily", "date", "id", "report_start_date", r"^\d{4}-\d{2}-\d{2}(~\d{4}-\d{2}-\d{2})?$", "invalid_date_range"),
    ("jst_monthly_orders", "order_time", "id", "order_time_at", r"^\d{4}-\d{2}-\d{2}[ T]\d{2}:\d{2}:\d{2}", "invalid_timestamp"),
    ("jst_monthly_orders", "ship_date", "id", "ship_date_value", r"^\d{4}-\d{2}-\d{2}", "invalid_ship_date"),
    ("jst_product_price", "source_date", "id", "source_date_value", r"^\d{4}-\d{2}-\d{2}$", "invalid_source_date"),
    ("jst_aftersale_returns", "order_date", "id", "order_date_value", r"^\d{4}-\d{2}-\d{2}", "invalid_aftersale_date"),
    ("jst_aftersale_returns", "order_time", "id", "order_time_value", r"^\d{4}-\d{2}-\d{2}", "invalid_aftersale_time"),
)


def _quote(identifier: str) -> str:
    if not identifier.replace("_", "").isalnum() or identifier[0].isdigit():
        raise ValueError(f"Invalid identifier: {identifier}")
    return f'"{identifier}"'


def _create_normalized_views(engine) -> None:
    views = (
        ("v_inventory_records_normalized", "inventory_records", "date_value", "business_date"),
        ("v_jst_daily_stock_normalized", "jst_daily_stock", "stock_date_value", "business_date"),
        ("v_vip_product_daily_normalized", "vip_product_daily", "report_start_date", "report_start_date_value"),
        ("v_jst_monthly_orders_normalized", "jst_monthly_orders", "order_time_at", "order_time_value"),
        ("v_jst_product_price_normalized", "jst_product_price", "source_date_value", "business_date"),
        ("v_jst_aftersale_returns_normalized", "jst_aftersale_returns", "order_date_value", "business_date"),
    )
    with engine.begin() as connection:
        for view_name, table_name, typed_column, alias in views:
            connection.execute(
                text(
                    f"CREATE OR REPLACE VIEW public.{_quote(view_name)} AS "
                    f"SELECT source.*, source.{_quote(typed_column)} AS {_quote(alias)} "
                    f"FROM public.{_quote(table_name)} AS source"
                )
            )


def _record_issues(engine) -> dict[str, int]:
    result: dict[str, int] = {}
    with engine.begin() as connection:
        for table_name, column_name, key_column, typed_column, valid_pattern, issue_type in ISSUE_SPECS:
            invalid_condition = (
                f"nullif(btrim(source.{_quote(column_name)}::text), '') IS NOT NULL "
                f"AND source.{_quote(typed_column)} IS NULL "
                f"AND source.{_quote(column_name)}::text !~ :valid_pattern"
            )
            count = connection.execute(
                text(
                    f"""
                    SELECT count(*)
                    FROM public.{_quote(table_name)} AS source
                    WHERE {invalid_condition}
                    """
                ),
                {"valid_pattern": valid_pattern},
            ).scalar_one()
            connection.execute(
                text(
                    f"""
                    INSERT INTO public.data_quality_issues
                        (table_name, column_name, record_key, issue_type, raw_value, details, last_seen_at, resolved_at)
                    SELECT :table_name, :column_name, source.{_quote(key_column)}::text,
                           :issue_type, source.{_quote(column_name)}::text,
                           jsonb_build_object('typed_column', CAST(:typed_column AS text)), now(), NULL
                    FROM public.{_quote(table_name)} AS source
                    WHERE {invalid_condition}
                    ON CONFLICT (table_name, column_name, record_key, issue_type)
                    DO UPDATE SET raw_value = EXCLUDED.raw_value,
                                  details = EXCLUDED.details,
                                  last_seen_at = now(),
                                  resolved_at = NULL
                    """
                ),
                {
                    "table_name": table_name,
                    "column_name": column_name,
                    "issue_type": issue_type,
                    "typed_column": typed_column,
                    "valid_pattern": valid_pattern,
                },
            )
            connection.execute(
                text(
                    f"""
                    UPDATE public.data_quality_issues AS issue
                    SET resolved_at = now()
                    WHERE issue.table_name = :table_name
                      AND issue.column_name = :column_name
                      AND issue.issue_type = :issue_type
                      AND issue.resolved_at IS NULL
                      AND NOT EXISTS (
                          SELECT 1
                          FROM public.{_quote(table_name)} AS source
                          WHERE source.{_quote(key_column)}::text = issue.record_key
                            AND {invalid_condition}
                      )
                    """
                ),
                {
                    "table_name": table_name,
                    "column_name": column_name,
                    "issue_type": issue_type,
                    "valid_pattern": valid_pattern,
                },
            )
            result[f"{table_name}.{column_name}"] = int(count)
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description="数据类型规范化与异常值审计")
    parser.add_argument("--skip-normalize", action="store_true", help="不执行已有的类型回填，仅检查异常")
    args = parser.parse_args()

    settings = load_settings()
    assert settings.database_url is not None
    engine = create_engine(settings.database_url)
    METADATA.create_all(engine, checkfirst=True)
    with engine.begin() as connection:
        run_id = connection.execute(
            text("INSERT INTO public.data_governance_runs (status, result) VALUES ('running', '{}'::jsonb) RETURNING id")
        ).scalar_one()
    try:
        if not args.skip_normalize:
            apply_core_database_optimizations(engine)
        _create_normalized_views(engine)
        issues = _record_issues(engine)
        with engine.begin() as connection:
            connection.execute(
                text(
                    "UPDATE public.data_governance_runs SET status = 'success', result = CAST(:result AS jsonb), finished_at = now() WHERE id = :run_id"
                ),
                {"run_id": run_id, "result": json.dumps(issues, ensure_ascii=True)},
            )
        print(f"[DONE] data-governance audit complete: {issues}")
        return 0
    except Exception as exc:  # pragma: no cover - diagnostics for scheduled execution
        with engine.begin() as connection:
            connection.execute(
                text(
                    "UPDATE public.data_governance_runs SET status = 'failed', result = CAST(:result AS jsonb), finished_at = now() WHERE id = :run_id"
                ),
                {"run_id": run_id, "result": json.dumps({"error": str(exc)}, ensure_ascii=True)},
            )
        print(f"[FAILED] {type(exc).__name__}: {exc}")
        print(traceback.format_exc())
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
