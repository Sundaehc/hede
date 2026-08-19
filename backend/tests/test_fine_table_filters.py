from api.routes.fine_table import (
    FINE_TABLE_GJ_SQL_FILTER_FIELDS,
    FINE_TABLE_SQL_FILTER_FIELDS,
    FINE_TABLE_SNAPSHOT_FILTER_CACHE_FIELDS,
    FineTableFilter,
    _fine_table_filter_value,
    _fine_table_row_matches_filter,
    _parse_fine_table_filters,
)


def test_fine_table_snapshot_filter_cache_covers_expensive_derived_fields():
    fields = set(FINE_TABLE_SNAPSHOT_FILTER_CACHE_FIELDS)

    assert {"status", "risk", "vip_7d_sales", "stock_qty", "daily_sales_0_quantity", "size_34/220"} <= fields
    assert "sku" not in fields
    assert "goods_tag" not in fields
    assert "cost" not in fields
    assert "cost" in FINE_TABLE_SQL_FILTER_FIELDS
    assert "cost" in FINE_TABLE_GJ_SQL_FILTER_FIELDS
    assert "platform" in FINE_TABLE_SQL_FILTER_FIELDS
    assert "platform" in FINE_TABLE_GJ_SQL_FILTER_FIELDS


def test_fine_table_filters_accept_in_and_not_in_values():
    filters = _parse_fine_table_filters(
        '[{"field":"year","operator":"in","values":["2026"]},'
        '{"field":"platform","operator":"in","values":["唯品"]},'
        '{"field":"factory_name","operator":"not_in","values":[""]}]'
    )

    assert [(item.field, item.operator, item.values) for item in filters] == [
        ("year", "in", ["2026"]),
        ("platform", "in", ["唯品"]),
        ("factory_name", "not_in", [""]),
    ]


def test_fine_table_filters_accept_calculated_and_dynamic_fields():
    filters = _parse_fine_table_filters(
        '[{"field":"vip_7d_sales","operator":"in","values":["10"]},'
        '{"field":"daily_sales_0_quantity","operator":"in","values":["2"]},'
        '{"field":"size_34/220","operator":"in","values":["1"]}]'
    )

    assert [item.field for item in filters] == [
        "vip_7d_sales",
        "daily_sales_0_quantity",
        "size_34/220",
    ]


def test_fine_table_filter_matches_derived_risk_and_size_values():
    row = {
        "stock_qty": 10,
        "vip_7d_sales": 8,
        "other_7d_sales": 4,
        "vip_daily_average_sales": 1,
        "other_30d_sales": 30,
        "inbound_qty": 2,
        "defect_in_transit_stock": 1,
        "size_stock": {"34/220": 3},
        "daily_sales": [{"quantity": 5, "uv": 2}],
        "status_key": "offline",
    }

    assert _fine_table_row_matches_filter(
        row,
        FineTableFilter(field="risk", operator="in", values=[_fine_table_filter_value(row, "risk")]),
    )
    assert _fine_table_row_matches_filter(
        row,
        FineTableFilter(field="size_34/220", operator="in", values=["3"]),
    )
    assert _fine_table_row_matches_filter(
        row,
        FineTableFilter(field="daily_sales_0_quantity", operator="in", values=["5"]),
    )
