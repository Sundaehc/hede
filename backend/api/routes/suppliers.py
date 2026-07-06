from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query, Request

from api.operation_log_utils import (
    SUPPLIER_FIELD_LABELS,
    build_changed_fields,
    summarize_changes,
    write_operation_log,
)
from api.schemas import BrandKey
from domain.gj_brand import CBANNER_MENS_BRAND, SUPPLIER_BRANDS, infer_supplier_brand_from_name

router = APIRouter()


def _normalize_brand(value: str | None) -> str | None:
    if value in (None, "", "all"):
        return None
    if value not in SUPPLIER_BRANDS:
        raise HTTPException(status_code=400, detail="无效品牌")
    return value


@router.get("/suppliers")
def list_suppliers(
    request: Request,
    page: int | None = Query(None, ge=1),
    page_size: int | None = Query(None, ge=1, le=200),
    query: str | None = None,
    brand: str | None = None,
    sort: str | None = None,
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
    return repository.list_suppliers_page(page=page or 1, page_size=page_size or 30, query=query, brand=normalized_brand, sort=sort)


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
