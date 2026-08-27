from api.routes.color_barcodes import _build_color_export_workbook


def test_color_export_contains_only_color_and_code_columns():
    workbook = _build_color_export_workbook(
        [
            {"color_name": "黑色", "color_barcode": "01", "brand": "cbanner_mens"},
            {"color_name": "白色", "color_barcode": "02", "brand": "cbanner_mens"},
        ]
    )

    rows = list(workbook.active.values)

    assert rows == [
        ("颜色", "颜色代码"),
        ("黑色", "01"),
        ("白色", "02"),
    ]
