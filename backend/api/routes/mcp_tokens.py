from contextlib import contextmanager
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from pydantic import BaseModel, ConfigDict, Field, StrictInt, field_validator
from sqlalchemy import insert, text
from sqlalchemy.exc import SQLAlchemyError

from api.routes.auth import require_permission
from domain.operation_log_schema import OPERATION_LOG_TABLE
from storage.mcp_token_repository import issue_credential, list_candidates, list_credentials, revoke_credential


NO_STORE = {"Cache-Control": "no-store", "Pragma": "no-cache"}


def require_token_admin(request: Request, response: Response):
    response.headers.update(NO_STORE)
    try:
        actor = require_permission(request, "system.admin")
    except HTTPException as error:
        error.headers = {**(error.headers or {}), **NO_STORE}
        raise
    if actor.get("role_code") != "super_admin" or actor.get("status") != "active":
        raise HTTPException(403, "仅超级管理员可以管理MCP凭证", headers=NO_STORE)
    if request.method == "POST":
        if request.headers.get("x-mcp-admin") != "1" or request.headers.get("content-type", "").split(";")[0].strip().lower() != "application/json":
            raise HTTPException(403, "请从中台Token管理页面提交", headers=NO_STORE)
        settings = getattr(request.app.state, "settings", None)
        origins = getattr(settings, "frontend_origins", ())
        origin = request.headers.get("origin")
        if request.headers.get("sec-fetch-site") == "cross-site" or (origin is not None and origin not in origins):
            raise HTTPException(403, "请求来源不受信任", headers=NO_STORE)
    return actor


router = APIRouter(prefix="/auth/admin/mcp-tokens", dependencies=[Depends(require_token_admin)])


class IssueTokenRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    user_id: Annotated[StrictInt, Field(gt=0)]
    profile: Literal["finance", "merchandise", "operation", "development", "design", "customer_service"]
    days: Annotated[StrictInt, Field(ge=1, le=90)] | None = 30
    label: str = Field(min_length=1, max_length=100)

    @field_validator("label")
    @classmethod
    def label_not_blank(cls, value):
        if not value.strip():
            raise ValueError("用途备注不能为空")
        return value.strip()


@contextmanager
def token_connection(request):
    engine = getattr(request.app.state.auth_repository, "engine", None)
    if engine is None:
        raise HTTPException(503, "MCP凭证管理暂不可用", headers=NO_STORE)
    try:
        with engine.begin() as connection:
            if connection.dialect.name == "postgresql":
                connection.exec_driver_sql("SET LOCAL statement_timeout=5000")
                connection.exec_driver_sql("SET LOCAL lock_timeout=1000")
                if connection.scalar(text("SELECT to_regclass('mcp_private.tokens')")) is None:
                    raise HTTPException(503, "MCP尚未初始化，请联系服务器管理员；不要在页面中重复初始化", headers=NO_STORE)
            yield connection
    except SQLAlchemyError:
        raise HTTPException(503, "MCP凭证数据库或审计不可用，请确认状态后重试", headers=NO_STORE) from None


def audit_change(connection, actor, action, item):
    summary = f"{'签发' if action == 'mcp_token_issue' else '撤销'}MCP凭证 #{item['id']}，用户ID {item['user_id']}，范围 {item['profile']}"
    if action == "mcp_token_issue":
        summary += "，永久有效" if item["expires_at"] is None else f"，到期时间 {item['expires_at']}"
    connection.execute(insert(OPERATION_LOG_TABLE).values(
        module="user", action=action, entity_type="mcp_token", entity_id=str(item["id"]),
        entity_label=item["label"], summary=summary, user_id=actor["id"], username=actor["username"],
        display_name=actor.get("display_name"), department_name=actor.get("department_name"), role_code=actor["role_code"],
    ))


@router.get("/users")
def candidates(request: Request, query: str = Query("", max_length=100), page: int = Query(1, ge=1, le=100000)):
    with token_connection(request) as connection:
        return list_candidates(connection, query=query.strip(), page=page)


@router.get("")
def tokens(request: Request, page: int = Query(1, ge=1, le=100000), page_size: int = Query(20, ge=1, le=100)):
    with token_connection(request) as connection:
        return list_credentials(connection, page=page, page_size=page_size)


@router.post("", status_code=201)
def issue(request: Request, body: IssueTokenRequest, actor=Depends(require_token_admin)):
    with token_connection(request) as connection:
        try:
            result = issue_credential(connection, **body.model_dump())
        except ValueError as error:
            raise HTTPException(400, str(error), headers=NO_STORE) from None
        audit_change(connection, actor, "mcp_token_issue", result["item"])
        return result


@router.post("/{token_id}/revoke")
def revoke(request: Request, token_id: int, actor=Depends(require_token_admin)):
    with token_connection(request) as connection:
        item, changed = revoke_credential(connection, token_id)
        if item is None:
            raise HTTPException(404, "凭证不存在", headers=NO_STORE)
        if changed:
            audit_change(connection, actor, "mcp_token_revoke", item)
        return {"item": item, "changed": changed, "message": "凭证已撤销"}
