"""Add gross and return metrics to the factory-channel summary."""

from __future__ import annotations

from alembic import op


revision = "20260821_0059"
down_revision = "20260821_0058"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE IF EXISTS factory_channel_sales_daily_summaries
            ADD COLUMN IF NOT EXISTS gross_quantity BIGINT NOT NULL DEFAULT 0,
            ADD COLUMN IF NOT EXISTS return_quantity BIGINT NOT NULL DEFAULT 0
        """
    )
    # Existing rows only contain net quantity. This is a conservative bridge
    # until the scheduled/source refresh rebuilds them with source quantities.
    op.execute(
        """
        UPDATE factory_channel_sales_daily_summaries
        SET gross_quantity = GREATEST(quantity, 0),
            return_quantity = GREATEST(-quantity, 0)
        WHERE gross_quantity = 0 AND return_quantity = 0 AND quantity <> 0
        """
    )


def downgrade() -> None:
    op.execute(
        """
        ALTER TABLE IF EXISTS factory_channel_sales_daily_summaries
            DROP COLUMN IF EXISTS gross_quantity,
            DROP COLUMN IF EXISTS return_quantity
        """
    )
