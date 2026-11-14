"""Supplier-level replenishment estimates and manually maintained rules."""
import logging
from typing import Annotated, Literal

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from api.operation_log_utils import write_operation_log
from api.routes.stock_alerts import _validate_brand
from domain.stock_replenishment import select_replenishment
from storage.stock_alert_rules import RuleConflict
from storage.stock_replenishment_facts import load_replenishment_facts, supplier_catalog

router = APIRouter(prefix="/stock-alerts/replenishment", tags=["存"])
logger = logging.getLogger(__name__)


@router.get("")
def list_replenishment(request: Request, brand: str = Query(min_length=1, max_length=100),
    supplier: str = Query(default="", max_length=200), query: str = Query(default="", max_length=200),
    status: Literal["suggested", "pending", "all"] = "suggested", window_days: int = 30,
    deduct_transit: bool = False, page: int = Query(default=1, ge=1),
    page_size: int = Query(default=25, ge=1, le=100), refresh: bool = False):
    _validate_brand(request, brand)
    if window_days not in {7, 15, 30}:
        raise HTTPException(status_code=400, detail="销量统计天数请选择 7、15 或 30 天")
    facts = load_replenishment_facts(request.app.state.repository, brand, window_days=window_days, refresh=refresh)
    result = select_replenishment(facts, request.app.state.stock_replenishment_rules.list_rules(brand),
        supplier=supplier, query=query, status=status, page=page, page_size=page_size, deduct_transit=deduct_transit)
    return JSONResponse(result, headers={"Cache-Control": "no-store"})


@router.get("/rules")
def get_replenishment_rules(request: Request, brand: str = Query(min_length=1, max_length=100),
    supplier: str = Query(min_length=1, max_length=200)):
    _validate_brand(request, brand)
    catalog = supplier_catalog(request.app.state.repository, brand)
    if supplier not in catalog:
        raise HTTPException(status_code=400, detail="该供应商未关联当前品牌的有效商品")
    rule = request.app.state.stock_replenishment_rules.list_rules(brand).get(supplier)
    public = {key: rule[key] for key in ("lead_days", "min_order_qty", "cover_days", "size_ratios", "version")} if rule else None
    return JSONResponse({"rule": public, "groups": catalog[supplier]}, headers={"Cache-Control": "no-store"})


class ReplenishmentRuleWrite(BaseModel):
    brand: str = Field(min_length=1, max_length=100)
    supplier: str = Field(min_length=1, max_length=200)
    lead_days: int = Field(ge=0, le=365)
    min_order_qty: int = Field(ge=1, le=1000000)
    cover_days: int = Field(ge=1, le=365)
    size_ratios: dict[str, dict[str, Annotated[int, Field(strict=True, ge=0, le=10000)]]] = Field(max_length=100)
    version: int = Field(ge=0)


@router.put("/rules")
def save_replenishment_rules(request: Request, body: ReplenishmentRuleWrite):
    _validate_brand(request, body.brand)
    catalog = supplier_catalog(request.app.state.repository, body.brand)
    groups = catalog.get(body.supplier)
    if groups is None:
        raise HTTPException(status_code=400, detail="该供应商未关联当前品牌的有效商品")
    for group, ratios in body.size_ratios.items():
        sizes = groups.get(group)
        if not sizes or set(ratios) != {size["name"] for size in sizes}:
            raise HTTPException(status_code=400, detail=f"尺码组“{group}”已变动或配比不完整，请刷新后重新填写")
        if any(isinstance(value, bool) or not 0 <= value <= 10000 for value in ratios.values()) or not any(ratios.values()):
            raise HTTPException(status_code=400, detail=f"尺码组“{group}”配比须为 0–10000 的整数，至少一个尺码大于 0")
    user = getattr(request.state, "current_user", None) or {}
    try:
        request.app.state.stock_replenishment_rules.save(**body.model_dump(), user_id=user.get("id"))
    except RuleConflict as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    try:
        write_operation_log(request, module="inventory", action="replenishment_rule_update", entity_type="replenishment_rule",
            entity_label=f"{body.brand}/{body.supplier}", summary="更新供应商补货规则（供应商合计起订量）",
            after_data={**body.model_dump(mode="json"), "version": body.version + 1})
    except Exception:
        logger.exception("Replenishment rule saved, but operation log could not be written")
    return {"message": "补货规则已保存"}
