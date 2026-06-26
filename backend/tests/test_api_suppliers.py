from __future__ import annotations

from fastapi.testclient import TestClient


def test_suppliers_are_scoped_by_brand(test_app_client: TestClient):
    first = test_app_client.post(
        "/suppliers",
        json={"brand": "cbanner_mens", "name": "同名供应商", "factory_code": "M01"},
    )
    assert first.status_code == 200

    second = test_app_client.post(
        "/suppliers",
        json={"brand": "cbanner_womens", "name": "同名供应商", "factory_code": "W01"},
    )
    assert second.status_code == 200

    mens = test_app_client.get("/suppliers", params={"brand": "cbanner_mens", "page": 1, "page_size": 30})
    assert mens.status_code == 200
    mens_body = mens.json()
    assert mens_body["total"] == 1
    assert mens_body["items"][0]["brand"] == "cbanner_mens"
    assert mens_body["items"][0]["factory_code"] == "M01"

    womens = test_app_client.get("/suppliers", params={"brand": "cbanner_womens", "page": 1, "page_size": 30})
    assert womens.status_code == 200
    womens_body = womens.json()
    assert womens_body["total"] == 1
    assert womens_body["items"][0]["brand"] == "cbanner_womens"
    assert womens_body["items"][0]["factory_code"] == "W01"


def test_suppliers_reject_duplicate_name_in_same_brand(test_app_client: TestClient):
    response = test_app_client.post(
        "/suppliers",
        json={"brand": "cbanner_mens", "name": "重复供应商"},
    )
    assert response.status_code == 200

    duplicate = test_app_client.post(
        "/suppliers",
        json={"brand": "cbanner_mens", "name": "重复供应商"},
    )
    assert duplicate.status_code == 400


def test_suppliers_infer_cbanner_womens_from_supplier_name(test_app_client: TestClient):
    response = test_app_client.post(
        "/suppliers",
        json={"brand": "cbanner_mens", "name": "千百度女鞋华东工厂", "factory_code": "W02"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["item"]["brand"] == "cbanner_womens"

    mens = test_app_client.get("/suppliers", params={"brand": "cbanner_mens", "page": 1, "page_size": 30})
    assert mens.status_code == 200
    assert mens.json()["total"] == 0

    womens = test_app_client.get("/suppliers", params={"brand": "cbanner_womens", "page": 1, "page_size": 30})
    assert womens.status_code == 200
    assert womens.json()["items"][0]["name"] == "千百度女鞋华东工厂"


def test_suppliers_infer_brand_suffixes_from_unit_supplier_name(test_app_client: TestClient):
    cases = [
        ("168（伊伴女鞋）", "eblan"),
        ("百吉鸿女鞋（烟斗）", "yandou"),
        ("笑脸华东工厂", "smiley"),
        ("SMILEY供应商", "smiley"),
        ("小莲供应商", "smiley"),
        ("NI供应商", "ni"),
        ("NIKE华东供应商", "ni"),
        ("耐克供应商", "ni"),
        ("6N6（千百度女鞋）", "cbanner_womens"),
        ("Y8Y9（千百度）", "cbanner_mens"),
    ]

    for name, expected_brand in cases:
        response = test_app_client.post(
            "/suppliers",
            json={"brand": "cbanner_mens", "name": name},
        )
        assert response.status_code == 200
        assert response.json()["item"]["brand"] == expected_brand
