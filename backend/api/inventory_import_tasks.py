from concurrent.futures import ThreadPoolExecutor
from hashlib import sha256
import json
import logging
from threading import BoundedSemaphore, Event, Thread

from fastapi import HTTPException

from api.operation_log_utils import actor_from_request
from storage.inventory_import_tasks import InventoryImportTasks


logger = logging.getLogger(__name__)


def configure_inventory_import_tasks(app, engine):
    app.state.inventory_import_tasks = InventoryImportTasks(engine)
    app.state.inventory_import_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="inventory-import")
    app.state.inventory_import_slots = BoundedSemaphore(1)


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
    return {
        "task_id": row["id"], "filename": row["filename"], "status": row["status"],
        "result": result, "error": row.get("error"), "error_status": row.get("error_status"),
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
    try:
        created = tasks.create(task_id, user_id, filename or "导入.xlsx", request_hash)
        if not created:
            return task_response(tasks.get(task_id, user_id))
        future = request.app.state.inventory_import_executor.submit(
            _run_import, tasks, task_id, run_import, request, filename, dict(form), content,
        )
        submitted = True
        future.add_done_callback(lambda _future: slots.release())
    except ValueError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    except Exception:
        if created:
            tasks.fail(task_id, "导入任务提交失败，本次未导入数据，请重新预检查后重试", 503)
        logger.exception("Failed to submit inventory import task %s", task_id)
        raise HTTPException(status_code=503, detail="导入任务提交失败，请稍后重试") from None
    finally:
        if not submitted:
            slots.release()
    return task_response(tasks.get(task_id, user_id))


def _run_import(tasks, task_id, run_import, request, filename, form, content):
    stopped = Event()

    def keep_alive():
        while not stopped.wait(15):
            try:
                tasks.heartbeat(task_id)
            except Exception:
                logger.exception("Failed to update inventory import heartbeat %s", task_id)

    heartbeat = Thread(target=keep_alive, name="inventory-import-heartbeat", daemon=True)
    try:
        if not tasks.start(task_id):
            return
        heartbeat.start()
        run_import(request, filename, form, content, task_id=task_id)
    except HTTPException as error:
        tasks.fail(task_id, str(error.detail), error.status_code)
    except Exception:
        logger.exception("Inventory import task %s failed", task_id)
        tasks.fail(task_id, "导入处理失败，本批次未提交。请联系管理员根据批次编号排查，不要选择覆盖已有数据。", 500)
    finally:
        stopped.set()
        if heartbeat.ident is not None:
            heartbeat.join(timeout=2)
