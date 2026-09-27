"""Add structured product tag definitions and assignments."""

from __future__ import annotations

from alembic import op
from domain.product_tag_schema import (
    PRODUCT_STYLE_ENTITIES_TABLE,
    PRODUCT_TAG_ASSIGNMENTS_TABLE,
    PRODUCT_TAG_DEFINITIONS_TABLE,
)


revision = "20260927_0073"
down_revision = "20260918_0072"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    PRODUCT_TAG_DEFINITIONS_TABLE.create(bind, checkfirst=True)
    PRODUCT_STYLE_ENTITIES_TABLE.create(bind, checkfirst=True)
    PRODUCT_TAG_ASSIGNMENTS_TABLE.create(bind, checkfirst=True)


def downgrade() -> None:
    bind = op.get_bind()
    PRODUCT_TAG_ASSIGNMENTS_TABLE.drop(bind, checkfirst=True)
    PRODUCT_STYLE_ENTITIES_TABLE.drop(bind, checkfirst=True)
    PRODUCT_TAG_DEFINITIONS_TABLE.drop(bind, checkfirst=True)
