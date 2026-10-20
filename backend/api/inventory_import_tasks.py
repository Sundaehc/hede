from concurrent.futures import ThreadPoolExecutor
from hashlib import sha256
import json
import logging
from threading import BoundedSemaphore, Event, Lock, Thread
from types import SimpleNamespace

from fastapi import HTTPException
from sqlalchemy.exc import SQLAlchemyError

from api.operation_log_utils import actor_from_request, write_operation_log
from storage.inventory_import_tasks import InventoryImportTasks


logger = logging.getLogger(__name__)


class InventoryImportMonitor:
    def __init__(self, app, tasks):
        self.app = app
        self.tasks = tasks
        self.stopped = Event()
        self.lock = Lock()
        self.pending_failures = {}
        self.thread = None

    def start(self):
        if self.thread is None or not self.thread.is_alive():
            self.stopped.clear()
            self.thread = Thread(target=self._watch, name="inventory-import-monitor", daemon=True)
            self.thread.start()

    def stop(self):
        self.stopped.set()
        if self.thread is not None:
            self.thread.join(timeout=2)

    def fail(self, request, task_id, filename, message, status_code):
        for attempt in range(3):
            try:
                changed = self.tasks.fail(task_id, message, status_code)
                with self.lock:
                    self.pending_failures.pop(task_id, None)
                if changed:
                    logger.error("Inventory import task %s failed: filename=%s status=%s reason=%s", task_id, filename, status_code, message)
                    self._audit_failure(request, task_id, filename, message)
                return
            except Exception:
                logger.exception("Failed to persist inventory import failure %s (attempt %s/3)", task_id, attempt + 1)
        with self.lock:
            failure_request = SimpleNamespace(app=self.app, state=SimpleNamespace(current_user=dict(actor_from_request(request) or {})))
            self.pending_failures[task_id] = (failure_request, filename, message, status_code)
        logger.critical("Inventory import task %s failure is awaiting database recovery; do not reimport", task_id)

    def reconcile(self):
        with self.lock:
            pending = list(self.pending_failures.items())
        for task_id, (request, filename, message, status_code) in pending:
            self.fail(request, task_id, filename, message, status_code)
        for row in self.tasks.expire_stale():
            request = SimpleNamespace(app=self.app, state=SimpleNamespace(current_user={"id": row["user_id"]}))
            self._audit_failure(request, row["id"], row["filename"], row["error"])

    def _audit_failure(self, request, task_id, filename, message):
        try:
            write_operation_log(
                request, module="inventory", action="import", entity_type="inventory_record",
                entity_label=filename or "模板导入", summary=f"模板导入失败：{message}（批次 {task_id}）",
                after_data={"task_id": task_id, "filename": filename, "status": "failed", "error": message},
            )
        except Exception:
            logger.exception("Failed to write inventory import failure operation log %s", task_id)

    def _watch(self):
        while not self.stopped.is_set():
            try:
                self.reconcile()
            except Exception:
                logger.exception("Inventory import monitor failed; will retry")
            if self.stopped.wait(15):
                break


def configure_inventory_import_tasks(app, engine):
    app.state.inventory_import_tasks = InventoryImportTasks(engine)
    app.state.inventory_import_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="inventory-import")
    app.state.inventory_import_slots = BoundedSemaphore(1)
    app.state.inventory_import_monitor = InventoryImportMonitor(app, app.state.inventory_import_tasks)


def task_user_id(request):
    user = actor_from_request(request)
    return user.get("id") if user else None


def task_response(row):
    result = row.get("result")
    if result:
        result = {**result, "message": (
            f"导入完成：新增 {result['created']} 条，覆盖 {result['replaced']} 条，"
            f"取消 {result['skipped']} 条，明细 {result['details']} 条"
        )}
    error = row.get("error")
    if row["status"] == "failed":
        error = f"{error or '导入失败，请联系管理员核对批次结果'}（批次编号：{row['id']}）"
    return {
        "task_id": row["id"], "filename": row["filename"], "status": row["status"],
        "result": result, "error": error, "error_status": row.get("error_status"),
    }


