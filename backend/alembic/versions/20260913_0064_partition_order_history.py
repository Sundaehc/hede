"""Partition retained order history by business year.

Revision ID: 20260913_0064
Revises: 20260911_0063
Create Date: 2026-09-13
"""

from __future__ import annotations

from alembic import op

from domain.history_partitioning import migrate_order_history_tables


revision = "20260913_0064"
down_revision = "20260911_0063"
branch_labels = None
depends_on = None


def upgrade() -> None:
    migrate_order_history_tables(op.get_bind())


def downgrade() -> None:
    raise RuntimeError(
        "Annual history partitioning is intentionally irreversible; "
        "restore a database backup to return to the unpartitioned layout."
    )
