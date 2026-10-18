from datetime import datetime, timedelta, timezone
from threading import Event
from time import monotonic, sleep
from types import SimpleNamespace
from unittest.mock import Mock

from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
import pytest
from sqlalchemy import create_engine, event, select, update
from sqlalchemy.pool import StaticPool

from api.inventory_import_tasks import configure_inventory_import_tasks, submit_inventory_import
from api.routes import inventory as routes
from domain.inventory_import_task_schema import INVENTORY_IMPORT_TASK_TABLE
from domain.inventory_schema import INVENTORY_TABLE, INVENTORY_DETAIL_TABLE, SUPPLIER_TABLE, WAREHOUSE_TABLE
from domain.inventory_template_import import TemplateDocument
from storage.inventory_import_tasks import InventoryImportTasks, complete_inventory_import
from storage.inventory_repository import InventoryRepository


@pytest.fixture
def setup_tasks():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    event.listen(engine, "connect", lambda connection, _record: connection.create_function("date_trunc", 2, lambda _unit, value: value))
    INVENTORY_IMPORT_TASK_TABLE.create(engine)
    app = FastAPI()
    configure_inventory_import_tasks(app, engine)
    app.include_router(routes.router)
    request = SimpleNamespace(app=app, state=SimpleNamespace(current_user={"id": 1}))
    yield engine, app, request, app.state.inventory_import_tasks
    app.state.inventory_import_executor.shutdown(wait=True)
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
