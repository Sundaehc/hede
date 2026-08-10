from domain.product_defaults import apply_product_defaults


def test_product_defaults_preserve_imported_barcode_build_rule():
    row = apply_product_defaults(
        "cbanner_mens",
        {"sku": "KT24Q3A030108", "barcode_build_rule": "货号+颜色代码+尺码"},
    )

    assert row["barcode_build_rule"] == "货号+颜色代码+尺码"


def test_product_defaults_set_cbanner_womens_group_name_only_when_blank():
    row = apply_product_defaults("cbanner_womens", {"group_name": ""})

    assert row["group_name"] == "女鞋"
