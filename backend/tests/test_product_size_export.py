from api.routes.import_export import (
    EXPORT_LABELS,
    _export_columns_for_brand,
    _export_label,
    _size_export_fallback_profiles,
    _size_export_product_name,
    _size_export_profiles_from_size_groups,
)


def test_product_export_headers_use_field_labels():
    assert EXPORT_LABELS["shoe_box_type"] == "鞋盒类型"
    assert EXPORT_LABELS["selling_points"] == "卖点"
    assert EXPORT_LABELS["barcode_build_rule"] == "条码构成逻辑"


def test_cbanner_womens_export_includes_style_fields_and_brand_labels():
    columns = _export_columns_for_brand("cbanner_womens")

    assert "sole_style" in columns
    assert "fashion_elements" in columns
    assert "opening_depth" in columns
    assert "boot_shaft" in columns
    assert "mesh_upper_type" in columns
    assert _export_label("heel_height", "cbanner_womens") == "后跟高"
    assert _export_label("upper_height", "cbanner_womens") == "鞋帮高度"


def test_other_brand_exports_omit_cbanner_womens_only_fields():
    columns = _export_columns_for_brand("cbanner_mens")

    assert "sole_style" not in columns
    assert "fashion_elements" not in columns
    assert "opening_depth" not in columns
    assert "boot_shaft" not in columns
    assert "mesh_upper_type" not in columns


def test_size_export_uses_archive_fallback_when_profile_is_missing():
    profiles = [
        {
            "id": 1,
            "product_code": "MATCH-34",
            "style_code": "MATCH",
            "size_barcode": "34",
        }
    ]
    source_items = [
        {"id": 10, "sku": "MATCH", "original_sku": "MATCH", "color": "黑色", "raw_payload": {}},
        {"id": 11, "sku": "MISSING", "original_sku": "MISSING", "color": "白色", "raw_payload": {}},
    ]

    fallback_profiles = _size_export_fallback_profiles(source_items, profiles)

    assert fallback_profiles == [
        {
            "id": "archive-11",
            "product_code": "MISSING",
            "style_code": "MISSING",
            "color_name": "白色",
            "size_barcode": "",
            "raw_payload": {},
        }
    ]


def test_size_export_does_not_add_fallback_for_profile_matched_archive_item():
    source_items = [
        {"id": 10, "sku": "MATCH", "original_sku": "MATCH", "color": "黑色", "raw_payload": {}},
    ]
    profiles = [
        {
            "id": 1,
            "product_code": "MATCH-34",
            "style_code": "MATCH",
            "size_barcode": "34",
        }
    ]

    assert _size_export_fallback_profiles(source_items, profiles) == []


def test_size_export_builds_one_product_code_per_size_group_item():
    profiles, source_codes = _size_export_profiles_from_size_groups(
        [
            {
                "id": 7,
                "sku": "SKU-001",
                "original_sku": "STYLE-001",
                "color": "黑色",
                "color_code": "01",
                "barcode_build_rule": "货号+颜色代码+尺码",
                "size_range": "女鞋尺码组",
                "raw_payload": {},
            },
        ],
        {
            "女鞋尺码组": [
                {"size_name": "34", "barcode": "220"},
                {"size_name": "35", "barcode": "225"},
            ],
        },
    )

    assert source_codes == {"SKU-001", "STYLE-001"}
    assert [profile["product_code"] for profile in profiles] == ["SKU-00101220", "SKU-00101225"]
    assert [profile["size_barcode"] for profile in profiles] == ["220", "225"]


def test_size_export_defaults_to_repeating_the_color_code_before_size():
    profiles, _ = _size_export_profiles_from_size_groups(
        [
            {
                "id": 8,
                "sku": "RCT63957D06",
                "original_sku": "RCT63957D06",
                "color": "咖色",
                "color_code": "06",
                "barcode_build_rule": None,
                "size_range": "女鞋尺码组",
                "raw_payload": {},
            },
        ],
        {"女鞋尺码组": [{"size_name": "34", "barcode": "220"}]},
    )

    assert profiles[0]["product_code"] == "RCT63957D0606220"


def test_size_export_product_name_uses_style_code_and_color_name():
    assert _size_export_product_name("RCT63957D06", "咖色", "RCT63957D0606220") == "RCT63957D06咖色"
