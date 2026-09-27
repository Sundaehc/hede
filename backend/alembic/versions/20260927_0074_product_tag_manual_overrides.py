"""Allow manual overrides for generated product tags."""

from __future__ import annotations

from alembic import op


revision = "20260927_0074"
down_revision = "20260927_0073"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE product_tag_definitions "
        "ADD COLUMN IF NOT EXISTS is_manual_override BOOLEAN NOT NULL DEFAULT FALSE"
    )


def downgrade() -> None:
    op.execute("ALTER TABLE product_tag_definitions DROP COLUMN IF EXISTS is_manual_override")
