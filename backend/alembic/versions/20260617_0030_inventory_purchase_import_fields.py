"""add purchase import inventory fields

Revision ID: 20260617_0030
Revises: 20260616_0029
Create Date: 2026-06-17
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision: str = "20260617_0030"
down_revision: str | None = "20260616_0029"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.add_column("inventory_records", sa.Column("handler", sa.Text(), nullable=True))
    op.add_column("inventory_details", sa.Column("color_barcode", sa.Text(), nullable=True))
    op.add_column("inventory_details", sa.Column("color_name", sa.Text(), nullable=True))
    op.add_column("inventory_details", sa.Column("size_quantities", sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column("inventory_details", "size_quantities")
    op.drop_column("inventory_details", "color_name")
    op.drop_column("inventory_details", "color_barcode")
    op.drop_column("inventory_records", "handler")
