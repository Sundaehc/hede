from domain.product_defaults import apply_product_defaults


def test_kt_sku_uses_sku_and_size_barcode_rule():
    row = apply_product_defaults(
        "cbanner_mens",
        {"sku": "KT24Q3A030108", "barcode_build_rule": "货号+颜色代码+尺码"},
    )

    assert row["barcode_build_rule"] == "货号+尺码"


def test_original_kt_sku_uses_sku_and_size_barcode_rule():
    row = apply_product_defaults(
        "cbanner_womens",
        {"sku": "A001", "original_sku": "kt24q3a030108"},
    )

    assert row["barcode_build_rule"] == "货号+尺码"
