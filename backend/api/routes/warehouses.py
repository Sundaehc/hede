from __future__ import annotations

from datetime import date
import logging
import re
from typing import Literal

from fastapi import APIRouter, HTTPException, Request

from api.operation_log_utils import (
    WAREHOUSE_FIELD_LABELS,
    WAREHOUSE_BRAND_FIELD_LABELS,
    build_changed_fields,
    summarize_changes,
    write_operation_log,
)
from api.routes.inventory import _stream_excel_workbook
from api.warehouse_inventory_export import build_ending_inventory_workbook

router = APIRouter()
ENDING_INVENTORY_EXPORT_LIMIT = 100_000


def _validate_inventory_date_range(date_start: date | None, date_end: date | None) -> None:
    if date_start and date_end and date_start > date_end:
        raise HTTPException(status_code=400, detail="开始日期不能晚于结束日期")


def _ordered_ids(payload: dict) -> list[int]:
    raw_ids = payload.get("ids")
    if not isinstance(raw_ids, list) or not raw_ids:
        raise HTTPException(status_code=400, detail="请提供完整排序结果")
    try:
        ids = [int(item) for item in raw_ids]
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=400, detail="排序数据格式不正确") from exc
    if len(ids) != len(set(ids)):
        raise HTTPException(status_code=400, detail="排序数据存在重复项")
    return ids


@router.get("/warehouses")
def list_warehouses(request: Request):
    repository = request.app.state.inventory_repository
    return {"items": repository.list_warehouses()}


@router.get("/warehouses/inventory-summary")
def list_warehouse_inventory_summary(
    request: Request,
    date_start: date | None = None,
    date_end: date | None = None,
):
    _validate_inventory_date_range(date_start, date_end)
    repository = request.app.state.inventory_repository
    return {"items": repository.list_warehouse_inventory_summary(
        date_start=date_start.isoformat() if date_start else None,
        date_end=date_end.isoformat() if date_end else None,
    )}


@router.get("/warehouses/{warehouse_id}/inventory")
def get_warehouse_inventory(
    request: Request,
    warehouse_id: int,
    date_start: date | None = None,
    date_end: date | None = None,
    product_code: str | None = None,
    ending_nonzero: bool = False,
    display_mode: Literal["goods", "barcode"] = "goods",
    page: int = 1,
    page_size: int = 20,
):
    _validate_inventory_date_range(date_start, date_end)
    repository = request.app.state.inventory_repository
    warehouse = repository.get_warehouse(warehouse_id)
    if warehouse is None:
        raise HTTPException(status_code=404, detail="Warehouse not found")
    return repository.get_warehouse_inventory(
        warehouse_name=str(warehouse.get("name") or ""),
        date_start=date_start.isoformat() if date_start else None,
        date_end=date_end.isoformat() if date_end else None,
        product_code=product_code,
        ending_nonzero=ending_nonzero,
        display_mode=display_mode,
        page=max(page, 1),
        page_size=min(max(page_size, 1), 200),
    )


@router.get("/warehouses/{warehouse_id}/inventory/export")
def export_warehouse_ending_inventory(
    request: Request, warehouse_id: int,
    date_start: date | None = None, date_end: date | None = None, product_code: str | None = None,
    display_mode: Literal["goods", "barcode"] = "goods",
):
    _validate_inventory_date_range(date_start, date_end)
    repository = request.app.state.inventory_repository
    warehouse = repository.get_warehouse(warehouse_id)
    if warehouse is None:
        raise HTTPException(status_code=404, detail="Warehouse not found")
    warehouse_name = str(warehouse.get("name") or "")
    filters = {
        "date_start": date_start.isoformat() if date_start else None,
        "date_end": date_end.isoformat() if date_end else None,
        "product_code": product_code,
        "display_mode": display_mode,
    }
    result = repository.get_warehouse_inventory(
        warehouse_name=warehouse_name, **filters, ending_nonzero=True,
        page=1, page_size=ENDING_INVENTORY_EXPORT_LIMIT,
    )
    if result["total"] > ENDING_INVENTORY_EXPORT_LIMIT:
        raise HTTPException(status_code=400, detail="期末库存商品超过 100000 条，请缩小日期或货号筛选范围后导出")
    workbook = build_ending_inventory_workbook(result, display_mode=display_mode)
    # Generate the file before recording success; log failures must not block a download.
    filename_warehouse = re.sub(r'[\\/:*?"<>|\x00-\x1f]', "_", warehouse_name)[:80]
    filename = f"期末库存_{filename_warehouse}_{filters['date_end'] or '全部日期'}.xlsx"
    response = _stream_excel_workbook(workbook, filename)
    try:
        write_operation_log(
            request, module="warehouse", action="export", entity_type="warehouse_inventory",
            entity_id=warehouse_id, entity_label=warehouse_name,
            summary=f"导出仓库 {warehouse_name} 期末库存商品 {result['total']} 条",
            after_data={"exported_rows": result["total"], "filters": filters, "ending_qty": result["totals"]["ending_qty"]},
        )
    except Exception:
        logging.getLogger(__name__).exception("Failed to record warehouse inventory export log")
    return response


