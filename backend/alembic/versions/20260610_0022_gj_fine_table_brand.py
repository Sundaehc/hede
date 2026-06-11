"""add fine table brand to gj merged product info

Revision ID: 20260610_0022
Revises: 20260608_0021
Create Date: 2026-06-10 15:30:00
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "20260610_0022"
down_revision: str | None = "20260608_0021"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "gj_merged_product_info",
        sa.Column("fine_table_brand", sa.Text(), nullable=True),
    )
    op.execute(
        """
        UPDATE gj_merged_product_info
        SET fine_table_brand = CASE
            WHEN upper(coalesce(brand, '')) LIKE '%TRUMPPIPE%'
              OR coalesce(brand, '') LIKE '%烟斗%' THEN 'yandou'
            WHEN upper(coalesce(brand, '')) LIKE '%EBLAN%'
              OR coalesce(brand, '') LIKE '%伊伴%' THEN 'eblan'
            WHEN coalesce(primary_supplier, '') LIKE '%千百度品牌方%' THEN NULL
            WHEN coalesce(primary_supplier, '') LIKE '%千百度女鞋%' THEN 'cbanner_womens'
            WHEN coalesce(primary_supplier, '') LIKE '%千百度%' THEN 'cbanner_mens'
            ELSE NULL
        END
        WHERE fine_table_brand IS NULL
        """
    )

    with op.get_context().autocommit_block():
        op.execute(
            """
            CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_gj_merged_product_info_source_brand_id_desc
            ON gj_merged_product_info (source_date_value, fine_table_brand, id DESC)
            """
        )
        op.execute("DROP INDEX CONCURRENTLY IF EXISTS idx_jst_stock_summary_date_code")


def downgrade() -> None:
    with op.get_context().autocommit_block():
        op.execute(
            """
            CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_jst_stock_summary_date_code
            ON jst_stock_summary (stock_date, product_code)
            """
        )
        op.execute("DROP INDEX CONCURRENTLY IF EXISTS idx_gj_merged_product_info_source_brand_id_desc")
    op.drop_column("gj_merged_product_info", "fine_table_brand")
