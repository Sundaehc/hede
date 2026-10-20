import asyncio
from datetime import date, datetime, timedelta, timezone
from concurrent.futures import Future
from threading import Event
from time import monotonic, sleep
from types import SimpleNamespace
from unittest.mock import MagicMock, Mock

from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
import pytest
from sqlalchemy import create_engine, event, select, update
from sqlalchemy.exc import DataError, OperationalError

from api.inventory_import_tasks import configure_inventory_import_tasks, submit_inventory_import
from api.routes import inventory as routes
from domain.inventory_import_task_schema import INVENTORY_IMPORT_TASK_TABLE
from domain.inventory_schema import INVENTORY_TABLE, INVENTORY_DETAIL_TABLE, SUPPLIER_TABLE, WAREHOUSE_TABLE
from domain.inventory_template_import import TemplateDocument
from storage.inventory_import_tasks import InventoryImportTasks, complete_inventory_import
from storage.inventory_repository import InventoryRepository


@pytest.fixture
def setup_tasks(tmp_path):
    engine = create_engine("sqlite:///" + (tmp_path / "inventory-import-tasks.sqlite3").as_posix(), connect_args={"check_same_thread": False})
    event.listen(engine, "connect", lambda connection, _record: connection.create_function("date_trunc", 2, lambda _unit, value: value))
    INVENTORY_IMPORT_TASK_TABLE.create(engine)
    app = FastAPI()
    configure_inventory_import_tasks(app, engine)
    app.include_router(routes.router)
    request = SimpleNamespace(app=app, state=SimpleNamespace(current_user={"id": 1}))
    yield engine, app, request, app.state.inventory_import_tasks
    app.state.inventory_import_executor.shutdown(wait=True)
    app.state.inventory_import_monitor.stop()
    engine.dispose()


def wait_terminal(tasks, task_id, user_id=1):
    deadline = monotonic() + 3
    while monotonic() < deadline:
        row = tasks.get(task_id, user_id)
        if row and row["status"] in {"succeeded", "failed"}:
            return row
        sleep(0.01)
    pytest.fail("Import task did not finish")


def finish(engine, task_id, result=None):
    with engine.begin() as connection:
        complete_inventory_import(connection, task_id, result or {"created": 1, "replaced": 0, "skipped": 0, "details": 2})


def test_submission_returns_while_work_continues_and_same_batch_never_runs_twice(setup_tasks):
    engine, app, request, tasks = setup_tasks
    started, release = Event(), Event()
    calls = []

    def run(*_args, task_id):
        calls.append(task_id)
        started.set()
        assert release.wait(3)
        finish(engine, task_id)

    task_id = "a" * 32
    try:
        result = submit_inventory_import(request, task_id, "test.xlsx", {}, b"data", run)
        assert result["status"] in {"queued", "running"}
        assert started.wait(2)
        again = submit_inventory_import(request, task_id, "test.xlsx", {}, b"data", run)
        assert again["task_id"] == task_id
        assert calls == [task_id]
        with pytest.raises(HTTPException) as error:
            submit_inventory_import(request, "b" * 32, "other.xlsx", {}, b"other", run)
        assert error.value.status_code == 429
    finally:
        release.set()
    assert wait_terminal(tasks, task_id)["status"] == "succeeded"
    again = submit_inventory_import(request, task_id, "test.xlsx", {}, b"data", run)
    assert again["result"]["created"] == 1
    assert calls == [task_id]


def test_batch_identity_and_owner_are_checked(setup_tasks):
    engine, _app, request, tasks = setup_tasks
    task_id = "a" * 32
    tasks.create(task_id, 1, "test.xlsx", "hash")
    assert tasks.get(task_id, 2) is None
    with pytest.raises(HTTPException) as error:
        submit_inventory_import(request, task_id, "different.xlsx", {}, b"data", Mock())
    assert error.value.status_code == 409
    request.state.current_user = {"id": 2}
    with pytest.raises(HTTPException) as error:
        routes.get_inventory_template_task(request, task_id)
    assert error.value.status_code == 404


def test_status_survives_repository_recreation_and_log_failure_after_commit(setup_tasks):
    engine, _app, request, tasks = setup_tasks

    def run(*_args, task_id):
        finish(engine, task_id)
        raise RuntimeError("operation log is unavailable after commit")

    task_id = "a" * 32
    submit_inventory_import(request, task_id, "test.xlsx", {}, b"data", run)
    assert wait_terminal(tasks, task_id)["status"] == "succeeded"
    assert InventoryImportTasks(engine).get(task_id, 1)["result"]["details"] == 2


