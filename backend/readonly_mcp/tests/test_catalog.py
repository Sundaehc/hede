import pytest

from readonly_mcp.catalog import allowed_datasets
from readonly_mcp.sql_policy import validate_query
from storage.mcp_token_repository import allowed_profiles


def principal(profile, permissions):
    return {"profile": profile, "permissions": ",".join(permissions)}


def test_finance_scope_contains_inventory_purchase_and_price_export_only():
    datasets = allowed_datasets(principal("finance", ["product.view", "product.price_export", "inventory.view", "purchase.view"]))
    assert {"products", "product_prices", "purchase_orders", "inventory_records", "jst_full_stock"} <= datasets.keys()
    assert "vip_product_daily" not in datasets
    assert "product_auxiliary_attributes" not in datasets


def test_merchandise_scope_contains_product_and_fine_table_data():
    datasets = allowed_datasets(principal("merchandise", ["product.view", "product.manage", "fine_table.view", "purchase.view", "inventory.view"]))
    assert {"products", "fine_table_snapshot_batches", "purchase_orders", "color_barcodes"} <= datasets.keys()
    assert "product_prices" in datasets


def test_operation_scope_excludes_inventory_and_reference_management():
    datasets = allowed_datasets(principal("operation", ["product.view", "product.manage", "fine_table.view", "purchase.view"]))
    assert {"products", "vip_product_daily", "purchase_orders", "product_goods_overrides"} <= datasets.keys()
    assert "inventory_records" not in datasets
    assert "color_barcodes" not in datasets


def test_development_scope_contains_all_business_permissions():
    datasets = allowed_datasets(principal("development", ["product.view", "product.manage", "fine_table.view", "purchase.view", "inventory.view"]))
    assert {"products", "inventory_records", "vip_product_daily", "product_goods_overrides", "color_barcodes"} <= datasets.keys()
    assert "product_prices" in datasets


def test_department_queries_only_use_authorized_views():
    finance = principal("finance", ["product.view", "inventory.view", "purchase.view"])
    operation = principal("operation", ["product.view", "fine_table.view", "purchase.view"])
    assert validate_query("SELECT sku, cost FROM product_prices", {}, finance).datasets == ("product_prices",)
    assert validate_query("SELECT sales_date, sales_quantity FROM jst_daily_sales", {}, operation).datasets == ("jst_daily_sales",)
    for identity, sql in (
        (finance, "SELECT * FROM vip_daily_sales"),
        (operation, "SELECT * FROM inventory_records"),
        (operation, "SELECT * FROM product_prices WHERE raw_payload IS NOT NULL"),
        (operation, "SELECT * FROM dewu_orders WHERE recipient_phone IS NOT NULL"),
        (operation, "SELECT * FROM size_groups"),
    ):
        with pytest.raises(ValueError):
            validate_query(sql, {}, identity)


def test_profile_binding_follows_department_and_current_permissions():
    user = {"status": "active", "role_code": "product_user", "department_code": "商品部",
            "permissions": "product.view,fine_table.view"}
    assert "merchandise" in allowed_profiles(user)
    user["department_code"] = "美工部"
    assert "merchandise" not in allowed_profiles(user)
    assert "design" in allowed_profiles(user)
    user["permissions"] = "fine_table.view"
    assert allowed_profiles(user) == []
