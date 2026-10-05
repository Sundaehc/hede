from domain.product_defaults import SMILEY_DEFAULT_SIZE_RANGE, apply_product_defaults, smiley_color_code


def test_product_defaults_override_kt_barcode_build_rule_with_fixed_rule():
    row = apply_product_defaults(
        "cbanner_mens",
        {"sku": "KT24Q3A030108", "barcode_build_rule": "货号+颜色代码+尺码"},
    )

    assert row["barcode_build_rule"] == "货号+尺码"


def test_product_defaults_set_cbanner_womens_group_name_only_when_blank():
    row = apply_product_defaults("cbanner_womens", {"group_name": ""})

    assert row["group_name"] == "女鞋"


def test_smiley_defaults_missing_size_range_without_overwriting_existing_group():
    assert apply_product_defaults("smiley", {"sku": "XL1234001", "size_range": " "})["size_range"] == SMILEY_DEFAULT_SIZE_RANGE
    assert apply_product_defaults("smiley", {"sku": "XL1234001", "size_range": "笑脸男鞋38-44"})["size_range"] == "笑脸男鞋38-44"
    assert "size_range" not in apply_product_defaults("ni", {"sku": "NI1234001"})


def test_smiley_color_code_uses_product_sku_suffix():
    assert smiley_color_code("  XL2026AB12  ") == "AB12"
    assert smiley_color_code("123") == "123"
    assert smiley_color_code(None) == ""


def test_product_defaults_set_fixed_barcode_rules_for_product_brands():
    for brand in ("cbanner_mens", "cbanner_womens", "eblan"):
        row = apply_product_defaults(brand, {"sku": "A1001"})
        assert row["barcode_build_rule"] == "货号+颜色代码+尺码"

    for brand in ("smiley", "ni"):
        row = apply_product_defaults(brand, {"sku": "A1001"})
        assert row["barcode_build_rule"] == "货号+尺码"

    row = apply_product_defaults("cbanner_mens", {"sku": "KT-Q15036A2"})
    assert row["barcode_build_rule"] == "货号+尺码"
