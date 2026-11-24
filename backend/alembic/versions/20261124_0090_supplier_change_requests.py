"""Store supplier change requests for product team review."""

from alembic import op

from domain.supplier_change_schema import SUPPLIER_CHANGE_TABLE

revision = "20261124_0090"
down_revision = "20261123_0089"
branch_labels = None
depends_on = None


def upgrade() -> None:
    SUPPLIER_CHANGE_TABLE.create(op.get_bind(), checkfirst=True)


def downgrade() -> None:
    SUPPLIER_CHANGE_TABLE.drop(op.get_bind(), checkfirst=True)
