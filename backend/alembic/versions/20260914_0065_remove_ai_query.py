"""Remove the retired natural-language AI query feature."""

from __future__ import annotations

from alembic import op


revision = "20260914_0065"
down_revision = "20260913_0064"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("DROP TABLE IF EXISTS ai_query_history")
    op.execute(
        "DELETE FROM operation_logs WHERE module = 'ai_query'"
    )


def downgrade() -> None:
    raise RuntimeError(
        "The retired AI query feature and its history are not restored by downgrade."
    )
