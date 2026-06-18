"""add inventory document number

Revision ID: 20260617_0031
Revises: 20260617_0030
Create Date: 2026-06-17
"""

from __future__ import annotations

from alembic import op


revision = "20260617_0031"
down_revision = "20260617_0030"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE IF EXISTS inventory_records ADD COLUMN IF NOT EXISTS document_number TEXT")
    op.execute(
        """
        UPDATE inventory_records
        SET document_number =
            upper(substr(md5(random()::text || id::text), 1, 5))
            || '-' ||
            to_char(
                coalesce(
                    date_value,
                    case
                        when date ~ '^\\d{4}-\\d{1,2}-\\d{1,2}$' then date::date
                        else current_date
                    end
                ),
                'YYYY-MM-DD'
            )
            || '-' ||
            lpad(floor(random() * 10000)::int::text, 4, '0')
        WHERE document_number IS NULL OR document_number = ''
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_inventory_records_document_number "
        "ON inventory_records (document_number)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_inventory_records_document_number")
    op.execute("ALTER TABLE IF EXISTS inventory_records DROP COLUMN IF EXISTS document_number")
