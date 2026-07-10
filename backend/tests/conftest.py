from __future__ import annotations

import os
from pathlib import Path

import config as config_module
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine

from config import load_settings
from domain.schema import METADATA
from fileio.image_matcher import ImageMatcher
from storage.product_repository import ProductRepository


@pytest.fixture(scope="session")
def test_database_url() -> str:
    database_url = os.getenv("TEST_DATABASE_URL")
    if not database_url:
        pytest.skip("TEST_DATABASE_URL must be set for backend database tests")
    return database_url


@pytest.fixture
def recreate_tables(test_database_url: str):
    engine = create_engine(test_database_url, future=True)
    METADATA.drop_all(engine)
    METADATA.create_all(engine)
    try:
        yield
    finally:
        METADATA.drop_all(engine)
        engine.dispose()


@pytest.fixture
def repository(test_database_url: str, recreate_tables) -> ProductRepository:
    return ProductRepository(test_database_url)


@pytest.fixture
def test_app_client(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    repository: ProductRepository,
    test_database_url: str,
) -> TestClient:
    backend_root = tmp_path / "backend-root"
    backend_root.mkdir()

    excel_root = tmp_path / "excel"
    cbanner_image_root = tmp_path / "qbd-images"
    yandou_image_root = tmp_path / "yandou-images"
    eblan_image_root = tmp_path / "eblan-images"

    for directory in (excel_root, cbanner_image_root, yandou_image_root, eblan_image_root):
        directory.mkdir()

    (cbanner_image_root / "ABC123.jpg").write_text("x", encoding="utf-8")
    (cbanner_image_root / "FALLBACK123.jpg").write_text("x", encoding="utf-8")

    monkeypatch.setattr(config_module, "BACKEND_ROOT", backend_root)
    monkeypatch.setenv("DATABASE_URL", test_database_url)
    monkeypatch.setenv("FRONTEND_ORIGIN", "http://localhost:3001")
    monkeypatch.setenv("EXCEL_ROOT", str(excel_root))
    monkeypatch.setenv("CBANNER_IMAGE_ROOT", str(cbanner_image_root))
    monkeypatch.setenv("YANDOU_IMAGE_ROOT", str(yandou_image_root))
    monkeypatch.setenv("EBLAN_IMAGE_ROOT", str(eblan_image_root))

    settings = load_settings(require_database=False)

    from api.app import create_app

    app = create_app(
        settings=settings,
        repository=repository,
        image_matchers={
            "cbanner_mens": ImageMatcher(cbanner_image_root),
            "cbanner_womens": ImageMatcher(cbanner_image_root),
            "yandou": ImageMatcher(yandou_image_root),
            "eblan": ImageMatcher(eblan_image_root),
        },
    )

    return TestClient(app)
