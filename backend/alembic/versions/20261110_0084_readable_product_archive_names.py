"""Rename manual product archives using recognizable brand names."""
from alembic import op

from storage.product_archive_table_names import rename_product_archive_tables


revision = "20261110_0084"
down_revision = "20261110_0083"
branch_labels = None
depends_on = None


def upgrade() -> None:
    rename_product_archive_tables(op.get_bind())


def downgrade() -> None:
    rename_product_archive_tables(op.get_bind(), downgrade=True)
