"""Link purchase-order details to stable product archive identities.

Revision ID: 20260917_0071
Revises: 20260917_0070
Create Date: 2026-09-17
"""

from __future__ import annotations

from alembic import op

from domain.product_archive_identity_schema import ensure_product_archive_identity_schema


revision = "20260917_0071"
down_revision = "20260917_0070"
branch_labels = None
depends_on = None


def upgrade() -> None:
    ensure_product_archive_identity_schema(op.get_bind())


def downgrade() -> None:
    connection = op.get_bind()
    rows = connection.exec_driver_sql("""
        SELECT c.relname
        FROM pg_trigger AS trigger
        JOIN pg_class AS c ON c.oid = trigger.tgrelid
        WHERE trigger.tgname = 'trg_hede_product_identity_sync'
          AND NOT trigger.tgisinternal
    """).scalars()
    for table_name in rows:
        if str(table_name).replace("_", "").isalnum():
            connection.exec_driver_sql(
                f"DROP TRIGGER IF EXISTS trg_hede_product_identity_sync ON {table_name}"
            )
    op.execute("DROP TRIGGER IF EXISTS trg_hede_purchase_detail_product_link ON inventory_details")
    op.execute("DROP TRIGGER IF EXISTS trg_hede_inventory_record_product_links ON inventory_records")
    op.execute("DROP FUNCTION IF EXISTS hede_refresh_document_product_links()")
    op.execute("DROP FUNCTION IF EXISTS hede_link_purchase_order_detail_product()")
    op.execute("DROP FUNCTION IF EXISTS hede_sync_product_archive_identity()")
    op.execute("DROP FUNCTION IF EXISTS hede_replace_purchase_product_cache(json, text, text, text, text)")
    op.drop_constraint(
        "fk_inventory_details_product_identity",
        "inventory_details",
        type_="foreignkey",
    )
    op.drop_index("idx_inventory_details_product_identity", table_name="inventory_details")
    op.drop_column("inventory_details", "product_identity_id")
    op.drop_table("product_archive_identities")
