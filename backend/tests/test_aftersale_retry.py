from __future__ import annotations

from datetime import date
from pathlib import Path

from scripts import import_aftersale_returns_daily as module


class _Status:
    def __init__(self) -> None:
        self.calls: list[tuple[str, date, str]] = []

    def mark_running(self, task_name, business_date, *, source_path=None):
        self.calls.append(("running", business_date, str(source_path)))

    def mark_finished(self, task_name, business_date, *, status, message, result=None, source_path=None):
        self.calls.append((status, business_date, message))


class _Repo:
    def __init__(self, results):
        self.results = iter(results)
        self.calls = 0

    def import_aftersale_returns(self, source_file):
        self.calls += 1
        result = next(self.results)
        if isinstance(result, Exception):
            raise result
        return result


def test_successful_retry_stops_without_a_third_attempt(monkeypatch, tmp_path: Path) -> None:
    source = tmp_path / "aftersale.xlsx"
    source.write_bytes(b"source")
    status = _Status()
    repo = _Repo([ValueError("temporary parse error"), {"imported": 3}])
    monkeypatch.setattr(
        module,
        "_wait_for_stable_source",
        lambda *args, **kwargs: {
            "modified_at": "2026-09-13T09:30:00+08:00",
            "size_bytes": 6,
        },
    )

    first = module._run_once(
        source_file=source,
        business_date=date.today(),
        status_repo=status,
        repo=repo,
    )
    second = module._run_once(
        source_file=source,
        business_date=date.today(),
        status_repo=status,
        repo=repo,
    )

    assert first is True
    assert second is False
    assert repo.calls == 2


def test_retry_deadline_marks_final_attempt_as_failed(tmp_path: Path) -> None:
    status = _Status()
    module._mark_retry_exhausted(
        status,
        source_file=tmp_path / "missing.xlsx",
        business_date=date(2026, 9, 13),
    )

    assert status.calls[-1][0] == "failed"
    assert "重试截止" in status.calls[-1][2]
