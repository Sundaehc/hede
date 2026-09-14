"""Store product heel height and rear heel height separately.

Revision ID: 20260914_0066
Revises: 20260914_0065
Create Date: 2026-09-14
"""

from __future__ import annotations

from alembic import op


revision = "20260914_0066"
down_revision = "20260914_0065"
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


def _alter_static_tables(*, add: bool) -> None:
    for table_name in PRODUCT_TABLES:
        clause = (
            "ADD COLUMN IF NOT EXISTS rear_heel_height TEXT"
            if add
            else "DROP COLUMN IF EXISTS rear_heel_height"
        )
        op.execute(f"ALTER TABLE IF EXISTS {table_name} {clause}")


def _alter_manual_tables(*, add: bool) -> None:
    clause = (
        "ADD COLUMN IF NOT EXISTS rear_heel_height TEXT"
        if add
        else "DROP COLUMN IF EXISTS rear_heel_height"
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
    op.execute(
        """
        UPDATE cbanner_womens_products
        SET rear_heel_height = COALESCE(
            NULLIF(BTRIM(raw_payload ->> '后跟高'), ''),
            NULLIF(BTRIM(extra_fields ->> '后跟高'), '')
        )
        WHERE COALESCE(BTRIM(rear_heel_height), '') = ''
          AND (
              COALESCE(BTRIM(raw_payload ->> '后跟高'), '') <> ''
              OR COALESCE(BTRIM(extra_fields ->> '后跟高'), '') <> ''
          )
        """
    )
    op.execute(
        """
        UPDATE cbanner_womens_products
        SET heel_height = COALESCE(
            NULLIF(BTRIM(raw_payload ->> '跟高'), ''),
            NULLIF(BTRIM(extra_fields ->> '跟高'), '')
        )
        WHERE (
            COALESCE(BTRIM(raw_payload ->> '跟高'), '') <> ''
            OR COALESCE(BTRIM(extra_fields ->> '跟高'), '') <> ''
        )
        """
    )


def downgrade() -> None:
    _alter_manual_tables(add=False)
    _alter_static_tables(add=False)
