from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

from api.operation_log_utils import (
    WAREHOUSE_FIELD_LABELS,
    WAREHOUSE_BRAND_FIELD_LABELS,
    build_changed_fields,
    summarize_changes,
    write_operation_log,
)

router = APIRouter()


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


@router.get("/warehouses/{warehouse_id}/inventory")
def get_warehouse_inventory(
    request: Request,
    warehouse_id: int,
    date_start: str | None = None,
    date_end: str | None = None,
    product_code: str | None = None,
    page: int = 1,
    page_size: int = 20,
):
    repository = request.app.state.inventory_repository
    warehouse = repository.get_warehouse(warehouse_id)
    if warehouse is None:
        raise HTTPException(status_code=404, detail="Warehouse not found")
    return repository.get_warehouse_inventory(
        warehouse_name=str(warehouse.get("name") or ""),
        date_start=date_start,
        date_end=date_end,
        product_code=product_code,
        page=max(page, 1),
        page_size=min(max(page_size, 1), 200),
    )


@router.get("/warehouses/{warehouse_id}/inventory/movements")
def list_warehouse_inventory_movements(
    request: Request,
    warehouse_id: int,
    date_start: str | None = None,
    date_end: str | None = None,
    product_code: str | None = None,
    color_name: str | None = None,
    color_spec: str | None = None,
    page: int = 1,
    page_size: int = 50,
):
    repository = request.app.state.inventory_repository
    warehouse = repository.get_warehouse(warehouse_id)
    if warehouse is None:
        raise HTTPException(status_code=404, detail="Warehouse not found")
    return repository.list_warehouse_inventory_movements(
        warehouse_name=str(warehouse.get("name") or ""),
        date_start=date_start,
        date_end=date_end,
        product_code=product_code,
        color_name=color_name,
        color_spec=color_spec,
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
