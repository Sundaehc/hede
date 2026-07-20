"""retain VIP daily report rows for each source date

Revision ID: 20260720_0041
Revises: 20260717_0040
Create Date: 2026-07-20
"""

from __future__ import annotations

from alembic import op


revision = "20260720_0041"
down_revision = "20260717_0040"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE vip_product_daily "
        "DROP CONSTRAINT IF EXISTS uq_daily_report_goods"
    )
    op.execute(
        "ALTER TABLE vip_product_daily "
        "DROP CONSTRAINT IF EXISTS uq_daily_report_goods_date"
    )
    op.execute(
        "ALTER TABLE vip_product_daily "
        "ADD CONSTRAINT uq_daily_report_goods_date "
        "UNIQUE (report_type, period, goods_id, date)"
    )


def downgrade() -> None:
    op.execute(
        "ALTER TABLE vip_product_daily "
        "DROP CONSTRAINT IF EXISTS uq_daily_report_goods_date"
    )
    op.execute(
        "ALTER TABLE vip_product_daily "
        "ADD CONSTRAINT uq_daily_report_goods "
        "UNIQUE (report_type, period, goods_id)"
    )
