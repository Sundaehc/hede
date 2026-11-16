"""Add archive remarks for all built-in and configured brands."""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

from domain.product_archive_naming import manual_product_table_name
from domain.schema import PRODUCT_ARCHIVE_TABLES


revision = "20261116_0086"
down_revision = "20261111_0085"
branch_labels = None
depends_on = None


def _archives(connection):
    existing = set(sa.inspect(connection).get_table_names())
    names = {table.name for table in PRODUCT_ARCHIVE_TABLES.values()}
    if "supplier_brands" in existing:
        for name in connection.execute(sa.text(
            "SELECT product_table_name FROM supplier_brands WHERE product_table_name IS NOT NULL"
        )).scalars():
            if valid_name := manual_product_table_name(name):
                names.add(valid_name)
    return sorted(names & existing)


def upgrade() -> None:
    connection = op.get_bind()
    for name in _archives(connection):
        if "remark" not in {column["name"] for column in sa.inspect(connection).get_columns(name)}:
            op.add_column(name, sa.Column("remark", sa.Text(), nullable=True))


def downgrade() -> None:
    connection = op.get_bind()
    for name in _archives(connection):
        if "remark" in {column["name"] for column in sa.inspect(connection).get_columns(name)}:
            op.drop_column(name, "remark")
