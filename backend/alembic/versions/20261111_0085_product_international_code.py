"""Add optional international codes to every configured product archive."""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

from domain.product_archive_naming import manual_product_table_name


revision = "20261111_0085"
down_revision = "20261110_0084"
branch_labels = None
depends_on = None


STATIC_ARCHIVES = (
    "cbanner_mens_products", "cbanner_womens_products", "yandou_products",
    "eblan_products", "smiley_products", "ni_products",
)


def _archives(connection):
    existing = set(sa.inspect(connection).get_table_names())
    names = set(STATIC_ARCHIVES)
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
        if "international_code" not in {column["name"] for column in sa.inspect(connection).get_columns(name)}:
            op.add_column(name, sa.Column("international_code", sa.Text(), nullable=True))


def downgrade() -> None:
    connection = op.get_bind()
    for name in _archives(connection):
        if "international_code" in {column["name"] for column in sa.inspect(connection).get_columns(name)}:
            op.drop_column(name, "international_code")
