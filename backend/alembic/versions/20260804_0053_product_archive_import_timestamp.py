"""Track the most recent Excel import for product archive quick exports."""

from alembic import op


revision = "20260804_0053"
down_revision = "20260804_0052"
branch_labels = None
depends_on = None


PRODUCT_TABLES = (
    "cbanner_mens_products",
    "cbanner_womens_products",
    "yandou_products",
    "eblan_products",
)


def upgrade() -> None:
    for table_name in PRODUCT_TABLES:
        op.execute(f"ALTER TABLE {table_name} ADD COLUMN IF NOT EXISTS last_imported_at TIMESTAMPTZ")
        op.execute(
            f"CREATE INDEX IF NOT EXISTS idx_{table_name}_last_imported_at "
            f"ON {table_name} (last_imported_at)"
        )


def downgrade() -> None:
    for table_name in PRODUCT_TABLES:
        op.execute(f"DROP INDEX IF EXISTS idx_{table_name}_last_imported_at")
        op.execute(f"ALTER TABLE {table_name} DROP COLUMN IF EXISTS last_imported_at")
