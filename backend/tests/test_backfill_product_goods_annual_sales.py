from scripts.backfill_product_goods_annual_sales import BrandMatcher, _longest_prefix, _prefix_index


def test_longest_prefix_prefers_the_more_specific_product_code():
    index = _prefix_index(["A100", "A1001"])

    assert _longest_prefix("A1001-39", index) == "A1001"


def test_brand_matcher_uses_unique_style_code_when_product_code_is_unavailable():
    matcher = BrandMatcher(
        product_ids={"A100": 1},
        original_skus={"A100": "STYLE-1"},
        style_codes={"STYLE-1": "A100"},
        prefix_index=_prefix_index(["A100"]),
    )

    assert matcher.resolve("", "STYLE-1") == "A100"
