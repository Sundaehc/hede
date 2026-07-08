from __future__ import annotations

from fastapi import Request
from starlette.responses import JSONResponse

from api.routes.auth import get_current_user_from_request, user_has_permission


PUBLIC_PATHS = (
    "/auth/login",
    "/auth/register",
    "/auth/options",
    "/public/docs",
    "/public/openapi.json",
    "/public/redoc",
)


def required_permission_for_request(method: str, path: str) -> str | tuple[str, ...] | None:
    if path.startswith("/auth/admin"):
        return "system.admin"
    if path.startswith("/auth/"):
        return None
    if path.startswith("/operation-logs"):
        return ("product.view", "fine_table.view", "inventory.view", "purchase.view")
    if path.startswith("/products"):
        return "product.view" if method == "GET" else "product.manage"
    if path == "/export":
        return "product.export"
    if path == "/import":
        return "product.import"
    if path.startswith("/images/refresh-product-images"):
        return "product.manage"
    if path.startswith("/images"):
        return "product.view"
    if path.startswith("/fine-table"):
        return "fine_table.export" if "export" in path and method != "GET" else "fine_table.view"
    if path.startswith("/suppliers") or path.startswith("/warehouses"):
        return "inventory.view" if method == "GET" else "inventory.manage"
    if path.startswith("/inventory/export"):
        return ("inventory.export", "purchase.export")
    if path.startswith("/inventory/import") or "import" in path:
        return ("inventory.manage", "purchase.import", "purchase.manage")
    if path.startswith("/inventory"):
        return "inventory.view" if method == "GET" else ("inventory.manage", "purchase.manage")
    return None


async def auth_middleware(request: Request, call_next):
    if request.method == "OPTIONS":
        return await call_next(request)

    path = request.url.path
    if any(path == public or path.startswith(public + "/") for public in PUBLIC_PATHS):
        return await call_next(request)

    repository = getattr(request.app.state, "auth_repository", None)
    if repository is None or not repository.has_users():
        return await call_next(request)

    user = get_current_user_from_request(request)
    if user is None:
        return JSONResponse({"detail": "未登录"}, status_code=401)

    permission = required_permission_for_request(request.method, path)
    if isinstance(permission, tuple):
        allowed = any(user_has_permission(user, item) for item in permission)
    else:
        allowed = user_has_permission(user, permission)
    if not allowed:
        return JSONResponse({"detail": "权限不足"}, status_code=403)

    request.state.current_user = user
    return await call_next(request)
