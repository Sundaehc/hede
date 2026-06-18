"""add supplier contact fields

Revision ID: 20260618_0033
Revises: 20260617_0032
Create Date: 2026-06-18
"""

from __future__ import annotations

from alembic import op


revision = "20260618_0033"
down_revision = "20260617_0032"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE IF EXISTS suppliers ADD COLUMN IF NOT EXISTS wechat TEXT")
    op.execute("ALTER TABLE IF EXISTS suppliers ADD COLUMN IF NOT EXISTS cooperation_status TEXT")


def downgrade() -> None:
    op.execute("ALTER TABLE IF EXISTS suppliers DROP COLUMN IF EXISTS cooperation_status")
    op.execute("ALTER TABLE IF EXISTS suppliers DROP COLUMN IF EXISTS wechat")
