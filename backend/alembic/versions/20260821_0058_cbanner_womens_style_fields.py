"""Add the C.banner women's style detail fields.

Revision ID: 20260821_0058
Revises: 20260821_0057
Create Date: 2026-08-21
"""

from __future__ import annotations

from alembic import op


revision = "20260821_0058"
down_revision = "20260821_0057"
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

STYLE_COLUMNS = (
    "sole_style",
    "fashion_elements",
    "opening_depth",
    "boot_shaft",
    "mesh_upper_type",
)


def _alter_static_tables(*, add: bool) -> None:
    for table_name in PRODUCT_TABLES:
        for column_name in STYLE_COLUMNS:
            clause = (
                f"ADD COLUMN IF NOT EXISTS {column_name} TEXT"
                if add
                else f"DROP COLUMN IF EXISTS {column_name}"
            )
            op.execute(f"ALTER TABLE IF EXISTS {table_name} {clause}")


def _alter_manual_tables(*, add: bool) -> None:
    for column_name in STYLE_COLUMNS:
        clause = (
            f"ADD COLUMN IF NOT EXISTS {column_name} TEXT"
            if add
            else f"DROP COLUMN IF EXISTS {column_name}"
        )
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
                    EXECUTE format('ALTER TABLE IF EXISTS %I {clause}', archive_table);
                END LOOP;
            END
            $$;
            """
        )


def upgrade() -> None:
    _alter_static_tables(add=True)
    _alter_manual_tables(add=True)


def downgrade() -> None:
    _alter_static_tables(add=False)
    _alter_manual_tables(add=False)
