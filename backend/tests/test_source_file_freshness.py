from __future__ import annotations

from datetime import date, datetime
from pathlib import Path

import pytest

from scripts.import_aftersale_returns_daily import _wait_for_stable_source
from scripts.source_file_freshness import (
    require_business_date_source,
    require_business_date_sources,
)


def _set_modified_at(path: Path, value: datetime) -> None:
    timestamp = value.astimezone().timestamp()
    path.touch()
    path.write_bytes(b"source")
    path.chmod(0o666)
    import os

    os.utime(path, (timestamp, timestamp))


def test_require_business_date_source_accepts_exact_date(tmp_path: Path) -> None:
    source = tmp_path / "source.xlsx"
    _set_modified_at(source, datetime(2026, 9, 13, 9, 30).astimezone())

    result = require_business_date_source(source, date(2026, 9, 13))

    assert result["source_file"] == str(source)
    assert str(result["modified_at"]).startswith("2026-09-13T09:30:00")


@pytest.mark.parametrize("modified_day", [date(2026, 9, 12), date(2026, 9, 14)])
def test_require_business_date_source_rejects_nonmatching_date(
    tmp_path: Path,
    modified_day: date,
) -> None:
    source = tmp_path / "source.xlsx"
    _set_modified_at(
        source,
        datetime.combine(modified_day, datetime.min.time()).astimezone(),
    )

    with pytest.raises(ValueError, match="当日文件"):
        require_business_date_source(source, date(2026, 9, 13))


def test_require_business_date_sources_rejects_batch_before_import(
    tmp_path: Path,
) -> None:
    current = tmp_path / "current.xlsx"
    stale = tmp_path / "stale.xlsx"
    _set_modified_at(current, datetime(2026, 9, 13, 9, 30).astimezone())
    _set_modified_at(stale, datetime(2026, 9, 12, 9, 30).astimezone())

    with pytest.raises(ValueError, match="stale.xlsx"):
        require_business_date_sources((current, stale), date(2026, 9, 13))


def test_aftersale_stability_check_rejects_future_date(tmp_path: Path) -> None:
    source = tmp_path / "aftersale.xlsx"
    _set_modified_at(source, datetime(2026, 9, 14, 9, 30).astimezone())

    with pytest.raises(TimeoutError, match="not the 2026-09-13 export"):
        _wait_for_stable_source(
            source,
            date(2026, 9, 13),
            timeout_seconds=0,
            minimum_age_seconds=0,
            confirmation_seconds=0,
            poll_interval_seconds=1,
        )
