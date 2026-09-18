from __future__ import annotations

import asyncio
from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from starlette.requests import Request
from starlette.responses import JSONResponse

from api import auth_middleware
from api.product_cost_access import user_can_view_product_cost
from api.routes.products import get_product, list_products
from storage.auth_repository import DEFAULT_ROLE_BY_DEPARTMENT, DEFAULT_ROLES


DEPARTMENT_ACCESS = [
    ("财务部", "finance_user", False, True),
    ("商品部", "product_user", True, True),
    ("运营部", "operation_user", True, True),
    ("开发部", "developer_user", True, True),
    ("美工部", "design_viewer", False, False),
    ("客服部", "customer_service_viewer", False, False),
]
ROLE_ACCESS = DEPARTMENT_ACCESS + [
    (department, "super_admin", True, True)
    for department, _, _, _ in DEPARTMENT_ACCESS
]


def _user(department: str, role_code: str) -> dict[str, object]:
    role = next(role for role in DEFAULT_ROLES if role["code"] == role_code)
    return {
        "department_code": department,
        "role_code": role_code,
        "permissions": role["permissions"].split(","),
    }


@pytest.mark.parametrize(("department", "role_code", "can_manage", "can_view_cost"), DEPARTMENT_ACCESS)
def test_department_defaults_match_product_access_policy(
    department: str, role_code: str, can_manage: bool, can_view_cost: bool,
) -> None:
    user = _user(department, role_code)

    assert DEFAULT_ROLE_BY_DEPARTMENT[department] == role_code
    assert "product.view" in user["permissions"]
    for permission in ("product.manage", "product.import", "product.export"):
        assert (permission in user["permissions"]) is can_manage
    assert user_can_view_product_cost(user) is can_view_cost


@pytest.mark.parametrize(("department", "role_code", "can_manage", "can_view_cost"), ROLE_ACCESS)
@pytest.mark.parametrize(("method", "path", "read_only"), [
    ("GET", "/products", True),
    ("GET", "/products/cbanner_mens/7", True),
    ("GET", "/images/serve/cbanner_mens/test.jpg", True),
    ("POST", "/products", False),
    ("PUT", "/products/cbanner_mens/7", False),
    ("DELETE", "/products/cbanner_mens/7", False),
    ("POST", "/products/batch-delete", False),
    ("POST", "/products/recycle-bin/cbanner_mens/7/restore", False),
    ("DELETE", "/products/recycle-bin/cbanner_mens/7", False),
    ("POST", "/import", False),
    ("GET", "/import/template", False),
    ("GET", "/export", False),
    ("POST", "/images/refresh-product-images", False),
])
def test_product_endpoints_enforce_department_permissions(
    monkeypatch,
    department: str,
    role_code: str,
    can_manage: bool,
    can_view_cost: bool,
    method: str,
    path: str,
    read_only: bool,
) -> None:
    user = _user(department, role_code)
    monkeypatch.setattr(auth_middleware, "get_current_user_from_request", lambda _: user)
    request = Request({
        "type": "http",
        "method": method,
        "path": path,
        "headers": [],
        "app": SimpleNamespace(state=SimpleNamespace(
            auth_repository=SimpleNamespace(has_users=lambda: True),
        )),
    })
    called = False

    async def call_next(current_request):
        nonlocal called
        called = True
        assert current_request.state.current_user == user
        return JSONResponse({"ok": True})

    response = asyncio.run(auth_middleware.auth_middleware(request, call_next))
    allowed = read_only or can_manage
    assert response.status_code == (200 if allowed else 403)
    assert called is allowed


@pytest.mark.parametrize(("department", "role_code", "can_manage", "can_view_cost"), ROLE_ACCESS)
@pytest.mark.parametrize("view", ["brand", "all", "detail"])
def test_product_responses_apply_department_cost_visibility(
    department: str, role_code: str, can_manage: bool, can_view_cost: bool, view: str,
) -> None:
    item = {
        "id": 7,
        "brand": "cbanner_mens",
        "sku": "TEST-SKU",
        "cost": "199.90",
        "cost_manual_override": True,
        "image_path": None,
        "raw_payload": {"成本单价": "199.90", "颜色": "黑色"},
        "extra_fields": {"gender_costs": {"female": "180", "male": "200"}},
    }
    repository = Mock()
    repository.is_product_archive_brand.return_value = True
    repository.list_products.return_value = {"items": [deepcopy(item)], "total": 1}
    repository.list_all_products.return_value = {"items": [deepcopy(item)], "total": 1}
    repository.get_product.return_value = deepcopy(item)
    request = SimpleNamespace(
        state=SimpleNamespace(current_user=_user(department, role_code)),
        app=SimpleNamespace(state=SimpleNamespace(
            repository=repository,
            settings=SimpleNamespace(image_roots={}),
        )),
    )

    if view == "detail":
        result = get_product(request, brand="cbanner_mens", product_id=7)
    else:
        response = list_products(request, brand="all" if view == "all" else "cbanner_mens")
        result = response["items"][0]

    assert result["sku"] == "TEST-SKU"
    assert result["raw_payload"]["颜色"] == "黑色"
    if can_view_cost:
        assert result["cost"] == "199.90"
        assert result["gender_costs"] == {"female": "180", "male": "200"}
        assert result["raw_payload"]["成本单价"] == "199.90"
    else:
        assert "cost" not in result
        assert "cost_manual_override" not in result
        assert "gender_costs" not in result
        assert result["raw_payload"] == {"颜色": "黑色"}
        assert result["extra_fields"] == {}
