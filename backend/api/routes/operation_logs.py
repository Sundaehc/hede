from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query, Request

from api.routes.auth import get_current_user_from_request, require_permission, user_has_permission


router = APIRouter(prefix="/operation-logs")


MODULE_PERMISSIONS = {
    "product": "product.view",
    "size_group": "product.view",
    "product_goods": "product.view",
    "fine_table": "fine_table.view",
    "inventory": "inventory.view",
    "purchase": "purchase.view",
    "purchase_inbound_detail": "inventory.view",
    "supplier": "inventory.view",
    "supplier_brand": "inventory.view",
    "warehouse": "inventory.view",
    "account_subject": "inventory.view",
    "general_customer": "inventory.view",
    "user": "system.admin",
    "ai_query": "system.admin",
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
    if isinstance(permission, tuple):
        user = get_current_user_from_request(request)
        if user is None:
            raise HTTPException(status_code=401, detail="未登录")
        if not any(user_has_permission(user, item) for item in permission):
            raise HTTPException(status_code=403, detail="权限不足")
    else:
        user = require_permission(request, permission)
    if module == "size_group":
        role_code = str(user.get("role_code") or "").strip()
        department_code = str(user.get("department_code") or "").strip()
        if role_code != "super_admin" and department_code not in {"商品部", "开发部"}:
            raise HTTPException(status_code=403, detail="尺码组管理操作日志仅限商品部、开发部和超级管理员查看")
    page = max(1, page)
    page_size = min(max(1, page_size), 100)
    return request.app.state.operation_log_repository.list_logs(
        module=module,
        query=query,
        page=page,
        page_size=page_size,
        exclude_super_admin_logs=str(user.get("role_code") or "") != "super_admin",
    )
