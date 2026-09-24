from datetime import date, datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock, Mock

import pytest

from scripts import refresh_product_images as images


BUSINESS_DATE = date(2026, 9, 24)


@pytest.fixture
def image_stage(tmp_path, monkeypatch):
    settings = SimpleNamespace(database_url="sqlite://", ucloud_us3_configured=True, image_roots={"cbanner": tmp_path})
    statuses = Mock()
    statuses.is_success.side_effect = lambda name, business_date: name == images.PRODUCT_TASK_NAME
    products = Mock()
    factory = Mock(return_value=products)
    refresh = Mock(return_value={"accepted": True, "status": "completed", "results": {}})
    upload = Mock(return_value={
        "scanned": 10, "candidates": 2, "uploaded": 2, "skipped_unchanged": 5,
        "missing": 2, "invalid": 1, "failed": 0, "errors": [],
    })
    monkeypatch.setattr(images, "ProductRepository", factory)
    monkeypatch.setattr(images, "run_product_image_refresh", refresh)
    monkeypatch.setattr(images, "run_product_image_us3_sync", upload)
    monkeypatch.setattr(images, "business_today", lambda: BUSINESS_DATE)
    return SimpleNamespace(settings=settings, statuses=statuses, products=products, factory=factory, refresh=refresh, upload=upload)


def test_daily_images_wait_for_archive_before_running_or_marking_success(image_stage):
    stage = image_stage
    stage.statuses.is_success.side_effect = lambda name, business_date: name == images.TASK_NAME
    assert images.run_daily_refresh(stage.settings, stage.statuses, BUSINESS_DATE) == 1
    stage.factory.assert_not_called()
    stage.refresh.assert_not_called()
    stage.upload.assert_not_called()
    assert stage.statuses.mark_finished.call_args.kwargs["status"] == "skipped"


def test_daily_images_skip_completed_day(image_stage):
    stage = image_stage
    stage.statuses.is_success.side_effect = None
    stage.statuses.is_success.return_value = True
    assert images.run_daily_refresh(stage.settings, stage.statuses, BUSINESS_DATE) == 0
    stage.factory.assert_not_called()
    stage.statuses.mark_running.assert_not_called()
    stage.statuses.mark_finished.assert_not_called()


def test_daily_images_refresh_then_upload_before_marking_success(image_stage):
    stage = image_stage
    sequence = Mock()
    sequence.attach_mock(stage.refresh, "refresh")
    sequence.attach_mock(stage.upload, "upload")
    sequence.attach_mock(stage.statuses.mark_finished, "finish")
    assert images.run_daily_refresh(stage.settings, stage.statuses, BUSINESS_DATE) == 0
    assert [call[0] for call in sequence.mock_calls] == ["refresh", "upload", "finish"]
    stage.refresh.assert_called_once_with(settings=stage.settings, repository=stage.products, brand=None, overwrite=False)
    stage.upload.assert_called_once_with(settings=stage.settings, repository=stage.products, brands=None, force=False, dry_run=False)
    assert stage.statuses.mark_finished.call_args.kwargs["status"] == "success"
    assert stage.statuses.mark_finished.call_args.kwargs["result"]["us3_sync"]["missing"] == 2
    stage.products.engine.dispose.assert_called_once()


@pytest.mark.parametrize("result", [
    {"accepted": False, "message": "busy"},
    {"accepted": True, "status": "failed", "error": "test-secret"},
    {"accepted": True, "status": "running"},
])
def test_refresh_not_completed_blocks_upload_and_daily_success(image_stage, result, capsys):
    stage = image_stage
    stage.refresh.return_value = result
    assert images.run_daily_refresh(stage.settings, stage.statuses, BUSINESS_DATE) == 1
    stage.upload.assert_not_called()
    assert stage.statuses.mark_finished.call_args.kwargs["status"] == "failed"
    assert "test-secret" not in capsys.readouterr().out
    stage.products.engine.dispose.assert_called_once()


def test_failed_upload_does_not_mark_daily_success(image_stage):
    stage = image_stage
    stage.upload.return_value["failed"] = 1
    assert images.run_daily_refresh(stage.settings, stage.statuses, BUSINESS_DATE) == 1
    assert stage.statuses.mark_finished.call_args.kwargs["status"] == "failed"
    stage.products.engine.dispose.assert_called_once()


@pytest.mark.parametrize("operation", ["factory", "refresh", "upload"])
def test_daily_exception_is_sanitized_and_resources_released(image_stage, operation, capsys):
    stage = image_stage
    getattr(stage, operation).side_effect = RuntimeError("test-secret")
    assert images.run_daily_refresh(stage.settings, stage.statuses, BUSINESS_DATE) == 1
    assert stage.statuses.mark_finished.call_args.kwargs["status"] == "failed"
    assert stage.statuses.mark_finished.call_args.kwargs["result"] == {"error_type": "RuntimeError"}
    assert "test-secret" not in capsys.readouterr().out
    if operation != "factory":
        stage.products.engine.dispose.assert_called_once()


def test_daily_images_require_configured_storage(image_stage):
    stage = image_stage
    stage.settings.ucloud_us3_configured = False
    assert images.run_daily_refresh(stage.settings, stage.statuses, BUSINESS_DATE) == 1
    stage.factory.assert_not_called()
    stage.refresh.assert_not_called()
    stage.upload.assert_not_called()
    assert stage.statuses.mark_finished.call_args.kwargs["status"] == "failed"