@pytest.mark.parametrize("error,expected_status", [(HTTPException(400, "模板格式不正确"), 400), (RuntimeError("private database error"), 500)])
def test_worker_records_failure_without_exposing_internal_exception(setup_tasks, error, expected_status):
    _engine, _app, request, tasks = setup_tasks

    def run(*_args, **_kwargs):
        raise error

    task_id = "a" * 32
    submit_inventory_import(request, task_id, "test.xlsx", {}, b"data", run)
    row = wait_terminal(tasks, task_id)
    assert row["error_status"] == expected_status
    assert "private database error" not in row["error"]
    assert row["result"] is None


def test_abandoned_task_becomes_failed_and_cannot_commit(setup_tasks):
    engine, _app, _request, tasks = setup_tasks
    task_id = "a" * 32
    tasks.create(task_id, 1, "test.xlsx", "hash")
    tasks.start(task_id)
    with engine.begin() as connection:
        connection.execute(update(INVENTORY_IMPORT_TASK_TABLE).where(INVENTORY_IMPORT_TASK_TABLE.c.id == task_id).values(heartbeat_at=datetime.now(timezone.utc) - timedelta(minutes=3)))
    assert tasks.get(task_id, 1)["status"] == "failed"
    with pytest.raises(ValueError, match="未提交"):
        finish(engine, task_id)


def test_document_write_and_success_result_share_a_transaction(setup_tasks):
    engine, _app, _request, tasks = setup_tasks
    for table in [INVENTORY_TABLE, INVENTORY_DETAIL_TABLE, SUPPLIER_TABLE, WAREHOUSE_TABLE]:
        table.create(engine)
    repository = object.__new__(InventoryRepository)
    repository.engine = engine
    repository._prepare_record = lambda record: {**InventoryRepository._prepare_record(record), "id": 1}
    with engine.begin() as connection:
        connection.execute(SUPPLIER_TABLE.insert().values(id=1, brand="ni", name="供应商"))
        connection.execute(WAREHOUSE_TABLE.insert().values(id=1, name="仓库"))
    plan = {"date": "2026-10-16", "document_type": "进货单", "supplier": "供应商", "warehouse": "仓库", "handler": "测试", "summary": "测试导入", "source_workbook": "test.xlsx", "source_sheet": "data", "brand": "ni", "decision": None, "details": [{"id": 1, "product_code": "TEST", "quantity": 1, "amount": 10}]}
    task_id = "a" * 32
    tasks.create(task_id, 1, "test.xlsx", "hash")
    with pytest.raises(ValueError, match="未提交"):
        repository.import_template_documents([plan], task_id=task_id)
    with engine.connect() as connection:
        assert connection.execute(select(INVENTORY_TABLE.c.id)).first() is None
        assert connection.execute(select(INVENTORY_DETAIL_TABLE.c.id)).first() is None
    assert tasks.get(task_id, 1)["status"] == "queued"
    tasks.start(task_id)
    result = repository.import_template_documents([plan], task_id=task_id)
    assert tasks.get(task_id, 1)["status"] == "succeeded"
    assert tasks.get(task_id, 1)["result"] == result


def test_operation_log_failure_does_not_turn_committed_import_into_http_500(monkeypatch):
    document = TemplateDocument("one", "2026-10-16", "应付款增加", "供应商", "", "测试", "费用", [{"product_name": "包装费", "amount": "10"}])
    repository = SimpleNamespace(preview_template_documents=lambda _documents: {"conflicts": []}, import_template_documents=lambda _plans: {"created": 1, "replaced": 0, "skipped": 0, "details": 1})
    request = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(inventory_repository=repository)))
    monkeypatch.setattr(routes, "read_template_documents", lambda _content: ("accounting", "data", [document]))
    monkeypatch.setattr(routes, "_validate_inventory_template_master_data", Mock())
    monkeypatch.setattr(routes, "write_operation_log", Mock(side_effect=RuntimeError("logging failed")))
    result = routes._import_inventory_template(request, "test.xlsx", {}, b"data")
    assert result["created"] == 1


