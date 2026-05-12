from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

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
    existing = repository.get_warehouse_by_name(name)
    if existing:
        raise HTTPException(status_code=400, detail=f"仓库 '{name}' 已存在")
    return {"item": repository.create_warehouse(payload), "message": "创建成功"}


@router.put("/warehouses/{warehouse_id}")
def update_warehouse(request: Request, warehouse_id: int, payload: dict):
    repository = request.app.state.inventory_repository
    record = repository.update_warehouse(warehouse_id, payload)
    if record is None:
        raise HTTPException(status_code=404, detail="Warehouse not found")
    return {"item": record, "message": "更新成功"}


@router.delete("/warehouses/{warehouse_id}")
def delete_warehouse(request: Request, warehouse_id: int):
    repository = request.app.state.inventory_repository
    if not repository.delete_warehouse(warehouse_id):
        raise HTTPException(status_code=404, detail="Warehouse not found")
    return {"message": "删除成功"}
