"""Share shoe-box label templates across authorized accounts.

Revision ID: 20260917_0070
Revises: 20260916_0069
Create Date: 2026-09-17
"""

from __future__ import annotations

from alembic import op


revision = "20260917_0070"
down_revision = "20260916_0069"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Preserve colliding per-account templates by assigning the older rows new keys.
    op.execute(
        """
        WITH ranked AS (
            SELECT
                id,
                ROW_NUMBER() OVER (
                    PARTITION BY template_key
                    ORDER BY updated_at DESC NULLS LAST, id DESC
                ) AS row_number
            FROM purchase_print_templates
        )
        UPDATE purchase_print_templates AS template
        SET template_key = template.template_key || '_legacy_' || template.id::text
        FROM ranked
        WHERE template.id = ranked.id
          AND ranked.row_number > 1
        """
    )
    op.execute(
        """
        WITH selected_default AS (
            SELECT id
            FROM purchase_print_templates
            ORDER BY is_default DESC, updated_at DESC NULLS LAST, id DESC
            LIMIT 1
        )
        UPDATE purchase_print_templates AS template
        SET is_default = (template.id = selected_default.id)
        FROM selected_default
        """
    )
    op.execute("UPDATE purchase_print_templates SET user_id = 0 WHERE user_id <> 0")
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_purchase_print_templates_shared_key "
        "ON purchase_print_templates (template_key)"
    )
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_purchase_print_templates_shared_default "
        "ON purchase_print_templates (is_default) WHERE is_default = TRUE"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS uq_purchase_print_templates_shared_default")
    op.execute("DROP INDEX IF EXISTS uq_purchase_print_templates_shared_key")
