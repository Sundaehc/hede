"""drop unused query indexes

Revision ID: 20260611_0023
Revises: 20260610_0022
Create Date: 2026-06-11 10:15:00
"""
from __future__ import annotations

from collections.abc import Sequence

from alembic import op


revision: str = "20260611_0023"
down_revision: str | None = "20260610_0022"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.get_context().autocommit_block():
        op.execute("DROP INDEX CONCURRENTLY IF EXISTS idx_gj_merged_product_info_primary_supplier_trgm")
        op.execute("DROP INDEX CONCURRENTLY IF EXISTS idx_jst_monthly_orders_shop_name")
        op.execute("DROP INDEX CONCURRENTLY IF EXISTS idx_jst_monthly_orders_status")


def downgrade() -> None:
    with op.get_context().autocommit_block():
        op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")
        op.execute(
            """
            CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_gj_merged_product_info_primary_supplier_trgm
            ON gj_merged_product_info USING GIN (primary_supplier gin_trgm_ops)
            """
        )
        op.execute(
            """
            CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_jst_monthly_orders_shop_name
            ON jst_monthly_orders (shop_name)
            """
        )
        op.execute(
            """
            CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_jst_monthly_orders_status
            ON jst_monthly_orders (status)
            """
        )
