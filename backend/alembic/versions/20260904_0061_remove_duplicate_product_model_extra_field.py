"""Remove product-model values duplicated in product archive extra fields."""

from alembic import op


revision = "20260904_0061"
down_revision = "20260827_0060"
branch_labels = None
depends_on = None


PRODUCT_ARCHIVE_TABLES = (
    "cbanner_mens_products",
    "cbanner_womens_products",
    "yandou_products",
    "eblan_products",
    "smiley_products",
    "ni_products",
)


def upgrade() -> None:
    for table_name in PRODUCT_ARCHIVE_TABLES:
        op.execute(
            f"""
            UPDATE {table_name}
            SET extra_fields = CASE
                WHEN (extra_fields::jsonb - U&'\\4EA7\\54C1\\578B\\53F7') = '{{}}'::jsonb
                    THEN NULL
                ELSE ((extra_fields::jsonb - U&'\\4EA7\\578B\\53F7')::json)
            END
            WHERE extra_fields IS NOT NULL
              AND jsonb_typeof(extra_fields::jsonb) = 'object'
              AND extra_fields::jsonb ? U&'\\4EA7\\54C1\\578B\\53F7'
            """
        )


def downgrade() -> None:
    # The removed value is already present in the formal product_model column;
    # restoring a duplicate JSON key would reintroduce the ambiguity.
    pass
