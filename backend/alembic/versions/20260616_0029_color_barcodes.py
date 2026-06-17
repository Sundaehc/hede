"""create color barcodes

Revision ID: 20260616_0029
Revises: 20260616_0028
Create Date: 2026-06-16
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision: str = "20260616_0029"
down_revision: str | None = "20260616_0028"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.create_table(
        "color_barcodes",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=False), primary_key=True),
        sa.Column("brand", sa.Text(), nullable=False),
        sa.Column("color_barcode", sa.Text(), nullable=False),
        sa.Column("color_name", sa.Text(), nullable=False),
        sa.Column("source_workbook", sa.Text(), nullable=False),
        sa.Column("source_sheet", sa.Text(), nullable=False),
        sa.Column("source_row_number", sa.Text(), nullable=False),
        sa.Column("raw_payload", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.date_trunc("minute", sa.func.now())),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.date_trunc("minute", sa.func.now())),
        sa.UniqueConstraint("brand", "color_barcode", name="uq_color_barcodes_brand_code"),
    )
    op.create_index("idx_color_barcodes_brand", "color_barcodes", ["brand"])
    op.create_index("idx_color_barcodes_color_barcode", "color_barcodes", ["color_barcode"])
    op.create_index("idx_color_barcodes_color_name", "color_barcodes", ["color_name"])


def downgrade() -> None:
    op.drop_index("idx_color_barcodes_color_name", table_name="color_barcodes")
    op.drop_index("idx_color_barcodes_color_barcode", table_name="color_barcodes")
    op.drop_index("idx_color_barcodes_brand", table_name="color_barcodes")
    op.drop_table("color_barcodes")
