from __future__ import annotations

import io

from fastapi.testclient import TestClient
from openpyxl import Workbook

from transform.rows import build_admin_record


def test_get_products_returns_paginated_rows(test_app_client: TestClient, repository):
    repository.create_product(
        "cbanner_mens",
        build_admin_record(
            "cbanner_mens",
            {
                "sku": "A1001",
                "original_sku": "OA1001",
            },
        ),
    )

    response = test_app_client.get(
        "/products",
        params={"brand": "cbanner_mens", "page": 1, "page_size": 20},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 1
    assert body["items"][0]["brand"] == "cbanner_mens"
    assert body["items"][0]["original_sku"] == "OA1001"


def test_get_product_returns_404_when_missing(test_app_client: TestClient):
    response = test_app_client.get("/products/cbanner_mens/99999")

    assert response.status_code == 404
    assert response.json()["detail"] == "Product not found"


def test_post_products_creates_product_via_build_admin_record(test_app_client: TestClient):
    response = test_app_client.post(
        "/products",
        json={
            "brand": "cbanner_mens",
            "payload": {
                "sku": "A1001",
                "original_sku": "OA1001",
                "color": "黑色",
            },
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["message"] == "Product created"
    assert body["item"]["brand"] == "cbanner_mens"
    assert body["item"]["source_workbook"] == "manual_admin"
    assert body["item"]["raw_payload"]["sku"] == "A1001"


def test_put_products_preserves_existing_metadata(test_app_client: TestClient, repository):
    created = repository.create_product(
        "cbanner_mens",
        build_admin_record(
            "cbanner_mens",
            {
                "sku": "A1001",
                "original_sku": "OA1001",
                "color": "黑色",
                "extra_fields": {"数据源列": "原始值"},
            },
        ),
    )

    response = test_app_client.put(
        f"/products/cbanner_mens/{created['id']}",
        json={
            "brand": "cbanner_mens",
            "payload": {
                "sku": "A1001",
                "original_sku": "OA1001",
                "color": "白金",
            },
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["message"] == "Product updated"
    assert body["item"]["color"] == "白金"
    assert body["item"]["source_workbook"] == created["source_workbook"]
    assert body["item"]["source_sheet"] == created["source_sheet"]
    assert body["item"]["source_row_number"] == created["source_row_number"]
    assert body["item"]["extra_fields"] == {"数据源列": "原始值"}


def test_put_products_rejects_brand_mismatch(test_app_client: TestClient, repository):
    created = repository.create_product(
        "cbanner_mens",
        build_admin_record(
            "cbanner_mens",
            {
                "sku": "A1001",
                "original_sku": "OA1001",
            },
        ),
    )

    response = test_app_client.put(
        f"/products/cbanner_mens/{created['id']}",
        json={
            "brand": "yandou",
            "payload": {
                "sku": "A1001",
                "original_sku": "OA1001",
            },
        },
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "Brand mismatch"



def test_put_products_returns_404_for_missing_row(test_app_client: TestClient):
    response = test_app_client.put(
        "/products/cbanner_mens/99999",
        json={
            "brand": "cbanner_mens",
            "payload": {
                "sku": "A1001",
                "original_sku": "OA1001",
            },
        },
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "Product not found"



def test_delete_products_returns_message_and_removes_row(test_app_client: TestClient, repository):
    created = repository.create_product(
        "cbanner_mens",
        build_admin_record(
            "cbanner_mens",
            {
                "sku": "A1001",
                "original_sku": "OA1001",
            },
        ),
    )

    response = test_app_client.delete(f"/products/cbanner_mens/{created['id']}")

    assert response.status_code == 200
    assert response.json() == {"message": "Product deleted"}
    assert repository.get_product("cbanner_mens", created["id"]) is None


def test_delete_products_returns_404_when_missing(test_app_client: TestClient):
    response = test_app_client.delete("/products/cbanner_mens/99999")

    assert response.status_code == 404
    assert response.json()["detail"] == "Product not found"


def test_post_products_rejects_empty_payload(test_app_client: TestClient):
    response = test_app_client.post(
        "/products",
        json={
            "brand": "cbanner_mens",
            "payload": {
                "sku": "   ",
                "original_sku": None,
                "color": "",
            },
        },
    )

    assert response.status_code == 422



def test_product_write_request_forbids_extra_top_level_fields(test_app_client: TestClient):
    response = test_app_client.post(
        "/products",
        json={
            "brand": "cbanner_mens",
            "payload": {
                "sku": "A1001",
                "original_sku": "OA1001",
            },
            "unexpected": "nope",
        },
    )

    assert response.status_code == 422



def test_product_payload_forbids_extra_fields(test_app_client: TestClient):
    response = test_app_client.post(
        "/products",
        json={
            "brand": "cbanner_mens",
            "payload": {
                "sku": "A1001",
                "original_sku": "OA1001",
                "unexpected": "nope",
            },
        },
    )

    assert response.status_code == 422


def test_import_products_updates_by_original_sku_without_clearing_blank_cells(
    test_app_client: TestClient,
    repository,
):
    existing = repository.create_product(
        "cbanner_mens",
        build_admin_record(
            "cbanner_mens",
            {
                "sku": "SKU-OLD",
                "original_sku": "ORIG-001",
                "color": "黑色",
                "upper_material": "牛皮",
                "execution_standard": "QB/T 1002",
                "season_category": "春秋",
            },
        ),
    )

    workbook = Workbook()
    worksheet = workbook.active
    worksheet.append(["货号", "原始货号", "颜色", "鞋面材质", "执行标准", "季节分类"])
    worksheet.append(["", "ORIG-001", "白色", "", "", ""])
    buffer = io.BytesIO()
    workbook.save(buffer)
    buffer.seek(0)

    response = test_app_client.post(
        "/import",
        params={"brand": "cbanner_mens"},
        files={
            "file": (
                "partial-products.xlsx",
                buffer.getvalue(),
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            ),
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["created"] == 0
    assert body["updated"] == 1

    updated = repository.get_product("cbanner_mens", existing["id"])
    assert updated is not None
    assert updated["color"] == "白色"
    assert updated["upper_material"] == "牛皮"
    assert updated["execution_standard"] == "QB/T 1002"
    assert updated["season_category"] == "春秋"

    listing = repository.list_products("cbanner_mens", query="ORIG-001", page=1, page_size=10)
    assert listing["total"] == 1