def test_task_endpoint_returns_202_and_status_does_not_cache(setup_tasks, monkeypatch):
    engine, app, _request, tasks = setup_tasks
    started, release = Event(), Event()

    def run(*_args, task_id):
        started.set()
        assert release.wait(3)
        finish(engine, task_id)

    monkeypatch.setattr(routes, "_import_inventory_template", run)
    task_id = "a" * 32
    try:
        with TestClient(app) as client:
            response = client.post("/inventory/import-template/tasks/" + task_id, files={"file": ("test.xlsx", b"data")})
            assert response.status_code == 202
            assert started.wait(2)
            status = client.get("/inventory/import-template/tasks/" + task_id)
            assert status.status_code == 200
            assert status.headers["cache-control"] == "no-store"
    finally:
        release.set()
    assert wait_terminal(tasks, task_id, user_id=None)["status"] == "succeeded"


def test_submission_failure_releases_capacity_and_records_no_commit(setup_tasks, monkeypatch):
    engine, app, request, tasks = setup_tasks
    original_submit = app.state.inventory_import_executor.submit
    monkeypatch.setattr(app.state.inventory_import_executor, "submit", Mock(side_effect=RuntimeError("executor stopped")))
    with pytest.raises(HTTPException) as error:
        submit_inventory_import(request, "a" * 32, "test.xlsx", {}, b"data", Mock())
    assert error.value.status_code == 503
    assert tasks.get("a" * 32, 1)["status"] == "failed"
    monkeypatch.setattr(app.state.inventory_import_executor, "submit", original_submit)
    submit_inventory_import(request, "b" * 32, "test.xlsx", {}, b"data", lambda *_args, task_id: finish(engine, task_id))
    assert wait_terminal(tasks, "b" * 32)["status"] == "succeeded"


def test_worker_start_failure_is_persisted_instead_of_leaving_a_queued_task(setup_tasks, monkeypatch):
    _engine, _app, request, tasks = setup_tasks
    monkeypatch.setattr(tasks, "start", Mock(side_effect=RuntimeError("cannot start")))
    run = Mock()
    submit_inventory_import(request, "a" * 32, "test.xlsx", {}, b"data", run)
    assert wait_terminal(tasks, "a" * 32)["status"] == "failed"
    run.assert_not_called()


def test_all_skipped_documents_complete_the_batch_without_writing_documents(setup_tasks, monkeypatch):
    engine, app, request, tasks = setup_tasks
    task_id = "a" * 32
    tasks.create(task_id, 1, "test.xlsx", "hash")
    tasks.start(task_id)
    app.state.inventory_repository = SimpleNamespace(engine=engine, preview_template_documents=lambda _documents: {"conflicts": [{"key": "one"}]})
    document = TemplateDocument("one", "2026-10-16", "应付款增加", "供应商", "", "测试", "费用", [{"product_name": "包装费", "amount": "10"}])
    monkeypatch.setattr(routes, "read_template_documents", lambda _content: ("accounting", "data", [document]))
    monkeypatch.setattr(routes, "_validate_inventory_template_master_data", Mock())
    result = routes._import_inventory_template(request, "test.xlsx", {"decisions": '{"one":{"action":"skip"}}'}, b"data", task_id=task_id)
    assert result["skipped"] == 1
    assert tasks.get(task_id, 1)["status"] == "succeeded"
    assert tasks.get(task_id, 1)["result"] == {"created": 0, "replaced": 0, "skipped": 1, "details": 0}


def test_invalid_task_identifier_is_rejected_before_scheduling(setup_tasks):
    _engine, app, _request, _tasks = setup_tasks
    with TestClient(app) as client:
        response = client.post("/inventory/import-template/tasks/invalid", files={"file": ("test.xlsx", b"data")})
    assert response.status_code == 400


def test_validation_failure_is_visible_in_status_operation_log_and_backend_log(setup_tasks, caplog):
    _engine, app, request, tasks = setup_tasks
    app.state.operation_log_repository = Mock()

    def run(*_args, **_kwargs):
        raise HTTPException(400, "第 18 行商品编码不存在")

    task_id = "a" * 32
    submit_inventory_import(request, task_id, "test.xlsx", {}, b"data", run)
    row = wait_terminal(tasks, task_id)
    app.state.inventory_import_executor.shutdown(wait=True)
    assert row["status"] == "failed"
    assert row["error"] == "第 18 行商品编码不存在"
    log = app.state.operation_log_repository.create_log.call_args.kwargs
    assert log["user"]["id"] == 1
    assert log["after_data"]["task_id"] == task_id
    assert log["after_data"]["status"] == "failed"
    assert task_id in caplog.text
    assert "第 18 行商品编码不存在" in caplog.text


