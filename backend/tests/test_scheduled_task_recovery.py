from datetime import datetime, timedelta, timezone
import os
import socket
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine, event, select

from api.routes.scheduled_tasks import list_scheduled_task_history, list_scheduled_task_runs
from domain.task_status_schema import SCHEDULED_TASK_RUN_TABLE
from storage import scheduled_task_recovery as recovery


NOW = datetime(2026, 10, 19, 5, 30, tzinfo=timezone.utc)


@pytest.fixture
def run_engine():
    engine = create_engine("sqlite://")
    event.listen(engine, "connect", lambda connection, record: connection.create_function("date_trunc", 2, lambda unit, value: value))
    SCHEDULED_TASK_RUN_TABLE.create(engine)
    rows = [
        (1, "price", "running", socket.gethostname(), 11, NOW - timedelta(hours=3)),
        (2, "price", "running", socket.gethostname(), 12, NOW - timedelta(hours=3)),
        (3, "price", "running", socket.gethostname(), 13, NOW - timedelta(hours=3)),
        (4, "price", "running", socket.gethostname(), 14, NOW - timedelta(seconds=30)),
        (5, "price", "running", "another-host", 15, NOW - timedelta(hours=3)),
        (6, "price", "success", socket.gethostname(), 16, NOW - timedelta(hours=3)),
        (7, "price", "running", socket.gethostname(), None, NOW - timedelta(hours=3)),
        (8, "other", "running", socket.gethostname(), 18, NOW - timedelta(hours=3)),
    ]
    with engine.begin() as connection:
        connection.execute(SCHEDULED_TASK_RUN_TABLE.insert(), [
            {"id": run_id, "task_name": task_name, "status": status, "host_name": host,
             "process_id": process_id, "started_at": started, "finished_at": None,
             "exit_code": 0 if status == "success" else None}
            for run_id, task_name, status, host, process_id, started in rows
        ])
    try:
        yield engine
    finally:
        engine.dispose()


def test_recovery_only_changes_confirmed_exited_local_old_processes(monkeypatch, run_engine):
    checked = []

    def process_state(process_id, started_at):
        checked.append(process_id)
        return {11: False, 12: True, 13: None, 18: False}[process_id]

    monkeypatch.setattr(recovery, "process_matches_run", process_state)
    assert recovery.reconcile_local_task_runs(run_engine, now=NOW, task_name="price") == 1
    assert checked == [11, 12, 13]
    with run_engine.connect() as connection:
        rows = {row["id"]: row for row in connection.execute(select(SCHEDULED_TASK_RUN_TABLE)).mappings()}
    assert rows[1]["status"] == "failed"
    assert rows[1]["exit_code"] == -1
    assert rows[1]["duration_ms"] is None
    assert rows[1]["error_summary"] == recovery.INTERRUPTED_RUN_MESSAGE
    assert rows[1]["finished_at"] == NOW.replace(tzinfo=None)
    assert all(rows[run_id]["status"] == "running" for run_id in (2, 3, 4, 5, 7, 8))
    assert rows[6]["status"] == "success"
    assert recovery.reconcile_local_task_runs(run_engine, now=NOW, task_name="price") == 0


def test_recovery_does_not_overwrite_concurrent_success(monkeypatch, run_engine):
    def completed_during_check(process_id, started_at):
        if process_id == 11:
            with run_engine.begin() as connection:
                connection.execute(SCHEDULED_TASK_RUN_TABLE.update().where(SCHEDULED_TASK_RUN_TABLE.c.id == 1).values(status="success", exit_code=0))
            return False
        return True

    monkeypatch.setattr(recovery, "process_matches_run", completed_during_check)
    assert recovery.reconcile_local_task_runs(run_engine, now=NOW) == 0
    with run_engine.connect() as connection:
        assert connection.execute(select(SCHEDULED_TASK_RUN_TABLE.c.status).where(SCHEDULED_TASK_RUN_TABLE.c.id == 1)).scalar_one() == "success"


def test_current_process_is_live_without_signalling_or_terminating_it():
    assert recovery.process_matches_run(os.getpid(), datetime.now(timezone.utc)) is True
    assert recovery.process_matches_run(0, datetime.now(timezone.utc)) is None


@pytest.mark.skipif(os.name != "nt", reason="Windows process creation identity check")
def test_pid_reuse_is_detected_by_creation_time():
    assert recovery.process_matches_run(os.getpid(), datetime(1970, 1, 1, tzinfo=timezone.utc)) is False


@pytest.mark.parametrize("endpoint", ["runs", "history"])
def test_task_queries_reconcile_interrupted_runs_before_returning_status(monkeypatch, run_engine, endpoint):
    request = SimpleNamespace(
        state=SimpleNamespace(current_user={"role_code": "super_admin"}),
        app=SimpleNamespace(state=SimpleNamespace(inventory_repository=SimpleNamespace(engine=run_engine))),
    )
    monkeypatch.setattr(recovery, "process_matches_run", lambda process_id, started_at: process_id != 11)
    if endpoint == "runs":
        result = list_scheduled_task_runs(request, run_date=NOW.date(), status="failed", query=None,
                                          latest_only=False, page=1, page_size=50)
    else:
        result = list_scheduled_task_history(request, task_name="price", limit=20)
    item = next(item for item in result["items"] if item["id"] == 1)
    assert item["status"] == "failed"
    assert item["error_summary"] == recovery.INTERRUPTED_RUN_MESSAGE
    if endpoint == "runs":
        assert result["total"] == 1
        assert result["summary"]["failed"] == 1
