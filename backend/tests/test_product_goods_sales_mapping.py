from api.routes.product_goods import _full_stock_size, _historical_order_targets, _is_clearance_channel, _platform_name, _resolve_jst_product_code, _stock_health_label
from domain.product_goods_historical_sales_schema import product_goods_historical_sales_table_for_year


def test_jst_sales_code_maps_to_the_longest_matching_goods_code():
    matched = _resolve_jst_product_code(
        "C0152140L0101250",
        "C0152140L01",
        ["C0152140L01", "C0152140L0101"],
        {"C0152140L01": "C0152140L01"},
    )

    assert matched == "C0152140L0101"


def test_size_suffixed_sales_code_maps_to_base_goods_code():
    assert _resolve_jst_product_code(
        "Q9941832W5252235",
        "Q9941832W52",
        ["Q9941832W52"],
        {"Q9941832W52": "Q9941832W52"},
    ) == "Q9941832W52"


def test_jst_sales_code_uses_style_only_when_it_is_unique():
    assert _resolve_jst_product_code("unmatched", "STYLE-1", ["SKU-1"], {"STYLE-1": "SKU-1"}) == "SKU-1"
    assert _resolve_jst_product_code("unmatched", "STYLE-1", ["SKU-1", "SKU-2"], {}) is None


def test_full_stock_size_only_maps_unambiguous_sizes():
    assert _full_stock_size("220") == "34"
    assert _full_stock_size("250.0") == "40"
    assert _full_stock_size("44") == "44"
    assert _full_stock_size("235-240") is None


def test_stock_health_uses_source_sale_days_and_shortage():
    assert _stock_health_label(None, 2) == "缺货"
    assert _stock_health_label(5, 0) == "低库存"
    assert _stock_health_label(30, 0) == "正常"
    assert _stock_health_label(90, 0) == "积压风险"


def test_shop_channel_mapping_takes_priority_over_keyword_matching():
    mappings = {"千百度女鞋-视频号女鞋旗舰店": "直播赛道"}
    assert _platform_name("千百度女鞋-视频号女鞋旗舰店", mappings) == "直播赛道"
    assert _platform_name("千百度女鞋-天猫旗舰店", mappings) == "天猫"


def test_clearance_channel_uses_the_raw_channel_name_and_clearance_platforms():
    assert _is_clearance_channel("千百度女鞋-天猫清仓店", "天猫") is True
    assert _is_clearance_channel("常规店铺", "拼多多清仓") is True
    assert _is_clearance_channel("千百度女鞋-天猫旗舰店", "天猫") is False


def test_historical_order_for_an_original_sku_applies_to_all_its_color_goods():
    assert _historical_order_targets(
        "STYLE-1",
        ["STYLE-1A", "STYLE-1B"],
        {"STYLE-1": ["STYLE-1A", "STYLE-1B"]},
    ) == ["STYLE-1A", "STYLE-1B"]


def test_historical_order_with_a_full_goods_code_prefers_that_goods_code():
    assert _historical_order_targets(
        "STYLE-1A230",
        ["STYLE-1A", "STYLE-1B"],
        {"STYLE-1": ["STYLE-1A", "STYLE-1B"]},
    ) == ["STYLE-1A"]


def test_historical_sales_source_rows_are_immutable():
    table = product_goods_historical_sales_table_for_year(2024)
    assert table.name == "product_goods_historical_sales_2024"
    assert {"brand", "source_workbook", "source_sheet", "source_row_number"} <= set(table.c.keys())
    assert any(
        constraint.name == "uq_product_goods_historical_sales_2024_source_row"
        for constraint in table.constraints
    )
    assert any(index.name == "idx_product_goods_historical_sales_2024_brand_product" for index in table.indexes)
