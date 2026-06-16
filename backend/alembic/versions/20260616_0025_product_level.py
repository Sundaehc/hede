"""add product level to brand product tables

Revision ID: 20260616_0025
Revises: 20260615_0024
Create Date: 2026-06-16
"""

from __future__ import annotations

from alembic import op


revision: str = "20260616_0025"
down_revision: str | None = "20260615_0024"
branch_labels: str | None = None
depends_on: str | None = None


PRODUCT_TABLES = (
    "cbanner_mens_products",
    "cbanner_womens_products",
    "yandou_products",
    "eblan_products",
)


def upgrade() -> None:
    for table_name in PRODUCT_TABLES:
        op.execute(f"ALTER TABLE {table_name} ADD COLUMN IF NOT EXISTS product_level TEXT")


def downgrade() -> None:
    for table_name in PRODUCT_TABLES:
        op.execute(f"ALTER TABLE {table_name} DROP COLUMN IF EXISTS product_level")
