import base64
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from sqlalchemy import Column, DateTime, Integer, MetaData, Table, Text, create_engine, inspect, update
from sqlalchemy.pool import StaticPool

from api import product_copywriting_jobs as jobs
from api.product_copywriting_jobs import prepare_copywriting
from domain.product_copywriting_schema import PRODUCT_COPYWRITING_TABLE
from scripts import generate_product_copywriting_daily as daily
from scripts import sync_products_and_copywriting_daily as workflow
from storage.product_copywriting_repository import ProductCopywritingRepository


BUSINESS_DATE = date(2026, 9, 22)
IMAGE_BYTES = base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+aQ3sAAAAASUVORK5CYII=")


@pytest.fixture
def settings(tmp_path):
    return SimpleNamespace(
        database_url="sqlite://", ark_api_key="test-secret", doubao_provider="custom",
        doubao_base_url="https://model.example.test", doubao_text_model="test-model",
        doubao_timeout_seconds=180, image_roots={"cbanner": tmp_path},
    )


@pytest.fixture
def product(tmp_path):
    path = tmp_path / "test.png"
    path.write_bytes(IMAGE_BYTES)
    return {"id": 7, "sku": "TEST-007", "launch_date": "2026-09-22", "image_path": str(path), "color": "灰色"}


@pytest.fixture
def saved():
    engine = create_engine("sqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False})
    repository = ProductCopywritingRepository(engine)
    repository.create_tables()
    yield repository
    engine.dispose()


@pytest.mark.parametrize("business_date,expected", [
    (BUSINESS_DATE, (date(2026, 9, 20), date(2026, 9, 21), date(2026, 9, 22))),
    (date(2026, 1, 1), (date(2025, 12, 30), date(2025, 12, 31), date(2026, 1, 1))),
    (date(2026, 3, 1), (date(2026, 2, 27), date(2026, 2, 28), date(2026, 3, 1))),
    (date(2028, 3, 1), (date(2028, 2, 28), date(2028, 2, 29), date(2028, 3, 1))),
])
def test_recent_three_days_includes_today_and_two_previous_days(business_date, expected):
    assert daily.recent_launch_dates(business_date) == expected


def test_business_date_uses_china_timezone_even_before_utc_midnight(monkeypatch):
    class FixedDatetime(datetime):
        @classmethod
        def now(cls, tz=None):
            return datetime(2026, 9, 21, 20, tzinfo=timezone.utc).astimezone(tz)
    monkeypatch.setattr(daily, "datetime", FixedDatetime)
    assert daily.business_today() == BUSINESS_DATE


def product_table(metadata, name):
    return Table(name, metadata,
        Column("id", Integer, primary_key=True), Column("sku", Text), Column("original_sku", Text),
        Column("launch_date", Text), Column("image_path", Text), Column("deleted_at", DateTime),
    )


def test_selector_filters_dates_images_deleted_excluded_and_existing_per_brand(saved, settings, product, monkeypatch):
    metadata = MetaData()
    table = product_table(metadata, "daily_products")
    metadata.create_all(saved.engine)
    rows = [
        {"id": number, "sku": f"TEST-{number}", "original_sku": None, "launch_date": day, "image_path": "image.png", "deleted_at": None}
        for number, day in enumerate([
            "2026-09-20", "2026-09-22", "2026-09-19", "2026-09-23", "2026/09/20",
            "2026-09-220", " 2026-09-21 ", None, "2026-09-20", "2026-09-21", "2026-09-22", "2026-09-20",
            "2026-09-16", "2026-09-17", "2026-09-18", "2026/09/19",
        ], start=1)
    ]
    rows[8]["image_path"] = None
    rows[9]["image_path"] = " \t "
    rows[10]["deleted_at"] = datetime(2026, 9, 22)
    rows[11]["sku"] = "excluded"
    with saved.engine.begin() as connection:
        connection.execute(table.insert(), rows)
    saved.claim(prepare_copywriting(settings, "cbanner_womens", 2, product), timeout_seconds=180)
    monkeypatch.setattr(daily, "not_excluded_sku_condition", lambda *columns: columns[0] != "excluded")
    products = SimpleNamespace(engine=saved.engine, product_archive_brands=lambda: ["cbanner_womens", "another_brand"], _table_for_brand=lambda _: table)
    found = {(brand, item["id"]) for brand, item in daily.target_products(products, BUSINESS_DATE)}
    assert found == {("cbanner_womens", number) for number in (1, 5, 7)} | {("another_brand", number) for number in (1, 2, 5, 7)}


def test_preview_does_not_create_copywriting_table(monkeypatch):
    engine = create_engine("sqlite://")
    metadata = MetaData()
    table = product_table(metadata, "preview_products")
    metadata.create_all(engine)
    with engine.begin() as connection:
        connection.execute(table.insert().values(id=1, sku="TEST", launch_date="2026-09-22", image_path="image.png"))
    monkeypatch.setattr(daily, "not_excluded_sku_condition", lambda *columns: columns[0] != "excluded")
    products = SimpleNamespace(engine=engine, product_archive_brands=lambda: ["brand"], _table_for_brand=lambda _: table)
    assert len(daily.target_products(products, BUSINESS_DATE)) == 1
    assert not inspect(engine).has_table("product_copywriting")
    engine.dispose()


@pytest.mark.parametrize("status", ["pending", "running", "failed", "completed", "expired"])
def test_insert_only_claim_never_touches_an_existing_record(saved, settings, product, status):
    values = prepare_copywriting(settings, "cbanner_womens", 7, product)
    token = saved.claim(values, timeout_seconds=180)
    if status == "completed":
        saved.complete("cbanner_womens", 7, token, "人工编辑后生成的旧文案")
    elif status == "failed":
        saved.fail("cbanner_womens", 7, token, "旧错误", 502)
    elif status == "pending":
        with saved.engine.begin() as connection:
            connection.execute(update(PRODUCT_COPYWRITING_TABLE).values(status="pending"))
    elif status == "expired":
        with saved.engine.begin() as connection:
            connection.execute(update(PRODUCT_COPYWRITING_TABLE).values(lease_expires_at=datetime.now(timezone.utc) - timedelta(minutes=1)))
    before = saved.get("cbanner_womens", 7)
    assert saved.claim({**values, "input_prompt": "不应覆盖的新提示词"}, timeout_seconds=180, only_if_missing=True) is None
    assert saved.get("cbanner_womens", 7) == before


def test_insert_only_claim_is_atomic_under_concurrency(tmp_path, settings, product):
    engine = create_engine(f"sqlite:///{(tmp_path / 'claims.db').as_posix()}", connect_args={"check_same_thread": False})
    repository = ProductCopywritingRepository(engine)
    repository.create_tables()
    values = prepare_copywriting(settings, "cbanner_womens", 7, product)
    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(lambda _: repository.claim(values, timeout_seconds=180, only_if_missing=True), range(2)))
    assert sum(token is not None for token in results) == 1
    assert repository.get("cbanner_womens", 7)["attempt_count"] == 1
    engine.dispose()