def test_daily_images_reject_unavailable_shared_directory(image_stage, tmp_path):
    stage = image_stage
    stage.settings.image_roots = {"cbanner": tmp_path / "unavailable"}
    assert images.run_daily_refresh(stage.settings, stage.statuses, BUSINESS_DATE) == 1
    stage.refresh.assert_not_called()
    stage.upload.assert_not_called()
    assert stage.statuses.mark_finished.call_args.kwargs["status"] == "failed"


def test_daily_images_crossing_midnight_are_not_marked_successful(image_stage, monkeypatch):
    stage = image_stage
    monkeypatch.setattr(images, "business_today", lambda: BUSINESS_DATE + timedelta(days=1))
    assert images.run_daily_refresh(stage.settings, stage.statuses, BUSINESS_DATE) == 1
    assert stage.statuses.mark_finished.call_args.kwargs["status"] == "failed"
    stage.products.engine.dispose.assert_called_once()


@pytest.mark.parametrize("arguments", [[], ["--brand", "cbanner_mens"], ["--overwrite"], ["--skip-us3"], ["--force-us3"], ["--dry-run-us3"]])
def test_manual_refresh_preserves_flags_without_certifying_daily_success(image_stage, monkeypatch, arguments):
    stage = image_stage
    status_factory = Mock()
    monkeypatch.setattr(images, "load_settings", Mock(return_value=stage.settings))
    monkeypatch.setattr(images, "ScheduledTaskStatusRepository", status_factory)
    monkeypatch.setattr("sys.argv", ["refresh_product_images", *arguments])
    assert images.main() == 0
    status_factory.assert_not_called()
    assert stage.refresh.call_args.kwargs["brand"] == ("cbanner_mens" if "--brand" in arguments else None)
    assert stage.refresh.call_args.kwargs["overwrite"] == ("--overwrite" in arguments)
    if "--skip-us3" in arguments:
        stage.upload.assert_not_called()
    else:
        assert stage.upload.call_args.kwargs["brands"] == (["cbanner_mens"] if "--brand" in arguments else None)
        assert stage.upload.call_args.kwargs["force"] == ("--force-us3" in arguments)
        assert stage.upload.call_args.kwargs["dry_run"] == ("--dry-run-us3" in arguments)
    stage.products.engine.dispose.assert_called_once()


def test_manual_refresh_without_us3_keeps_local_fallback(image_stage, monkeypatch):
    stage = image_stage
    stage.settings.ucloud_us3_configured = False
    monkeypatch.setattr(images, "load_settings", Mock(return_value=stage.settings))
    monkeypatch.setattr("sys.argv", ["refresh_product_images"])
    assert images.main() == 0
    stage.refresh.assert_called_once()
    stage.upload.assert_not_called()
    stage.products.engine.dispose.assert_called_once()


@pytest.mark.parametrize("arguments", [["--brand", "cbanner_mens"], ["--overwrite"], ["--skip-us3"], ["--force-us3"], ["--dry-run-us3"]])
def test_daily_mode_rejects_partial_or_manual_options(monkeypatch, arguments):
    loader = Mock()
    monkeypatch.setattr(images, "load_settings", loader)
    monkeypatch.setattr("sys.argv", ["refresh_product_images", "--daily", *arguments])
    with pytest.raises(SystemExit) as error:
        images.main()
    assert error.value.code == 2
    loader.assert_not_called()


@pytest.mark.parametrize("outcome", ["busy", "success", "exception"])
def test_daily_entrypoint_lock_and_engine_cleanup(image_stage, monkeypatch, outcome):
    stage = image_stage
    statuses = MagicMock()
    connection = statuses.engine.connect.return_value.execution_options.return_value.__enter__.return_value
    connection.execute.return_value.scalar_one.return_value = outcome != "busy"
    runner = Mock(return_value=0)
    if outcome == "exception":
        runner.side_effect = RuntimeError("failed")
    monkeypatch.setattr(images, "load_settings", Mock(return_value=stage.settings))
    monkeypatch.setattr(images, "ScheduledTaskStatusRepository", Mock(return_value=statuses))
    monkeypatch.setattr(images, "run_daily_refresh", runner)
    monkeypatch.setattr("sys.argv", ["refresh_product_images", "--daily"])
    if outcome == "exception":
        with pytest.raises(RuntimeError):
            images.main()
    else:
        assert images.main() == (1 if outcome == "busy" else 0)
    if outcome == "busy":
        runner.assert_not_called()
        assert connection.execute.call_count == 1
    else:
        runner.assert_called_once_with(stage.settings, statuses, BUSINESS_DATE)
        assert "pg_advisory_unlock" in str(connection.execute.call_args.args[0])
    assert connection.execute.call_args.args[1] == {"key": images.IMAGE_LOCK_ID}
    statuses.engine.dispose.assert_called_once()


def test_daily_business_date_uses_beijing_timezone(monkeypatch):
    class FixedDatetime(datetime):
        @classmethod
        def now(cls, tz=None):
            return datetime(2026, 9, 23, 20, tzinfo=timezone.utc).astimezone(tz)

    monkeypatch.setattr(images, "datetime", FixedDatetime)
    assert images.business_today() == BUSINESS_DATE