def test_worker_returning_without_committed_result_is_not_left_running(setup_tasks):
    _engine, _app, request, tasks = setup_tasks
    task_id = "a" * 32
    submit_inventory_import(request, task_id, "test.xlsx", {}, b"data", Mock())
    row = wait_terminal(tasks, task_id)
    assert row["status"] == "failed"
    assert "未确认成功提交" in row["error"]


def test_failure_status_is_retried_after_a_transient_database_error(setup_tasks, monkeypatch):
    _engine, _app, request, tasks = setup_tasks
    original_fail = tasks.fail
    calls = []

    def fail(*args):
        calls.append(args)
        if len(calls) == 1:
            raise RuntimeError("database temporarily unavailable")
        return original_fail(*args)

    monkeypatch.setattr(tasks, "fail", fail)
    task_id = "a" * 32
    submit_inventory_import(request, task_id, "test.xlsx", {}, b"data", Mock(side_effect=HTTPException(400, "模板无效")))
    assert wait_terminal(tasks, task_id)["error"] == "模板无效"
    assert len(calls) == 2


def test_failed_status_is_recovered_by_monitor_after_database_returns(setup_tasks, monkeypatch, caplog):
    _engine, app, request, tasks = setup_tasks
    task_id = "a" * 32
    original_fail = tasks.fail
    monkeypatch.setattr(tasks, "fail", Mock(side_effect=RuntimeError("database offline")))
    submit_inventory_import(request, task_id, "test.xlsx", {}, b"data", Mock(side_effect=HTTPException(400, "模板错误")))
    app.state.inventory_import_executor.shutdown(wait=True)
    assert tasks.get(task_id, 1)["status"] == "running"
    assert task_id in app.state.inventory_import_monitor.pending_failures
    assert "awaiting database recovery" in caplog.text
    monkeypatch.setattr(tasks, "fail", original_fail)
    app.state.inventory_import_monitor.reconcile()
    assert tasks.get(task_id, 1)["status"] == "failed"
    assert tasks.get(task_id, 1)["error"] == "模板错误"
    assert not app.state.inventory_import_monitor.pending_failures


def test_stale_task_is_detected_without_a_browser_status_request(setup_tasks, caplog):
    engine, app, _request, tasks = setup_tasks
    task_id = "a" * 32
    tasks.create(task_id, 1, "test.xlsx", "hash")
    tasks.start(task_id)
    with engine.begin() as connection:
        connection.execute(update(INVENTORY_IMPORT_TASK_TABLE).where(INVENTORY_IMPORT_TASK_TABLE.c.id == task_id).values(heartbeat_at=datetime.now(timezone.utc) - timedelta(minutes=3)))
    app.state.operation_log_repository = Mock()
    app.state.inventory_import_monitor.reconcile()
    with engine.connect() as connection:
        row = connection.execute(select(INVENTORY_IMPORT_TASK_TABLE).where(INVENTORY_IMPORT_TASK_TABLE.c.id == task_id)).mappings().one()
        assert row["status"] == "failed"
        assert row["finished_at"] is not None
    assert app.state.operation_log_repository.create_log.call_args.kwargs["after_data"]["task_id"] == task_id
    assert "interrupted" in caplog.text
    with pytest.raises(ValueError, match="未提交"):
        finish(engine, task_id)


@pytest.mark.parametrize("cancelled", [False, True])
def test_future_exception_or_cancellation_is_observed_and_releases_capacity(setup_tasks, monkeypatch, cancelled):
    _engine, app, request, tasks = setup_tasks
    future = Future()
    monkeypatch.setattr(app.state.inventory_import_executor, "submit", Mock(return_value=future))
    task_id = "a" * 32
    submit_inventory_import(request, task_id, "test.xlsx", {}, b"data", Mock())
    if cancelled:
        future.cancel()
    else:
        future.set_exception(RuntimeError("worker escaped"))
    assert tasks.get(task_id, 1)["status"] == "failed"
    assert app.state.inventory_import_slots.acquire(blocking=False)
    app.state.inventory_import_slots.release()


def test_failure_operation_log_error_does_not_hide_task_failure(setup_tasks):
    _engine, app, request, tasks = setup_tasks
    app.state.operation_log_repository = Mock()
    app.state.operation_log_repository.create_log.side_effect = RuntimeError("audit unavailable")
    task_id = "a" * 32
    submit_inventory_import(request, task_id, "test.xlsx", {}, b"data", Mock(side_effect=HTTPException(400, "模板错误")))
    assert wait_terminal(tasks, task_id)["error"] == "模板错误"


