"""baseline schema

Revision ID: 20260521_0001
Revises:
Create Date: 2026-05-21 00:01:00
"""
from __future__ import annotations

from collections.abc import Sequence

from alembic import op

from domain import gj_schema, inventory_schema, vip_schema  # noqa: F401 - register tables on METADATA
from domain.schema import METADATA


revision: str = "20260521_0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    METADATA.create_all(bind, checkfirst=True)
    _create_current_indexes()


def downgrade() -> None:
    bind = op.get_bind()
    METADATA.drop_all(bind, checkfirst=True)


def _create_current_indexes() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")

    for table in ("cbanner_mens_products", "cbanner_womens_products", "yandou_products", "eblan_products"):
        op.execute(f"CREATE INDEX IF NOT EXISTS idx_{table}_year ON {table} (year)")
        op.execute(f"CREATE INDEX IF NOT EXISTS idx_{table}_sku_trgm ON {table} USING GIN (sku gin_trgm_ops)")
        op.execute(
            f"CREATE INDEX IF NOT EXISTS idx_{table}_original_sku_trgm "
            f"ON {table} USING GIN (original_sku gin_trgm_ops)"
        )

    statements = [
        "CREATE INDEX IF NOT EXISTS idx_inventory_records_date_value ON inventory_records (date_value)",
        "CREATE INDEX IF NOT EXISTS idx_jst_stock_date_qty ON jst_daily_stock (stock_date, product_code, available_qty)",
        "CREATE INDEX IF NOT EXISTS idx_jst_stock_date_value_code ON jst_daily_stock (stock_date_value, product_code)",
        "CREATE INDEX IF NOT EXISTS idx_jst_monthly_orders_order_time_at ON jst_monthly_orders (order_time_at)",
        "CREATE INDEX IF NOT EXISTS idx_jst_monthly_orders_product_code ON jst_monthly_orders (product_code)",
        "CREATE INDEX IF NOT EXISTS idx_jst_monthly_orders_style_code ON jst_monthly_orders (style_code)",
        "CREATE INDEX IF NOT EXISTS idx_jst_monthly_orders_shop_name ON jst_monthly_orders (shop_name)",
        "CREATE INDEX IF NOT EXISTS idx_jst_monthly_orders_status ON jst_monthly_orders (status)",
        "CREATE INDEX IF NOT EXISTS idx_jst_monthly_orders_ship_date_value ON jst_monthly_orders (ship_date_value)",
        "CREATE INDEX IF NOT EXISTS idx_jst_monthly_orders_time_product ON jst_monthly_orders (order_time_at, product_code)",
        "CREATE INDEX IF NOT EXISTS idx_vip_daily_report_dates ON vip_product_daily (report_start_date, report_end_date)",
        "CREATE INDEX IF NOT EXISTS idx_daily_snapshots_goods_code_date ON vip_product_daily_snapshots (goods_code, snapshot_date)",
        "CREATE INDEX IF NOT EXISTS idx_daily_snapshots_snapshot_date ON vip_product_daily_snapshots (snapshot_date)",
    ]
    for statement in statements:
        op.execute(statement)