@router.get("/warehouses/{warehouse_id}/inventory/movements")
def list_warehouse_inventory_movements(
    request: Request,
    warehouse_id: int,
    date_start: date | None = None,
    date_end: date | None = None,
    product_code: str | None = None,
    product_name: str | None = None,
    color_name: str | None = None,
    color_spec: str | None = None,
    exact_match: bool = False,
    display_mode: Literal["goods", "barcode"] = "goods",
    product_identity_id: int | None = None,
    inventory_size_key: str | None = None,
    unallocated: bool = False,
    page: int = 1,
    page_size: int = 50,
):
    _validate_inventory_date_range(date_start, date_end)
    if display_mode == "barcode" and (not exact_match or inventory_size_key is None):
        raise HTTPException(status_code=400, detail="请从编码库存行查看对应尺码的明细")
    repository = request.app.state.inventory_repository
    warehouse = repository.get_warehouse(warehouse_id)
    if warehouse is None:
        raise HTTPException(status_code=404, detail="Warehouse not found")
    return repository.list_warehouse_inventory_movements(
        warehouse_name=str(warehouse.get("name") or ""),
        date_start=date_start.isoformat() if date_start else None,
        date_end=date_end.isoformat() if date_end else None,
        product_code=product_code,
        product_name=product_name,
        color_name=color_name,
        color_spec=color_spec,
        exact_match=exact_match,
        display_mode=display_mode,
        product_identity_id=product_identity_id,
        inventory_size_key=inventory_size_key,
        unallocated=unallocated,
        page=max(page, 1),
        page_size=min(max(page_size, 1), 200),
    )


@router.get("/warehouse-brands")
def list_warehouse_brands(request: Request):
    repository = request.app.state.inventory_repository
    return {"items": repository.list_warehouse_brands()}


@router.post("/warehouse-brands")
def create_warehouse_brand(request: Request, payload: dict):
    repository = request.app.state.inventory_repository
    name = str(payload.get("name") or "").strip()
    if not name:
        raise HTTPException(status_code=400, detail="品牌名称不能为空")
    if repository.get_warehouse_brand_by_name(name):
        raise HTTPException(status_code=400, detail=f"品牌 '{name}' 已存在")
    item = repository.create_warehouse_brand({"name": name})
    write_operation_log(
        request,
        module="warehouse",
        action="create",
        entity_type="warehouse_brand",
        entity_id=item.get("id"),
        entity_label=name,
        summary=f"新增仓库品牌 {name}",
        before_data=None,
        after_data=item,
    )
    return {"item": item, "message": "创建成功"}


@router.put("/warehouse-brands/order")
def reorder_warehouse_brands(request: Request, payload: dict):
    repository = request.app.state.inventory_repository
    ids = _ordered_ids(payload)
    if not repository.reorder_warehouse_brands(ids):
        raise HTTPException(status_code=409, detail="品牌列表已变更，请刷新后重试")
    write_operation_log(
        request,
        module="warehouse",
        action="reorder",
        entity_type="warehouse_brand_order",
        entity_id=None,
        entity_label="仓库品牌",
        summary="调整仓库品牌排序",
        before_data=None,
        after_data={"ids": ids},
    )
    return {"message": "排序已保存"}


@router.put("/warehouse-brands/{brand_id}")
def update_warehouse_brand(request: Request, brand_id: int, payload: dict):
    repository = request.app.state.inventory_repository
    name = str(payload.get("name") or "").strip()
    if not name:
        raise HTTPException(status_code=400, detail="品牌名称不能为空")
    before = repository.get_warehouse_brand(brand_id)
    if before is None:
        raise HTTPException(status_code=404, detail="Warehouse brand not found")
    duplicate = repository.get_warehouse_brand_by_name(name)
    if duplicate and int(duplicate.get("id") or 0) != brand_id:
        raise HTTPException(status_code=400, detail=f"品牌 '{name}' 已存在")
    item = repository.update_warehouse_brand(brand_id, {"name": name})
    if item is None:
        raise HTTPException(status_code=404, detail="Warehouse brand not found")
    changes = build_changed_fields(before, item, WAREHOUSE_BRAND_FIELD_LABELS)
    write_operation_log(
        request,
        module="warehouse",
        action="update",
        entity_type="warehouse_brand",
        entity_id=brand_id,
        entity_label=name,
        summary=summarize_changes("编辑仓库品牌", name, changes),
        changed_fields=changes,
        before_data=before,
        after_data=item,
    )
    return {"item": item, "message": "更新成功"}


