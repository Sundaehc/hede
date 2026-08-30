from scripts.export_fine_table_daily import _columns_for_rows


def test_columns_for_rows_uses_chinese_labels_for_product_fields() -> None:
    expected_labels = {
        "platform": "所属平台",
        "boot_shaft": "靴筒",
        "sole_style": "跟底款式",
        "opening_depth": "开口深度",
        "shoe_box_type": "鞋盒类型",
        "selling_points": "卖点",
        "mesh_upper_type": "鞋网面类型",
        "fashion_elements": "流行元素",
        "barcode_build_rule": "条码构成逻辑",
        "category": "分类",
        "last_imported_at": "最近导入时间",
        "deleted_at": "删除时间",
    }
    columns = _columns_for_rows([{**dict.fromkeys(expected_labels), "future_field": "value"}])
    labels_by_key = dict(columns)

    for key, label in expected_labels.items():
        assert labels_by_key[key] == label
        assert key not in labels_by_key.values()

    assert labels_by_key["future_field"] == "future_field"
