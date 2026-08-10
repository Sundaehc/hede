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


def test_fixed_barcode_rules_are_applied_by_brand():
    assert apply_product_defaults("cbanner_mens", {"sku": "C5562217D06"})["barcode_build_rule"] == "货号+颜色代码+尺码"
    assert apply_product_defaults("cbanner_womens", {"sku": "C5562217D06"})["barcode_build_rule"] == "货号+颜色代码+尺码"
    assert apply_product_defaults("eblan", {"sku": "E5562217D06"})["barcode_build_rule"] == "货号+颜色代码+尺码"
    assert apply_product_defaults("smiley", {"sku": "S5562217D06"})["barcode_build_rule"] == "货号+尺码"
    assert apply_product_defaults("ni", {"sku": "NIA2253A020115"})["barcode_build_rule"] == "货号+尺码"
