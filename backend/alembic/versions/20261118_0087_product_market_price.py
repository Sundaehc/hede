"""Add optional market prices to Smiley and NI product archives."""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20261118_0087"
down_revision = "20261116_0086"
branch_labels = None
depends_on = None

ARCHIVES = ("smiley_products", "ni_products")


def upgrade() -> None:
    connection = op.get_bind()
    existing = set(sa.inspect(connection).get_table_names())
    for name in ARCHIVES:
        if name in existing and "market_price" not in {
            column["name"] for column in sa.inspect(connection).get_columns(name)
        }:
            op.add_column(name, sa.Column("market_price", sa.Numeric(10, 2), nullable=True))


def downgrade() -> None:
    connection = op.get_bind()
    existing = set(sa.inspect(connection).get_table_names())
    for name in ARCHIVES:
        if name in existing and "market_price" in {
            column["name"] for column in sa.inspect(connection).get_columns(name)
        }:
            op.drop_column(name, "market_price")
