"""Support multiple named shoe-box label templates per account."""

from __future__ import annotations

from alembic import op


revision = "20260916_0069"
down_revision = "20260915_0068"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE IF EXISTS purchase_print_templates "
        "ADD COLUMN IF NOT EXISTS template_name TEXT NOT NULL DEFAULT '默认模板'"
    )
    op.execute(
        "ALTER TABLE IF EXISTS purchase_print_templates "
        "ADD COLUMN IF NOT EXISTS is_default BOOLEAN NOT NULL DEFAULT FALSE"
    )
    op.execute(
        "UPDATE purchase_print_templates "
        "SET template_name = '默认模板' "
        "WHERE template_name IS NULL OR BTRIM(template_name) = ''"
    )
    op.execute(
        "UPDATE purchase_print_templates AS current_template "
        "SET is_default = TRUE "
        "WHERE current_template.template_key = 'shoe_box_label' "
        "AND NOT EXISTS ("
        "  SELECT 1 FROM purchase_print_templates AS existing_default "
        "  WHERE existing_default.user_id = current_template.user_id "
        "    AND existing_default.is_default = TRUE"
        ")"
    )
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_purchase_print_templates_user_default "
        "ON purchase_print_templates (user_id) WHERE is_default = TRUE"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS uq_purchase_print_templates_user_default")
    op.execute("ALTER TABLE IF EXISTS purchase_print_templates DROP COLUMN IF EXISTS is_default")
    op.execute("ALTER TABLE IF EXISTS purchase_print_templates DROP COLUMN IF EXISTS template_name")
