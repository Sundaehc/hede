from __future__ import annotations

from datetime import date, datetime

from scripts.import_smiley_fine_table_daily import _parse_retry_until, _run_with_retry


def test_successful_retry_stops_after_success() -> None:
    results = iter([1, 0, 1])
    attempts: list[int] = []
    sleeps: list[float] = []

    def run_attempt() -> int:
        attempts.append(1)
        return next(results)

    exit_code = _run_with_retry(
        run_attempt,
        retry_until=datetime(2026, 9, 17, 16, 0),
        retry_interval_seconds=1800,
        now=lambda: datetime(2026, 9, 17, 9, 10),
        sleep=sleeps.append,
    )

    assert exit_code == 0
    assert len(attempts) == 2
    assert sleeps == [1800]


def test_failed_attempt_stops_at_retry_deadline() -> None:
    attempts: list[int] = []

    exit_code = _run_with_retry(
        lambda: attempts.append(1) or 1,
        retry_until=datetime(2026, 9, 17, 16, 0),
        retry_interval_seconds=1800,
        now=lambda: datetime(2026, 9, 17, 16, 0),
        sleep=lambda _seconds: None,
    )

    assert exit_code == 1
    assert len(attempts) == 1


def test_retry_wait_is_capped_by_remaining_time() -> None:
    times = iter(
        [
            datetime(2026, 9, 17, 15, 55),
            datetime(2026, 9, 17, 16, 0),
        ]
    )
    sleeps: list[float] = []

    exit_code = _run_with_retry(
        lambda: 1,
        retry_until=datetime(2026, 9, 17, 16, 0),
        retry_interval_seconds=1800,
        now=lambda: next(times),
        sleep=sleeps.append,
    )

    assert exit_code == 1
    assert sleeps == [300]


def test_parse_retry_until_uses_business_date() -> None:
    assert _parse_retry_until("16:00", business_date=date(2026, 9, 17)) == datetime(
        2026, 9, 17, 16, 0
    )
