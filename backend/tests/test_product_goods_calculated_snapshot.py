from api.routes.product_goods import _calculated_snapshot_data


def test_calculated_snapshot_data_preserves_current_view_fields():
    data = _calculated_snapshot_data(
        {
            "year": "2026",
            "style_code": "ABC01",
            "image_url": "/images/example.jpg",
            "stock_total": 12,
            "in_transit_total": 3,
            "inventory_total": 15,
            "stock_by_size": {"36": 12},
            "daily_sales_by_date": {"2026-07-23": 2},
            "daily_platform_sales": {"唯品": 1, "天猫": 1},
            "metrics": {"total_sales": 50},
        }
    )

    assert data["year"] == "2026"
    assert data["snapshot_format"] == "product_goods_calculated_snapshot_v1"
    assert data["style_code"] == "ABC01"
    assert data["image_url"] == "/images/example.jpg"
    assert data["stock_by_size"] == {"36": 12}
    assert data["daily_sales_by_date"] == {"2026-07-23": 2}
    assert data["daily_platform_sales"] == {"唯品": 1, "天猫": 1}
    assert data["metrics"] == {
        "total_sales": 50,
        "stock_total": 12,
        "in_transit_total": 3,
        "inventory_total": 15,
    }
