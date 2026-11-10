"""Invalidate warehouse query reuse on all committed inventory source changes."""
from alembic import op
from sqlalchemy import text
from domain.warehouse_inventory_revision_schema import SOURCE_TABLES, install_revision_tracking

revision = "20261110_0083"
down_revision = "20261110_0082"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(text("SET LOCAL lock_timeout = '5s'"))
    install_revision_tracking(op.get_bind())


def downgrade() -> None:
    for table in SOURCE_TABLES:
        op.execute(text(f"DROP TRIGGER IF EXISTS trg_{table}_warehouse_inventory_revision ON public.{table}"))
    op.execute(text("DROP FUNCTION IF EXISTS public.mark_warehouse_inventory_changed()"))
    op.execute(text("DROP TABLE IF EXISTS public.warehouse_inventory_revisions"))
