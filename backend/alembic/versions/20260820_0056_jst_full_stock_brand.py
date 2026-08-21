"""Add brand to the JST full inventory table.

Revision ID: 20260820_0056
Revises: 20260819_0055
Create Date: 2026-08-20
"""

from __future__ import annotations

from alembic import op


revision = "20260820_0056"
down_revision = "20260819_0055"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE jst_full_stock ADD COLUMN IF NOT EXISTS brand TEXT")
    op.execute("CREATE INDEX IF NOT EXISTS idx_jst_full_stock_brand ON jst_full_stock (brand)")


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_jst_full_stock_brand")
    op.execute("ALTER TABLE jst_full_stock DROP COLUMN IF EXISTS brand")
