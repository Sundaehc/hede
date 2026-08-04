from storage.product_repository import _unique_color_codes


def test_unique_color_codes_keeps_only_unambiguous_color_names():
    result = _unique_color_codes([
        {"color_name": "黑色", "color_barcode": "01"},
        {"color_name": "白色", "color_barcode": "02"},
        {"color_name": "白色", "color_barcode": "03"},
        {"color_name": "", "color_barcode": "04"},
    ])

    assert result == {"黑色": "01"}