def test_monitor_starts_reconciles_and_stops(setup_tasks):
    _engine, app, _request, _tasks = setup_tasks
    monitor = app.state.inventory_import_monitor
    reconciled = Event()
    monitor.reconcile = reconciled.set
    monitor.start()
    monitor.start()
    assert reconciled.wait(2)
    monitor.stop()
    assert not monitor.thread.is_alive()
    reconciled.clear()
    monitor.start()
    assert reconciled.wait(2)
    monitor.stop()
    assert not monitor.thread.is_alive()


@pytest.mark.parametrize("sqlstate,reason", [
    ("55P03", "锁等待超时"),
    ("57014", "执行超时"),
    ("40P01", "死锁"),
    ("08006", "数据库访问异常"),
])
def test_database_failure_reports_safe_reason_and_batch_identifier(setup_tasks, sqlstate, reason, caplog):
    _engine, app, request, tasks = setup_tasks
    database_error = RuntimeError("private database host and query parameters")
    database_error.sqlstate = sqlstate
    error = OperationalError("private sql", {}, database_error)
    task_id = "a" * 32
    submit_inventory_import(request, task_id, "test.xlsx", {}, b"data", Mock(side_effect=error))
    row = wait_terminal(tasks, task_id)
    assert row["error_status"] == 503
    assert reason in row["error"]
    assert "private" not in row["error"]
    assert task_id in caplog.text
    app.state.inventory_import_executor.shutdown(wait=True)


def test_numeric_overflow_reports_data_range_instead_of_database_outage(setup_tasks, caplog):
    _engine, app, request, tasks = setup_tasks
    database_error = RuntimeError("private sql and parameters")
    database_error.sqlstate = "22003"
    error = DataError("private sql", {}, database_error)
    task_id = "a" * 32

    submit_inventory_import(request, task_id, "test.xlsx", {}, b"data", Mock(side_effect=error))
    row = wait_terminal(tasks, task_id)
    app.state.inventory_import_executor.shutdown(wait=True)

    assert row["error_status"] == 400
    assert "超出数据库字段范围" in row["error"]
    assert "本批次未提交" in row["error"]
    assert "不同摘要拆分单据" in row["error"]
    assert "数据库访问异常" not in row["error"]
    assert "private" not in row["error"]
    assert row["result"] is None
    assert task_id in caplog.text


def test_monitor_does_not_fail_live_or_completed_batches(setup_tasks):
    engine, app, _request, tasks = setup_tasks
    for task_id in ("a" * 32, "b" * 32):
        tasks.create(task_id, 1, "test.xlsx", "hash")
        tasks.start(task_id)
    finish(engine, "b" * 32)
    app.state.inventory_import_monitor.reconcile()
    assert tasks.get("a" * 32, 1)["status"] == "running"
    assert tasks.get("b" * 32, 1)["status"] == "succeeded"


def test_pending_failure_cannot_overwrite_a_committed_success(setup_tasks, monkeypatch):
    engine, app, request, tasks = setup_tasks
    task_id = "a" * 32
    tasks.create(task_id, 1, "test.xlsx", "hash")
    tasks.start(task_id)
    original_fail = tasks.fail
    monkeypatch.setattr(tasks, "fail", Mock(side_effect=RuntimeError("status unavailable")))
    app.state.inventory_import_monitor.fail(request, task_id, "test.xlsx", "状态未知", 500)
    finish(engine, task_id)
    monkeypatch.setattr(tasks, "fail", original_fail)
    app.state.inventory_import_monitor.reconcile()
    assert tasks.get(task_id, 1)["status"] == "succeeded"
    assert not app.state.inventory_import_monitor.pending_failures


def test_application_lifecycle_starts_and_stops_monitor(monkeypatch):
    from api import app as app_module

    monkeypatch.setattr(app_module, "_warm_default_product_goods_page", Mock())
    app = FastAPI()
    app.state.inventory_import_monitor = Mock()
    app.state.inventory_import_executor = Mock()

    async def exercise():
        async with app_module._app_lifespan(app):
            app.state.inventory_import_monitor.start.assert_called_once()
            app.state.inventory_import_monitor.stop.assert_not_called()

    asyncio.run(exercise())
    app.state.inventory_import_executor.shutdown.assert_called_once_with(wait=False, cancel_futures=True)
    app.state.inventory_import_monitor.stop.assert_called_once()


