from pipeline.import_pipeline import PROTECTED_SYNC_BRANDS, _gj_row_to_product_row


def test_gj_product_row_keeps_product_name_and_model_in_their_own_fields():
    product = _gj_row_to_product_row(
        {
            "goods_code": "6362022150800",
            "original_goods_code": "6976845091142",
            "product_name": "女休闲鞋",
            "extra_fields": {"产品型号": "一型半"},
            "raw_payload": {"产品型号": "一型半"},
        },
        brand_group="smiley",
        archive_row=None,
        image_path=None,
    )

    assert product is not None
    assert product["product_name"] == "女休闲鞋"
    assert product["product_model"] == "一型半"


def test_smiley_is_included_in_the_daily_product_archive_sync():
    assert "smiley" not in PROTECTED_SYNC_BRANDS
    assert "ni" in PROTECTED_SYNC_BRANDS


def test_daily_product_row_includes_all_cbanner_womens_style_fields():
    expected = {
        "toe_shape": "方头",
        "sole_style": "粗跟",
        "fashion_elements": "金属装饰",
        "rear_heel_height": "中跟(3-5cm)",
        "heel_height": "4cm",
        "upper_height": "低帮",
        "opening_depth": "浅口",
        "boot_shaft": "短筒",
        "closure_type": "套脚",
        "mesh_upper_type": "单网面",
    }

    product = _gj_row_to_product_row(
        {
            "goods_code": "WOMENS-STYLE-001",
            "original_goods_code": "WOMENS-STYLE-001",
        },
        brand_group="cbanner_womens",
        archive_row={**expected, "extra_fields": {}},
        image_path=None,
    )

    assert product is not None
    for field, value in expected.items():
        assert product[field] == value
