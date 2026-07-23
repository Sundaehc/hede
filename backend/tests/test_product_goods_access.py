from types import SimpleNamespace

import pytest
from starlette.requests import Request

from api import auth_middleware


def _request() -> Request:
    scope = {
        "type": "http",
        "method": "GET",
        "path": "/product-goods",
        "headers": [],
        "app": SimpleNamespace(
            state=SimpleNamespace(
                auth_repository=SimpleNamespace(has_users=lambda: True)
            )
        ),
    }
    return Request(scope)


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("role_code", "department_code"),
    [
        ("super_admin", "开发部"),
        ("product_user", "商品部"),
        ("developer_user", "开发部"),
    ],
)
async def test_product_goods_allows_authorized_departments(
    monkeypatch, role_code: str, department_code: str
):
    request = _request()
    monkeypatch.setattr(
        auth_middleware,
        "get_current_user_from_request",
        lambda _: {"role_code": role_code, "department_code": department_code},
    )

    response = await auth_middleware.auth_middleware(request, lambda _: _ok())

    assert response == "ok"


@pytest.mark.anyio
async def test_product_goods_rejects_other_departments(monkeypatch):
    request = _request()
    monkeypatch.setattr(
        auth_middleware,
        "get_current_user_from_request",
        lambda _: {"role_code": "design_viewer", "department_code": "美工部"},
    )

    response = await auth_middleware.auth_middleware(request, lambda _: _ok())

    assert response.status_code == 403


async def _ok():
    return "ok"
