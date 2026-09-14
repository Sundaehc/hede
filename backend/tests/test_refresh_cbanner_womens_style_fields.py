from scripts.refresh_cbanner_womens_style_fields import SOURCE_LABELS, _source_fields


def test_source_fields_use_requested_columns_without_generic_fallbacks():
    source = {
        "鞋头": 0,
        "鞋头款式": "方头",
        "鞋帮": 6,
        "鞋帮高度": "低帮",
        "跟高": "4cm",
        "后跟高": "中跟(3-5cm)",
    }

    fields = _source_fields(source)

    assert set(fields) <= set(SOURCE_LABELS)
    assert fields["toe_shape"] == "方头"
    assert fields["upper_height"] == "低帮"
    assert fields["heel_height"] == "4cm"
    assert fields["rear_heel_height"] == "中跟(3-5cm)"


def test_source_fields_do_not_treat_generic_toe_and_upper_as_style_fields():
    fields = _source_fields({"鞋头": 0, "鞋帮": 6, "跟高": 4.5})

    assert fields == {"heel_height": "4.5"}
