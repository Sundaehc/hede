"""Persist background inventory template import results."""

from alembic import op

from domain.inventory_import_task_schema import INVENTORY_IMPORT_TASK_TABLE


revision = "20261016_0077"
down_revision = "20261009_0076"
branch_labels = None
depends_on = None


def upgrade() -> None:
    INVENTORY_IMPORT_TASK_TABLE.create(op.get_bind(), checkfirst=True)


def downgrade() -> None:
    INVENTORY_IMPORT_TASK_TABLE.drop(op.get_bind(), checkfirst=True)

