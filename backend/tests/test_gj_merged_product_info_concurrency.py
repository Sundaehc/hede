from datetime import date
from types import SimpleNamespace
from unittest.mock import MagicMock, Mock

import pytest
from sqlalchemy.exc import IntegrityError

from scripts import import_gj_merged_product_info as importer
from scripts import import_gj_merged_product_info_daily as daily


@pytest.mark.parametrize("outcome", ["busy", "success", "failure"])
def test_daily_lock_prevents_overlapping_import_and_releases_connection(monkeypatch, tmp_path, outcome):
    settings = SimpleNamespace(database_url="postgresql://unused", jst_price_root=tmp_path)
    statuses = MagicMock()
    connection = statuses.engine.connect.return_value.execution_options.return_value.__enter__.return_value
    connection.execute.return_value.scalar_one.return_value = outcome != "busy"
    runner = Mock(return_value=0)
    if outcome == "failure":
        runner.side_effect = RuntimeError("failed")
    monkeypatch.setattr(daily, "load_settings", Mock(return_value=settings))
    monkeypatch.setattr(daily, "ScheduledTaskStatusRepository", Mock(return_value=statuses))
    monkeypatch.setattr(daily, "run_daily_import", runner)
    monkeypatch.setattr("sys.argv", ["import_gj_merged_product_info_daily"])

    if outcome == "failure":
        with pytest.raises(RuntimeError, match="failed"):
            daily.main()
    else:
        assert daily.main() == 0
    calls = connection.execute.call_args_list
    assert "pg_try_advisory_lock" in str(calls[0].args[0])
    assert calls[0].args[1] == {"key": daily.DAILY_LOCK_ID}
    if outcome == "busy":
        runner.assert_not_called()
        assert len(calls) == 1
        statuses.mark_running.assert_not_called()
        statuses.mark_finished.assert_not_called()
    else:
        runner.assert_called_once()
        assert "pg_advisory_unlock" in str(calls[-1].args[0])
    statuses.engine.dispose.assert_called_once()


def test_daily_check_runs_after_lock_and_skips_existing_success(monkeypatch, tmp_path):
    statuses = Mock()
    statuses.successful_dates.return_value = {date(2026, 10, 19)}
    importer_mock = Mock()
    monkeypatch.setattr(daily, "import_gj_merged_product_info", importer_mock)
    summary = daily._run_once(database_url="unused", source_root=tmp_path, status_repo=statuses,
                              dates=[date(2026, 10, 19)], force=False)
    assert summary.skipped_success == 1
    importer_mock.assert_not_called()
    statuses.mark_running.assert_not_called()
    statuses.mark_finished.assert_not_called()


@pytest.mark.parametrize("force", [False, True])
def test_daily_import_keeps_success_recording_and_force_behavior(monkeypatch, tmp_path, force):
    source_dir = tmp_path / "2026-10-19"
    source_dir.mkdir()
    statuses = Mock()
    statuses.successful_dates.return_value = set()
    importer_mock = Mock(return_value={"imported": 2})
    monkeypatch.setattr(daily, "import_gj_merged_product_info", importer_mock)
    summary = daily._run_once(database_url="unused", source_root=tmp_path, status_repo=statuses,
                              dates=[date(2026, 10, 19)], force=force)
    assert summary.imported == 1
    assert summary.failed == 0
    importer_mock.assert_called_once_with("unused", source_dir)
    assert statuses.mark_finished.call_args.kwargs["status"] == "success"
    if force:
        statuses.successful_dates.assert_not_called()
    else:
        statuses.successful_dates.assert_called_once()


def test_daily_missing_source_remains_retryable_without_import(monkeypatch, tmp_path):
    statuses = Mock()
    statuses.successful_dates.return_value = set()
    importer_mock = Mock()
    monkeypatch.setattr(daily, "import_gj_merged_product_info", importer_mock)
    summary = daily._run_once(database_url="unused", source_root=tmp_path, status_repo=statuses,
                              dates=[date(2026, 10, 19)], force=False)
    assert summary.missing_source == 1
    assert summary.retry_target_unresolved
    assert statuses.mark_finished.call_args.kwargs["status"] == "skipped"
    importer_mock.assert_not_called()


def test_daily_failure_message_omits_sql_parameters_but_retains_traceback(monkeypatch, tmp_path):
    (tmp_path / "2026-10-19").mkdir()
    statuses = Mock()
    statuses.successful_dates.return_value = set()
    error = IntegrityError("INSERT INTO products", [{"secret_payload": "private data"}], RuntimeError("duplicate goods code"))
    monkeypatch.setattr(daily, "import_gj_merged_product_info", Mock(side_effect=error))
    summary = daily._run_once(database_url="unused", source_root=tmp_path, status_repo=statuses,
                              dates=[date(2026, 10, 19)], force=False)
    assert summary.failed == 1
    assert summary.retry_target_unresolved
    result = statuses.mark_finished.call_args.kwargs
    assert result["status"] == "failed"
    assert result["message"] == "IntegrityError: duplicate goods code"
    assert "secret_payload" not in result["message"]
    assert "Traceback" in result["result"]["traceback"]


@pytest.mark.parametrize("fail_insert", [False, True])
def test_import_serializes_same_date_before_delete_and_disposes_engine(monkeypatch, tmp_path, fail_insert):
    source_dir = tmp_path / "2026-10-19"
    source_file = source_dir / "男女鞋合并商品信息.xlsx"
    engine = MagicMock()
    connection = engine.begin.return_value.__enter__.return_value
    connection.dialect.name = "postgresql"
    rows = [{"source_date": "2026-10-19", "goods_code": "SKU1", "product_name": "old"},
            {"source_date": "2026-10-19", "goods_code": "SKU1", "product_name": "latest"}]
    monkeypatch.setattr(importer, "_source_file", Mock(return_value=source_file))
    monkeypatch.setattr(importer, "_read_rows", Mock(return_value=rows))
    create_engine = Mock(return_value=engine)
    monkeypatch.setattr(importer, "create_engine", create_engine)
    if fail_insert:
        connection.execute.side_effect = [None, None, RuntimeError("insert failed")]
        with pytest.raises(RuntimeError, match="insert failed"):
            importer.import_gj_merged_product_info("unused", source_dir)
        assert engine.begin.return_value.__exit__.call_args.args[0] is RuntimeError
    else:
        result = importer.import_gj_merged_product_info("unused", source_dir)
        assert result["read_rows"] == 2
        assert result["imported"] == 1
    calls = connection.execute.call_args_list
    assert "pg_advisory_xact_lock" in str(calls[0].args[0])
    assert calls[0].args[1] == {"namespace": importer.IMPORT_LOCK_NAMESPACE, "source_date": "2026-10-19"}
    assert str(calls[1].args[0]).startswith("DELETE FROM gj_merged_product_info")
    assert str(calls[2].args[0]).startswith("INSERT INTO gj_merged_product_info")
    assert calls[2].args[1] == [rows[-1]]
    assert create_engine.call_args.kwargs["hide_parameters"] is True
    engine.dispose.assert_called_once()
