from types import SimpleNamespace

import pytest
from starlette.requests import Request

from api import auth_middleware


def _request() -> Request:
    scope = {
        "type": "http",
        "method": "GET",
        "path": "/product-tags",
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
    [("super_admin", "财务部"), ("developer_user", "开发部")],
)
async def test_product_tag_management_allows_development_and_super_admin(
    monkeypatch, role_code: str, department_code: str
):
    request = _request()
    monkeypatch.setattr(
        auth_middleware,
        "get_current_user_from_request",
        lambda _: {
            "role_code": role_code,
            "department_code": department_code,
        },
    )

    response = await auth_middleware.auth_middleware(request, lambda _: _ok())

    assert response == "ok"


@pytest.mark.anyio
@pytest.mark.parametrize("department_code", ["商品部", "运营部", "财务部", "美工部"])
async def test_product_tag_management_rejects_other_departments(
    monkeypatch, department_code: str
):
    request = _request()
    monkeypatch.setattr(
        auth_middleware,
        "get_current_user_from_request",
        lambda _: {
            "role_code": "department_user",
            "department_code": department_code,
        },
    )

    response = await auth_middleware.auth_middleware(request, lambda _: _ok())

    assert response.status_code == 403


async def _ok():
    return "ok"
