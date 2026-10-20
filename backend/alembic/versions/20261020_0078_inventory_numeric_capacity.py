"""Expand inventory quantity and monetary fields without rounding existing data."""

from pathlib import Path

from alembic import op
from sqlalchemy import text


revision = "20261020_0078"
down_revision = "20261016_0077"
branch_labels = None
depends_on = None


def upgrade() -> None:
    path = Path(__file__).resolve().parents[3] / "database" / "inventory-numeric-capacity-2026-10-20.sql"
    op.get_bind().execute(text("SET LOCAL statement_timeout = '30s'"))
    op.get_bind().execute(text(path.read_text(encoding="utf-8")))


def downgrade() -> None:
    raise RuntimeError("不能自动缩小经营历程数值范围，请先核对全部数据并制定回退方案")
