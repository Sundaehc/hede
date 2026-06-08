"""optimize fine table query indexes

Revision ID: 20260608_0021
Revises: 20260608_0020
Create Date: 2026-06-08 17:40:00
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "20260608_0021"
down_revision: str | None = "20260608_0020"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


PRODUCT_TABLES = (
    "cbanner_mens_products",
    "cbanner_womens_products",
    "yandou_products",
    "eblan_products",
)


def _snapshot_row_tables() -> list[str]:
    bind = op.get_bind()
    return [
        row.tablename
        for row in bind.execute(
            sa.text(
                """
                SELECT tablename
                FROM pg_tables
                WHERE schemaname = current_schema()
                  AND tablename ~ '^fine_table_snapshot_rows_[0-9]{4}$'
                ORDER BY tablename
                """
            )
        )
    ]


def _create_indexes_concurrently(statements: list[str]) -> None:
    with op.get_context().autocommit_block():
        op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")
        for statement in statements:
            op.execute(statement)


def _drop_indexes_concurrently(index_names: list[str]) -> None:
    with op.get_context().autocommit_block():
        for index_name in index_names:
            op.execute(f"DROP INDEX CONCURRENTLY IF EXISTS {index_name}")


def upgrade() -> None:
    statements = [
        "CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_gj_merged_product_info_source_date_id_desc "
        "ON gj_merged_product_info (source_date_value, id DESC)",
        "CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_gj_merged_product_info_source_date_goods_updated "
        "ON gj_merged_product_info (source_date_value, goods_code, updated_at DESC, id DESC)",
        "CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_gj_merged_product_info_goods_code_trgm "
        "ON gj_merged_product_info USING GIN (goods_code gin_trgm_ops)",
        "CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_gj_merged_product_info_original_goods_code_trgm "
        "ON gj_merged_product_info USING GIN (original_goods_code gin_trgm_ops)",
        "CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_gj_merged_product_info_primary_supplier_trgm "
        "ON gj_merged_product_info USING GIN (primary_supplier gin_trgm_ops)",
        "CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_vip_ops_goods_code_updated "
        "ON vip_product_ops (goods_code, updated_at DESC, id DESC)",
        "CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_vip_daily_goods_code_report_updated "
        "ON vip_product_daily (goods_code, report_end_date DESC, updated_at DESC, id DESC)",
        "CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_daily_snapshots_code_type_period_date "
        "ON vip_product_daily_snapshots (goods_code, report_type, period, snapshot_date)",
        "CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_jst_price_code_date_updated "
        "ON jst_product_price (goods_code, source_date_value DESC, updated_at DESC, id DESC)",
        "CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_jst_monthly_orders_style_time "
        "ON jst_monthly_orders (style_code, order_time_at)",
        "CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_jst_size_stock_product_size "
        "ON jst_size_stock (product_code, size)",
        "CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_jst_stock_summary_product_code "
        "ON jst_stock_summary (product_code)",
        "CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_jst_purchase_defects_product_code "
        "ON jst_purchase_defects (product_code)",
    ]
    for table_name in PRODUCT_TABLES:
        statements.append(
            f"CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_{table_name}_original_sku "
            f"ON {table_name} (original_sku)"
        )
    for table_name in _snapshot_row_tables():
        statements.extend(
            [
                f"CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_{table_name}_sku_trgm "
                f"ON {table_name} USING GIN (sku gin_trgm_ops)",
                f"CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_{table_name}_original_sku_trgm "
                f"ON {table_name} USING GIN (original_sku gin_trgm_ops)",
            ]
        )

    _create_indexes_concurrently(statements)


def downgrade() -> None:
    index_names = [
        "idx_gj_merged_product_info_source_date_id_desc",
        "idx_gj_merged_product_info_source_date_goods_updated",
        "idx_gj_merged_product_info_goods_code_trgm",
        "idx_gj_merged_product_info_original_goods_code_trgm",
        "idx_gj_merged_product_info_primary_supplier_trgm",
        "idx_vip_ops_goods_code_updated",
        "idx_vip_daily_goods_code_report_updated",
        "idx_daily_snapshots_code_type_period_date",
        "idx_jst_price_code_date_updated",
        "idx_jst_monthly_orders_style_time",
        "idx_jst_size_stock_product_size",
        "idx_jst_stock_summary_product_code",
        "idx_jst_purchase_defects_product_code",
        *(f"idx_{table_name}_original_sku" for table_name in PRODUCT_TABLES),
    ]
    for table_name in _snapshot_row_tables():
        index_names.extend(
            [
                f"idx_{table_name}_sku_trgm",
                f"idx_{table_name}_original_sku_trgm",
            ]
        )

    _drop_indexes_concurrently(index_names)
