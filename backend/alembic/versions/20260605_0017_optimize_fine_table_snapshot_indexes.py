"""drop redundant fine table snapshot indexes

Revision ID: 20260605_0017
Revises: 20260604_0016
Create Date: 2026-06-05 10:00:00
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "20260605_0017"
down_revision: str | None = "20260604_0016"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _snapshot_row_tables() -> list[str]:
    bind = op.get_bind()
    return [
        row.tablename
        for row in bind.execute(
            sa.text(
                """
                SELECT tablename
                FROM pg_tables
                WHERE schemaname = current_schema()
                  AND (
                    tablename = 'fine_table_snapshot_rows'
                    OR tablename ~ '^fine_table_snapshot_rows_[0-9]{4}$'
                    OR tablename ~ '^fine_table_snapshot_rows_[0-9]{4}_[0-9]{2}$'
                  )
                ORDER BY tablename
                """
            )
        )
    ]


def upgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_fine_table_snapshot_batches_brand_date")
    for table_name in _snapshot_row_tables():
        op.execute(f"DROP INDEX IF EXISTS idx_{table_name}_batch")
        op.execute(f"DROP INDEX IF EXISTS idx_{table_name}_batch_row_index")


def downgrade() -> None:
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_fine_table_snapshot_batches_brand_date "
        "ON fine_table_snapshot_batches (brand, snapshot_date)"
    )
    for table_name in _snapshot_row_tables():
        op.execute(f"CREATE INDEX IF NOT EXISTS idx_{table_name}_batch ON {table_name} (batch_id)")
        op.execute(
            f"CREATE INDEX IF NOT EXISTS idx_{table_name}_batch_row_index "
            f"ON {table_name} (batch_id, row_index)"
        )
