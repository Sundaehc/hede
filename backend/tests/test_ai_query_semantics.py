import pytest

from domain.ai_query_semantics import (
    SemanticQueryError,
    is_semantic_source_exposed,
    referenced_table_names,
    validate_semantic_query,
)


@pytest.mark.parametrize(
    "raw_table",
    [
        "jst_daily_sales",
        "jst_daily_sales_2026",
        "vip_daily_sales_2026",
        "product_goods_historical_sales_2025",
        "fine_table_snapshot_metrics",
        "vip_product_daily",
    ],
)
def test_raw_or_duplicate_sources_are_hidden_from_ai(raw_table: str):
    assert is_semantic_source_exposed(raw_table) is False


@pytest.mark.parametrize(
    "view_name",
    [
        "v_jst_daily_sales",
        "v_vip_daily_sales",
        "v_product_goods_historical_sales",
        "v_fine_table_snapshot_rows",
        "v_vip_product_daily_normalized",
    ],
)
def test_canonical_views_are_exposed_to_ai(view_name: str):
    assert is_semantic_source_exposed(view_name) is True


def test_product_archive_query_requires_active_rows():
    with pytest.raises(SemanticQueryError):
        validate_semantic_query(
            "查询千百度女鞋商品",
            "SELECT sku FROM cbanner_womens_products",
        )

    tables = validate_semantic_query(
        "查询千百度女鞋商品",
        "SELECT sku FROM cbanner_womens_products WHERE deleted_at IS NULL",
    )
    assert tables == {"cbanner_womens_products"}


def test_jst_sales_uses_net_quantity_and_channel_mapping():
    with pytest.raises(SemanticQueryError):
        validate_semantic_query(
            "查询各平台销量",
            "SELECT channel, SUM(sales_quantity) FROM v_jst_daily_sales GROUP BY channel",
        )

    sql = """
        SELECT COALESCE(mapping.channel, sales.channel) AS platform,
               SUM(sales.net_sales_quantity) AS sales_quantity
        FROM v_jst_daily_sales AS sales
        LEFT JOIN product_goods_shop_channel_mappings AS mapping
          ON mapping.brand = 'cbanner_womens' AND mapping.shop_name = sales.channel
        GROUP BY COALESCE(mapping.channel, sales.channel)
    """
    assert validate_semantic_query("查询千百度女鞋各平台销量", sql) == {
        "v_jst_daily_sales",
        "product_goods_shop_channel_mappings",
    }


def test_combined_jst_and_vip_sales_requires_mapping_and_vip_deduplication():
    without_mapping = """
        SELECT SUM(net_sales_quantity) FROM v_jst_daily_sales
        UNION ALL
        SELECT SUM(sales_quantity) FROM v_vip_daily_sales
    """
    with pytest.raises(SemanticQueryError, match="渠道映射"):
        validate_semantic_query("查询近7天销量", without_mapping)

    without_deduplication = """
        SELECT SUM(sales.net_sales_quantity)
        FROM v_jst_daily_sales AS sales
        LEFT JOIN product_goods_shop_channel_mappings AS mapping
          ON mapping.brand = sales.brand AND mapping.shop_name = sales.channel
        UNION ALL
        SELECT SUM(sales_quantity) FROM v_vip_daily_sales
    """
    with pytest.raises(SemanticQueryError, match="重复唯品"):
        validate_semantic_query("查询近7天销量", without_deduplication)

    valid_sql = """
        SELECT SUM(sales.net_sales_quantity)
        FROM v_jst_daily_sales AS sales
        LEFT JOIN product_goods_shop_channel_mappings AS mapping
          ON mapping.brand = sales.brand AND mapping.shop_name = sales.channel
        WHERE NOT EXISTS (
            SELECT 1
            FROM v_vip_daily_sales AS vip
            WHERE COALESCE(mapping.channel, sales.channel, '') ILIKE '%唯品%'
              AND vip.sales_date = sales.sales_date
              AND vip.goods_code LIKE sales.product_code || '%'
        )
        UNION ALL
        SELECT SUM(sales_quantity) FROM v_vip_daily_sales
    """
    assert validate_semantic_query("查询近7天销量", valid_sql) == {
        "v_jst_daily_sales",
        "v_vip_daily_sales",
        "product_goods_shop_channel_mappings",
    }

    equivalent_negated_exists_sql = """
        SELECT SUM(sales.net_sales_quantity)
        FROM v_jst_daily_sales AS sales
        LEFT JOIN product_goods_shop_channel_mappings AS mapping
          ON mapping.brand = 'cbanner_womens' AND mapping.shop_name = sales.channel
        WHERE NOT (
            COALESCE(mapping.channel, sales.channel, '') = '唯品'
            AND EXISTS (
                SELECT 1 FROM v_vip_daily_sales AS vip
                WHERE vip.sales_date = sales.sales_date
                  AND vip.goods_code LIKE sales.product_code || '%'
            )
        )
        UNION ALL
        SELECT SUM(sales_quantity) FROM v_vip_daily_sales
    """
    assert validate_semantic_query(
        "查询千百度女鞋近7天销量", equivalent_negated_exists_sql
    ) == {
        "v_jst_daily_sales",
        "v_vip_daily_sales",
        "product_goods_shop_channel_mappings",
    }


