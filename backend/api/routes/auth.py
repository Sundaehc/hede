from __future__ import annotations

from collections.abc import Mapping
from typing import Literal
from urllib.parse import urlsplit

from fastapi import APIRouter, HTTPException, Query, Request, Response
from pydantic import BaseModel, ConfigDict
from sqlalchemy.exc import IntegrityError

from api.operation_log_utils import (
    USER_FIELD_LABELS,
    build_changed_fields,
    summarize_changes,
    write_operation_log,
)
from storage.auth_repository import SESSION_COOKIE_NAME, SESSION_MAX_AGE_SECONDS


router = APIRouter(prefix="/auth")


DepartmentCode = str
StatusCode = Literal["active", "disabled"]


class LoginRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    username: str
    password: str


class AdminUserUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    display_name: str | None = None
    department_code: DepartmentCode | None = None
    role_code: str | None = None
    status: StatusCode | None = None
    password: str | None = None


class AdminUserCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    username: str
    password: str
    display_name: str
    department_code: DepartmentCode
    role_code: str
    status: StatusCode = "active"


def sanitize_user(user: dict[str, object]) -> dict[str, object]:
    return {key: value for key, value in user.items() if key != "password_hash"}


USER_STATUS_LABELS = {
    "active": "启用",
    "disabled": "禁用",
}


def user_entity_label(user: Mapping[str, object] | None) -> str:
    if not user:
        return ""
    return str(user.get("username") or user.get("display_name") or user.get("id") or "").strip()


def user_log_payload(user: Mapping[str, object] | None) -> dict[str, object]:
    if not user:
        return {}
    status = str(user.get("status") or "").strip()
    return {
        "username": user.get("username") or "",
        "display_name": user.get("display_name") or "",
        "department_name": user.get("department_name") or user.get("department_code") or "",
        "role_name": user.get("role_name") or user.get("role_code") or "",
        "status": USER_STATUS_LABELS.get(status, status),
    }


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


def session_cookie_is_secure(request: Request) -> bool:
    """Use Secure cookies at the public HTTPS proxy while retaining LAN HTTP access."""
    forwarded_proto = request.headers.get("x-forwarded-proto", "")
    if forwarded_proto:
        return forwarded_proto.split(",", 1)[0].strip().lower() == "https"

    origin = request.headers.get("origin", "").strip()
    if origin:
        return urlsplit(origin).scheme.lower() == "https"

    return request.url.scheme.lower() == "https"


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
        secure=session_cookie_is_secure(request),
        path="/",
    )
    return {"user": sanitize_user(user), "message": "登录成功"}


@router.post("/register")
def register():
    raise HTTPException(status_code=403, detail="注册功能已关闭，请联系管理员创建账号")


@router.post("/logout")
def logout(request: Request, response: Response):
    repository = request.app.state.auth_repository
    repository.revoke_session(request.cookies.get(SESSION_COOKIE_NAME))
    response.delete_cookie(
        SESSION_COOKIE_NAME,
        path="/",
        secure=session_cookie_is_secure(request),
        httponly=True,
        samesite="lax",
    )
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
def admin_list_users(
    request: Request,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
):
    require_permission(request, "system.admin")
    repository = request.app.state.auth_repository
    payload = repository.list_users_page(page=page, page_size=page_size)
    return {
        **payload,
        "items": [sanitize_user(user) for user in payload["items"]],
    }


@router.post("/admin/users", status_code=201)
def admin_create_user(request: Request, body: AdminUserCreateRequest):
    actor = require_permission(request, "system.admin")
    request.state.current_user = actor
    repository = request.app.state.auth_repository

    payload = body.model_dump()
    payload["username"] = body.username.strip()
    payload["display_name"] = body.display_name.strip()
    payload["department_code"] = body.department_code.strip()
    payload["role_code"] = body.role_code.strip()

    if len(str(payload["username"])) < 2:
        raise HTTPException(status_code=400, detail="账号至少需要 2 个字符")
    if any(character.isspace() for character in str(payload["username"])):
        raise HTTPException(status_code=400, detail="账号不能包含空格")
    if not payload["display_name"]:
        raise HTTPException(status_code=400, detail="姓名不能为空")
    if len(body.password) < 8:
        raise HTTPException(status_code=400, detail="密码至少需要 8 个字符")

    departments = {str(item["code"]) for item in repository.list_departments()}
    if payload["department_code"] not in departments:
        raise HTTPException(status_code=400, detail="所选部门不存在")

    role = next(
        (
            item
            for item in repository.list_roles()
            if str(item.get("code") or "") == payload["role_code"]
        ),
        None,
    )
    if role is None:
        raise HTTPException(status_code=400, detail="所选角色不存在")
    role_department = str(role.get("department_code") or "").strip()
    if role_department and role_department != payload["department_code"]:
        raise HTTPException(status_code=400, detail="所选角色不属于该部门")

    try:
        user = repository.create_user(payload, first_user_is_admin=False)
    except IntegrityError as exc:
        raise HTTPException(status_code=409, detail="该账号已存在") from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    after_log = user_log_payload(user)
    after_log["password"] = "已设置"
    changes = build_changed_fields({}, after_log, USER_FIELD_LABELS)
    label = user_entity_label(user)
    write_operation_log(
        request,
        module="user",
        action="create",
        entity_type="auth_user",
        entity_id=user.get("id"),
        entity_label=label,
        summary=f"创建用户 {label}",
        changed_fields=changes,
        after_data=after_log,
    )
    return {"item": sanitize_user(user), "message": f"账号 {label} 已创建"}


@router.patch("/admin/users/{user_id}")
def admin_update_user(request: Request, user_id: int, body: AdminUserUpdateRequest):
    actor = require_permission(request, "system.admin")
    request.state.current_user = actor
    repository = request.app.state.auth_repository
    before = repository.get_user(user_id)
    if before is None:
        raise HTTPException(status_code=404, detail="用户不存在")

    payload = body.model_dump(exclude_none=True)
    password_changed = bool(str(payload.get("password") or ""))
    user = repository.update_user(user_id, payload)
    if user is None:
        raise HTTPException(status_code=404, detail="用户不存在")

    before_log = user_log_payload(before)
    after_log = user_log_payload(user)
    if password_changed:
        before_log["password"] = "未修改"
        after_log["password"] = "已修改"
    changes = build_changed_fields(before_log, after_log, USER_FIELD_LABELS)
    label = user_entity_label(user)
    write_operation_log(
        request,
        module="user",
        action="update",
        entity_type="auth_user",
        entity_id=user_id,
        entity_label=label,
        summary=summarize_changes("编辑用户", label, changes),
        changed_fields=changes,
        before_data=before_log,
        after_data=after_log,
    )
    return {"item": sanitize_user(user), "message": "用户已更新"}
