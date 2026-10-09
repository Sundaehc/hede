"""Separate product archive factory shipping prices from cost prices."""

from __future__ import annotations

from alembic import op


revision = "20261009_0076"
down_revision = "20261009_0075"
branch_labels = None
depends_on = None


PRODUCT_TABLES = (
    "cbanner_mens_products",
    "cbanner_womens_products",
    "yandou_products",
    "eblan_products",
    "smiley_products",
    "ni_products",
)


def _alter_cost_price(action: str) -> None:
    for table_name in PRODUCT_TABLES:
        op.execute(f"ALTER TABLE IF EXISTS {table_name} {action}")
    op.execute(
        f"""
        DO $$
        DECLARE
            archive_table TEXT;
        BEGIN
            IF to_regclass('supplier_brands') IS NULL THEN
                RETURN;
            END IF;
            FOR archive_table IN
                SELECT product_table_name
                FROM supplier_brands
                WHERE product_archive_enabled = TRUE
                  AND product_table_name ~ '^manual_product_archive_[0-9]+$'
            LOOP
                EXECUTE format('ALTER TABLE IF EXISTS %I {action}', archive_table);
            END LOOP;
        END
        $$;
        """
    )


def upgrade() -> None:
    _alter_cost_price("ADD COLUMN IF NOT EXISTS cost_price NUMERIC(10, 2)")


def downgrade() -> None:
    _alter_cost_price("DROP COLUMN IF EXISTS cost_price")
