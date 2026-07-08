from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query, Request

from api.routes.auth import require_permission


router = APIRouter(prefix="/operation-logs")


MODULE_PERMISSIONS = {
    "product": "product.view",
    "fine_table": "fine_table.view",
    "inventory": "inventory.view",
    "purchase": "purchase.view",
    "supplier": "inventory.view",
    "warehouse": "inventory.view",
    "account_subject": "inventory.view",
    "general_customer": "inventory.view",
    "user": "system.admin",
}


@router.get("")
def list_operation_logs(
    request: Request,
    module: str = Query(...),
    query: str | None = None,
    page: int = 1,
    page_size: int = 20,
):
    permission = MODULE_PERMISSIONS.get(module)
    if permission is None:
        raise HTTPException(status_code=400, detail="日志模块无效")
    require_permission(request, permission)
    page = max(1, page)
    page_size = min(max(1, page_size), 100)
    return request.app.state.operation_log_repository.list_logs(
        module=module,
        query=query,
        page=page,
        page_size=page_size,
    )
