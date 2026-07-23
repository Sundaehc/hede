from api.routes.product_goods import (
    _allocate_replenishment_by_sales,
    _post_replenishment_inventory_by_size,
    _post_replenishment_turnover_days,
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
