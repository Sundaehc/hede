from domain.product_size_code import build_product_size_code


def test_build_product_size_code_matches_product_archive_export_rule():
    assert build_product_size_code("RCT63957D06", "06", "220", "货号+颜色代码+尺码") == "RCT63957D0606220"
    assert build_product_size_code("RCT63957D06", "06", "220", "货号+尺码") == "RCT63957D06220"
