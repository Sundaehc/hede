from __future__ import annotations

import io
import urllib.parse
from decimal import Decimal
from typing import Literal

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import StreamingResponse
from openpyxl import Workbook
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from api.excel_export import style_excel_worksheet
from api.fine_table_cache import clear_fine_table_cache
from api.operation_log_utils import (
    SUPPLIER_FIELD_LABELS,
    actor_from_request,
    build_changed_fields,
    summarize_changes,
    write_operation_log,
)
from api.product_goods_cache import clear_product_goods_cache
from api.routes.auth import user_has_permission
from domain.gj_brand import CBANNER_MENS_BRAND, EBLAN_BRAND, EBLAN_WOMENS_SUPPLIER_BRAND, infer_supplier_brand_from_name
from domain.schema import PRODUCT_ARCHIVE_TABLES
from domain.supplier_change_schema import SupplierChangeConflict, SupplierNameExists
from storage.auth_repository import normalize_department_code
from storage.date_normalization import parse_date

router = APIRouter()

SUPPLIER_EXPORT_BRAND_LABELS = {
    "cbanner_mens": "千百度男鞋",
    "cbanner_womens": "千百度女鞋",
    "yandou": "烟斗",
    "eblan": "伊伴",
    "smiley": "笑脸",
    "ni": "NI",
}


def _normalize_brand(repository, value: str | None) -> str | None:
    if value in (None, "", "all"):
        return None
    if repository.get_supplier_brand_by_code(str(value)) is None:
        raise HTTPException(status_code=400, detail="无效品牌")
    return str(value)


def _stream_supplier_export(workbook: Workbook, filename: str) -> StreamingResponse:
    buffer = io.BytesIO()
    workbook.save(buffer)
    buffer.seek(0)
    return StreamingResponse(
        buffer,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={
            "Content-Disposition": f"attachment; filename*=UTF-8''{urllib.parse.quote(filename)}",
            "Content-Length": str(buffer.getbuffer().nbytes),
            "X-Content-Type-Options": "nosniff",
            "Cache-Control": "no-store",
        },
    )


@router.get("/suppliers")
def list_suppliers(
    request: Request,
    page: int | None = Query(None, ge=1),
    page_size: int | None = Query(None, ge=1, le=200),
    query: str | None = None,
    brand: str | None = None,
    include_balances: bool = False,
    date_start: str | None = None,
    date_end: str | None = None,
):
    repository = request.app.state.inventory_repository
    normalized_brand = _normalize_brand(repository, brand)
    if date_start and parse_date(date_start) is None:
        raise HTTPException(status_code=400, detail="起始日期无效")
    if date_end and parse_date(date_end) is None:
        raise HTTPException(status_code=400, detail="截止日期无效")
    if date_start and date_end and parse_date(date_start) > parse_date(date_end):
        raise HTTPException(status_code=400, detail="起始日期不能晚于截止日期")
    if page is None and page_size is None and not query and not include_balances:
        items = repository.list_suppliers(brand=normalized_brand)
        return {
            "items": items,
            "total": len(items),
            "page": 1,
            "page_size": len(items),
        }
    return repository.list_suppliers_page(
        page=page or 1, page_size=page_size or 30, query=query, brand=normalized_brand,
        include_balances=include_balances, date_start=date_start, date_end=date_end,
    )