@pytest.mark.parametrize("flag", ["retry_failed", "refresh_outdated_template", "force_regenerate"])
def test_insert_only_rejects_regeneration_flags(saved, settings, product, flag):
    with pytest.raises(ValueError):
        saved.claim(prepare_copywriting(settings, "cbanner_womens", 7, product), timeout_seconds=180, only_if_missing=True, **{flag: True})
    assert saved.get("cbanner_womens", 7) is None


def test_daily_generation_sends_image_once_and_preserves_success(saved, settings, product, monkeypatch):
    model = Mock(return_value="真实模型输出")
    monkeypatch.setattr(jobs, "request_doubao_copywriting", model)
    products = Mock(get_product=Mock(return_value=product))
    assert daily.generate_one(settings, products, saved, "cbanner_womens", 7, BUSINESS_DATE)["status"] == "completed"
    before = saved.get("cbanner_womens", 7)
    product["color"] = "黑色"
    assert daily.generate_one(settings, products, saved, "cbanner_womens", 7, BUSINESS_DATE)["reason"] == "existing_record"
    assert saved.get("cbanner_womens", 7) == before
    model.assert_called_once_with(settings, before["input_prompt"], image_data_url="data:image/png;base64," + base64.b64encode(IMAGE_BYTES).decode("ascii"))