@router.delete("/warehouse-brands/{brand_id}")
def delete_warehouse_brand(request: Request, brand_id: int):
    repository = request.app.state.inventory_repository
    before = repository.get_warehouse_brand(brand_id)
    if before is None:
        raise HTTPException(status_code=404, detail="Warehouse brand not found")
    result = repository.delete_warehouse_brand(brand_id)
    if result == "in_use":
        raise HTTPException(status_code=400, detail="该品牌下仍有仓库，请先删除或调整仓库品牌")
    if result == "not_found":
        raise HTTPException(status_code=404, detail="Warehouse brand not found")
    label = str(before.get("name") or brand_id).strip()
    write_operation_log(
        request,
        module="warehouse",
        action="delete",
        entity_type="warehouse_brand",
        entity_id=brand_id,
        entity_label=label,
        summary=f"删除仓库品牌 {label}",
        before_data=before,
        after_data=None,
    )
    return {"message": "删除成功"}


@router.post("/warehouses")
def create_warehouse(request: Request, payload: dict):
    repository = request.app.state.inventory_repository
    name = str(payload.get("name") or "").strip()
    brand = str(payload.get("brand") or "").strip()
    if not name:
        raise HTTPException(status_code=400, detail="仓库名称不能为空")
    if not brand:
        raise HTTPException(status_code=400, detail="请选择仓库品牌")
    payload["name"] = name
    payload["brand"] = brand
    if not repository.get_warehouse_brand_by_name(brand):
        raise HTTPException(status_code=400, detail=f"仓库品牌 '{brand}' 不存在")
    existing = repository.get_warehouse_by_name(name)
    if existing:
        raise HTTPException(status_code=400, detail=f"仓库 '{name}' 已存在")
    item = repository.create_warehouse(payload)
    label = str(item.get("name") or item.get("id") or "").strip()
    write_operation_log(
        request,
        module="warehouse",
        action="create",
        entity_type="warehouse",
        entity_id=item.get("id"),
        entity_label=label,
        summary=f"新增仓库 {label}".strip(),
        before_data=None,
        after_data=item,
    )
    return {"item": item, "message": "创建成功"}


@router.put("/warehouses/order")
def reorder_warehouses(request: Request, payload: dict):
    repository = request.app.state.inventory_repository
    brand = str(payload.get("brand") or "").strip()
    if not brand:
        raise HTTPException(status_code=400, detail="请选择仓库品牌")
    ids = _ordered_ids(payload)
    if not repository.reorder_warehouses(brand, ids):
        raise HTTPException(status_code=409, detail="仓库列表已变更，请刷新后重试")
    write_operation_log(
        request,
        module="warehouse",
        action="reorder",
        entity_type="warehouse_order",
        entity_id=None,
        entity_label=brand,
        summary=f"调整仓库排序：{brand}",
        before_data=None,
        after_data={"brand": brand, "ids": ids},
    )
    return {"message": "排序已保存"}


@router.put("/warehouses/{warehouse_id}")
def update_warehouse(request: Request, warehouse_id: int, payload: dict):
    repository = request.app.state.inventory_repository
    name = str(payload.get("name") or "").strip()
    if not name:
        raise HTTPException(status_code=400, detail="仓库名称不能为空")
    before = repository.get_warehouse(warehouse_id)
    if before is None:
        raise HTTPException(status_code=404, detail="Warehouse not found")
    brand = str(payload.get("brand") or before.get("brand") or "").strip()
    if not brand:
        raise HTTPException(status_code=400, detail="请选择仓库品牌")
    if not repository.get_warehouse_brand_by_name(brand):
        raise HTTPException(status_code=400, detail=f"仓库品牌 '{brand}' 不存在")
    payload["name"] = name
    payload["brand"] = brand
    record = repository.update_warehouse(warehouse_id, payload)
    if record is None:
        raise HTTPException(status_code=404, detail="Warehouse not found")
    label = str(record.get("name") or before.get("name") or warehouse_id).strip()
    changes = build_changed_fields(before, record, WAREHOUSE_FIELD_LABELS)
    write_operation_log(
        request,
        module="warehouse",
        action="update",
        entity_type="warehouse",
        entity_id=warehouse_id,
        entity_label=label,
        summary=summarize_changes("编辑仓库", label, changes),
        changed_fields=changes,
        before_data=before,
        after_data=record,
    )
    return {"item": record, "message": "更新成功"}


@router.delete("/warehouses/{warehouse_id}")
def delete_warehouse(request: Request, warehouse_id: int):
    repository = request.app.state.inventory_repository
    before = repository.get_warehouse(warehouse_id)
    if before is None:
        raise HTTPException(status_code=404, detail="Warehouse not found")
    if not repository.delete_warehouse(warehouse_id):
        raise HTTPException(status_code=404, detail="Warehouse not found")
    label = str(before.get("name") or warehouse_id).strip()
    write_operation_log(
        request,
        module="warehouse",
        action="delete",
        entity_type="warehouse",
        entity_id=warehouse_id,
        entity_label=label,
        summary=f"删除仓库 {label}".strip(),
        before_data=before,
        after_data=None,
    )
    return {"message": "删除成功"}