@router.get("/suppliers/export")
def export_suppliers(
    request: Request,
    query: str | None = None,
    brand: str | None = None,
    date_start: str | None = None,
    date_end: str | None = None,
):
    repository = request.app.state.inventory_repository
    normalized_brand = _normalize_brand(repository, brand)
    if date_start and parse_date(date_start) is None:
        raise HTTPException(status_code=400, detail="起始日期无效")
    if date_end and parse_date(date_end) is None:
        raise HTTPException(status_code=400, detail="截止日期无效")
    if date_start and date_end and parse_date(date_start) > parse_date(date_end):
        raise HTTPException(status_code=400, detail="起始日期不能晚于截止日期")
    items = repository.list_suppliers_page(
        page=1,
        page_size=200,
        query=query,
        brand=normalized_brand,
        include_balances=True,
        date_start=date_start,
        date_end=date_end,
    )
    rows = list(items.get("items") or [])
    while len(rows) < int(items.get("total") or 0):
        page = len(rows) // 200 + 1
        next_page = repository.list_suppliers_page(
            page=page,
            page_size=200,
            query=query,
            brand=normalized_brand,
            include_balances=True,
            date_start=date_start,
            date_end=date_end,
        )
        next_rows = list(next_page.get("items") or [])
        if not next_rows:
            break
        rows.extend(next_rows)

    workbook = Workbook()
    worksheet = workbook.active
    worksheet.title = "供应商"
    worksheet.append(["供应商名称", "工厂代码", "期初余额", "本期发生额", "期末余额"])
    for item in rows:
        worksheet.append([
            item.get("name") or "",
            item.get("factory_code") or "",
            Decimal(str(item.get("beginning_balance") or "0")),
            Decimal(str(item.get("period_amount") or "0")),
            Decimal(str(item.get("ending_balance") or "0")),
        ])
    style_excel_worksheet(worksheet, width_by_header={"供应商名称": 28, "工厂代码": 16, "期初余额": 18, "本期发生额": 18, "期末余额": 18})

    selected_brand = repository.get_supplier_brand_by_code(normalized_brand) if normalized_brand else None
    brand_label = "全部品牌" if selected_brand is None else str(selected_brand.get("name") or normalized_brand)
    keyword = str(query or "").strip()
    summary = f"导出供应商 {len(rows)} 条（{brand_label}{f'，关键词：{keyword}' if keyword else ''}）"
    write_operation_log(
        request,
        module="supplier",
        action="export",
        entity_type="supplier",
        summary=summary,
        after_data={"count": len(rows), "brand": normalized_brand, "query": keyword, "date_start": date_start, "date_end": date_end},
    )
    filename = f"供应商管理_{brand_label}.xlsx"
    return _stream_supplier_export(workbook, filename)


@router.get("/supplier-brands")
def list_supplier_brands(request: Request):
    return {"items": request.app.state.inventory_repository.list_supplier_brands()}


@router.post("/supplier-brands")
def create_supplier_brand(request: Request, payload: dict):
    repository = request.app.state.inventory_repository
    name = str(payload.get("name") or "").strip()
    if not name:
        raise HTTPException(status_code=400, detail="品牌名称不能为空")
    if any(str(item.get("name") or "") == name for item in repository.list_supplier_brands()):
        raise HTTPException(status_code=400, detail=f"品牌“{name}”已存在")
    item = repository.create_supplier_brand({"name": name})
    request.app.state.repository.ensure_manual_product_archive(item)
    write_operation_log(
        request,
        module="supplier_brand",
        action="create_brand",
        entity_type="supplier_brand",
        entity_id=item.get("id"),
        entity_label=name,
        summary=f"新增品牌 {name}",
        after_data=item,
    )
    return {"item": item, "message": "创建成功"}


@router.put("/supplier-brands/{brand_id}")
def update_supplier_brand(request: Request, brand_id: int, payload: dict):
    repository = request.app.state.inventory_repository
    name = str(payload.get("name") or "").strip()
    if not name:
        raise HTTPException(status_code=400, detail="品牌名称不能为空")
    before = repository.get_supplier_brand(brand_id)
    if before is None:
        raise HTTPException(status_code=404, detail="Supplier brand not found")
    if any(item.get("id") != brand_id and str(item.get("name") or "") == name for item in repository.list_supplier_brands()):
        raise HTTPException(status_code=400, detail=f"品牌“{name}”已存在")
    item = repository.update_supplier_brand(brand_id, {"name": name})
    if item is None:
        raise HTTPException(status_code=404, detail="Supplier brand not found")
    changes = build_changed_fields(before, item, {"name": "品牌名称"})
    write_operation_log(
        request,
        module="supplier_brand",
        action="update_brand",
        entity_type="supplier_brand",
        entity_id=brand_id,
        entity_label=name,
        summary=summarize_changes("编辑品牌", name, changes),
        changed_fields=changes,
        before_data=before,
        after_data=item,
    )
    return {"item": item, "message": "更新成功"}


@router.delete("/supplier-brands/{brand_id}")
def delete_supplier_brand(request: Request, brand_id: int):
    repository = request.app.state.inventory_repository
    before = repository.get_supplier_brand(brand_id)
    if before is None:
        raise HTTPException(status_code=404, detail="品牌不存在")

    brand_code = str(before.get("code") or "")
    if brand_code in PRODUCT_ARCHIVE_TABLES:
        raise HTTPException(status_code=400, detail="该品牌已关联商品信息档案，不能删除")

    if bool(before.get("product_archive_enabled")):
        product_table = str(before.get("product_table_name") or "")
        if product_table:
            with request.app.state.repository.engine.connect() as connection:
                product_count = connection.execute(text(f"SELECT count(*) FROM {product_table}")).scalar_one()
            if product_count:
                raise HTTPException(status_code=400, detail=f"该品牌商品档案中还有 {product_count} 个商品，不能删除")

    supplier_count = repository.count_suppliers_by_brand(brand_code)
    if supplier_count:
        raise HTTPException(status_code=400, detail=f"该品牌下还有 {supplier_count} 个供应商，不能删除")

    deleted = repository.delete_supplier_brand(brand_id)
    if deleted is None:
        raise HTTPException(status_code=404, detail="品牌不存在")
    name = str(deleted.get("name") or brand_id)
    write_operation_log(
        request,
        module="supplier_brand",
        action="delete_brand",
        entity_type="supplier_brand",
        entity_id=brand_id,
        entity_label=name,
        summary=f"删除品牌 {name}",
        before_data=before,
    )
    return {"message": "删除成功"}


