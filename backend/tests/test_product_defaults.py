from domain.product_defaults import apply_product_defaults


def test_product_defaults_override_kt_barcode_build_rule_with_fixed_rule():
    row = apply_product_defaults(
        "cbanner_mens",
        {"sku": "KT24Q3A030108", "barcode_build_rule": "货号+颜色代码+尺码"},
    )

    assert row["barcode_build_rule"] == "货号+尺码"


def test_product_defaults_set_cbanner_womens_group_name_only_when_blank():
    row = apply_product_defaults("cbanner_womens", {"group_name": ""})

    assert row["group_name"] == "女鞋"


def test_product_defaults_set_fixed_barcode_rules_for_product_brands():
    for brand in ("cbanner_mens", "cbanner_womens", "eblan"):
        row = apply_product_defaults(brand, {"sku": "A1001"})
        assert row["barcode_build_rule"] == "货号+颜色代码+尺码"

    for brand in ("smiley", "ni"):
        row = apply_product_defaults(brand, {"sku": "A1001"})
        assert row["barcode_build_rule"] == "货号+尺码"

    row = apply_product_defaults("cbanner_mens", {"sku": "KT-Q15036A2"})
    assert row["barcode_build_rule"] == "货号+尺码"