@pytest.mark.parametrize("change,reason", [
    ({"image_path": None}, "missing_image"), ({"image_path": " \t "}, "missing_image"),
    ({"launch_date": "2026-09-15"}, "outside_scope"), ({"launch_date": "2026-09-23"}, "outside_scope"),
    ({"launch_date": "2026-09-16"}, "outside_scope"), ({"launch_date": "2026-09-19"}, "outside_scope"),
    ({"launch_date": None}, "outside_scope"),
])
def test_worker_rechecks_scope_and_never_inserts_for_skips(saved, settings, product, monkeypatch, change, reason):
    product.update(change)
    model = Mock()
    monkeypatch.setattr(jobs, "request_doubao_copywriting", model)
    products = Mock(get_product=Mock(return_value=product))
    assert daily.generate_one(settings, products, saved, "cbanner_womens", 7, BUSINESS_DATE)["reason"] == reason
    assert saved.get("cbanner_womens", 7) is None
    model.assert_not_called()


def test_race_with_manual_claim_never_calls_model_or_changes_record(saved, settings, product, monkeypatch):
    values = prepare_copywriting(settings, "cbanner_womens", 7, product)
    original_claim = saved.claim
    def manual_claim_race(*args, **kwargs):
        original_claim({**values, "input_prompt": "用户自定义提示词"}, timeout_seconds=180)
        return original_claim(*args, **kwargs)
    monkeypatch.setattr(saved, "claim", manual_claim_race)
    model = Mock()
    monkeypatch.setattr(jobs, "request_doubao_copywriting", model)
    products = Mock(get_product=Mock(return_value=product))
    assert daily.generate_one(settings, products, saved, "cbanner_womens", 7, BUSINESS_DATE)["reason"] == "existing_record"
    assert saved.get("cbanner_womens", 7)["input_prompt"] == "用户自定义提示词"
    model.assert_not_called()


def test_daily_failure_is_not_automatically_retried(saved, settings, product, monkeypatch):
    model = Mock(side_effect=RuntimeError("private-secret"))
    monkeypatch.setattr(jobs, "request_doubao_copywriting", model)
    products = Mock(get_product=Mock(return_value=product))
    assert daily.generate_one(settings, products, saved, "cbanner_womens", 7, BUSINESS_DATE)["status"] == "failed"
    before = saved.get("cbanner_womens", 7)
    assert daily.generate_one(settings, products, saved, "cbanner_womens", 7, BUSINESS_DATE)["reason"] == "existing_record"
    assert saved.get("cbanner_womens", 7) == before
    model.assert_called_once()
    assert "private-secret" not in before["last_error"]


class FakeStatuses:
    def __init__(self, successes=()):
        self.states = {name: "success" for name in successes}
        self.events = []

    def is_success(self, name, business_date):
        assert business_date == BUSINESS_DATE
        return self.states.get(name) == "success"

    def mark_running(self, name, business_date):
        self.states[name] = "running"
        self.events.append((name, "running"))

    def mark_finished(self, name, business_date, **kwargs):
        self.states[name] = kwargs["status"]
        self.events.append((name, kwargs["status"]))


@pytest.fixture
def workflow_clock(monkeypatch):
    monkeypatch.setattr(workflow, "business_today", lambda: BUSINESS_DATE)


def test_workflow_runs_dependencies_archive_then_generation(settings, monkeypatch, workflow_clock):
    statuses = FakeStatuses()
    sequence = []
    def run_import(module, task_name, log_file):
        sequence.append(module)
        statuses.states[module] = "success"
        return 0
    def generate(*args):
        assert statuses.is_success(workflow.PRODUCT_TASK_NAME, BUSINESS_DATE)
        sequence.append("copywriting")
        return {"target_count": 2, "completed": 2}
    monkeypatch.setattr(workflow, "run_import", run_import)
    monkeypatch.setattr(workflow, "run_daily_generation", generate)
    assert workflow.run_workflow(settings, statuses, BUSINESS_DATE) == 0
    assert sequence == ["import_price_daily", "import_gj_merged_product_info_daily", "sync_products_daily", "copywriting"]
    assert statuses.states[workflow.TASK_NAME] == "success"
    assert workflow.run_workflow(settings, statuses, BUSINESS_DATE) == 0
    assert len(sequence) == 4


