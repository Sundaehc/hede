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
from api.routes.auth import user_has_permission
from api.routes.stock_alert_tasks import (
    _actor, _assignee, _batch_response, _log, _manager, _response, _unique_ids,
)
from api.operation_log_utils import write_operation_log
from api.stock_product_images import add_stock_product_images
from storage.stock_alert_rules import RuleConflict
from storage.stock_alert_tasks import TaskConflict, business_today
from storage.stock_overview import load_stock_overview, weekly_observations
from storage.stock_portfolio_detail import load_portfolio_detail
from storage.stock_phase_two import recovery_summary
from domain.stock_portfolio import portfolio_page


router = APIRouter(prefix="/stock-alerts", tags=["存"])
logger = logging.getLogger(__name__)


def _overview(state, brand, today, refresh=False):
    def read_rules():
        return (state.stock_alert_rules.list_rules(brand), state.stock_replenishment_rules.list_rules(brand),
                state.stock_overview_policies.list_rules(brand))

    operating = getattr(state, "stock_operating", None)
    return load_stock_overview(state.repository, brand, today, refresh=refresh, read_rules=read_rules,
                               read_decisions=(lambda: operating.decisions(brand)) if operating else None)


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
    return _response({**{key: value for key, value in data.items() if key not in {"recommendations", "portfolio", "unobservable"}}, "policies": list(policies.values()), "items": items, "counts": counts,
                      "assignable": assignable, "in_progress": in_progress, "page": page, "page_size": size,
                      "total": total, "today": today})


@router.get("/overview/portfolio")
def stock_portfolio(request: Request, brand: str = Query(min_length=1, max_length=100),
    year: str = Query(default="", max_length=30), season: str = Query(default="", max_length=100),
    category: str = Query(default="", max_length=150), query: str = Query(default="", max_length=200),
    status: Literal["", "selling", "next_season", "size_imbalance", "clearance", "watch", "review", "confirmed"] = "",
    page: int = Query(default=1, ge=1), refresh: bool = False):
    _actor(request)
    _validate_brand(request, brand)
    data, _ = _overview(request.app.state, brand, business_today(), refresh)
    return _response({**portfolio_page(data["portfolio"], year=year, season=season, category=category,
                                       query=query, status=status, page=page),
                      "sources": data["sources"]})


@router.get("/overview/items/{product_id}")
def stock_portfolio_detail(request: Request, product_id: int, brand: str = Query(min_length=1, max_length=100)):
    user = _actor(request)
    _validate_brand(request, brand)
    state = request.app.state
    detail = load_portfolio_detail(
        state.repository, brand, product_id, state.stock_operating.decisions(brand),
        can_view_inventory=user_has_permission(user, "inventory.view"),
        can_view_purchases=user_has_permission(user, "purchase.view"), today=business_today(),
    )
    if detail is None:
        raise HTTPException(404, "该商品不在当前品牌的有效档案中")
    add_stock_product_images(request, detail["items"], brand=brand)
    return _response(detail)


