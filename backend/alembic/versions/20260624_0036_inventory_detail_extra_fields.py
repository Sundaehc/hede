"""add inventory detail extra fields

Revision ID: 20260624_0036
Revises: 20260624_0035
Create Date: 2026-06-24
"""

from __future__ import annotations

from alembic import op


revision = "20260624_0036"
down_revision = "20260624_0035"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE IF EXISTS inventory_details ADD COLUMN IF NOT EXISTS extra_fields JSON")


def downgrade() -> None:
    op.execute("ALTER TABLE IF EXISTS inventory_details DROP COLUMN IF EXISTS extra_fields")
