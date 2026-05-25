"""rename jst_purchase_diff to jst_purchase_defects

Revision ID: 20260525_0004
Revises: 20260525_0003
Create Date: 2026-05-25 15:40:00
"""
from __future__ import annotations

from collections.abc import Sequence

from alembic import op


revision: str = "20260525_0004"
down_revision: str | None = "20260525_0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("ALTER TABLE IF EXISTS jst_purchase_diff RENAME TO jst_purchase_defects")
    op.execute(
        "ALTER INDEX IF EXISTS jst_purchase_diff_pkey RENAME TO jst_purchase_defects_pkey"
    )


def downgrade() -> None:
    op.execute("ALTER TABLE IF EXISTS jst_purchase_defects RENAME TO jst_purchase_diff")
    op.execute(
        "ALTER INDEX IF EXISTS jst_purchase_defects_pkey RENAME TO jst_purchase_diff_pkey"
    )
