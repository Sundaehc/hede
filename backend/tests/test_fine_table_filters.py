from fastapi import HTTPException

from api.routes.fine_table import _parse_fine_table_filters


def test_fine_table_filters_accept_in_and_not_in_values():
    filters = _parse_fine_table_filters(
        '[{"field":"year","operator":"in","values":["2026"]},'
        '{"field":"factory_name","operator":"not_in","values":[""]}]'
    )

    assert [(item.field, item.operator, item.values) for item in filters] == [
        ("year", "in", ["2026"]),
        ("factory_name", "not_in", [""]),
    ]


def test_fine_table_filters_reject_unknown_fields():
    try:
        _parse_fine_table_filters('[{"field":"vip_7d_sales","operator":"in","values":["10"]}]')
    except HTTPException as exc:
        assert exc.status_code == 400
    else:
        raise AssertionError("Expected invalid fine-table filter to be rejected")
