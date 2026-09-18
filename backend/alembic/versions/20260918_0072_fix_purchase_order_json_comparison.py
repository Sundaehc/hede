"""Fix JSON comparison when editing purchase-order headers.

Revision ID: 20260918_0072
Revises: 20260917_0071
Create Date: 2026-09-18
"""

from __future__ import annotations

from alembic import op

from domain.product_archive_identity_schema import install_document_product_link_function


revision = "20260918_0072"
down_revision = "20260917_0071"
branch_labels = None
depends_on = None


def upgrade() -> None:
    install_document_product_link_function(op.get_bind())


def downgrade() -> None:
    """Keep the compatible comparison until the identity feature is removed."""