@router.post("/suppliers")
def create_supplier(request: Request, payload: dict, confirm_cross_brand_code: bool = False):
    repository = request.app.state.inventory_repository
    name = str(payload.get("name") or "").strip()
    brand = payload.get("brand") or infer_supplier_brand_from_name(name) or CBANNER_MENS_BRAND
    if brand == EBLAN_BRAND and infer_supplier_brand_from_name(name) == EBLAN_WOMENS_SUPPLIER_BRAND:
        brand = EBLAN_WOMENS_SUPPLIER_BRAND
    normalized_brand = _normalize_brand(repository, str(brand))
    if not name:
        raise HTTPException(status_code=400, detail="供应商名称不能为空")
    payload["name"] = name
    payload["brand"] = normalized_brand
    existing = repository.get_supplier_by_name(name)
    if existing:
        raise HTTPException(status_code=400, detail=str(SupplierNameExists(name)))
    factory_code = str(payload.get("factory_code") or "").strip()
    if factory_code and not confirm_cross_brand_code:
        conflicts = repository.list_supplier_factory_code_conflicts(factory_code, brand=normalized_brand)
        if conflicts:
            labels = "、".join(
                f"{row['brand_name'] or SUPPLIER_EXPORT_BRAND_LABELS.get(row['brand'], row['brand'])}（{row['name']}）"
                for row in conflicts
            )
            raise HTTPException(
                status_code=409,
                detail=f"工厂代码“{factory_code}”已在其他品牌中使用：{labels}。是否继续创建？",
            )
    try:
        item = repository.create_supplier(payload)
    except SupplierNameExists as error:
        raise HTTPException(400, str(error)) from error
    label = str(item.get("name") or item.get("id") or "").strip()
    write_operation_log(
        request,
        module="supplier",
        action="create",
        entity_type="supplier",
        entity_id=item.get("id"),
        entity_label=label,
        summary=f"新增供应商 {label}".strip(),
        before_data=None,
        after_data=item,
    )
    return {"item": item, "message": "创建成功"}


def _supplier_change_user(request: Request):
    actor = actor_from_request(request)
    if not actor or not actor.get("id"):
        raise HTTPException(401, "请先登录")
    if not any(user_has_permission(actor, permission) for permission in ("supplier.manage", "inventory.manage")):
        raise HTTPException(403, "没有供应商管理权限")
    return actor


def _can_review_supplier_changes(actor):
    return normalize_department_code(actor.get("department_code")) == "商品部"


def _public_supplier_change(row):
    return {
        **{key: value for key, value in row.items() if key not in {"before", "proposed"}},
        "supplier_name": row["before"]["name"],
        "supplier_brand": row["before"]["brand"],
        "supplier_factory_code": row["before"]["factory_code"],
        "changes": build_changed_fields(row["before"], row["proposed"], SUPPLIER_FIELD_LABELS),
    }


def _record_supplier_update(request: Request, outcome):
    before, record = outcome["before"], outcome["item"]
    if (before.get("name"), before.get("brand")) != (record.get("name"), record.get("brand")):
        clear_fine_table_cache()
        clear_product_goods_cache()
    label = record["name"]
    changes = build_changed_fields(before, record, SUPPLIER_FIELD_LABELS)
    if changes:
        write_operation_log(
            request, module="supplier", action="update", entity_type="supplier", entity_id=record["id"],
            entity_label=label, summary=summarize_changes("编辑供应商", label, changes),
            changed_fields=changes, before_data=before, after_data=record,
        )
    if outcome.get("history_sync_skipped"):
        return record, "已更新供应商；因品牌变更或存在同名档案，历史单据保留原名称，请按单核对"
    return record, "供应商已更新"


@router.get("/suppliers/change-requests")
def list_supplier_changes(request: Request, page: int = Query(1, ge=1),
                          status: Literal["pending", "approved", "rejected", "all"] = "pending"):
    actor = _supplier_change_user(request)
    can_review = _can_review_supplier_changes(actor)
    response = request.app.state.inventory_repository.list_supplier_changes(
        page=page, status=status, requester_id=None if can_review else actor["id"],
    )
    return {**response, "items": [_public_supplier_change(row) for row in response["items"]],
            "can_review": can_review}


