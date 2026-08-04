"""Add barcode build rule to product archives."""

from alembic import op


revision = "20260804_0051"
down_revision = "20260803_0050"
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
        op.execute(f"ALTER TABLE {table_name} ADD COLUMN IF NOT EXISTS barcode_build_rule TEXT")


def downgrade() -> None:
    for table_name in PRODUCT_TABLES:
        op.execute(f"ALTER TABLE {table_name} DROP COLUMN IF EXISTS barcode_build_rule")
