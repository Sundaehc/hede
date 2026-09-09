from __future__ import annotations

from datetime import datetime, timedelta
from types import SimpleNamespace

from scripts import import_daily_sales_reports


class _StatusRepository:
    def __init__(self):
        self.running_calls: list[tuple] = []
        self.finished_calls: list[tuple] = []

    def mark_running(self, *args, **kwargs):
        self.running_calls.append((args, kwargs))

    def mark_finished(self, *args, **kwargs):
        self.finished_calls.append((args, kwargs))


class _SummaryRepository:
    def __init__(self):
        self.calls: list[dict] = []

    def refresh(self, **kwargs):
        self.calls.append(kwargs)
        return {"written": 1}


def _configure(monkeypatch, tmp_path, *, results):
    status_repository = _StatusRepository()
    summary_repository = _SummaryRepository()

    class _Repository:
        def __init__(self, database_url):
            self.results = iter(results)
            self.calls = 0

        def import_jst_daily_sales(self, source_file):
            self.calls += 1
            return next(self.results)

        def import_vip_daily_sales(self, source_file):
            raise AssertionError("VIP import must not start")

    repository = _Repository("postgresql://unused")
    monkeypatch.setattr(
        import_daily_sales_reports,
        "load_settings",
        lambda require_database=True: SimpleNamespace(
            database_url="postgresql://unused",
            daily_sales_report_root=tmp_path,
        ),
    )
    monkeypatch.setattr(import_daily_sales_reports, "DailySalesRepository", lambda database_url: repository)
    monkeypatch.setattr(
        import_daily_sales_reports,
        "ScheduledTaskStatusRepository",
        lambda database_url: status_repository,
    )
    monkeypatch.setattr(
        import_daily_sales_reports,
        "FactoryChannelSalesSummaryRepository",
        lambda database_url: summary_repository,
    )
    return repository, status_repository, summary_repository


def test_stale_source_date_is_not_reported_as_success(monkeypatch, tmp_path):
    _, status_repository, summary_repository = _configure(
        monkeypatch,
        tmp_path,
        results=[{"upserted": 10, "sales_dates": ["2026-09-07"]}],
    )
    monkeypatch.setattr(
        "sys.argv",
        [
            "import_daily_sales_reports",
            "--source",
            "jst",
            "--expected-sales-date",
            "2026-09-08",
            "--skip-product-goods-refresh",
        ],
    )

    assert import_daily_sales_reports.main() == 1
    assert status_repository.finished_calls[-1][1]["status"] == "skipped"
    assert summary_repository.calls == []


def test_expected_source_date_refreshes_summary(monkeypatch, tmp_path):
    _, status_repository, summary_repository = _configure(
        monkeypatch,
        tmp_path,
        results=[{"upserted": 10, "sales_dates": ["2026-09-08"]}],
    )
    monkeypatch.setattr(
        "sys.argv",
        [
            "import_daily_sales_reports",
            "--source",
            "jst",
            "--expected-sales-date",
            "2026-09-08",
            "--skip-product-goods-refresh",
        ],
    )

    assert import_daily_sales_reports.main() == 0
    assert status_repository.finished_calls[-1][1]["status"] == "success"
    assert summary_repository.calls == [
        {
            "sales_year": 2026,
            "date_start": import_daily_sales_reports.date(2026, 9, 8),
            "date_end": import_daily_sales_reports.date(2026, 9, 8),
        }
    ]


def test_stale_source_retries_until_expected_date_arrives(monkeypatch, tmp_path):
    repository, status_repository, summary_repository = _configure(
        monkeypatch,
        tmp_path,
        results=[
            {"upserted": 10, "sales_dates": ["2026-09-07"]},
            {"upserted": 12, "sales_dates": ["2026-09-08"]},
        ],
    )
    monkeypatch.setattr(
        "sys.argv",
        [
            "import_daily_sales_reports",
            "--source",
            "jst",
            "--expected-sales-date",
            "2026-09-08",
            "--retry-until",
            "23:59",
            "--retry-interval-seconds",
            "1",
            "--skip-product-goods-refresh",
        ],
    )
    monkeypatch.setattr(
        import_daily_sales_reports,
        "_parse_retry_until",
        lambda value: datetime.now() + timedelta(minutes=1),
    )
    monkeypatch.setattr(import_daily_sales_reports.time, "sleep", lambda seconds: None)

    assert import_daily_sales_reports.main() == 0
    assert repository.calls == 2
    assert [call[1]["status"] for call in status_repository.finished_calls] == ["skipped", "success"]
    assert len(summary_repository.calls) == 1
