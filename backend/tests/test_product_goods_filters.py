from fastapi import HTTPException

from api.routes.product_goods import (
    _base_style_code,
    _parse_product_goods_filters,
    _product_type_value,
    _style_summary_item,
)


def test_product_goods_filters_accept_multiple_supported_conditions():
    filters = _parse_product_goods_filters(
        '[{"field":"year","operator":"equals","value":"2026"},'
        '{"field":"platform","operator":"empty"}]'
    )

    assert [(item.field, item.operator, item.value) for item in filters] == [
        ("year", "equals", "2026"),
        ("platform", "empty", None),
    ]


def test_product_goods_filters_reject_unknown_fields():
    try:
        _parse_product_goods_filters('[{"field":"stock_total","operator":"equals","value":"10"}]')
    except HTTPException as exc:
        assert exc.status_code == 400
    else:
        raise AssertionError("Expected invalid product-goods filter to be rejected")


def test_product_goods_filters_require_a_value_for_text_match():
    try:
        _parse_product_goods_filters('[{"field":"year","operator":"contains","value":"  "}]')
    except HTTPException as exc:
        assert exc.status_code == 400
    else:
        raise AssertionError("Expected missing filter value to be rejected")


def test_product_goods_filters_accept_a_multi_value_selection():
    filters = _parse_product_goods_filters(
        '[{"field":"platform","operator":"not_in","values":["唯品", ""]}]'
    )

    assert filters[0].operator == "not_in"
    assert filters[0].values == ["唯品", ""]


def test_style_summary_aggregates_color_rows_and_hides_color():
    summary = _style_summary_item(
        "A100",
        [
            {
                "id": 1,
                "style_code": "A100",
                "goods_code": "A100-RED",
                "color": "红",
                "stock_total": 10,
                "in_transit_total": 2,
                "inventory_total": 12,
                "stock_by_size": {"36": 6},
                "daily_sales_by_date": {"2026-07-22": 3},
                "annual_sales": {"2026": 20},
                "monthly_sales": {"26-7": 8},
                "daily_platform_sales": {"天猫": 2},
                "weekly_platform_sales": {},
                "monthly_platform_sales": {},
                "in_transit_by_size": {"36": 2},
                "inventory_by_size": {"36": 8},
                "shortage_by_size": {},
                "sales_by_size": {"36": 3},
                "replenishment_by_size": {"36": 1},
                "post_replenishment_by_size": {"36": 7},
                "metrics": {"total_sales": 20, "week_sales": 5, "post_replenishment_turnover_days": 30},
            },
            {
                "id": 2,
                "style_code": "A100",
                "goods_code": "A100-BLUE",
                "color": "蓝",
                "stock_total": 8,
                "in_transit_total": 1,
                "inventory_total": 9,
                "stock_by_size": {"36": 4, "37": 4},
                "daily_sales_by_date": {"2026-07-22": 2},
                "annual_sales": {"2026": 15},
                "monthly_sales": {"26-7": 5},
                "daily_platform_sales": {"天猫": 1},
                "weekly_platform_sales": {},
                "monthly_platform_sales": {},
                "in_transit_by_size": {"37": 1},
                "inventory_by_size": {"36": 4, "37": 5},
                "shortage_by_size": {},
                "sales_by_size": {"36": 1, "37": 1},
                "replenishment_by_size": {"37": 2},
                "post_replenishment_by_size": {"37": 6},
                "metrics": {"total_sales": 15, "week_sales": 4, "post_replenishment_turnover_days": 20},
            },
        ],
    )

    assert summary["goods_code"] == "A100"
    assert summary["color"] is None
    assert summary["stock_total"] == 18
    assert summary["stock_by_size"] == {"36": 10, "37": 4}
    assert summary["annual_sales"] == {"2026": 35}
    assert summary["metrics"]["total_sales"] == 35
    assert summary["metrics"]["post_replenishment_turnover_days"] is None


def test_style_summary_removes_the_two_character_color_suffix():
    assert _base_style_code("A6054521D01") == "A6054521D"
    assert _base_style_code("EB634763DA4") == "EB634763D"
    assert _base_style_code("KT-Q15036A2") == "KT-Q15036"


def test_product_type_defaults_kt_goods_codes_to_clogs():
    assert _product_type_value(None, " KT-Q15036A2 ") == "洞洞鞋"
    assert _product_type_value("凉鞋", "KT-Q15036A2") == "凉鞋"
    assert _product_type_value(None, "A6054521D01") is None
