"""Add indexes for inventory product-code search.

Revision ID: 20260617_0032
Revises: 20260617_0031
Create Date: 2026-06-17
"""

from __future__ import annotations

from alembic import op


revision = "20260617_0032"
down_revision = "20260617_0031"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_inventory_details_product_code "
        "ON inventory_details (product_code)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_jst_stock_product_code "
        "ON jst_daily_stock (product_code)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_inventory_details_product_code_trgm "
        "ON inventory_details USING GIN (product_code gin_trgm_ops)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_jst_stock_product_code_trgm "
        "ON jst_daily_stock USING GIN (product_code gin_trgm_ops)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_jst_stock_product_code_trgm")
    op.execute("DROP INDEX IF EXISTS idx_inventory_details_product_code_trgm")
    op.execute("DROP INDEX IF EXISTS idx_jst_stock_product_code")
    op.execute("DROP INDEX IF EXISTS idx_inventory_details_product_code")
