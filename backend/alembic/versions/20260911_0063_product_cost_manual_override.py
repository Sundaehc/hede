"""Preserve manually maintained product archive costs.

Revision ID: 20260911_0063
Revises: 20260911_0062
Create Date: 2026-09-11
"""

from __future__ import annotations

from alembic import op


revision = "20260911_0063"
down_revision = "20260911_0062"
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


def upgrade() -> None:
    for table_name in PRODUCT_TABLES:
        op.execute(
            f"ALTER TABLE IF EXISTS {table_name} "
            "ADD COLUMN IF NOT EXISTS cost_manual_override "
            "BOOLEAN NOT NULL DEFAULT FALSE"
        )
    op.execute(
        """
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
                EXECUTE format(
                    'ALTER TABLE IF EXISTS %I ADD COLUMN IF NOT EXISTS '
                    'cost_manual_override BOOLEAN NOT NULL DEFAULT FALSE',
                    archive_table
                );
            END LOOP;
        END
        $$;
        """
    )


def downgrade() -> None:
    for table_name in PRODUCT_TABLES:
        op.execute(
            f"ALTER TABLE IF EXISTS {table_name} "
            "DROP COLUMN IF EXISTS cost_manual_override"
        )
    op.execute(
        """
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
                WHERE product_table_name ~ '^manual_product_archive_[0-9]+$'
            LOOP
                EXECUTE format(
                    'ALTER TABLE IF EXISTS %I DROP COLUMN IF EXISTS cost_manual_override',
                    archive_table
                );
            END LOOP;
        END
        $$;
        """
    )
