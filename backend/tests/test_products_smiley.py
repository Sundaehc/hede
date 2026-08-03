from types import SimpleNamespace

from api.routes.products import _smiley_product_base_item


def test_smiley_base_info_maps_only_product_fields():
    item = _smiley_product_base_item(
        {
            "id": 11,
            "image_path": r"\\Hede\图片\产品45主图随时更新\45主图\笑脸45度图\S100.jpg",
            "sku": "S100",
            "original_sku": "S100",
            "factory_code": "FAC-1",
            "factory_sku": "MODEL-1",
            "market_price": 899,
            "cost": 120,
            "product_name": "笑脸测试鞋",
            "barcode": "690000000001",
            "execution_standard": "QB/T",
            "insole_material": "鞋垫",
            "outsole_material": "橡胶",
            "lining_material": "织物",
            "upper_material": "牛皮",
            "shoe_box_spec": "标准鞋盒",
            "accessories": "备用鞋带",
            "first_order_date": "2026-01-01",
            "season_category": "春季",
            "source_workbook": "smiley.xlsx",
            "source_sheet": "精细表",
            "source_row_number": 2,
            "stock_qty": 999,
            "total_7d_sales": 100,
        },
        SimpleNamespace(image_roots={}),
    )

    assert item["brand"] == "smiley"
    assert item["sku"] == "S100"
    assert item["factory_code"] == "FAC-1"
    assert item["factory_sku"] == "MODEL-1"
    assert item["market_price"] == 899
    assert item["barcode"] == "690000000001"
    assert item["upper_material"] == "牛皮"
    assert item["image_url"] is None
    assert "stock_qty" not in item
    assert "total_7d_sales" not in item
