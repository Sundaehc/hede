from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel, ConfigDict

from storage.auth_repository import SESSION_COOKIE_NAME, SESSION_MAX_AGE_SECONDS


router = APIRouter(prefix="/auth")


DepartmentCode = str
StatusCode = Literal["active", "disabled"]


class LoginRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    username: str
    password: str


class RegisterRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    username: str
    password: str
    display_name: str
    department_code: DepartmentCode


class AdminUserUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    display_name: str | None = None
    department_code: DepartmentCode | None = None
    role_code: str | None = None
    status: StatusCode | None = None
    password: str | None = None


def sanitize_user(user: dict[str, object]) -> dict[str, object]:
    return {key: value for key, value in user.items() if key != "password_hash"}


def user_has_permission(user: dict[str, object] | None, permission: str | None) -> bool:
    if permission is None:
        return True
    if user is None:
        return False
    permissions = user.get("permissions")
    if not isinstance(permissions, list):
        return False
    return "*" in permissions or permission in permissions


def get_current_user_from_request(request: Request) -> dict[str, object] | None:
    repository = request.app.state.auth_repository
    return repository.get_user_by_session(request.cookies.get(SESSION_COOKIE_NAME))


def require_permission(request: Request, permission: str) -> dict[str, object]:
    user = get_current_user_from_request(request)
    if user is None:
        raise HTTPException(status_code=401, detail="未登录")
    if not user_has_permission(user, permission):
        raise HTTPException(status_code=403, detail="权限不足")
    return user


@router.post("/login")
def login(request: Request, response: Response, body: LoginRequest):
    repository = request.app.state.auth_repository
    user = repository.authenticate(body.username, body.password)
    if user is None:
        raise HTTPException(status_code=401, detail="用户名或密码错误")

    client_host = request.client.host if request.client else None
    token, _expires_at = repository.create_session(
        int(user["id"]),
        ip_address=client_host,
        user_agent=request.headers.get("user-agent"),
    )
    response.set_cookie(
        SESSION_COOKIE_NAME,
        token,
        httponly=True,
        max_age=SESSION_MAX_AGE_SECONDS,
        samesite="lax",
        secure=False,
        path="/",
    )
    return {"user": sanitize_user(user), "message": "登录成功"}


@router.post("/register")
def register(request: Request, response: Response, body: RegisterRequest):
    repository = request.app.state.auth_repository
    try:
        user = repository.create_user(body.model_dump())
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"注册失败：{exc}") from exc

    client_host = request.client.host if request.client else None
    token, _expires_at = repository.create_session(
        int(user["id"]),
        ip_address=client_host,
        user_agent=request.headers.get("user-agent"),
    )
    response.set_cookie(
        SESSION_COOKIE_NAME,
        token,
        httponly=True,
        max_age=SESSION_MAX_AGE_SECONDS,
        samesite="lax",
        secure=False,
        path="/",
    )
    return {"user": sanitize_user(user), "message": "注册成功"}


@router.post("/logout")
def logout(request: Request, response: Response):
    repository = request.app.state.auth_repository
    repository.revoke_session(request.cookies.get(SESSION_COOKIE_NAME))
    response.delete_cookie(SESSION_COOKIE_NAME, path="/")
    return {"message": "已退出登录"}


@router.get("/me")
def me(request: Request):
    user = get_current_user_from_request(request)
    if user is None:
        raise HTTPException(status_code=401, detail="未登录")
    return {"user": sanitize_user(user)}


@router.get("/options")
def options(request: Request):
    repository = request.app.state.auth_repository
    return {
        "departments": repository.list_departments(),
        "roles": repository.list_roles(),
        "has_users": repository.has_users(),
    }


@router.get("/admin/users")
def admin_list_users(request: Request):
    require_permission(request, "system.admin")
    repository = request.app.state.auth_repository
    return {"items": [sanitize_user(user) for user in repository.list_users()]}


@router.patch("/admin/users/{user_id}")
def admin_update_user(request: Request, user_id: int, body: AdminUserUpdateRequest):
    require_permission(request, "system.admin")
    repository = request.app.state.auth_repository
    user = repository.update_user(user_id, body.model_dump(exclude_none=True))
    if user is None:
        raise HTTPException(status_code=404, detail="用户不存在")
    return {"item": sanitize_user(user), "message": "用户已更新"}
