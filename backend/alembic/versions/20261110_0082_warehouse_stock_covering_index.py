"""Cover warehouse product grouping and quantities without wide detail reads."""
from alembic import op
from sqlalchemy import text

revision = "20261110_0082"
down_revision = "20261105_0081"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # A concurrent build keeps normal inventory reads and writes available.
    # Do not build this large index during application startup.
    with op.get_context().autocommit_block():
        op.execute(text("SET lock_timeout = '5s'"))
        op.execute(text("SET statement_timeout = '180s'"))
        op.execute(text("SET maintenance_work_mem = '32MB'"))
        op.execute(text("SET max_parallel_maintenance_workers = 0"))
        try:
            op.execute(text(
                "CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_inventory_details_warehouse_stock "
                "ON public.inventory_details (document_id) "
                "INCLUDE (product_code, product_name, color_name, color_spec, quantity)"
            ))
            valid = op.get_bind().execute(text(
                "SELECT indisvalid FROM pg_index WHERE indexrelid = "
                "'public.idx_inventory_details_warehouse_stock'::regclass"
            )).scalar_one()
            if not valid:
                raise RuntimeError("Warehouse inventory index is invalid; inspect and repair before retrying")
        finally:
            op.execute(text("RESET lock_timeout"))
            op.execute(text("RESET statement_timeout"))
            op.execute(text("RESET maintenance_work_mem"))
            op.execute(text("RESET max_parallel_maintenance_workers"))


def downgrade() -> None:
    with op.get_context().autocommit_block():
        op.execute(text("DROP INDEX CONCURRENTLY IF EXISTS public.idx_inventory_details_warehouse_stock"))
