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
        ("NI", "ni"),
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


def test_supplier_brand_can_be_deleted_when_unreferenced(test_app_client: TestClient):
    created = test_app_client.post("/supplier-brands", json={"name": "待删除测试品牌"})
    assert created.status_code == 200

    brand_id = created.json()["item"]["id"]
    deleted = test_app_client.delete(f"/supplier-brands/{brand_id}")

    assert deleted.status_code == 200
    assert deleted.json()["message"] == "删除成功"


def test_supplier_brand_cannot_be_deleted_when_suppliers_exist(test_app_client: TestClient):
    created_brand = test_app_client.post("/supplier-brands", json={"name": "关联供应商测试品牌"})
    assert created_brand.status_code == 200
    brand = created_brand.json()["item"]

    created_supplier = test_app_client.post("/suppliers", json={"brand": brand["code"], "name": "关联供应商"})
    assert created_supplier.status_code == 200

    deleted = test_app_client.delete(f"/supplier-brands/{brand['id']}")
    assert deleted.status_code == 400
    assert "关联供应商" in deleted.json()["detail"]


def test_supplier_brand_and_supplier_operation_logs_are_separate(test_app_client: TestClient):
    created_brand = test_app_client.post("/supplier-brands", json={"name": "日志隔离测试品牌"})
    assert created_brand.status_code == 200
    brand = created_brand.json()["item"]

    created_supplier = test_app_client.post(
        "/suppliers",
        json={"brand": brand["code"], "name": "日志隔离测试供应商"},
    )
    assert created_supplier.status_code == 200

    repository = test_app_client.app.state.operation_log_repository
    brand_logs = repository.list_logs(
        module="supplier_brand",
        query=None,
        page=1,
        page_size=20,
    )
    supplier_logs = repository.list_logs(
        module="supplier",
        query=None,
        page=1,
        page_size=20,
    )

    assert brand_logs["total"] == 1
    assert brand_logs["items"][0]["entity_type"] == "supplier_brand"
    assert supplier_logs["total"] == 1
    assert supplier_logs["items"][0]["entity_type"] == "supplier"
