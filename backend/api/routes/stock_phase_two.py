"""On-demand inventory planning and weekly clearance review."""
from datetime import date, timedelta
from decimal import Decimal
import logging
from typing import Annotated, Literal

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.encoders import jsonable_encoder
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import insert, inspect, select, text
from sqlalchemy.exc import IntegrityError

from api.operation_log_utils import write_operation_log
from api.routes.auth import user_has_permission
from api.routes.stock_alerts import _validate_brand
from api.routes.stock_alert_tasks import _actor, _manager, _response
from domain.stock_phase_two import allocate, choose_weights, forecast, reliable_transit
from domain.stock_portfolio import replenishment_block
from storage.stock_alert_tasks import business_today
from storage.stock_overview import weekly_observations
from storage.stock_phase_two import (
    ARRIVALS, BASELINES, CAMPAIGNS, ORDER_LINKS, RECOVERY, SCOPED_BASELINES, arrival_board, campaigns, planning_facts, recovery_summary, save_record,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/stock-alerts/planning", tags=["存"])
QuantityMap = dict[Annotated[str, Field(min_length=1, max_length=80)], Annotated[int, Field(strict=True, ge=0, le=1_000_000)]]


def _context(request, brand):
    user = _actor(request)
    _validate_brand(request, brand)
    return user, request.app.state


def _finance(user):
    return user.get("role_code") == "super_admin" or user.get("department_code") == "财务部"


def _require(user, permission):
    if not user_has_permission(user, permission):
        raise HTTPException(403, "无权确认采购到货")


def _log(request, action, brand, label, record):
    try:
        write_operation_log(request, module="inventory", action=action, entity_type="stock_planning",
                            entity_label=f"{brand}/{label}", summary=label, after_data=jsonable_encoder(record))
    except Exception:
        logger.exception("Stock planning change saved, but operation log failed")


def _load(connection, state, brand, product_id, today, **kwargs):
    result = planning_facts(connection, state.repository, brand, product_id, today, **kwargs)
    if result is None:
        raise HTTPException(404, "未找到当前品牌的有效商品档案")
    if "reference_error" in result:
        raise HTTPException(422, result["reference_error"])
    return result


def _planning_result(conn, state, brand, product_id, today, need_by, total, campaign_id, user, **references):
    facts = _load(conn, state, brand, product_id, today, show_orders=user_has_permission(user, "purchase.view"), **references)
    sizes = facts["sizes"]
    block = replenishment_block({"id": product_id, **facts}, state.stock_overview_policies.list_rules(brand),
                                state.stock_operating.decisions(brand), today)
    sales_ok = facts["sales_complete"]
    # Coverage compares absolute known movement with all movement so returns cannot hide missing sizes.
    weights, basis = choose_weights(sizes, facts["sales"], facts["known_volume"], facts["sales_volume"],
                                    sales_ok, facts["baseline"])
    reference = facts["reference"]
    if reference is not None:
        weights = reference["weights"]
        basis = reference["kind"] if weights else "manual"
    reliable = reliable_transit(sizes, facts["confirmations"], facts["source_transit"], today, need_by) if facts["stock_ready"] else {}
    from_stock = {size: facts["stock"].get(size, 0) + reliable.get(size, 0) for size in sizes}
    selected = conn.execute(select(CAMPAIGNS).where(CAMPAIGNS.c.brand == brand, CAMPAIGNS.c.id == campaign_id)).mappings().one_or_none() if campaign_id else None
    if campaign_id and selected is None:
        raise HTTPException(404, "未找到当前品牌的活动")
    demand = forecast(facts["sales_total"] if sales_ok else None, facts["sales_days"], today, need_by, selected)
    # Plan only against known current stock. Explicit confirmations never change stock.
    availability = sum(from_stock.values()) if facts["stock_ready"] else None
    demand["normal_shortage"] = max(0, demand["normal"] - availability) if demand["normal"] is not None and availability is not None else None
    demand["campaign_shortage"] = max(0, demand["campaign"] - availability) if demand["campaign"] is not None and availability is not None else None
    suggested = allocate(sizes, weights, from_stock, total) if total is not None and not block and facts["stock_ready"] and sales_ok else None
    return {**{key: facts[key] for key in ("sku", "product_name", "category", "size_group", "sizes", "stock_date", "stock_ready",
             "sales_start", "cutoff", "sales_complete", "sales_days", "baseline", "orders", "known_volume", "sales_volume",
             "color", "season", "allocation_season", "allocation_seasons", "heel_group", "related_categories", "other_colors",
             "reference", "legacy_baseline")},
            "stock": facts["stock"], "sales": facts["sales"], "source_transit": facts["source_transit"],
            "today": today, "need_by": need_by, "total": total, "eligible_transit": reliable, "weights": weights, "basis": basis,
            "demand": demand, "suggested": suggested, "campaigns": campaigns(conn, brand, today), "selected_campaign": dict(selected) if selected else None,
            "blocked_reason": block}


@router.get("/items/{product_id}")
def item_plan(request: Request, product_id: int, brand: str = Query(min_length=1, max_length=100),
              need_by: date | None = None, total: int | None = Query(default=None, ge=1, le=1_000_000),
              campaign_id: int | None = Query(default=None, gt=0),
              season: str | None = Query(default=None, max_length=80),
              reference_category: str | None = Query(default=None, min_length=1, max_length=150),
              reference_product_id: int | None = Query(default=None, gt=0)):
    user, state = _context(request, brand)
    if reference_category is not None and reference_product_id is not None:
        raise HTTPException(422, "每次试算只能选一个配码参考")
    today = business_today()
    need_by = need_by or today + timedelta(days=13)
    if not today <= need_by <= today + timedelta(days=365):
        raise HTTPException(422, "需求日期须在今天至未来 365 天之间")
    with state.repository.engine.connect().execution_options(isolation_level="REPEATABLE READ") as conn, conn.begin():
        conn.exec_driver_sql("SET TRANSACTION READ ONLY")
        conn.exec_driver_sql("SET LOCAL statement_timeout = '15s'")
        result = _planning_result(conn, state, brand, product_id, today, need_by, total, campaign_id, user,
                                  season=season, reference_category=reference_category, reference_product_id=reference_product_id)
    return _response(result)


class BrandWrite(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    brand: str = Field(min_length=1, max_length=100)


class BaselineWrite(BrandWrite):
    product_id: int = Field(gt=0)
    season: str | None = Field(default=None, max_length=80)
    weights: QuantityMap = Field(min_length=1, max_length=100)


@router.put("/size-baseline")
def size_baseline(request: Request, body: BaselineWrite):
    user, state = _context(request, body.brand)
    _manager(user)
    with state.repository.engine.begin() as conn:
        facts = _load(conn, state, body.brand, body.product_id, business_today(), full=False, show_orders=False,
                      include_confirmations=False, season=body.season)
        if not facts["category"] or facts["category"] == "0" or not facts["size_group"] or set(body.weights) != set(facts["sizes"]) or not any(body.weights.values()):
            raise HTTPException(422, "请先完善品名和尺码组，并为每个尺码填写权重（至少一项大于零）")
        keys = {"brand": body.brand, "category": facts["category"], "size_group": facts["size_group"]}
        table = BASELINES
        if facts["allocation_season"] or facts["heel_group"]:
            table = SCOPED_BASELINES
            keys.update(season=facts["allocation_season"], heel=facts["heel_group"])
        row = save_record(conn, table, keys, {"weights": body.weights, "updated_by": user["id"]})
    _log(request, "stock_size_baseline", body.brand, "更新品类配码基准", row)
    return _response({"message": "品类配码基准已保存", "item": row})


class CampaignWrite(BrandWrite):
    name: str = Field(min_length=1, max_length=100)
    start_date: date
    end_date: date
    factor: Decimal = Field(ge=Decimal("0.1"), le=Decimal("10"), max_digits=5, decimal_places=3)


@router.get("/campaigns")
def list_campaigns(request: Request, brand: str = Query(min_length=1, max_length=100)):
    _, state = _context(request, brand)
    with state.repository.engine.connect() as conn:
        items = campaigns(conn, brand, business_today() - timedelta(days=365))
    return _response({"items": items})


@router.post("/campaigns")
def add_campaign(request: Request, body: CampaignWrite):
    user, state = _context(request, body.brand)
    _manager(user)
    if body.start_date > body.end_date or (body.end_date - body.start_date).days > 365:
        raise HTTPException(422, "活动日期范围无效")
    with state.repository.engine.begin() as conn:
        row = dict(conn.execute(insert(CAMPAIGNS).values(**body.model_dump(), created_by=user["id"]).returning(CAMPAIGNS)).mappings().one())
    _log(request, "stock_demand_campaign", body.brand, "录入营销活动", row)
    return _response({"message": "活动已保存", "item": row})


class ArrivalWrite(BrandWrite):
    product_id: int = Field(gt=0)
    order_id: int = Field(gt=0)
    eta: date | None
    sizes: QuantityMap = Field(default_factory=dict, max_length=100)
    note: str = Field(min_length=1, max_length=1000)


@router.get("/arrivals")
def list_arrivals(request: Request, brand: str = Query(min_length=1, max_length=100),
                  scope: Literal["confirmed", "due_soon", "overdue"] = "confirmed",
                  page: int = Query(default=1, ge=1)):
    user, state = _context(request, brand)
    if not user_has_permission(user, "purchase.view"):
        raise HTTPException(403, "无权查看采购到货")
    today = business_today()
    with state.repository.engine.connect().execution_options(isolation_level="REPEATABLE READ") as conn, conn.begin():
        conn.exec_driver_sql("SET TRANSACTION READ ONLY")
        conn.exec_driver_sql("SET LOCAL statement_timeout = '15s'")
        rows = arrival_board(conn, state.repository, brand, today, scope)
    page_size = 25
    total = len(rows or [])
    page = min(page, max(1, (total + page_size - 1) // page_size))
    return _response({"items": (rows or [])[(page - 1) * page_size:page * page_size],
                      "today": today, "through": today + timedelta(days=2), "source_ready": rows is not None,
                      "page": page, "page_size": page_size, "total": total})


@router.put("/arrivals")
def confirm_arrival(request: Request, body: ArrivalWrite):
    user, state = _context(request, body.brand)
    _manager(user)
    _require(user, "purchase.manage")
    today = business_today()
    sizes = {name: qty for name, qty in body.sizes.items() if qty}
    if body.eta is None and sizes:
        raise HTTPException(422, "撤销确认时不能填写预计数量")
    if body.eta is not None and (not today <= body.eta <= today + timedelta(days=365) or not sizes):
        raise HTTPException(422, "请选择有效的预计到仓日，并填写至少一个尺码的确认数量")
    with state.repository.engine.begin() as conn:
        # Use the parent order to serialize confirmations, including the first save.
        if inspect(conn).has_table("inventory_records"):
            conn.execute(text("SELECT id FROM inventory_records WHERE id=:id FOR UPDATE"), {"id": body.order_id})
        facts = _load(conn, state, body.brand, body.product_id, today, full=False)
        order = next((row for row in facts["orders"] or [] if row["id"] == body.order_id), None)
        if order is None:
            raise HTTPException(404, "该采购单未关联当前货号")
        if any(size not in facts["sizes"] or value > order["remaining_sizes"].get(size, 0) for size, value in sizes.items()):
            raise HTTPException(409, "确认数量超出已核对的采购单分码未收量")
        row = save_record(conn, ARRIVALS, {"brand": body.brand, "product_id": body.product_id, "order_id": body.order_id},
                          {"eta": body.eta, "sizes": sizes, "receipt_basis": order["receipt_basis"], "note": body.note, "updated_by": user["id"]})
    _log(request, "stock_confirmed_arrival", body.brand, "确认到仓" if body.eta else "撤销到仓确认", row)
    return _response({"message": "到仓确认已保存" if body.eta else "已撤销到仓确认"})


class OrderLinkWrite(BrandWrite):
    product_id: int = Field(gt=0)
    order_id: int = Field(gt=0)
    external_number: str = Field(min_length=1, max_length=100)
    note: str = Field(min_length=1, max_length=1000)


@router.put("/purchase-order-link")
def link_purchase_order(request: Request, body: OrderLinkWrite):
    user, state = _context(request, body.brand)
    _manager(user)
    _require(user, "purchase.manage")
    try:
        with state.repository.engine.begin() as conn:
            if inspect(conn).has_table("inventory_records"):
                conn.execute(text("SELECT id FROM inventory_records WHERE id=:id FOR UPDATE"), {"id": body.order_id})
            facts = _load(conn, state, body.brand, body.product_id, business_today(), full=False)
            order = next((row for row in facts["orders"] or [] if row["id"] == body.order_id), None)
            if not order:
                raise HTTPException(404, "该采购单未关联当前货号")
            collision = conn.scalar(text("""SELECT id FROM inventory_records WHERE document_number=:number
                    AND document_type='进货订单' AND deleted_at IS NULL AND id<>:order_id LIMIT 1"""),
                {"number": body.external_number, "order_id": body.order_id})
            if collision is not None:
                raise HTTPException(409, "该聚水潭单号与其他中台采购单号冲突")
            row = save_record(conn, ORDER_LINKS, {"order_id": body.order_id}, {
                "external_number": body.external_number, "note": body.note, "updated_by": user["id"]})
            if order["external_number"] != body.external_number:
                conn.execute(ARRIVALS.update().where(ARRIVALS.c.order_id == body.order_id, ARRIVALS.c.eta.is_not(None))
                    .values(eta=None, sizes={}, receipt_basis={}, note="采购单号关联变更，原到仓确认已撤销",
                            updated_by=user["id"], updated_at=row["updated_at"]))
    except IntegrityError as error:
        raise HTTPException(409, "该聚水潭采购单号已关联其他采购单") from error
    _log(request, "stock_purchase_order_link", body.brand, "关联聚水潭采购单号", row)
    return _response({"message": "采购单号已关联"})


def _week_bounds(first):
    if first.weekday() != 0 or first + timedelta(days=6) >= business_today():
        raise HTTPException(422, "请选择已经结束的自然周周一")
    return first, first + timedelta(days=6)


@router.get("/clearance-week")
def clearance_week(request: Request, first: date, brand: str = Query(min_length=1, max_length=100)):
    user, state = _context(request, brand)
    start, end = _week_bounds(first)
    _, completed, clearance = state.stock_alert_tasks.overview_week(brand, start, end)
    observations = weekly_observations(state.repository, brand, start, end, completed, clearance, include_details=True)
    rows = observations["clearance_items"]
    with state.repository.engine.connect() as conn:
        recorded = {row["product_id"]: dict(row) for row in conn.execute(select(RECOVERY).where(
            RECOVERY.c.brand == brand, RECOVERY.c.week_start == start, RECOVERY.c.product_id.in_(clearance))).mappings()}
        summary = recovery_summary(conn, brand, start, clearance)
    for row in rows:
        recovery = recorded.get(row["product_id"])
        row["recovery"] = {"amount": format(recovery["amount"], ".2f"), "reference": recovery["reference"]} if recovery else None
    return _response({"start": start, "end": end, "items": rows,
        "can_confirm": _finance(user),
        "stock_covered": sum(row["ending_stock"] is not None for row in rows), **summary})


class RecoveryWrite(BrandWrite):
    first: date
    product_id: int = Field(gt=0)
    amount: Decimal = Field(ge=0, max_digits=16, decimal_places=2)
    reference: str = Field(min_length=1, max_length=1000)


@router.put("/clearance-week/recovery")
def confirm_recovery(request: Request, body: RecoveryWrite):
    user, state = _context(request, body.brand)
    if not _finance(user):
        raise HTTPException(403, "仅财务部或超级管理员可确认回收金额")
    first, end = _week_bounds(body.first)
    _, _, clearance = state.stock_alert_tasks.overview_week(body.brand, first, end)
    if body.product_id not in clearance:
        raise HTTPException(409, "该货号本周没有已完成的清货待办")
    with state.repository.engine.begin() as conn:
        row = save_record(conn, RECOVERY, {"brand": body.brand, "week_start": first, "product_id": body.product_id},
            {"amount": body.amount, "reference": body.reference, "updated_by": user["id"]})
    _log(request, "stock_clearance_recovery", body.brand, "确认清货回收金额", row)
    return _response({"message": "回收金额已确认",
                      "item": {"amount": format(row["amount"], ".2f"), "reference": row["reference"]}})