def test_background_validation_error_is_returned_by_status_api(setup_tasks, monkeypatch):
    _engine, app, _request, tasks = setup_tasks
    monkeypatch.setattr(routes, "_import_inventory_template", Mock(side_effect=HTTPException(400, "第 18 行商品编码不存在")))
    task_id = "a" * 32
    with TestClient(app) as client:
        response = client.post("/inventory/import-template/tasks/" + task_id, files={"file": ("test.xlsx", b"data")})
        assert response.status_code == 202
        wait_terminal(tasks, task_id, user_id=None)
        status = client.get("/inventory/import-template/tasks/" + task_id)
        assert status.status_code == 200
        assert status.json()["status"] == "failed"
        assert "第 18 行商品编码不存在" in status.json()["error"]
        assert task_id in status.json()["error"]
        assert status.json()["error_status"] == 400
        assert status.headers["cache-control"] == "no-store"


def test_background_write_error_rolls_back_an_overwrite_and_is_reported(setup_tasks):
    engine, app, request, tasks = setup_tasks
    for table in (INVENTORY_TABLE, INVENTORY_DETAIL_TABLE, SUPPLIER_TABLE, WAREHOUSE_TABLE):
        table.create(engine)
    with engine.begin() as connection:
        connection.execute(SUPPLIER_TABLE.insert().values(id=1, brand="ni", name="供应商"))
        connection.execute(WAREHOUSE_TABLE.insert().values(id=1, name="仓库"))
        connection.execute(INVENTORY_TABLE.insert().values(
            id=1, document_number="JHD-1", date="2026-10-16", date_value=date(2026, 10, 16),
            document_type="进货单", supplier="供应商", warehouse="仓库", handler="原经手人", summary="原摘要",
        ))
        connection.execute(INVENTORY_DETAIL_TABLE.insert().values(id=1, document_id=1, product_code="OLD", quantity=3, amount=30))
    repository = object.__new__(InventoryRepository)
    repository.engine = engine
    plan = {
        "date": "2026-10-16", "document_type": "进货单", "supplier": "供应商", "warehouse": "仓库",
        "handler": "新经手人", "summary": "原摘要", "source_workbook": "test.xlsx", "source_sheet": "data", "brand": "ni",
        "decision": "overwrite", "details": [{"id": 2, "product_code": "NEW", "quantity": 2, "amount": 20}],
    }

    def fail_after_replacement(_connection, _cursor, statement, _parameters, _context, _executemany):
        if statement.startswith("INSERT INTO " + INVENTORY_DETAIL_TABLE.name):
            raise RuntimeError("controlled write failure")

    event.listen(engine, "before_cursor_execute", fail_after_replacement)
    task_id = "a" * 32
    submit_inventory_import(request, task_id, "test.xlsx", {}, b"data", lambda *_args, task_id: repository.import_template_documents([plan], task_id=task_id))
    row = wait_terminal(tasks, task_id)
    app.state.inventory_import_executor.shutdown(wait=True)
    assert row["status"] == "failed"
    assert row["result"] is None
    with engine.connect() as connection:
        record = connection.execute(select(INVENTORY_TABLE)).mappings().one()
        detail = connection.execute(select(INVENTORY_DETAIL_TABLE)).mappings().one()
    assert record["document_number"] == "JHD-1"
    assert record["handler"] == "原经手人"
    assert detail["product_code"] == "OLD"
    assert detail["quantity"] == 3


def test_background_postgresql_write_limits_are_local_to_import_transaction():
    repository = object.__new__(InventoryRepository)
    connection = Mock()
    connection.dialect.name = "postgresql"
    repository.engine = MagicMock()
    repository.engine.begin.return_value.__enter__.return_value = connection

    class StopAtLock(Exception):
        pass

    statements = []

    def execute(statement):
        statements.append(str(statement))
        if "pg_advisory_xact_lock" in str(statement):
            raise StopAtLock

    connection.execute.side_effect = execute
    with pytest.raises(StopAtLock):
        repository.import_template_documents([], task_id="a" * 32)
    assert statements == [
        "SET LOCAL lock_timeout = '30s'", "SET LOCAL statement_timeout = '10min'", "SELECT pg_advisory_xact_lock(42917001)",
    ]
    statements.clear()
    with pytest.raises(StopAtLock):
        repository.import_template_documents([])
    assert statements == ["SELECT pg_advisory_xact_lock(42917001)"]
