from datetime import date

from api.routes.product_goods import (
    _factory_dashboard_expected_date_range,
    _missing_dates_between,
)


def test_current_year_coverage_stops_at_yesterday() -> None:
    assert _factory_dashboard_expected_date_range(
        2026,
        date_start=None,
        date_end=None,
        today=date(2026, 8, 23),
    ) == (date(2026, 1, 1), date(2026, 8, 22))


def test_past_year_coverage_uses_full_year_and_filters() -> None:
    assert _factory_dashboard_expected_date_range(
        2025,
        date_start=date(2025, 2, 1),
        date_end=date(2025, 2, 3),
        today=date(2026, 8, 23),
    ) == (date(2025, 2, 1), date(2025, 2, 3))


def test_missing_dates_between_returns_only_gaps() -> None:
    assert _missing_dates_between(
        date(2026, 8, 20),
        date(2026, 8, 22),
        {date(2026, 8, 20), date(2026, 8, 22)},
    ) == [date(2026, 8, 21)]
