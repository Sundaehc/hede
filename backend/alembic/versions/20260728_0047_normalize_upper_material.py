"""Normalize composite upper-material labels."""

from alembic import op


revision = "20260728_0047"
down_revision = "20260728_0046"
branch_labels = None
depends_on = None


def _normalize(table_name: str) -> None:
    op.execute(
        f"""
        UPDATE {table_name}
        SET upper_material = replace(
            replace(
                replace(upper_material, '复合材料-2', '上层合成革/下层羊剖层革'),
                '复合材料-1', '上层合成革/下层牛剖层革'
            ),
            '复合材料-', '上层合成革/下层牛剖层革'
        )
        WHERE upper_material LIKE '%复合材料-%'
        """
    )


def upgrade() -> None:
    for table_name in (
        "cbanner_mens_products",
        "cbanner_womens_products",
        "yandou_products",
        "eblan_products",
        "gj_merged_product_info",
    ):
        _normalize(table_name)


def downgrade() -> None:
    pass
