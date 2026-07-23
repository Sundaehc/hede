from fastapi import HTTPException

from api.routes.product_goods import _parse_product_goods_filters


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