class SupplierReviewDecision(BaseModel):
    decision: Literal["approve", "reject"]
    note: str = Field(default="", max_length=1000)


@router.put("/suppliers/change-requests/{request_id}")
def review_supplier_change(request: Request, request_id: int, body: SupplierReviewDecision):
    actor = _supplier_change_user(request)
    if not _can_review_supplier_changes(actor):
        raise HTTPException(403, "仅商品组可审核供应商变更")
    approved = body.decision == "approve"
    note = body.note.strip()
    if not approved and not note:
        raise HTTPException(400, "请填写驳回原因")
    try:
        outcome = request.app.state.inventory_repository.review_supplier_change(
            request_id, approved=approved, note=note, actor=actor,
        )
    except PermissionError as error:
        raise HTTPException(403, str(error)) from error
    except SupplierChangeConflict as error:
        raise HTTPException(409, str(error)) from error
    except IntegrityError as error:
        if getattr(error.orig, "sqlstate", None) != "23505":
            raise
        raise HTTPException(409, "供应商档案或申请已变化，请刷新后重试") from error
    if outcome is None:
        raise HTTPException(404, "申请不存在")
    message = _record_supplier_update(request, outcome)[1] if approved else "申请已驳回"
    review = _public_supplier_change(outcome["review"])
    write_operation_log(
        request, module="supplier", action="approve_change" if approved else "reject_change",
        entity_type="supplier_change_request", entity_id=request_id, entity_label=review["supplier_name"],
        summary=f"供应商变更申请 #{request_id}：{message}", after_data=review,
    )
    return {"review": review, "message": message}


@router.get("/suppliers/{supplier_id}")
def get_supplier(request: Request, supplier_id: int):
    item = request.app.state.inventory_repository.get_supplier(supplier_id)
    if item is None:
        raise HTTPException(status_code=404, detail="供应商不存在")
    return {"item": item}


@router.put("/suppliers/{supplier_id}")
def update_supplier(request: Request, supplier_id: int, payload: dict):
    repository = request.app.state.inventory_repository
    name = str(payload.get("name") or "").strip()
    brand = payload.get("brand") or infer_supplier_brand_from_name(name) or CBANNER_MENS_BRAND
    if brand == EBLAN_BRAND and infer_supplier_brand_from_name(name) == EBLAN_WOMENS_SUPPLIER_BRAND:
        brand = EBLAN_WOMENS_SUPPLIER_BRAND
    normalized_brand = _normalize_brand(repository, str(brand))
    if not name or not normalized_brand:
        raise HTTPException(status_code=400, detail="请填写供应商名称并选择品牌")
    payload.update(name=name, brand=normalized_brand)
    try:
        outcome = repository.update_supplier(supplier_id, payload, actor=actor_from_request(request))
    except SupplierChangeConflict as error:
        raise HTTPException(409, str(error)) from error
    except IntegrityError as error:
        if getattr(error.orig, "sqlstate", None) != "23505":
            raise
        raise HTTPException(409, "供应商档案或申请已变化，请刷新后重试") from error
    if outcome is None:
        raise HTTPException(404, "Supplier not found")
    if "review" in outcome:
        review = _public_supplier_change(outcome["review"])
        write_operation_log(
            request, module="supplier", action="request_change", entity_type="supplier_change_request",
            entity_id=review["id"], entity_label=review["supplier_name"],
            summary=f"提交供应商变更申请 #{review['id']}", after_data=review,
        )
        return {"review": review, "message": f"申请 #{review['id']} 已提交，等待商品组审核后生效"}
    record, message = _record_supplier_update(request, outcome)
    return {"item": record, "message": message, "history_sync_skipped": outcome.get("history_sync_skipped", False)}


@router.delete("/suppliers/{supplier_id}")
def delete_supplier(request: Request, supplier_id: int):
    repository = request.app.state.inventory_repository
    before = repository.get_supplier(supplier_id)
    if before is None:
        raise HTTPException(status_code=404, detail="Supplier not found")
    try:
        deleted = repository.delete_supplier(supplier_id)
    except SupplierChangeConflict as error:
        raise HTTPException(409, str(error)) from error
    if not deleted:
        raise HTTPException(status_code=404, detail="Supplier not found")
    label = str(before.get("name") or supplier_id).strip()
    write_operation_log(
        request,
        module="supplier",
        action="delete",
        entity_type="supplier",
        entity_id=supplier_id,
        entity_label=label,
        summary=f"删除供应商 {label}".strip(),
        before_data=before,
        after_data=None,
    )
    return {"message": "删除成功"}
