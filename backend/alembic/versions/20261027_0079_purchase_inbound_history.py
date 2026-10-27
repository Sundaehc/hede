"""Add yearly partitioned purchase inbound history and age references."""

from pathlib import Path

from alembic import op
from sqlalchemy import text


revision = "20261027_0079"
down_revision = "20261020_0078"
branch_labels = None
depends_on = None


def upgrade() -> None:
    path = Path(__file__).resolve().parents[3] / "database" / "purchase-inbound-history-2026-10-27.sql"
    op.get_bind().execute(text("SET LOCAL lock_timeout = '5s'"))
    op.get_bind().execute(text(path.read_text(encoding="utf-8")))


def downgrade() -> None:
    raise RuntimeError("采购入库历史包含来源凭证，禁止自动删除；请先备份并审核回退方案")
