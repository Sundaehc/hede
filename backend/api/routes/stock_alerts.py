from decimal import Decimal
import logging
from typing import Literal

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import JSONResponse
from fastapi.encoders import jsonable_encoder
from pydantic import BaseModel, Field

from api.operation_log_utils import write_operation_log
from api.stock_product_images import add_stock_product_images
from domain.stock_alerts import select_alerts
from storage.stock_alert_facts import load_stock_alert_facts
from storage.stock_alert_rules import RuleConflict

router = APIRouter(prefix="/stock-alerts", tags=["存"])
logger = logging.getLogger(__name__)


def _validate_brand(request, brand):
    if brand not in request.app.state.repository.product_archive_brands():
        raise HTTPException(status_code=400, detail="请选择有效的商品档案品牌")


@router.get("/options")
def stock_alert_options(request: Request):
    return {"brands": [{"value": item["code"], "label": "伊伴" if item["code"] == "eblan" else item["name"]}
                       for item in request.app.state.inventory_repository.list_product_archive_brands()]}


@router.get("")
def list_stock_alerts(request: Request, brand: str = Query(min_length=1, max_length=100),
    kind: Literal["zero", "slow"] = "zero", status: Literal["warning", "pending"] = "warning",
    season: str = Query(default="", max_length=100), query: str = Query(default="", max_length=200),
    page: int = Query(default=1, ge=1), page_size: int = Query(default=25, ge=1, le=100), refresh: bool = False):
    _validate_brand(request, brand)
    facts = load_stock_alert_facts(request.app.state.repository, brand, refresh=refresh)
    result = select_alerts(facts, rules=request.app.state.stock_alert_rules.list_rules(brand), kind=kind,
                          status=status, season=season, query=query, page=page, page_size=page_size)
    tasks = request.app.state.stock_alert_tasks.active_for(brand, kind, [item["id"] for item in result["items"]])
    for item in result["items"]:
        item["task"] = tasks.get(item["id"])
    add_stock_product_images(request, result["items"], brand=brand)
    return JSONResponse(jsonable_encoder(result), headers={"Cache-Control": "no-store"})


class RuleWrite(BaseModel):
    brand: str = Field(min_length=1, max_length=100)
    season: str = Field(default="", max_length=100)
    kind: Literal["zero", "slow"]
    age_days: int = Field(ge=1, le=3650)
    rate: Decimal = Field(default=Decimal(20), ge=0, le=100, allow_inf_nan=False)
    version: int = Field(ge=0)


@router.put("/rules")
def save_stock_alert_rule(request: Request, body: RuleWrite):
    _validate_brand(request, body.brand)
    user = getattr(request.state, "current_user", None) or {}
    try:
        request.app.state.stock_alert_rules.save(**body.model_dump(), user_id=user.get("id"))
    except RuleConflict as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    try:
        write_operation_log(request, module="inventory", action="stock_alert_rule_update", entity_type="stock_alert_rule",
            entity_label=f"{body.brand}/{body.season or '全部季节'}/{body.kind}", summary="更新库存预警规则",
            after_data={**body.model_dump(mode="json"), "version": body.version + 1})
    except Exception:
        logger.exception("Stock alert rule saved, but operation log could not be written")
    return {"message": "预警规则已保存"}


@router.get("/seasonal-analysis")
def seasonal_analysis(request: Request, brand: str = Query(min_length=1, max_length=100),
    year: int = Query(ge=2000, le=2100), quarter: int = Query(ge=1, le=4),
    season: str = Query(default="", max_length=100), query: str = Query(default="", max_length=200),
    status: Literal["all", "single", "pending", "arrivals", "zero"] = "all",
    page: int = Query(default=1, ge=1), page_size: int = Query(default=25, ge=1, le=100), refresh: bool = False):
    from domain.seasonal_analysis import analyze_quarter
    from storage.seasonal_analysis_facts import load_seasonal_analysis_facts

    _validate_brand(request, brand)
    facts = load_seasonal_analysis_facts(request.app.state.repository, brand, year, refresh=refresh,
                                        zero_quarter=quarter if status == "zero" else None)
    result = analyze_quarter(facts, year=year, quarter=quarter,
        season=season, query=query, status=status, page=page, page_size=page_size)
    add_stock_product_images(request, result["items"], brand=brand)
    return JSONResponse(jsonable_encoder(result), headers={"Cache-Control": "no-store"})


@router.get("/seasonal-analysis/items/{product_id}")
def seasonal_item_review(request: Request, product_id: int,
    brand: str = Query(min_length=1, max_length=100), year: int = Query(ge=2000, le=2100),
    quarter: int = Query(ge=1, le=4), receipt_page: int = Query(default=1, ge=1, le=1000)):
    from api.routes.auth import user_has_permission
    from storage.seasonal_item_review import load_seasonal_item_review

    _validate_brand(request, brand)
    user = getattr(request.state, "current_user", None) or {}
    show_receipt_numbers = user_has_permission(user, "inventory.view")
    detail = load_seasonal_item_review(request.app.state.repository, brand, product_id, year, quarter,
                                      receipt_page=receipt_page, show_receipt_numbers=show_receipt_numbers)
    if detail is None:
        raise HTTPException(status_code=404, detail="当前季度没有这款商品的复盘记录")
    return JSONResponse(jsonable_encoder(detail), headers={"Cache-Control": "no-store"})
