"""add supplier factory code

Revision ID: 20260604_0012
Revises: 20260604_0011
Create Date: 2026-06-04 13:58:00
"""
from __future__ import annotations

from collections.abc import Sequence

from alembic import op


revision: str = "20260604_0012"
down_revision: str | None = "20260604_0011"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("ALTER TABLE suppliers ADD COLUMN IF NOT EXISTS factory_code TEXT")
    op.execute("CREATE INDEX IF NOT EXISTS idx_suppliers_factory_code ON suppliers (factory_code)")


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_suppliers_factory_code")
    op.execute("ALTER TABLE suppliers DROP COLUMN IF EXISTS factory_code")
