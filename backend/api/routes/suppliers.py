from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query, Request

router = APIRouter()


@router.get("/suppliers")
def list_suppliers(
    request: Request,
    page: int | None = Query(None, ge=1),
    page_size: int | None = Query(None, ge=1, le=200),
    query: str | None = None,
):
    repository = request.app.state.inventory_repository
    if page is None and page_size is None and not query:
        items = repository.list_suppliers()
        return {
            "items": items,
            "total": len(items),
            "page": 1,
            "page_size": len(items),
        }
    return repository.list_suppliers_page(page=page or 1, page_size=page_size or 30, query=query)


@router.post("/suppliers")
def create_supplier(request: Request, payload: dict):
    repository = request.app.state.inventory_repository
    name = payload.get("name", "").strip()
    if not name:
        raise HTTPException(status_code=400, detail="供应商名称不能为空")
    existing = repository.get_supplier_by_name(name)
    if existing:
        raise HTTPException(status_code=400, detail=f"供应商 '{name}' 已存在")
    return {"item": repository.create_supplier(payload), "message": "创建成功"}


@router.put("/suppliers/{supplier_id}")
def update_supplier(request: Request, supplier_id: int, payload: dict):
    repository = request.app.state.inventory_repository
    record = repository.update_supplier(supplier_id, payload)
    if record is None:
        raise HTTPException(status_code=404, detail="Supplier not found")
    return {"item": record, "message": "更新成功"}


@router.delete("/suppliers/{supplier_id}")
def delete_supplier(request: Request, supplier_id: int):
    repository = request.app.state.inventory_repository
    if not repository.delete_supplier(supplier_id):
        raise HTTPException(status_code=404, detail="Supplier not found")
    return {"message": "删除成功"}
