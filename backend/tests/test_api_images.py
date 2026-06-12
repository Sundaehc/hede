from __future__ import annotations

from fastapi.testclient import TestClient


def test_image_lookup_prefers_original_sku(test_app_client: TestClient):
    response = test_app_client.post(
        "/images/lookup",
        json={"brand": "cbanner_mens", "original_sku": "ABC123", "sku": "FALLBACK123"},
    )

    assert response.status_code == 200
    assert response.json()["found"] is True
    assert response.json()["matched_by"] == "original_sku"
    assert response.json()["image_path"].endswith("ABC123.jpg")


def test_image_lookup_falls_back_to_sku(test_app_client: TestClient):
    response = test_app_client.post(
        "/images/lookup",
        json={"brand": "cbanner_mens", "original_sku": "MISSING", "sku": "FALLBACK123"},
    )

    assert response.status_code == 200
    assert response.json()["found"] is True
    assert response.json()["matched_by"] == "sku"
    assert response.json()["image_path"].endswith("FALLBACK123.jpg")


def test_image_lookup_returns_none_when_no_match(test_app_client: TestClient):
    response = test_app_client.post(
        "/images/lookup",
        json={"brand": "cbanner_mens", "original_sku": "MISSING", "sku": "ALSO_MISSING"},
    )

    assert response.status_code == 200
    assert response.json() == {
        "found": False,
        "image_path": None,
        "matched_by": "none",
        "message": "Image not found",
    }


def test_image_lookup_rejects_missing_lookup_values(test_app_client: TestClient):
    response = test_app_client.post(
        "/images/lookup",
        json={"brand": "cbanner_mens", "original_sku": "   ", "sku": None},
    )

    assert response.status_code == 422



def test_image_lookup_request_forbids_extra_top_level_fields(test_app_client: TestClient):
    response = test_app_client.post(
        "/images/lookup",
        json={
            "brand": "cbanner_mens",
            "original_sku": "ABC123",
            "unexpected": "nope",
        },
    )

    assert response.status_code == 422



def test_create_app_is_import_safe_without_database_url():
    from api.app import create_app
    from config import Settings

    settings = Settings(
        database_url=None,
        frontend_origin="http://localhost:3000",
        excel_root="unused",
        cbanner_image_root="unused",
        yandou_image_root="unused",
        eblan_image_root="unused",
    )

    app = create_app(
        settings=settings,
        repository=object(),
        inventory_repository=object(),
        image_matchers={
            "cbanner_mens": object(),
            "cbanner_womens": object(),
            "yandou": object(),
            "eblan": object(),
        },
    )

    assert app.state.settings is settings
    assert app.state.repository is not None
    assert app.state.inventory_repository is not None
    assert app.state.image_matchers["cbanner_mens"] is not None
