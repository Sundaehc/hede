from datetime import date, datetime

from api.routes.product_goods import (
    _factory_dashboard_expected_date_range,
    _factory_dashboard_pending_refresh_dates,
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


def test_yesterday_is_pending_before_daily_refresh_finishes() -> None:
    missing_dates = [date(2026, 8, 22), date(2026, 8, 23)]

    assert _factory_dashboard_pending_refresh_dates(
        "jst",
        missing_dates,
        now=datetime(2026, 8, 24, 9, 15),
    ) == [date(2026, 8, 23)]
    assert _factory_dashboard_pending_refresh_dates(
        "vip",
        missing_dates,
        now=datetime(2026, 8, 24, 10, 15),
    ) == [date(2026, 8, 23)]


def test_yesterday_becomes_missing_after_refresh_deadline() -> None:
    assert _factory_dashboard_pending_refresh_dates(
        "vip",
        [date(2026, 8, 23)],
        now=datetime(2026, 8, 24, 11, 20),
    ) == []


def test_historical_source_has_no_daily_refresh_window() -> None:
    assert _factory_dashboard_pending_refresh_dates(
        "historical",
        [date(2026, 8, 23)],
        now=datetime(2026, 8, 24, 9, 15),
    ) == []
