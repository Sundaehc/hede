from domain.product_size_code import build_product_size_code


def test_build_product_size_code_matches_product_archive_export_rule():
    assert build_product_size_code("RCT63957D06", "06", "220", "货号+颜色代码+尺码") == "RCT63957D0606220"
    assert build_product_size_code("RCT63957D06", "06", "220", "货号+尺码") == "RCT63957D06220"


def test_build_product_size_code_enforces_fixed_brand_rules():
    assert build_product_size_code(
        "RCT63957D06",
        "06",
        "220",
        "货号+尺码",
        brand="cbanner_womens",
    ) == "RCT63957D0606220"
    assert build_product_size_code(
        "NIA2253A020115",
        "01",
        "35",
        "货号+颜色代码+尺码",
        brand="ni",
    ) == "NIA2253A02011535"
    assert build_product_size_code(
        "KT24Q3A030108",
        "08",
        "260",
        "货号+颜色代码+尺码",
    ) == "KT24Q3A030108260"
