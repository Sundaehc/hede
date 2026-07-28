"""Drop the ambiguous stock column from the price table.

Revision ID: 20260728_0046
Revises: 20260722_0045
Create Date: 2026-07-28
"""

from __future__ import annotations

from alembic import op


revision = "20260728_0046"
down_revision = "20260722_0045"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("DROP VIEW IF EXISTS v_jst_product_price_normalized")
    op.execute("ALTER TABLE jst_product_price DROP COLUMN IF EXISTS stock_qty")
    op.execute(
        """
        CREATE VIEW v_jst_product_price_normalized AS
        SELECT source.*, source.source_date_value AS business_date
        FROM jst_product_price AS source
        """
    )


def downgrade() -> None:
    op.execute("DROP VIEW IF EXISTS v_jst_product_price_normalized")
    op.execute("ALTER TABLE jst_product_price ADD COLUMN IF NOT EXISTS stock_qty INTEGER")
    op.execute(
        """
        CREATE VIEW v_jst_product_price_normalized AS
        SELECT source.*, source.source_date_value AS business_date
        FROM jst_product_price AS source
        """
    )
