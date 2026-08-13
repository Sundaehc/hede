from __future__ import annotations

import io
import urllib.parse

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import StreamingResponse
from openpyxl import Workbook

from api.excel_export import style_excel_worksheet
from api.operation_log_utils import (
    SUPPLIER_FIELD_LABELS,
    build_changed_fields,
    summarize_changes,
    write_operation_log,
)
from api.schemas import BrandKey
from domain.gj_brand import CBANNER_MENS_BRAND, SUPPLIER_BRANDS, infer_supplier_brand_from_name

router = APIRouter()

SUPPLIER_EXPORT_BRAND_LABELS = {
    "cbanner_mens": "千百度男鞋",
    "cbanner_womens": "千百度女鞋",
    "yandou": "烟斗",
    "eblan": "伊伴",
    "smiley": "笑脸",
    "ni": "NI",
}


def _normalize_brand(value: str | None) -> str | None:
    if value in (None, "", "all"):
        return None
    if value not in SUPPLIER_BRANDS:
        raise HTTPException(status_code=400, detail="无效品牌")
    return value


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
):
    repository = request.app.state.inventory_repository
    normalized_brand = _normalize_brand(brand)
    if page is None and page_size is None and not query:
        items = repository.list_suppliers(brand=normalized_brand)
        return {
            "items": items,
            "total": len(items),
            "page": 1,
            "page_size": len(items),
        }
    return repository.list_suppliers_page(page=page or 1, page_size=page_size or 30, query=query, brand=normalized_brand)


@router.get("/suppliers/export")
def export_suppliers(request: Request, query: str | None = None, brand: str | None = None):
    repository = request.app.state.inventory_repository
    normalized_brand = _normalize_brand(brand)
    items = repository.list_suppliers_page(
        page=1,
        page_size=200,
        query=query,
        brand=normalized_brand,
    )
    rows = list(items.get("items") or [])
    while len(rows) < int(items.get("total") or 0):
        page = len(rows) // 200 + 1
        next_page = repository.list_suppliers_page(
            page=page,
            page_size=200,
            query=query,
            brand=normalized_brand,
        )
        next_rows = list(next_page.get("items") or [])
        if not next_rows:
            break
        rows.extend(next_rows)

    workbook = Workbook()
    worksheet = workbook.active
    worksheet.title = "供应商"
    worksheet.append(["供应商名称", "工厂代码", "联系人", "微信号", "合作状态", "地址", "备注"])
    for item in rows:
        worksheet.append([
            item.get("name") or "",
            item.get("factory_code") or "",
            item.get("contact") or "",
            item.get("wechat") or "",
            item.get("cooperation_status") or "",
            item.get("address") or "",
            item.get("notes") or "",
        ])
    style_excel_worksheet(worksheet, width_by_header={"供应商名称": 28, "联系人": 16, "微信号": 20, "合作状态": 14, "地址": 30, "备注": 30})

    brand_label = "全部品牌" if normalized_brand is None else str(normalized_brand)
    keyword = str(query or "").strip()
    summary = f"导出供应商 {len(rows)} 条（{brand_label}{f'，关键词：{keyword}' if keyword else ''}）"
    write_operation_log(
        request,
        module="supplier",
        action="export",
        entity_type="supplier",
        summary=summary,
        after_data={"count": len(rows), "brand": normalized_brand, "query": keyword},
    )
    filename = f"供应商管理_{SUPPLIER_EXPORT_BRAND_LABELS.get(normalized_brand or '', '总览')}.xlsx"
    return _stream_supplier_export(workbook, filename)


@router.post("/suppliers")
def create_supplier(request: Request, payload: dict):
    repository = request.app.state.inventory_repository
    name = payload.get("name", "").strip()
    brand: BrandKey = infer_supplier_brand_from_name(name) or payload.get("brand") or CBANNER_MENS_BRAND
    _normalize_brand(brand)
    if not name:
        raise HTTPException(status_code=400, detail="供应商名称不能为空")
    payload["name"] = name
    payload["brand"] = brand
    existing = repository.get_supplier_by_name(name, brand=brand)
    if existing:
        raise HTTPException(status_code=400, detail=f"供应商 '{name}' 已存在")
    item = repository.create_supplier(payload)
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


@router.put("/suppliers/{supplier_id}")
def update_supplier(request: Request, supplier_id: int, payload: dict):
    repository = request.app.state.inventory_repository
    name = str(payload.get("name") or "").strip()
    brand: BrandKey = infer_supplier_brand_from_name(name) or payload.get("brand") or CBANNER_MENS_BRAND
    _normalize_brand(brand)
    if not name:
        raise HTTPException(status_code=400, detail="供应商名称不能为空")
    existing = repository.get_supplier_by_name(name, brand=brand)
    if existing and existing.get("id") != supplier_id:
        raise HTTPException(status_code=400, detail=f"供应商 '{name}' 已存在")
    payload["name"] = name
    payload["brand"] = brand
    before = repository.get_supplier(supplier_id)
    if before is None:
        raise HTTPException(status_code=404, detail="Supplier not found")
    record = repository.update_supplier(supplier_id, payload)
    if record is None:
        raise HTTPException(status_code=404, detail="Supplier not found")
    label = str(record.get("name") or before.get("name") or supplier_id).strip()
    changes = build_changed_fields(before, record, SUPPLIER_FIELD_LABELS)
    write_operation_log(
        request,
        module="supplier",
        action="update",
        entity_type="supplier",
        entity_id=supplier_id,
        entity_label=label,
        summary=summarize_changes("编辑供应商", label, changes),
        changed_fields=changes,
        before_data=before,
        after_data=record,
    )
    return {"item": record, "message": "更新成功"}


@router.delete("/suppliers/{supplier_id}")
def delete_supplier(request: Request, supplier_id: int):
    repository = request.app.state.inventory_repository
    before = repository.get_supplier(supplier_id)
    if before is None:
        raise HTTPException(status_code=404, detail="Supplier not found")
    if not repository.delete_supplier(supplier_id):
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
