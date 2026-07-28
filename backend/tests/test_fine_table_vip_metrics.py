from api.routes.fine_table import _daily_metric_with_original_fallback


def test_original_sku_compass_metrics_are_available_as_fallback():
    current_daily = {}
    original_daily = {
        ("罗盘", "30d"): {
            "reject_count": "3",
            "reject_rate": "12.50%",
        },
    }

    reject_count = _daily_metric_with_original_fallback(
        current_daily,
        original_daily,
        "30d",
        "reject_count",
    )
    reject_rate = _daily_metric_with_original_fallback(
        current_daily,
        original_daily,
        "30d",
        "reject_rate",
    )

    assert reject_count == "3"
    assert reject_rate == "12.50%"


def test_current_sku_compass_metrics_take_priority():
    current_daily = {
        ("罗盘", "30d"): {
            "reject_count": "0",
            "reject_rate": "0.00%",
        },
    }
    original_daily = {
        ("罗盘", "30d"): {
            "reject_count": "3",
            "reject_rate": "12.50%",
        },
    }

    reject_count = _daily_metric_with_original_fallback(
        current_daily,
        original_daily,
        "30d",
        "reject_count",
    )
    reject_rate = _daily_metric_with_original_fallback(
        current_daily,
        original_daily,
        "30d",
        "reject_rate",
    )

    assert reject_count == "0"
    assert reject_rate == "0.00%"
