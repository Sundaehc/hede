"""drop notes from general customer brand and shop tables

Revision ID: 20260616_0026
Revises: 20260616_0025
Create Date: 2026-06-16
"""

from __future__ import annotations

from alembic import op


revision: str = "20260616_0026"
down_revision: str | None = "20260616_0025"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.execute("ALTER TABLE IF EXISTS general_customer_brands DROP COLUMN IF EXISTS notes")
    op.execute("ALTER TABLE IF EXISTS general_customer_shops DROP COLUMN IF EXISTS notes")


def downgrade() -> None:
    op.execute("ALTER TABLE IF EXISTS general_customer_brands ADD COLUMN IF NOT EXISTS notes TEXT")
    op.execute("ALTER TABLE IF EXISTS general_customer_shops ADD COLUMN IF NOT EXISTS notes TEXT")
