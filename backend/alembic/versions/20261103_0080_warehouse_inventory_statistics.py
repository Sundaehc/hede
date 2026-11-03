"""Improve estimates of distinct warehouse inventory product groups."""
from alembic import op
from sqlalchemy import text

revision = "20261103_0080"
down_revision = "20261027_0079"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(text("SET LOCAL lock_timeout = '5s'"))
    op.execute(text("SET LOCAL statement_timeout = '60s'"))
    op.execute(text(
        "CREATE STATISTICS IF NOT EXISTS public.st_inventory_details_warehouse_product_group (ndistinct) "
        "ON product_code, product_name, color_name, color_spec FROM public.inventory_details"
    ))
    op.execute(text("ANALYZE public.inventory_details (product_code, product_name, color_name, color_spec)"))


def downgrade() -> None:
    op.execute(text("DROP STATISTICS IF EXISTS public.st_inventory_details_warehouse_product_group"))
