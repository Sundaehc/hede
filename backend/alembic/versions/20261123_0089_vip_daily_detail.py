"""Add returns, available stock and prices to VIP daily sales."""

from alembic import op

from domain.vip_daily_detail import migrate_vip_daily_detail


revision = "20261123_0089"
down_revision = "20261121_0088"
branch_labels = None
depends_on = None


def upgrade() -> None:
    migrate_vip_daily_detail(op.get_bind())


def downgrade() -> None:
    migrate_vip_daily_detail(op.get_bind(), drop=True)
