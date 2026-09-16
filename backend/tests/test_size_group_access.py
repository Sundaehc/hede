from types import SimpleNamespace

import pytest
from starlette.requests import Request

from api import auth_middleware


def _request(path: str) -> Request:
    return Request({
        "type": "http",
        "method": "GET",
        "path": path,
        "headers": [],
        "app": SimpleNamespace(
            state=SimpleNamespace(
                auth_repository=SimpleNamespace(has_users=lambda: True)
            )
        ),
    })


async def _ok(_request):
    return "ok"


@pytest.mark.anyio
@pytest.mark.parametrize(
    "permissions",
    [
        ["product.view"],
        ["purchase.view"],
        ["inventory.view"],
        ["*"],
    ],
)
async def test_size_group_options_allow_business_read_permissions(
    monkeypatch,
    permissions: list[str],
) -> None:
    request = _request("/size-groups/options")
    monkeypatch.setattr(
        auth_middleware,
        "get_current_user_from_request",
        lambda _: {
            "role_code": "department_user",
            "department_code": "运营部",
            "permissions": permissions,
        },
    )

    response = await auth_middleware.auth_middleware(request, _ok)

    assert response == "ok"


@pytest.mark.anyio
async def test_size_group_options_reject_unrelated_accounts(monkeypatch) -> None:
    request = _request("/size-groups/options")
    monkeypatch.setattr(
        auth_middleware,
        "get_current_user_from_request",
        lambda _: {
            "role_code": "department_user",
            "department_code": "其他部门",
            "permissions": [],
        },
    )

    response = await auth_middleware.auth_middleware(request, _ok)

    assert response.status_code == 403


@pytest.mark.anyio
async def test_size_group_management_remains_department_restricted(monkeypatch) -> None:
    request = _request("/size-groups")
    monkeypatch.setattr(
        auth_middleware,
        "get_current_user_from_request",
        lambda _: {
            "role_code": "operation_user",
            "department_code": "运营部",
            "permissions": ["product.view", "purchase.view"],
        },
    )

    response = await auth_middleware.auth_middleware(request, _ok)

    assert response.status_code == 403
    assert "尺码组管理" in response.body.decode("utf-8")


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("role_code", "department_code"),
    [
        ("product_user", "商品部"),
        ("developer_user", "开发部"),
    ],
)
async def test_size_group_management_allows_product_department_and_super_admin(
    monkeypatch,
    role_code: str,
    department_code: str,
) -> None:
    request = _request("/size-groups")
    monkeypatch.setattr(
        auth_middleware,
        "get_current_user_from_request",
        lambda _: {
            "role_code": role_code,
            "department_code": department_code,
            "permissions": ["product.view"],
        },
    )

    response = await auth_middleware.auth_middleware(request, _ok)

    assert response == "ok"


@pytest.mark.anyio
async def test_size_group_management_rejects_unrelated_department(monkeypatch) -> None:
    request = _request("/size-groups")
    monkeypatch.setattr(
        auth_middleware,
        "get_current_user_from_request",
        lambda _: {
            "role_code": "operation_user",
            "department_code": "运营部",
            "permissions": ["product.view", "product.manage"],
        },
    )

    response = await auth_middleware.auth_middleware(request, _ok)

    assert response.status_code == 403
