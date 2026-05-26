"""drop extra in-transit columns from jst_stock_summary

Revision ID: 20260526_0006
Revises: 20260526_0005
Create Date: 2026-05-26 00:06:00
"""
from __future__ import annotations

from collections.abc import Sequence

from alembic import op


revision: str = "20260526_0006"
down_revision: str | None = "20260526_0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("ALTER TABLE IF EXISTS jst_stock_summary DROP COLUMN IF EXISTS order_in_transit_qty")
    op.execute("ALTER TABLE IF EXISTS jst_stock_summary DROP COLUMN IF EXISTS defect_in_transit_qty")


def downgrade() -> None:
    op.execute("ALTER TABLE IF EXISTS jst_stock_summary ADD COLUMN IF NOT EXISTS order_in_transit_qty INTEGER")
    op.execute("ALTER TABLE IF EXISTS jst_stock_summary ADD COLUMN IF NOT EXISTS defect_in_transit_qty INTEGER")
