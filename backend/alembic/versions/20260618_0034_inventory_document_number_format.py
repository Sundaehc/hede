"""format inventory document numbers by type and date

Revision ID: 20260618_0034
Revises: 20260618_0033
Create Date: 2026-06-18
"""

from __future__ import annotations

from alembic import op


revision = "20260618_0034"
down_revision = "20260618_0033"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        WITH numbered AS (
            SELECT
                id,
                CASE document_type
                    WHEN '进货单' THEN 'JHD'
                    WHEN '进货退货单' THEN 'JHTHD'
                    WHEN '报溢单' THEN 'BYD'
                    WHEN '报损单' THEN 'BSD'
                    WHEN '批发销售单' THEN 'PFXSD'
                    WHEN '批发销售退货单' THEN 'PFXSTHD'
                    WHEN '同价调拨单' THEN 'TJDBD'
                    ELSE 'DJ'
                END AS prefix,
                to_char(
                    coalesce(
                        date_value,
                        nullif(date, '')::date,
                        created_at::date,
                        current_date
                    ),
                    'YYYY-MM-DD'
                ) AS doc_date,
                row_number() OVER (
                    PARTITION BY
                        CASE document_type
                            WHEN '进货单' THEN 'JHD'
                            WHEN '进货退货单' THEN 'JHTHD'
                            WHEN '报溢单' THEN 'BYD'
                            WHEN '报损单' THEN 'BSD'
                            WHEN '批发销售单' THEN 'PFXSD'
                            WHEN '批发销售退货单' THEN 'PFXSTHD'
                            WHEN '同价调拨单' THEN 'TJDBD'
                            ELSE 'DJ'
                        END,
                        coalesce(date_value, nullif(date, '')::date, created_at::date, current_date)
                    ORDER BY id
                ) AS seq
            FROM inventory_records
        )
        UPDATE inventory_records AS r
        SET document_number = numbered.prefix || '-' || numbered.doc_date || '-' || lpad(numbered.seq::text, 4, '0')
        FROM numbered
        WHERE numbered.id = r.id
        """
    )


def downgrade() -> None:
    pass