class ClearanceWrite(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    brand: str = Field(min_length=1, max_length=100)
    product_id: int = Field(gt=0)
    confirmed: bool
    reason: str = Field(min_length=1, max_length=1000)
    version: int = Field(ge=0)


@router.put("/overview/clearance")
def save_clearance(request: Request, body: ClearanceWrite):
    user = _actor(request)
    _manager(user)
    _validate_brand(request, body.brand)
    state = request.app.state
    if not state.repository.get_products_by_ids(body.brand, [body.product_id]):
        raise HTTPException(404, "该商品不在当前品牌的有效档案中")
    try:
        decision = state.stock_operating.save_clearance(**body.model_dump(), user_id=user["id"])
    except RuleConflict as error:
        raise HTTPException(409, str(error)) from error
    try:
        write_operation_log(request, module="inventory", action="stock_clearance_decision",
                            entity_type="stock_clearance_decision", entity_id=body.product_id,
                            entity_label=f"{body.brand}/{body.product_id}",
                            summary="确认清仓" if body.confirmed else "解除清仓",
                            after_data=jsonable_encoder(decision))
    except Exception:
        logger.exception("Clearance decision saved, but operation log could not be written")
    return _response({"item": decision, "message": "已确认清仓" if body.confirmed else "已解除清仓"})


class AutoAssignmentWrite(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    brand: str = Field(min_length=1, max_length=100)
    kind: Literal["zero", "slow", "replenish", "clearance"]
    enabled: bool
    assignee_id: int = Field(gt=0)
    due_days: int = Field(ge=0, le=90)
    version: int = Field(ge=0)


@router.get("/overview/auto-assignment")
def get_auto_assignment(request: Request, brand: str = Query(min_length=1, max_length=100)):
    _manager(_actor(request))
    _validate_brand(request, brand)
    return _response({"items": request.app.state.stock_operating.assignments(brand)})


@router.put("/overview/auto-assignment")
def save_auto_assignment(request: Request, body: AutoAssignmentWrite):
    user = _actor(request)
    _manager(user)
    _validate_brand(request, body.brand)
    if body.enabled:
        _assignee(request, body.assignee_id)
    try:
        row = request.app.state.stock_operating.save_assignment(**body.model_dump(), user_id=user["id"])
    except RuleConflict as error:
        raise HTTPException(409, str(error)) from error
    return _response({"item": row, "message": "自动派办规则已保存"})


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
    with state.repository.engine.connect() as conn:
        recovery = recovery_summary(conn, brand, first, clearance)
    return _response({"start": first, "end": last, **counts, "completed_styles": len(completed), **observations, **recovery})


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


class OverviewTaskSelection(BaseModel):
    model_config = ConfigDict(extra="forbid")
    product_id: int = Field(gt=0)
    kind: Literal["zero", "slow", "replenish", "clearance"]
    signature: str = Field(pattern=r"^[0-9a-f]{64}$")


class OverviewAssignment(BaseModel):
    model_config = ConfigDict(extra="forbid")
    brand: str = Field(min_length=1, max_length=100)
    assignee_id: int = Field(gt=0)
    due_date: date
    measures: str = Field(default="", max_length=2000)


class OverviewTaskCreate(OverviewAssignment, OverviewTaskSelection):
    pass


class OverviewTaskBatchCreate(OverviewAssignment):
    items: list[OverviewTaskSelection] = Field(min_length=1, max_length=500)


def _validate_assignment(row, selection: OverviewTaskSelection, due_date: date):
    if row is None or _signature(row) != selection.signature:
        raise HTTPException(409, "建议依据已变化，请刷新库存经营总览后重试")
    if selection.kind == "clearance" and due_date > date.fromisoformat(row["due_date"]):
        raise HTTPException(400, "清货待办期限不能晚于当前建议的最晚处理日")


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
    _validate_assignment(row, body, body.due_date)
    try:
        task = request.app.state.stock_alert_tasks.create(snapshot=jsonable_encoder(row), kind=body.kind,
            assignee=assignee, due_date=body.due_date, measures=body.measures.strip(), actor=user)
    except TaskConflict as error:
        raise HTTPException(409, str(error)) from error
    _log(request, "stock_alert_task_create", task)
    return _response({"item": task})


@router.post("/tasks/batch-from-overview")
def assign_overview_tasks(request: Request, body: OverviewTaskBatchCreate):
    user = _actor(request)
    _manager(user)
    keys = [(item.product_id, item.kind) for item in body.items]
    _unique_ids(keys)
    _validate_brand(request, body.brand)
    assignee = _assignee(request, body.assignee_id)
    today = business_today()
    if body.due_date < today:
        raise HTTPException(400, "处理期限不能早于今天（北京时间）")

    state = request.app.state
    data, _ = _overview(state, body.brand, today)
    selected = set(keys)
    rows = {
        (row["id"], row["kind"]): row for row in data["recommendations"]
        if (row["id"], row["kind"]) in selected
    }
    entries, failed = [], []
    for item, key in zip(body.items, keys):
        row = rows.get(key)
        try:
            _validate_assignment(row, item, body.due_date)
        except HTTPException as error:
            reason = (
                "建议依据已变化，请刷新并重新勾选后再分配"
                if error.status_code == 409 else error.detail
            )
            failed.append({
                "id": f"{item.product_id}/{item.kind}",
                "label": row["sku"] if row else f"商品 #{item.product_id}",
                "reason": reason,
            })
        else:
            entries.append((jsonable_encoder(row), item.kind))

    saved, conflicts = state.stock_alert_tasks.create_many_by_kind(
        entries, assignee=assignee, due_date=body.due_date, measures=body.measures.strip(), actor=user,
    )
    failed.extend({
        "id": f"{item['id']}/{item['kind']}", "label": item["label"], "reason": item["reason"],
    } for item in conflicts)
    return _batch_response(
        request, "stock_overview_task_batch_create", len(keys), saved, failed,
        lambda item: f"{item['product_id']}/{item['kind']}",
    )
