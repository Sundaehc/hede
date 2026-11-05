"""Fill missing inbound and return prices when product archive costs change."""
from alembic import op

from domain.product_archive_identity_schema import _install_functions


revision = "20261105_0081"
down_revision = "20261103_0080"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Replace functions only: existing triggers retain their identities, and no
    # historical prices are overwritten or backfilled during deployment.
    _install_functions(op.get_bind())


def downgrade() -> None:
    """Retain compatible functions and prices already filled by the feature."""
