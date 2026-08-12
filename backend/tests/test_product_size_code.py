from domain.product_size_code import build_product_size_code
from storage.product_repository import _unique_color_codes


def test_build_product_size_code_matches_product_archive_export_rule():
    assert build_product_size_code("RCT63957D06", "06", "220", "货号+颜色代码+尺码") == "RCT63957D0606220"
    assert build_product_size_code("C2663367D01", "01", "38", "货号+颜色代码+尺码") == "C2663367D010138"
    assert build_product_size_code("RCT63957D06", "06", "220", "货号+尺码") == "RCT63957D06220"


def test_color_code_matching_accepts_optional_trailing_color_character():
    mapping = _unique_color_codes([
        {"color_name": "卡其", "color_barcode": "17"},
    ])

    assert mapping["卡其"] == "17"
    assert mapping["卡其色"] == "17"
