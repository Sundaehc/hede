"""Preserve customer shops with historical business by disabling them."""

from __future__ import annotations

from alembic import op


revision = "20261009_0075"
down_revision = "20260927_0074"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE general_customer_shops "
        "ADD COLUMN IF NOT EXISTS is_active BOOLEAN NOT NULL DEFAULT TRUE"
    )


def downgrade() -> None:
    op.execute("ALTER TABLE general_customer_shops DROP COLUMN IF EXISTS is_active")
