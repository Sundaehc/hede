"""Remove the retired master-data and product-code mapping layer."""

from __future__ import annotations

from alembic import op


revision = "20260915_0067"
down_revision = "20260914_0066"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Drop dependent compatibility views before their source tables.
    op.execute("DROP VIEW IF EXISTS v_master_data_aliases")
    op.execute("DROP VIEW IF EXISTS v_product_code_mappings")
    op.execute("DROP TABLE IF EXISTS master_data_aliases")
    op.execute("DROP TABLE IF EXISTS master_data_entities")
    op.execute("DROP TABLE IF EXISTS product_code_mappings")


def downgrade() -> None:
    raise RuntimeError(
        "The retired master-data layer was intentionally removed and is not restored by downgrade."
    )