def submit_inventory_import(request, task_id, filename, form, content, run_import):
    tasks = getattr(request.app.state, "inventory_import_tasks", None)
    if tasks is None:
        raise HTTPException(status_code=503, detail="后台导入服务尚未初始化，请联系管理员重启后端")
    user_id = task_user_id(request)
    request_hash = sha256(content + json.dumps({
        "filename": filename, "brand": str(form.get("brand") or ""),
        "decisions": str(form.get("decisions") or "{}"),
    }, sort_keys=True).encode()).hexdigest()
    existing = tasks.get(task_id, user_id)
    if existing:
        if existing["request_hash"] != request_hash:
            raise HTTPException(status_code=409, detail="批次编号与文件不匹配，请重新选择文件")
        return task_response(existing)
    slots = request.app.state.inventory_import_slots
    if not slots.acquire(blocking=False):
        raise HTTPException(status_code=429, detail="已有导入任务正在处理，请等待完成后再提交")
    created = False
    submitted = False
    monitor = request.app.state.inventory_import_monitor
    try:
        created = tasks.create(task_id, user_id, filename or "导入.xlsx", request_hash)
        if not created:
            return task_response(tasks.get(task_id, user_id))
        future = request.app.state.inventory_import_executor.submit(
            _run_import, tasks, task_id, run_import, request, filename, dict(form), content,
        )
        submitted = True
        def finished(completed):
            try:
                if completed.cancelled():
                    monitor.fail(request, task_id, filename, "导入任务在开始前被取消，本批次未提交，请重新预检查后导入。", 503)
                elif error := completed.exception():
                    logger.error("Inventory import worker %s exited unexpectedly", task_id, exc_info=(type(error), error, error.__traceback__))
                    monitor.fail(request, task_id, filename, "后台导入任务异常退出，请核对批次结果后重新预检查。", 500)
            except Exception:
                logger.exception("Failed to finalize inventory import worker %s", task_id)
            finally:
                slots.release()

        future.add_done_callback(finished)
    except ValueError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    except Exception:
        if created:
            monitor.fail(request, task_id, filename, "导入任务提交失败，本次未导入数据，请重新预检查后重试", 503)
        logger.exception("Failed to submit inventory import task %s", task_id)
        raise HTTPException(status_code=503, detail="导入任务提交失败，请稍后重试") from None
    finally:
        if not submitted:
            slots.release()
    return task_response(tasks.get(task_id, user_id))


def _run_import(tasks, task_id, run_import, request, filename, form, content):
    stopped = Event()
    monitor = request.app.state.inventory_import_monitor

    def keep_alive():
        while not stopped.wait(15):
            try:
                if not tasks.heartbeat(task_id):
                    logger.error("Inventory import heartbeat stopped for inactive task %s", task_id)
                    return
            except Exception:
                logger.exception("Failed to update inventory import heartbeat %s", task_id)

    heartbeat = Thread(target=keep_alive, name="inventory-import-heartbeat", daemon=True)
    try:
        if not tasks.start(task_id):
            monitor.fail(request, task_id, filename, "导入任务未能开始，请核对批次状态后重新预检查。", 503)
            return
        heartbeat.start()
        logger.info("Inventory import task %s started: user=%s filename=%s", task_id, task_user_id(request), filename)
        run_import(request, filename, form, content, task_id=task_id)
        row = tasks.get(task_id, task_user_id(request))
        if row is None or row["status"] != "succeeded":
            monitor.fail(request, task_id, filename, "导入处理已退出，但未确认成功提交，请核对批次后重新预检查。", 500)
        else:
            logger.info("Inventory import task %s succeeded: result=%s", task_id, row["result"])
    except HTTPException as error:
        monitor.fail(request, task_id, filename, str(error.detail), error.status_code)
    except Exception as error:
        logger.exception("Inventory import task %s failed", task_id)
        if isinstance(error, SQLAlchemyError):
            sqlstate = getattr(getattr(error, "orig", None), "sqlstate", None)
            if sqlstate == "22003":
                monitor.fail(
                    request, task_id, filename,
                    "数量、单价、金额或单据汇总超出数据库字段范围，本批次未提交。"
                    "请核对数据，必要时使用不同摘要拆分单据，再重新预检查后导入。", 400,
                )
                return
            reason = {
                "55P03": "数据库锁等待超时",
                "57014": "数据库执行超时或查询被取消",
                "40P01": "数据库并发冲突（死锁）",
            }.get(sqlstate, "数据库访问异常")
            monitor.fail(request, task_id, filename, reason + "，请联系管理员根据批次编号核对结果后重新预检查，不要直接重复导入。", 503)
        else:
            monitor.fail(request, task_id, filename, "导入处理失败，请联系管理员根据批次编号核对结果，不要重复导入或覆盖已有数据。", 500)
    finally:
        stopped.set()
        if heartbeat.ident is not None:
            heartbeat.join(timeout=2)
