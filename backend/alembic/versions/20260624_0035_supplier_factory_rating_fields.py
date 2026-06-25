"""add supplier factory rating fields

Revision ID: 20260624_0035
Revises: 20260618_0034
Create Date: 2026-06-24
"""

from __future__ import annotations

from alembic import op


revision = "20260624_0035"
down_revision = "20260618_0034"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE IF EXISTS suppliers ADD COLUMN IF NOT EXISTS factory_grade TEXT")
    op.execute("ALTER TABLE IF EXISTS suppliers ADD COLUMN IF NOT EXISTS factory_suggestion TEXT")
    op.execute("CREATE INDEX IF NOT EXISTS idx_suppliers_factory_grade ON suppliers (factory_grade)")


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_suppliers_factory_grade")
    op.execute("ALTER TABLE IF EXISTS suppliers DROP COLUMN IF EXISTS factory_suggestion")
    op.execute("ALTER TABLE IF EXISTS suppliers DROP COLUMN IF EXISTS factory_grade")
