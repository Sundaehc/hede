from api.routes.product_goods import (
    _allocate_replenishment_by_sales,
    _manual_size_quantities,
    _post_replenishment_inventory_by_size,
    _post_replenishment_turnover_days,
    _size_inventory_risk_flags,
    _size_from_color_spec,
    _stock_health_label,
)


def test_replenishment_allocation_targets_post_replenishment_size_mix():
    assert _allocate_replenishment_by_sales(10, 20, {"34": 4, "35": 6}, {"34": 3, "35": 2}) == {
        "34": 8,
        "35": 2,
    }


def test_replenishment_allocation_distributes_rounding_remainder_by_size():
    assert _allocate_replenishment_by_sales(5, 5, {}, {"34": 1, "35": 1, "36": 1}) == {
        "34": 2,
        "35": 2,
        "36": 1,
    }


def test_post_replenishment_inventory_and_turnover_use_allocated_quantities():
    replenishment = _allocate_replenishment_by_sales(
        10,
        20,
        {"34": 4, "35": 6},
        {"34": 3, "35": 2},
    )

    assert _post_replenishment_inventory_by_size({"34": 4, "35": 6}, replenishment) == {
        "34": 12,
        "35": 8,
    }
    assert _post_replenishment_turnover_days(30, 5) == 84.0


def test_clog_sizes_are_parsed_and_supported_for_manual_replenishment():
    assert _size_from_color_spec("KT-白色 225-230") == "225-230"
    assert _size_from_color_spec("240~245") == "240-245"
    assert _manual_size_quantities(
        {"225-230": 4, "230-235": -1},
        allow_negative=True,
    ) == {"225-230": 4, "230-235": -1}


def test_size_inventory_flags_detect_broken_and_biased_stock():
    assert _size_inventory_risk_flags(
        {"34": 1, "35": 8, "36": 1, "37": 0, "38": 0}
    ) == (True, True)
    assert _size_inventory_risk_flags(
        {"34": 3, "35": 3, "36": 3, "37": 1, "38": 1, "39": 3}
    ) == (True, False)
    assert _stock_health_label(18, 0, False, False) == "周转≤20天"
    assert _stock_health_label(28, 0, False, False) == "周转≤30天"
