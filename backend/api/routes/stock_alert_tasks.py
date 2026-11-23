"""In-app alert follow-up workflow; no background fact scans or external messages."""
from datetime import date
from decimal import Decimal
import logging
from typing import Annotated, Literal

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field

from api.operation_log_utils import write_operation_log
from api.stock_product_images import add_stock_product_images
from api.routes.auth import user_has_permission
from api.routes.stock_alerts import _validate_brand
from domain.stock_alerts import evaluate_alert, resolve_rule
from storage.stock_alert_facts import load_stock_alert_facts
from storage.stock_alert_tasks import TaskConflict, business_today


router = APIRouter(prefix="/stock-alerts/tasks", tags=["预警待办"])
logger = logging.getLogger(__name__)


def _actor(request):
    user = getattr(request.state, "current_user", None)
    if not user or not user.get("id"):
        raise HTTPException(401, "请先登录后处理预警待办")
    if not user_has_permission(user, "product.view"):
        raise HTTPException(403, "权限不足")
    return user


def _manager(user):
    if not user_has_permission(user, "product.manage"):
        raise HTTPException(403, "仅有商品管理权限的账户可以分配负责人和处理期限")


def _assignee(request, user_id):
    user = request.app.state.auth_repository.get_user(user_id)
    if not user or user.get("status") != "active" or not user_has_permission(user, "product.view"):
        raise HTTPException(400, "请选择已启用且有商品查看权限的负责人")
    return user


def _response(data):
    return JSONResponse(jsonable_encoder(data), headers={"Cache-Control": "no-store"})


def _log(request, action, item):
    try:
        write_operation_log(request, module="inventory", action=action, entity_type="stock_alert_task",
            entity_id=item["id"], entity_label=f"#{item['id']} {item['sku']}", summary="更新预警处理待办",
            after_data={key: item[key] for key in ("status", "assignee_id", "assignee_name", "due_date", "measures", "result", "version")})
    except Exception:
        logger.exception("Alert task saved with its history, but operation log could not be written")


class TaskCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    brand: str = Field(min_length=1, max_length=100)
    product_id: int = Field(gt=0)
    kind: Literal["zero", "slow"]
    assignee_id: int = Field(gt=0)
    due_date: date
    measures: str = Field(default="", max_length=2000)


class TaskChanges(BaseModel):
    model_config = ConfigDict(extra="forbid")
    assignee_id: int | None = Field(default=None, gt=0)
    due_date: date | None = None
    status: Literal["pending", "processing", "completed"] | None = None
    measures: str | None = Field(default=None, max_length=2000)
    result: str | None = Field(default=None, max_length=2000)


class TaskUpdate(TaskChanges):
    version: int = Field(ge=1)


class TaskBatchCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    brand: str = Field(min_length=1, max_length=100)
    kind: Literal["zero", "slow"]
    product_ids: list[Annotated[int, Field(gt=0)]] = Field(min_length=1, max_length=500)
    assignee_id: int = Field(gt=0)
    due_date: date
    measures: str = Field(default="", max_length=2000)


