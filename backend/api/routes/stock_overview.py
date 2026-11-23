"""Daily inventory decisions, approved exit policies and weekly follow-up."""
from datetime import date, timedelta
from hashlib import sha256
import json
import logging
from typing import Literal

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.encoders import jsonable_encoder
from pydantic import BaseModel, ConfigDict, Field

from api.routes.stock_alerts import _validate_brand
from api.routes.stock_alert_tasks import _actor, _assignee, _log, _manager, _response
from api.operation_log_utils import write_operation_log
from api.stock_product_images import add_stock_product_images
from storage.stock_alert_rules import RuleConflict
from storage.stock_alert_tasks import TaskConflict, business_today
from storage.stock_overview import load_stock_overview, weekly_observations


router = APIRouter(prefix="/stock-alerts", tags=["存"])
logger = logging.getLogger(__name__)


def _overview(state, brand, today, refresh=False):
    def read_rules():
        return (state.stock_alert_rules.list_rules(brand), state.stock_replenishment_rules.list_rules(brand),
                state.stock_overview_policies.list_rules(brand))

    return load_stock_overview(state.repository, brand, today, refresh=refresh, read_rules=read_rules)


def _signature(row):
    return sha256(json.dumps(row, ensure_ascii=False, sort_keys=True, default=str).encode()).hexdigest()


@router.get("/overview")
def stock_overview(request: Request, brand: str = Query(min_length=1, max_length=100),
    kind: Literal["all", "zero", "slow", "replenish", "clearance", "review"] = "all",
    query: str = Query(default="", max_length=200), page: int = Query(default=1, ge=1), refresh: bool = False):
    _actor(request)
    _validate_brand(request, brand)
    today = business_today()
    state = request.app.state
    data, policies = _overview(state, brand, today, refresh)
    active = state.stock_alert_tasks.overview_active(brand)
    rows = data["recommendations"]
    filters = query.strip().casefold()
    counts = {key: 0 for key in ("zero", "slow", "replenish", "clearance", "review")}
    # Rows already have business priority order. Partition once instead of sorting
    # the entire matching brand again on every page.
    matching = ([], [], [])
    assignable, in_progress = 0, 0
    for row in rows:
        task = active.get((row["id"], row["kind"]))
        if not task and row["kind"] in {"replenish", "clearance"}:
            opposite = "replenish" if row["kind"] == "clearance" else "clearance"
            task = active.get((row["id"], opposite))
            if task:
                row = {**row, "reason": row["reason"] + "；已有相反的待办，先核对现有处理"}
        if row["kind"] != "review":
            assignable += task is None
            in_progress += task is not None
        counts[row["kind"]] += 1
        if (kind == "all" or kind == row["kind"]) and (not filters or any(
            filters in str(row.get(key) or "").casefold() for key in ("sku", "original_sku", "product_name", "color"))):
            matching[2 if row["kind"] == "review" else int(task is not None)].append((task, row))
    size = 25
    total = sum(map(len, matching))
    page = min(page, max(1, (total + size - 1) // size))
    offset, page_rows = (page - 1) * size, []
    for group in matching:
        if offset >= len(group):
            offset -= len(group)
            continue
        page_rows.extend(group[offset:offset + size - len(page_rows)])
        offset = 0
        if len(page_rows) == size:
            break
    items = [{**row, "task": task, "signature": _signature(row) if row["kind"] != "review" and not task else None}
             for task, row in page_rows]
    add_stock_product_images(request, items, brand=brand)
    return _response({**{key: value for key, value in data.items() if key != "recommendations"}, "policies": list(policies.values()), "items": items, "counts": counts,
                      "assignable": assignable, "in_progress": in_progress, "page": page, "page_size": size,
                      "total": total, "today": today})


@router.get("/overview/week")
def stock_overview_week(request: Request, brand: str = Query(min_length=1, max_length=100)):
    _actor(request)
    _validate_brand(request, brand)
    today = business_today()
    first = today - timedelta(days=today.weekday() + 7)
    last = first + timedelta(days=6)
    state = request.app.state
    counts, completed, clearance = state.stock_alert_tasks.overview_week(brand, first, last)
    observations = weekly_observations(state.repository, brand, first, last, completed, clearance)
    return _response({"start": first, "end": last, **counts, "completed_styles": len(completed), **observations})


class ExitPolicyWrite(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    brand: str = Field(min_length=1, max_length=100)
    year: str = Field(pattern=r"^(20|21)[0-9]{2}$")
    season: str = Field(min_length=1, max_length=100)
    sale_start: date | None = None
    exit_date: date
    lead_days: int = Field(ge=1, le=365)
    target_rate: int = Field(ge=1, le=100)
    channel: str = Field(min_length=1, max_length=100)
    version: int = Field(ge=0)


@router.put("/overview/rules")
def save_exit_policy(request: Request, body: ExitPolicyWrite):
    user = _actor(request)
    _manager(user)
    _validate_brand(request, body.brand)
    if body.sale_start and body.sale_start > body.exit_date:
        raise HTTPException(400, "再次开售日不能晚于退出日")
    try:
        request.app.state.stock_overview_policies.save(**body.model_dump(), user_id=user["id"])
    except RuleConflict as error:
        raise HTTPException(409, str(error)) from error
    try:
        write_operation_log(request, module="inventory", action="stock_overview_exit_policy_update",
                            entity_type="stock_overview_exit_policy", entity_label=f"{body.brand}/{body.year}/{body.season}",
                            summary="更新库存退出规则", after_data={**body.model_dump(mode="json"), "version": body.version + 1})
    except Exception:
        logger.exception("Exit policy saved, but operation log could not be written")
    return _response({"message": "退出规则已保存"})


class OverviewTaskCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    brand: str = Field(min_length=1, max_length=100)
    product_id: int = Field(gt=0)
    kind: Literal["zero", "slow", "replenish", "clearance"]
    signature: str = Field(pattern=r"^[0-9a-f]{64}$")
    assignee_id: int = Field(gt=0)
    due_date: date
    measures: str = Field(default="", max_length=2000)


@router.post("/tasks/from-overview")
def assign_overview_task(request: Request, body: OverviewTaskCreate):
    user = _actor(request)
    _manager(user)
    _validate_brand(request, body.brand)
    assignee = _assignee(request, body.assignee_id)
    today = business_today()
    if body.due_date < today:
        raise HTTPException(400, "处理期限不能早于今天（北京时间）")
    data, _ = _overview(request.app.state, body.brand, today)
    row = next((row for row in data["recommendations"] if row["id"] == body.product_id and row["kind"] == body.kind), None)
    if row is None or _signature(row) != body.signature:
        raise HTTPException(409, "建议依据已变化，请刷新库存经营总览后重试")
    if body.kind == "clearance" and body.due_date > date.fromisoformat(row["due_date"]):
        raise HTTPException(400, "清货待办期限不能晚于当前建议的最晚处理日")
    try:
        task = request.app.state.stock_alert_tasks.create(snapshot=jsonable_encoder(row), kind=body.kind,
            assignee=assignee, due_date=body.due_date, measures=body.measures.strip(), actor=user)
    except TaskConflict as error:
        raise HTTPException(409, str(error)) from error
    _log(request, "stock_alert_task_create", task)
    return _response({"item": task})