def test_pending_sources_stop_archive_sync_and_model_generation(settings, monkeypatch, workflow_clock):
    statuses = FakeStatuses()
    importer = Mock(return_value=0)
    generator = Mock()
    monkeypatch.setattr(workflow, "run_import", importer)
    monkeypatch.setattr(workflow, "run_daily_generation", generator)
    assert workflow.run_workflow(settings, statuses, BUSINESS_DATE) == 0
    assert importer.call_count == 2
    generator.assert_not_called()
    assert statuses.states[workflow.TASK_NAME] == "skipped"


@pytest.mark.parametrize("exit_code", [0, 1])
def test_archive_failure_or_missing_success_marker_prevents_generation(settings, monkeypatch, workflow_clock, exit_code):
    statuses = FakeStatuses(module for module, _, _ in workflow.PREREQUISITES)
    monkeypatch.setattr(workflow, "run_import", Mock(return_value=exit_code))
    generator = Mock()
    monkeypatch.setattr(workflow, "run_daily_generation", generator)
    assert workflow.run_workflow(settings, statuses, BUSINESS_DATE) == 1
    generator.assert_not_called()


def test_resume_after_archive_success_does_not_import_again(settings, monkeypatch, workflow_clock):
    statuses = FakeStatuses([workflow.PRODUCT_TASK_NAME])
    importer = Mock()
    generator = Mock(return_value={"target_count": 1, "completed": 1})
    monkeypatch.setattr(workflow, "run_import", importer)
    monkeypatch.setattr(workflow, "run_daily_generation", generator)
    assert workflow.run_workflow(settings, statuses, BUSINESS_DATE) == 0
    importer.assert_not_called()
    generator.assert_called_once_with(settings, BUSINESS_DATE)


def test_generation_failure_does_not_undo_successful_archive(settings, monkeypatch, workflow_clock):
    statuses = FakeStatuses([workflow.PRODUCT_TASK_NAME])
    monkeypatch.setattr(workflow, "run_daily_generation", Mock(return_value={"target_count": 1, "failed": 1}))
    assert workflow.run_workflow(settings, statuses, BUSINESS_DATE) == 1
    assert statuses.states[workflow.PRODUCT_TASK_NAME] == "success"
    assert statuses.states[workflow.COPYWRITING_TASK_NAME] == "failed"


def test_generation_exception_is_sanitized_and_logged_in_both_statuses(settings, monkeypatch, workflow_clock, capsys):
    statuses = FakeStatuses([workflow.PRODUCT_TASK_NAME])
    monkeypatch.setattr(workflow, "run_daily_generation", Mock(side_effect=RuntimeError("test-secret")))
    assert workflow.run_workflow(settings, statuses, BUSINESS_DATE) == 1
    assert statuses.states[workflow.TASK_NAME] == "failed"
    assert statuses.states[workflow.COPYWRITING_TASK_NAME] == "failed"
    assert "test-secret" not in capsys.readouterr().out


def test_midnight_crossover_prevents_using_old_business_date(settings, monkeypatch):
    statuses = FakeStatuses([workflow.PRODUCT_TASK_NAME])
    monkeypatch.setattr(workflow, "business_today", lambda: BUSINESS_DATE + timedelta(days=1))
    generator = Mock()
    monkeypatch.setattr(workflow, "run_daily_generation", generator)
    assert workflow.run_workflow(settings, statuses, BUSINESS_DATE) == 1
    generator.assert_not_called()


def test_prerequisite_runner_uses_existing_logged_imports_without_force(monkeypatch):
    runner = Mock(return_value=SimpleNamespace(returncode=0))
    monkeypatch.setattr(workflow.subprocess, "run", runner)
    assert workflow.run_import("import_price_daily", "HedeImportPriceDaily", "import_price_daily.log") == 0
    command = runner.call_args.args[0]
    assert command.count("-m") == 2
    assert "--lookback-days" in command and "--allow-missing-current" in command
    assert "--force" not in command and "--execute" not in command
    assert runner.call_args.kwargs["env"]["PYTHONIOENCODING"] == "utf-8"


