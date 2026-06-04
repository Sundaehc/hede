"""optimize fine table snapshot tables

Revision ID: 20260604_0011
Revises: 20260603_0010
Create Date: 2026-06-04 00:11:00
"""
from __future__ import annotations

from collections.abc import Sequence

from alembic import op


revision: str = "20260604_0011"
down_revision: str | None = "20260603_0010"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE fine_table_snapshot_batches
        ADD COLUMN IF NOT EXISTS latest_order_date_value DATE
        """
    )
    op.execute(
        """
        UPDATE fine_table_snapshot_batches
        SET latest_order_date_value =
            CASE
                WHEN latest_order_date ~ '^\\d{4}-\\d{2}-\\d{2}$' THEN latest_order_date::date
                ELSE NULL
            END
        WHERE latest_order_date_value IS NULL
        """
    )
    op.execute("ALTER TABLE fine_table_snapshot_batches DROP COLUMN IF EXISTS latest_order_date")
    op.execute("ALTER TABLE fine_table_snapshot_batches RENAME COLUMN latest_order_date_value TO latest_order_date")

    op.execute("ALTER TABLE fine_table_snapshot_rows DROP COLUMN IF EXISTS brand")
    op.execute(
        """
        DELETE FROM fine_table_snapshot_rows
        WHERE id IN (
            SELECT id
            FROM (
                SELECT
                    id,
                    row_number() OVER (
                        PARTITION BY batch_id, row_index
                        ORDER BY id
                    ) AS duplicate_rank
                FROM fine_table_snapshot_rows
            ) ranked
            WHERE duplicate_rank > 1
        )
        """
    )
    op.execute(
        """
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1
                FROM pg_constraint
                WHERE conname = 'uq_fine_table_snapshot_rows_batch_row_index'
            ) THEN
                ALTER TABLE fine_table_snapshot_rows
                ADD CONSTRAINT uq_fine_table_snapshot_rows_batch_row_index
                UNIQUE (batch_id, row_index);
            END IF;
        END
        $$;
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_fine_table_snapshot_rows_batch_row_index "
        "ON fine_table_snapshot_rows (batch_id, row_index)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_fine_table_snapshot_rows_batch_original_sku "
        "ON fine_table_snapshot_rows (batch_id, original_sku)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_fine_table_snapshot_rows_batch_original_sku")
    op.execute("DROP INDEX IF EXISTS idx_fine_table_snapshot_rows_batch_row_index")
    op.execute(
        """
        ALTER TABLE fine_table_snapshot_rows
        DROP CONSTRAINT IF EXISTS uq_fine_table_snapshot_rows_batch_row_index
        """
    )
    op.execute("ALTER TABLE fine_table_snapshot_rows ADD COLUMN IF NOT EXISTS brand TEXT")
    op.execute(
        """
        UPDATE fine_table_snapshot_rows rows
        SET brand = batches.brand
        FROM fine_table_snapshot_batches batches
        WHERE rows.batch_id = batches.id
        """
    )
    op.execute("ALTER TABLE fine_table_snapshot_rows ALTER COLUMN brand SET NOT NULL")

    op.execute(
        """
        ALTER TABLE fine_table_snapshot_batches
        ADD COLUMN IF NOT EXISTS latest_order_date_text TEXT
        """
    )
    op.execute(
        """
        UPDATE fine_table_snapshot_batches
        SET latest_order_date_text = latest_order_date::text
        WHERE latest_order_date_text IS NULL
        """
    )
    op.execute("ALTER TABLE fine_table_snapshot_batches DROP COLUMN IF EXISTS latest_order_date")
    op.execute("ALTER TABLE fine_table_snapshot_batches RENAME COLUMN latest_order_date_text TO latest_order_date")
