"""Create the independently revocable product image credential table."""
from __future__ import annotations

from alembic import op

from domain.auth_schema import PRODUCT_IMAGE_TOKEN_TABLE


revision = "20261121_0088"
down_revision = "20261118_0087"
branch_labels = None
depends_on = None


def upgrade() -> None:
    PRODUCT_IMAGE_TOKEN_TABLE.create(op.get_bind(), checkfirst=True)


def downgrade() -> None:
    PRODUCT_IMAGE_TOKEN_TABLE.drop(op.get_bind(), checkfirst=True)