class TaskVersion(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: int = Field(gt=0)
    version: int = Field(ge=1)


class TaskBatchUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    items: list[TaskVersion] = Field(min_length=1, max_length=500)
    changes: TaskChanges


def _prepare_changes(request, user, values):
    if not values or any(value is None for value in values.values()):
        raise HTTPException(400, "请填写有效的处理内容")
    values = dict(values)
    if "assignee_id" in values or "due_date" in values:
        _manager(user)
    if "assignee_id" in values:
        assignee = _assignee(request, values["assignee_id"])
        values["assignee_name"] = assignee.get("display_name") or assignee["username"]
    for key in ("measures", "result"):
        if key in values:
            values[key] = values[key].strip()
    return values


def _validate_change(user, item, values):
    if not user_has_permission(user, "product.manage") and item["assignee_id"] != user["id"]:
        raise HTTPException(403, "只能处理分配给自己的预警待办")
    if "due_date" in values and values["due_date"] != item["due_date"] and values["due_date"] < business_today():
        raise HTTPException(400, "新的处理期限不能早于今天（北京时间）")
    exit_limit = (item.get("snapshot") or {}).get("due_date") if item.get("kind") == "clearance" else None
    if exit_limit and "due_date" in values and values["due_date"].isoformat() > exit_limit:
        raise HTTPException(400, "清货待办期限不能晚于建议的最晚处理日")
    if values.get("status") == "completed" and (
        not values.get("measures", item["measures"]).strip() or not values.get("result", item["result"]).strip()
    ):
        raise HTTPException(400, "完成前请填写处理措施和处理结果")


def _unique_ids(ids):
    if len(ids) != len(set(ids)):
        raise HTTPException(400, "批量操作中不能重复选择同一项")


def _batch_response(request, action, total, saved, failed, key):
    try:
        write_operation_log(request, module="inventory", action=action, entity_type="stock_alert_task",
            entity_label=f"批量操作 {total} 项", summary=f"预警待办批量操作：成功 {len(saved)} 项，失败 {len(failed)} 项",
            after_data={"task_ids": [item["id"] for item in saved], "failed": failed})
    except Exception:
        logger.exception("Batch tasks saved with history, but operation log could not be written")
    return _response({"total": total, "succeeded": [item[key] for item in saved], "failed": failed})


@router.get("/assignees")
def assignees(request: Request):
    _manager(_actor(request))
    return _response({"items": request.app.state.auth_repository.list_stock_alert_assignees()})


@router.get("/reminders")
def reminders(request: Request):
    user = _actor(request)
    return _response(request.app.state.stock_alert_tasks.reminders(user["id"]))


@router.get("")
def list_tasks(request: Request, scope: Literal["mine", "all"] = "mine",
    status: Literal["open", "overdue", "completed", "all"] = "open",
    brand: str = Query(default="", max_length=100), kind: Literal["", "zero", "slow", "replenish", "clearance"] = "",
    query: str = Query(default="", max_length=200), page: int = Query(default=1, ge=1),
    page_size: int = Query(default=25, ge=1, le=100)):
    user = _actor(request)
    result = request.app.state.stock_alert_tasks.list(
        user_id=user["id"], scope=scope, status=status, brand=brand, kind=kind, query=query, page=page, page_size=page_size)
    add_stock_product_images(request, result["items"], id_key="product_id")
    return _response(result)


@router.post("")
def create_task(request: Request, body: TaskCreate):
    user = _actor(request)
    _manager(user)
    _validate_brand(request, body.brand)
    assignee = _assignee(request, body.assignee_id)
    if body.due_date < business_today():
        raise HTTPException(400, "处理期限不能早于今天（北京时间）")
    facts = load_stock_alert_facts(request.app.state.repository, body.brand)
    source = next((row for row in facts["items"] if row["id"] == body.product_id), None)
    if not facts.get("ready") or not source or Decimal(source["available_quantity"]) <= 0:
        raise HTTPException(409, "商品当前不在有效预警中，请刷新预警清单后重试")
    rules = request.app.state.stock_alert_rules.list_rules(body.brand)
    snapshot = evaluate_alert(source, body.kind, resolve_rule(rules, body.kind, source["season"] or ""))
    if not snapshot["warning"]:
        raise HTTPException(409, "商品当前已不满足此类预警条件，请刷新预警清单后重试")
    snapshot.update(stock_date=facts.get("stock_date"), sales_end=facts.get("sales_end"))
    try:
        item = request.app.state.stock_alert_tasks.create(snapshot=jsonable_encoder(snapshot), kind=body.kind,
            assignee=assignee, due_date=body.due_date, measures=body.measures.strip(), actor=user)
    except TaskConflict as error:
        raise HTTPException(409, str(error)) from error
    _log(request, "stock_alert_task_create", item)
    return _response({"item": item})


@router.post("/batch-create")
def create_tasks(request: Request, body: TaskBatchCreate):
    user = _actor(request)
    _manager(user)
    _unique_ids(body.product_ids)
    _validate_brand(request, body.brand)
    assignee = _assignee(request, body.assignee_id)
    if body.due_date < business_today():
        raise HTTPException(400, "处理期限不能早于今天（北京时间）")
    facts = load_stock_alert_facts(request.app.state.repository, body.brand)
    rules = request.app.state.stock_alert_rules.list_rules(body.brand)
    sources = {item["id"]: item for item in facts["items"]}
    snapshots, failed = [], []
    for product_id in body.product_ids:
        source = sources.get(product_id)
        reason = None
        if not facts.get("ready") or source is None or Decimal(source["available_quantity"]) <= 0:
            reason = "商品当前不在有效预警中，请刷新预警清单"
        else:
            snapshot = evaluate_alert(source, body.kind, resolve_rule(rules, body.kind, source["season"] or ""))
            if not snapshot["warning"]:
                reason = "商品已不满足此类预警条件，请刷新预警清单"
            else:
                snapshot.update(stock_date=facts.get("stock_date"), sales_end=facts.get("sales_end"))
                snapshots.append(jsonable_encoder(snapshot))
        if reason:
            failed.append({"id": product_id, "label": source["sku"] if source else f"商品 #{product_id}", "reason": reason})
    saved, conflicts = request.app.state.stock_alert_tasks.create_many(snapshots, kind=body.kind,
        assignee=assignee, due_date=body.due_date, measures=body.measures.strip(), actor=user)
    return _batch_response(request, "stock_alert_task_batch_create", len(body.product_ids), saved, failed + conflicts, "product_id")


@router.post("/batch-update")
def update_tasks(request: Request, body: TaskBatchUpdate):
    user = _actor(request)
    ids = [item.id for item in body.items]
    _unique_ids(ids)
    values = _prepare_changes(request, user, body.changes.model_dump(exclude_unset=True))
    repo = request.app.state.stock_alert_tasks
    current = repo.get_many(ids)
    entries, failed = [], []
    for selection in body.items:
        item = current.get(selection.id)
        try:
            if item is None:
                raise HTTPException(404, "预警待办不存在")
            _validate_change(user, item, values)
        except HTTPException as error:
            failed.append({"id": selection.id, "label": item["sku"] if item else f"待办 #{selection.id}", "reason": str(error.detail)})
        else:
            entries.append({"id": selection.id, "label": item["sku"], "version": selection.version, "values": values})
    saved, conflicts = repo.save_many(entries, actor=user)
    return _batch_response(request, "stock_alert_task_batch_update", len(ids), saved, failed + conflicts, "id")


@router.get("/{task_id}")
def task_detail(request: Request, task_id: int):
    _actor(request)
    item = request.app.state.stock_alert_tasks.get(task_id)
    if item is None:
        raise HTTPException(404, "预警待办不存在")
    add_stock_product_images(request, [item], id_key="product_id")
    return _response({"item": item})


@router.get("/{task_id}/events")
def task_events(request: Request, task_id: int, page: int = Query(default=1, ge=1)):
    _actor(request)
    if request.app.state.stock_alert_tasks.get(task_id) is None:
        raise HTTPException(404, "预警待办不存在")
    return _response(request.app.state.stock_alert_tasks.events(task_id, page=page))


@router.patch("/{task_id}")
def update_task(request: Request, task_id: int, body: TaskUpdate):
    user = _actor(request)
    repo = request.app.state.stock_alert_tasks
    item = repo.get(task_id)
    if item is None:
        raise HTTPException(404, "预警待办不存在")
    values = _prepare_changes(request, user, body.model_dump(exclude_unset=True, exclude={"version"}))
    _validate_change(user, item, values)
    try:
        saved = repo.save(task_id, version=body.version, values=values, actor=user)
    except TaskConflict as error:
        raise HTTPException(409, str(error)) from error
    _log(request, "stock_alert_task_update", saved)
    add_stock_product_images(request, [saved], id_key="product_id")
    return _response({"item": saved})
