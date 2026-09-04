from __future__ import annotations

from types import SimpleNamespace

from scripts import import_jst_daily


class _StatusRepository:
    def __init__(self, *, succeeded: bool = False):
        self.succeeded = succeeded
        self.running_calls: list[tuple] = []
        self.finished_calls: list[tuple] = []

    def is_success(self, task_name, business_date):
        return self.succeeded

    def mark_running(self, *args, **kwargs):
        self.running_calls.append((args, kwargs))

    def mark_finished(self, *args, **kwargs):
        self.finished_calls.append((args, kwargs))


def _configure(monkeypatch, tmp_path, status_repository):
    monkeypatch.setattr(
        import_jst_daily,
        "load_settings",
        lambda: SimpleNamespace(database_url="postgresql://unused", jst_stock_root=tmp_path),
    )
    monkeypatch.setattr(
        import_jst_daily,
        "ScheduledTaskStatusRepository",
        lambda database_url: status_repository,
    )
    monkeypatch.setattr(
        "sys.argv",
        ["import_jst_daily", "--business-date", "2026-09-04"],
    )


def test_successful_business_date_skips_import(monkeypatch, tmp_path):
    status_repository = _StatusRepository(succeeded=True)
    _configure(monkeypatch, tmp_path, status_repository)
    monkeypatch.setattr(
        import_jst_daily,
        "VipRepository",
        lambda database_url: (_ for _ in ()).throw(AssertionError("import must not start")),
    )

    assert import_jst_daily.main() == 0
    assert status_repository.running_calls == []
    assert status_repository.finished_calls == []


def test_missing_source_keeps_task_retryable(monkeypatch, tmp_path):
    status_repository = _StatusRepository()
    _configure(monkeypatch, tmp_path, status_repository)

    assert import_jst_daily.main() == 1
    assert status_repository.finished_calls[-1][1]["status"] == "skipped"


def test_complete_import_marks_business_date_success(monkeypatch, tmp_path):
    source_dir = tmp_path / "09.04"
    source_dir.mkdir()
    (source_dir / "商品库存.xlsx").touch()
    (source_dir / "采购单管理.xlsx").touch()
    status_repository = _StatusRepository()
    _configure(monkeypatch, tmp_path, status_repository)

    class _Repository:
        def import_size_stock(self, file_path, *, snapshot_date):
            return {"imported": 10}

        def import_stock_summary(self, file_path, *, snapshot_date):
            return {"imported": 5}

        def import_purchase_diff(self, file_path):
            return {"imported": 2}

    monkeypatch.setattr(import_jst_daily, "VipRepository", lambda database_url: _Repository())

    assert import_jst_daily.main() == 0
    assert status_repository.finished_calls[-1][1]["status"] == "success"
