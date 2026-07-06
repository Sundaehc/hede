from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

from api.operation_log_utils import (
    WAREHOUSE_FIELD_LABELS,
    build_changed_fields,
    summarize_changes,
    write_operation_log,
)

router = APIRouter()


@router.get("/warehouses")
def list_warehouses(request: Request):
    repository = request.app.state.inventory_repository
    return {"items": repository.list_warehouses()}


@router.post("/warehouses")
def create_warehouse(request: Request, payload: dict):
    repository = request.app.state.inventory_repository
    name = payload.get("name", "").strip()
    if not name:
        raise HTTPException(status_code=400, detail="仓库名称不能为空")
    payload["name"] = name
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


@router.put("/warehouses/{warehouse_id}")
def update_warehouse(request: Request, warehouse_id: int, payload: dict):
    repository = request.app.state.inventory_repository
    name = str(payload.get("name") or "").strip()
    if not name:
        raise HTTPException(status_code=400, detail="仓库名称不能为空")
    payload["name"] = name
    before = repository.get_warehouse(warehouse_id)
    if before is None:
        raise HTTPException(status_code=404, detail="Warehouse not found")
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