def test_daily_batch_no_candidates_does_not_require_model_key(settings, monkeypatch):
    settings.ark_api_key = None
    products = Mock()
    repository = Mock()
    monkeypatch.setattr(daily, "ProductRepository", Mock(return_value=products))
    monkeypatch.setattr(daily, "ProductCopywritingRepository", Mock(return_value=repository))
    monkeypatch.setattr(daily, "target_products", Mock(return_value=[]))
    worker = Mock()
    monkeypatch.setattr(daily, "generate_one", worker)
    result = daily.run_daily_generation(settings, BUSINESS_DATE)
    assert result == {"start_date": "2026-09-20", "end_date": "2026-09-22", "target_count": 0}
    worker.assert_not_called()
    products.engine.dispose.assert_called_once()


def test_daily_batch_summarizes_results_and_releases_engine(settings, monkeypatch):
    products = Mock()
    repository = Mock()
    monkeypatch.setattr(daily, "ProductRepository", Mock(return_value=products))
    monkeypatch.setattr(daily, "ProductCopywritingRepository", Mock(return_value=repository))
    monkeypatch.setattr(daily, "target_products", Mock(return_value=[("brand", {"id": 1}), ("brand", {"id": 2})]))
    worker = Mock(side_effect=lambda settings, products, saved, brand, product_id, business_date: {"status": "completed" if product_id == 1 else "failed"})
    monkeypatch.setattr(daily, "generate_one", worker)
    result = daily.run_daily_generation(settings, BUSINESS_DATE)
    assert result["target_count"] == 2 and result["completed"] == 1 and result["failed"] == 1
    assert worker.call_count == 2
    products.engine.dispose.assert_called_once()


def test_preview_cli_does_not_create_tables_or_execute_generation(settings, monkeypatch, capsys):
    products = Mock()
    monkeypatch.setattr(daily, "load_settings", Mock(return_value=settings))
    monkeypatch.setattr(daily, "business_today", lambda: BUSINESS_DATE)
    monkeypatch.setattr(daily, "ProductRepository", Mock(return_value=products))
    monkeypatch.setattr(daily, "target_products", Mock(return_value=[("brand", {"id": 1})]))
    generator = Mock()
    monkeypatch.setattr(daily, "run_daily_generation", generator)
    monkeypatch.setattr("sys.argv", ["generate_product_copywriting_daily"])
    assert daily.main() == 0
    generator.assert_not_called()
    output = capsys.readouterr().out
    assert '"execute": false' in output
    assert '"start_date": "2026-09-20"' in output
    assert '"end_date": "2026-09-22"' in output
    products.engine.dispose.assert_called_once()


def test_execute_cli_requires_successful_archive_sync(settings, monkeypatch):
    statuses = Mock()
    statuses.is_success.return_value = False
    monkeypatch.setattr(daily, "load_settings", Mock(return_value=settings))
    monkeypatch.setattr(daily, "business_today", lambda: BUSINESS_DATE)
    monkeypatch.setattr(daily, "ScheduledTaskStatusRepository", Mock(return_value=statuses))
    generator = Mock()
    monkeypatch.setattr(daily, "run_daily_generation", generator)
    monkeypatch.setattr("sys.argv", ["generate_product_copywriting_daily", "--execute"])
    assert daily.main() == 1
    generator.assert_not_called()
    statuses.engine.dispose.assert_called_once()


@pytest.mark.parametrize("acquired", [False, True])
def test_workflow_main_uses_session_lock_and_releases_it(settings, monkeypatch, acquired):
    connection = Mock()
    connection.execute.return_value.scalar_one.return_value = acquired
    statuses = Mock()
    class ConnectionContext:
        def __enter__(self):
            return connection
        def __exit__(self, *args):
            return False
    statuses.engine.connect.return_value.execution_options.return_value = ConnectionContext()
    monkeypatch.setattr(workflow, "load_settings", Mock(return_value=settings))
    monkeypatch.setattr(workflow, "ScheduledTaskStatusRepository", Mock(return_value=statuses))
    monkeypatch.setattr(workflow, "business_today", lambda: BUSINESS_DATE)
    runner = Mock(return_value=0)
    monkeypatch.setattr(workflow, "run_workflow", runner)
    assert workflow.main() == 0
    if acquired:
        runner.assert_called_once_with(settings, statuses, BUSINESS_DATE)
        assert "pg_advisory_unlock" in str(connection.execute.call_args.args[0])
    else:
        runner.assert_not_called()
        assert connection.execute.call_count == 1
    statuses.engine.dispose.assert_called_once()
