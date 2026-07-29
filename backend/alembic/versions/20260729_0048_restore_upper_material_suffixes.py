"""Restore composite upper-material suffixes from source payloads."""

from alembic import op


revision = "20260729_0048"
down_revision = "20260728_0047"
branch_labels = None
depends_on = None


def _normalized(expression: str) -> str:
    return f"""
        replace(
            replace(
                replace({expression}, '复合材料-2', '上层合成革/下层羊剖层革'),
                '复合材料-1', '上层合成革/下层牛剖层革'
            ),
            '复合材料-', '上层合成革/下层牛剖层革'
        )
    """


def _restore_product_table(table_name: str) -> None:
    source_material = "COALESCE(g.raw_payload ->> '鞋面材质', g.raw_payload ->> '帮面材质')"
    op.execute(
        f"""
        WITH matched AS (
            SELECT DISTINCT ON (product.id)
                product.id,
                {_normalized(source_material)} AS upper_material
            FROM {table_name} AS product
            JOIN gj_merged_product_info AS g
              ON g.goods_code IN (product.sku, product.original_sku)
              OR g.original_goods_code IN (product.sku, product.original_sku)
            WHERE {source_material} LIKE '%复合材料-%'
            ORDER BY product.id, g.source_date_value DESC NULLS LAST, g.updated_at DESC, g.id DESC
        )
        UPDATE {table_name} AS product
        SET upper_material = matched.upper_material
        FROM matched
        WHERE product.id = matched.id
        """
    )


def upgrade() -> None:
    source_material = "COALESCE(raw_payload ->> '鞋面材质', raw_payload ->> '帮面材质')"
    op.execute(
        f"""
        UPDATE gj_merged_product_info
        SET upper_material = {_normalized(source_material)}
        WHERE {source_material} LIKE '%复合材料-%'
        """
    )
    for table_name in (
        "cbanner_mens_products",
        "cbanner_womens_products",
        "yandou_products",
        "eblan_products",
    ):
        _restore_product_table(table_name)
    op.execute(
        f"""
        UPDATE smiley_fine_table
        SET upper_material = {_normalized(source_material)}
        WHERE {source_material} LIKE '%复合材料-%'
        """
    )


def downgrade() -> None:
    pass
