"""create smiley fine table

Revision ID: 20260615_0024
Revises: 20260611_0023
Create Date: 2026-06-15 11:00:00
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "20260615_0024"
down_revision: str | None = "20260611_0023"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "smiley_fine_table",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=False), primary_key=True),
        sa.Column("snapshot_date", sa.Date(), nullable=False),
        sa.Column("source_workbook", sa.Text(), nullable=False),
        sa.Column("source_sheet", sa.Text(), nullable=False),
        sa.Column("source_row_number", sa.Integer(), nullable=False),
        sa.Column("image_path", sa.Text(), nullable=True),
        sa.Column("sku", sa.Text(), nullable=False),
        sa.Column("original_sku", sa.Text(), nullable=True),
        sa.Column("factory_code", sa.Text(), nullable=True),
        sa.Column("factory_sku", sa.Text(), nullable=True),
        sa.Column("market_price", sa.Numeric(10, 2), nullable=True),
        sa.Column("cost", sa.Numeric(10, 2), nullable=True),
        sa.Column("product_name", sa.Text(), nullable=True),
        sa.Column("barcode", sa.Text(), nullable=True),
        sa.Column("execution_standard", sa.Text(), nullable=True),
        sa.Column("insole_material", sa.Text(), nullable=True),
        sa.Column("outsole_material", sa.Text(), nullable=True),
        sa.Column("lining_material", sa.Text(), nullable=True),
        sa.Column("upper_material", sa.Text(), nullable=True),
        sa.Column("shoe_box_spec", sa.Text(), nullable=True),
        sa.Column("accessories", sa.Text(), nullable=True),
        sa.Column("first_order_date", sa.Date(), nullable=True),
        sa.Column("season_category", sa.Text(), nullable=True),
        sa.Column("stock_qty", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("inbound_qty", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("warehouse_stock", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("available_stock", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("daily_sales_total", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("total_3d_sales", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("total_7d_sales", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("total_15d_sales", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("total_30d_sales", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("shop_sales", sa.JSON(), nullable=False),
        sa.Column("size_stock", sa.JSON(), nullable=False),
        sa.Column("return_rates", sa.JSON(), nullable=False),
        sa.Column("remark", sa.Text(), nullable=True),
        sa.Column("raw_payload", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.date_trunc("minute", sa.func.now())),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.date_trunc("minute", sa.func.now()),
        ),
        sa.UniqueConstraint("snapshot_date", "sku", name="uq_smiley_fine_table_date_sku"),
    )
    op.create_index("idx_smiley_fine_table_snapshot_date", "smiley_fine_table", ["snapshot_date"])
    op.create_index("idx_smiley_fine_table_sku", "smiley_fine_table", ["sku"])
    op.create_index("idx_smiley_fine_table_original_sku", "smiley_fine_table", ["original_sku"])


def downgrade() -> None:
    op.drop_index("idx_smiley_fine_table_original_sku", table_name="smiley_fine_table")
    op.drop_index("idx_smiley_fine_table_sku", table_name="smiley_fine_table")
    op.drop_index("idx_smiley_fine_table_snapshot_date", table_name="smiley_fine_table")
    op.drop_table("smiley_fine_table")
