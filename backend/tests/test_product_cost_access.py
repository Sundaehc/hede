from __future__ import annotations

from types import SimpleNamespace

from api.product_cost_access import (
    redact_product_cost_item,
    redact_product_cost_log_item,
    user_can_view_product_cost,
)
from api.routes.import_export import _export_columns_for_brand, _size_export_headers_for_brand
from api.routes.products import list_products


def test_customer_service_and_design_cannot_view_product_cost() -> None:
    assert not user_can_view_product_cost({"department_code": "客服部", "role_code": "customer_service_viewer"})
    assert not user_can_view_product_cost({"department_code": "美工部", "role_code": "design_viewer"})
    assert user_can_view_product_cost({"department_code": "商品部", "role_code": "product_user"})
    assert user_can_view_product_cost({"department_code": "客服部", "role_code": "super_admin"})


def test_product_cost_redaction_removes_nested_cost_values() -> None:
    item = redact_product_cost_item({
        "sku": "SKU001",
        "cost": "199.90",
        "cost_manual_override": True,
        "gender_costs": {"female": "180", "male": "200"},
        "raw_payload": {
            "颜色": "黑色",
            "成本价": "199.90",
            "预设售价3": "209.90",
        },
        "extra_fields": {
            "gender_costs": {"female": "180", "male": "200"},
            "鞋面材质": "牛皮",
        },
    })

    assert item == {
        "sku": "SKU001",
        "raw_payload": {"颜色": "黑色"},
        "extra_fields": {"鞋面材质": "牛皮"},
    }


def test_product_list_redacts_cost_for_customer_service() -> None:
    class _Repository:
        def is_product_archive_brand(self, brand):
            return brand == "cbanner_mens"

        def list_products(self, brand, **kwargs):
            return {
                "items": [{
                    "id": 1,
                    "sku": "SKU001",
                    "cost": "199.90",
                    "cost_manual_override": True,
                    "image_path": None,
                    "raw_payload": {"成本单价": "199.90", "颜色": "黑色"},
                    "extra_fields": {"gender_costs": {"female": "180", "male": "200"}},
                }],
                "total": 1,
            }

    request = SimpleNamespace(
        state=SimpleNamespace(current_user={
            "department_code": "客服部",
            "role_code": "customer_service_viewer",
        }),
        app=SimpleNamespace(state=SimpleNamespace(
            settings=SimpleNamespace(image_roots={}),
            repository=_Repository(),
        )),
    )

    response = list_products(request, brand="cbanner_mens")
    item = response["items"][0]

    assert "cost" not in item
    assert "cost_manual_override" not in item
    assert "gender_costs" not in item
    assert item["raw_payload"] == {"颜色": "黑色"}
    assert item["extra_fields"] == {}


def test_product_operation_log_redacts_cost_changes() -> None:
    item = redact_product_cost_log_item({
        "summary": "编辑商品 SKU001：修改了 成本、颜色",
        "changed_fields": [
            {"field": "cost", "label": "成本", "before": "100", "after": "120"},
            {"field": "color", "label": "颜色", "before": "黑色", "after": "白色"},
        ],
        "before_data": {"cost": "100", "color": "黑色"},
        "after_data": {"cost": "120", "color": "白色"},
    })

    assert item["changed_fields"] == [
        {"field": "color", "label": "颜色", "before": "黑色", "after": "白色"}
    ]
    assert item["summary"] == "编辑商品 SKU001：修改了 颜色"
    assert item["before_data"] == {"color": "黑色"}
    assert item["after_data"] == {"color": "白色"}


def test_restricted_product_exports_remove_cost_columns() -> None:
    assert "cost" not in _export_columns_for_brand("cbanner_womens", include_cost=False)
    assert "成本价" not in _size_export_headers_for_brand("cbanner_womens", include_cost=False)
    assert "cost" in _export_columns_for_brand("cbanner_womens")
    assert "成本价" in _size_export_headers_for_brand("cbanner_womens")
