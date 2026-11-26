"""Store the 3-day and 30-day sales from the JST full stock workbook."""

from alembic import op


revision = "20261125_0091"
down_revision = "20261124_0090"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("SET LOCAL lock_timeout = '5s'")
    op.execute(
        "ALTER TABLE jst_full_stock "
        "ADD COLUMN IF NOT EXISTS sales_3d_qty INTEGER, "
        "ADD COLUMN IF NOT EXISTS sales_30d_qty INTEGER"
    )


def downgrade() -> None:
    op.execute("SET LOCAL lock_timeout = '5s'")
    op.execute(
        "ALTER TABLE jst_full_stock "
        "DROP COLUMN IF EXISTS sales_3d_qty, DROP COLUMN IF EXISTS sales_30d_qty"
    )
