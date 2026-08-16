from __future__ import annotations

import io
import urllib.parse

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import StreamingResponse
from openpyxl import Workbook
from sqlalchemy import text

from api.excel_export import style_excel_worksheet
from api.operation_log_utils import (
    SUPPLIER_FIELD_LABELS,
    build_changed_fields,
    summarize_changes,
    write_operation_log,
)
from domain.gj_brand import CBANNER_MENS_BRAND, infer_supplier_brand_from_name
from domain.schema import PRODUCT_ARCHIVE_TABLES

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
):
    repository = request.app.state.inventory_repository
    normalized_brand = _normalize_brand(repository, brand)
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
    normalized_brand = _normalize_brand(repository, brand)
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
        after_data={"count": len(rows), "brand": normalized_brand, "query": keyword},
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
def create_supplier(request: Request, payload: dict):
    repository = request.app.state.inventory_repository
    name = str(payload.get("name") or "").strip()
    brand = payload.get("brand") or infer_supplier_brand_from_name(name) or CBANNER_MENS_BRAND
    normalized_brand = _normalize_brand(repository, str(brand))
    if not name:
        raise HTTPException(status_code=400, detail="供应商名称不能为空")
    payload["name"] = name
    payload["brand"] = normalized_brand
    existing = repository.get_supplier_by_name(name, brand=normalized_brand)
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
    brand = payload.get("brand") or infer_supplier_brand_from_name(name) or CBANNER_MENS_BRAND
    normalized_brand = _normalize_brand(repository, str(brand))
    if not name:
        raise HTTPException(status_code=400, detail="供应商名称不能为空")
    existing = repository.get_supplier_by_name(name, brand=normalized_brand)
    if existing and existing.get("id") != supplier_id:
        raise HTTPException(status_code=400, detail=f"供应商 '{name}' 已存在")
    payload["name"] = name
    payload["brand"] = normalized_brand
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
