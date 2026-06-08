"""fill empty cbanner womens group name

Revision ID: 20260608_0020
Revises: 20260608_0019
Create Date: 2026-06-08 14:35:00
"""
from __future__ import annotations

from collections.abc import Sequence

from alembic import op


revision: str = "20260608_0020"
down_revision: str | None = "20260608_0019"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        UPDATE cbanner_womens_products
        SET group_name = '女鞋'
        WHERE group_name IS NULL
           OR btrim(group_name) = ''
        """
    )


def downgrade() -> None:
    pass
