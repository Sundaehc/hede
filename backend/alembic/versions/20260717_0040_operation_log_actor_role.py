"""store operation log actor roles

Revision ID: 20260717_0040
Revises: 20260713_0039
Create Date: 2026-07-17
"""

from __future__ import annotations

from alembic import op


revision = "20260717_0040"
down_revision = "20260713_0039"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE IF EXISTS operation_logs ADD COLUMN IF NOT EXISTS role_code TEXT")
    op.execute(
        """
        UPDATE operation_logs AS log
        SET role_code = user_record.role_code
        FROM auth_users AS user_record
        WHERE log.user_id = user_record.id
          AND log.role_code IS NULL
        """
    )


def downgrade() -> None:
    op.execute("ALTER TABLE IF EXISTS operation_logs DROP COLUMN IF EXISTS role_code")
