"""Add shoe box type and selling points to product archives.

Revision ID: 20260721_0044
Revises: 20260721_0043
Create Date: 2026-07-21
"""

from __future__ import annotations

from alembic import op


revision = "20260721_0044"
down_revision = "20260721_0043"
branch_labels = None
depends_on = None

PRODUCT_TABLES = (
    "cbanner_mens_products",
    "cbanner_womens_products",
    "yandou_products",
    "eblan_products",
)


def upgrade() -> None:
    for table_name in PRODUCT_TABLES:
        op.execute(f"ALTER TABLE IF EXISTS {table_name} ADD COLUMN IF NOT EXISTS shoe_box_type TEXT")
        op.execute(f"ALTER TABLE IF EXISTS {table_name} ADD COLUMN IF NOT EXISTS selling_points TEXT")


def downgrade() -> None:
    for table_name in PRODUCT_TABLES:
        op.execute(f"ALTER TABLE IF EXISTS {table_name} DROP COLUMN IF EXISTS selling_points")
        op.execute(f"ALTER TABLE IF EXISTS {table_name} DROP COLUMN IF EXISTS shoe_box_type")
