"""normalize inventory document types

Revision ID: 20260616_0028
Revises: 20260616_0027
Create Date: 2026-06-16
"""

from __future__ import annotations

from alembic import op


revision: str = "20260616_0028"
down_revision: str | None = "20260616_0027"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.execute(
        """
        UPDATE inventory_records
        SET document_type = CASE document_type
            WHEN '工厂进货单' THEN '进货单'
            WHEN '工厂退货单' THEN '进货退货单'
            ELSE document_type
        END
        WHERE document_type IN ('工厂进货单', '工厂退货单')
        """
    )


def downgrade() -> None:
    op.execute(
        """
        UPDATE inventory_records
        SET document_type = CASE document_type
            WHEN '进货单' THEN '工厂进货单'
            WHEN '进货退货单' THEN '工厂退货单'
            ELSE document_type
        END
        WHERE document_type IN ('进货单', '进货退货单')
        """
    )
