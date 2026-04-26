from __future__ import annotations

from fastapi.testclient import TestClient

from transform.rows import build_admin_record


def test_get_products_returns_paginated_rows(test_app_client: TestClient, repository):
    repository.create_product(
        "qbd_mens",
        build_admin_record(
            "qbd_mens",
            {
                "sku": "A1001",
                "original_sku": "OA1001",
            },
        ),
    )

    response = test_app_client.get(
        "/products",
        params={"brand": "qbd_mens", "page": 1, "page_size": 20},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 1
    assert body["items"][0]["brand"] == "qbd_mens"
    assert body["items"][0]["original_sku"] == "OA1001"


def test_get_product_returns_404_when_missing(test_app_client: TestClient):
    response = test_app_client.get("/products/qbd_mens/99999")

    assert response.status_code == 404
    assert response.json()["detail"] == "Product not found"


def test_post_products_creates_product_via_build_admin_record(test_app_client: TestClient):
    response = test_app_client.post(
        "/products",
        json={
            "brand": "qbd_mens",
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
    assert body["item"]["brand"] == "qbd_mens"
    assert body["item"]["source_workbook"] == "manual_admin"
    assert body["item"]["raw_payload"]["sku"] == "A1001"


def test_put_products_preserves_existing_metadata(test_app_client: TestClient, repository):
    created = repository.create_product(
        "qbd_mens",
        build_admin_record(
            "qbd_mens",
            {
                "sku": "A1001",
                "original_sku": "OA1001",
                "color": "黑色",
            },
        ),
    )

    response = test_app_client.put(
        f"/products/qbd_mens/{created['id']}",
        json={
            "brand": "qbd_mens",
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


def test_put_products_rejects_brand_mismatch(test_app_client: TestClient, repository):
    created = repository.create_product(
        "qbd_mens",
        build_admin_record(
            "qbd_mens",
            {
                "sku": "A1001",
                "original_sku": "OA1001",
            },
        ),
    )

    response = test_app_client.put(
        f"/products/qbd_mens/{created['id']}",
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
        "/products/qbd_mens/99999",
        json={
            "brand": "qbd_mens",
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
        "qbd_mens",
        build_admin_record(
            "qbd_mens",
            {
                "sku": "A1001",
                "original_sku": "OA1001",
            },
        ),
    )

    response = test_app_client.delete(f"/products/qbd_mens/{created['id']}")

    assert response.status_code == 200
    assert response.json() == {"message": "Product deleted"}
    assert repository.get_product("qbd_mens", created["id"]) is None


def test_delete_products_returns_404_when_missing(test_app_client: TestClient):
    response = test_app_client.delete("/products/qbd_mens/99999")

    assert response.status_code == 404
    assert response.json()["detail"] == "Product not found"


def test_post_products_rejects_empty_payload(test_app_client: TestClient):
    response = test_app_client.post(
        "/products",
        json={
            "brand": "qbd_mens",
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
            "brand": "qbd_mens",
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
            "brand": "qbd_mens",
            "payload": {
                "sku": "A1001",
                "original_sku": "OA1001",
                "unexpected": "nope",
            },
        },
    )

    assert response.status_code == 422