def test_brand_mapping_uses_internal_brand_code():
    invalid_sql = """
        SELECT SUM(sales.net_sales_quantity)
        FROM v_jst_daily_sales AS sales
        LEFT JOIN product_goods_shop_channel_mappings AS mapping
          ON mapping.brand = '千百度女鞋' AND mapping.shop_name = sales.channel
    """
    with pytest.raises(SemanticQueryError, match="cbanner_womens"):
        validate_semantic_query("查询千百度女鞋各平台销量", invalid_sql)


def test_source_product_codes_use_prefix_matching_for_base_sku():
    exact_sql = """
        SELECT SUM(actual_stock_qty)
        FROM jst_full_stock
        WHERE sync_date = (SELECT MAX(sync_date) FROM jst_full_stock)
          AND product_code = 'QC153883D54'
    """
    with pytest.raises(SemanticQueryError, match="前缀匹配"):
        validate_semantic_query("查询 QC153883D54 当前库存", exact_sql)

    prefix_sql = """
        SELECT SUM(COALESCE(actual_stock_qty, 0) + COALESCE(purchase_warehouse_stock_qty, 0))
        FROM jst_full_stock
        WHERE sync_date = (SELECT MAX(sync_date) FROM jst_full_stock)
          AND product_code LIKE 'QC153883D54' || '%'
    """
    assert validate_semantic_query("查询 QC153883D54 当前库存", prefix_sql) == {
        "jst_full_stock"
    }


def test_inventory_components_require_null_safe_business_formula():
    sql = """
        SELECT SUM(actual_stock_qty + purchase_warehouse_stock_qty)
        FROM jst_full_stock
        WHERE sync_date = (SELECT MAX(sync_date) FROM jst_full_stock)
    """
    with pytest.raises(SemanticQueryError, match="COALESCE"):
        validate_semantic_query("查询当前在仓库存", sql)


def test_precomputed_and_daily_sales_cannot_be_added_together():
    sql = """
        SELECT SUM(period.sales_quantity) + SUM(daily.net_sales_quantity)
        FROM product_goods_sales_periods AS period
        CROSS JOIN v_jst_daily_sales AS daily
    """
    with pytest.raises(SemanticQueryError):
        validate_semantic_query("查询本月销量", sql)


def test_current_full_stock_requires_latest_sync_date():
    with pytest.raises(SemanticQueryError):
        validate_semantic_query(
            "查询当前库存",
            "SELECT product_code, SUM(actual_stock_qty) FROM jst_full_stock GROUP BY product_code",
        )

    sql = """
        SELECT product_code, SUM(actual_stock_qty) AS stock_quantity
        FROM jst_full_stock
        WHERE sync_date = (SELECT MAX(sync_date) FROM jst_full_stock)
        GROUP BY product_code
    """
    assert validate_semantic_query("查询当前库存", sql) == {"jst_full_stock"}


def test_fine_table_history_requires_brand_and_snapshot_date():
    with pytest.raises(SemanticQueryError):
        validate_semantic_query(
            "查询历史精细表",
            "SELECT payload FROM v_fine_table_snapshot_rows",
        )

    sql = """
        SELECT payload
        FROM v_fine_table_snapshot_rows
        WHERE brand = 'cbanner_womens' AND snapshot_date = DATE '2026-08-15'
    """
    assert validate_semantic_query("查询历史精细表", sql) == {
        "v_fine_table_snapshot_rows"
    }


def test_referenced_tables_ignore_cte_aliases():
    sql = "WITH sales AS (SELECT * FROM v_jst_daily_sales) SELECT * FROM sales"
    assert referenced_table_names(sql) == {"v_jst_daily_sales"}
