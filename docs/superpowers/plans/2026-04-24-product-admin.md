# Product Admin Page Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a shadcn-based product admin page in `frontend/` plus a lightweight FastAPI API layer in `backend/` for brand-tabbed listing, `original_sku` search, CRUD, and image lookup.

**Architecture:** Keep `frontend/` responsible only for UI state and API calls. Add a new backend web layer that reuses the existing PostgreSQL schema, row normalization helpers, and image directory settings through a dedicated repository plus FastAPI routes.

**Tech Stack:** Next.js 16, React 19, TypeScript, shadcn/Radix, pnpm, FastAPI, SQLAlchemy 2, pytest, Vitest, Testing Library

---

## Working assumptions

- Backend commands run from `E:\hede\backend`.
- Frontend commands run from `E:\hede\frontend`.
- Add `FRONTEND_ORIGIN=http://localhost:3000` to `backend/.env` for local CORS.
- Add `NEXT_PUBLIC_API_BASE_URL=http://127.0.0.1:8000` to `frontend/.env.local` for local API calls.
- Create a dedicated PostgreSQL test database and export `TEST_DATABASE_URL` before backend integration tests.
- Keep all UI code under `frontend/`; do not create frontend code anywhere else.

## File structure

### Modify

- `.gitignore` — ignore `frontend/.env.local`
- `backend/pyproject.toml` — add FastAPI runtime deps and backend API test deps
- `backend/config.py` — add `frontend_origin` setting
- `backend/transform/rows.py` — add manual admin payload normalization helpers
- `backend/tests/test_config.py` — cover `FRONTEND_ORIGIN`
- `backend/tests/test_transform.py` — cover admin payload normalization and metadata rules
- `frontend/package.json` — add Vitest scripts and test dependencies
- `frontend/app/page.tsx` — replace placeholder with admin page entrypoint

### Create

- `backend/api/__init__.py`
- `backend/api/app.py`
- `backend/api/schemas.py`
- `backend/api/routes/__init__.py`
- `backend/api/routes/products.py`
- `backend/api/routes/images.py`
- `backend/api_main.py`
- `backend/storage/product_repository.py`
- `backend/tests/conftest.py`
- `backend/tests/test_product_repository.py`
- `backend/tests/test_api_products.py`
- `backend/tests/test_api_images.py`
- `frontend/vitest.config.ts`
- `frontend/vitest.setup.ts`
- `frontend/components/ui/input.tsx`
- `frontend/components/ui/tabs.tsx`
- `frontend/components/ui/dialog.tsx`
- `frontend/components/ui/label.tsx`
- `frontend/components/ui/table.tsx`
- `frontend/components/ui/alert.tsx`
- `frontend/components/ui/select.tsx`
- `frontend/lib/brands.ts`
- `frontend/lib/types.ts`
- `frontend/lib/api.ts`
- `frontend/lib/api.test.ts`
- `frontend/components/product-admin/product-admin-page.tsx`
- `frontend/components/product-admin/product-admin-page.test.tsx`
- `frontend/components/product-admin/product-toolbar.tsx`
- `frontend/components/product-admin/product-tabs.tsx`
- `frontend/components/product-admin/product-table.tsx`
- `frontend/components/product-admin/product-form-dialog.tsx`
- `frontend/components/product-admin/product-form-dialog.test.tsx`
- `frontend/components/product-admin/image-lookup-status.tsx`
- `frontend/components/product-admin/delete-product-dialog.tsx`

## Chunk 1: Backend API foundation

### Task 1: Add backend web dependencies and config plumbing

**Files:**
- Modify: `backend/pyproject.toml`
- Modify: `backend/config.py`
- Test: `backend/tests/test_config.py`

- [ ] **Step 1: Write the failing tests**

```python
from pathlib import Path

import config as config_module
from config import load_settings


def test_load_settings_defaults_frontend_origin(monkeypatch, tmp_path: Path):
    monkeypatch.setattr(config_module, "BACKEND_ROOT", tmp_path)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("FRONTEND_ORIGIN", raising=False)

    settings = load_settings(require_database=False)

    assert settings.frontend_origin == "http://localhost:3000"


def test_load_settings_reads_frontend_origin_from_env(monkeypatch, tmp_path: Path):
    monkeypatch.setattr(config_module, "BACKEND_ROOT", tmp_path)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setenv("FRONTEND_ORIGIN", "http://127.0.0.1:3001")

    settings = load_settings(require_database=False)

    assert settings.frontend_origin == "http://127.0.0.1:3001"
```

- [ ] **Step 2: Run the tests to verify they fail**

Run:
```bash
python -m pytest tests/test_config.py -v
```

Expected: FAIL with `AttributeError` or assertion failure because `Settings` has no `frontend_origin`.

- [ ] **Step 3: Write the minimal implementation**

Add the new setting to `backend/config.py` and add web dependencies to `backend/pyproject.toml`.

```python
@dataclass(frozen=True)
class Settings:
    database_url: str | None
    excel_root: Path
    qbd_image_root: Path
    yandou_image_root: Path
    yiban_image_root: Path
    frontend_origin: str
```

```python
return Settings(
    database_url=database_url,
    excel_root=_path_from_env("EXCEL_SOURCE_ROOT", DEFAULT_EXCEL_ROOT),
    qbd_image_root=_path_from_env("QBD_IMAGE_ROOT", DEFAULT_QBD_IMAGE_ROOT),
    yandou_image_root=_path_from_env("YANDOU_IMAGE_ROOT", DEFAULT_YANDOU_IMAGE_ROOT),
    yiban_image_root=_path_from_env("YIBAN_IMAGE_ROOT", DEFAULT_YIBAN_IMAGE_ROOT),
    frontend_origin=os.getenv("FRONTEND_ORIGIN", "http://localhost:3000"),
)
```

```toml
[project]
dependencies = [
    "openpyxl>=3.1.5",
    "python-dotenv>=1.1.1",
    "SQLAlchemy>=2.0.44",
    "psycopg[binary]>=3.2.12",
    "xlrd>=2.0.2",
    "fastapi>=0.115.0",
    "uvicorn>=0.32.0",
]

[project.optional-dependencies]
dev = [
    "pytest>=8.4.2",
    "httpx>=0.28.0",
]
```

- [ ] **Step 4: Run the tests to verify they pass**

Run:
```bash
python -m pytest tests/test_config.py -v
```

Expected: PASS for the existing dry-run test and the two new `FRONTEND_ORIGIN` tests.

- [ ] **Step 5: Commit**

```bash
git add pyproject.toml config.py tests/test_config.py
git commit -m "feat: add backend web configuration"
```

### Task 2: Add manual admin payload normalization helpers

**Files:**
- Modify: `backend/transform/rows.py`
- Test: `backend/tests/test_transform.py`

- [ ] **Step 1: Write the failing tests**

```python
from decimal import Decimal

from transform.rows import build_admin_record, normalize_admin_payload


def test_normalize_admin_payload_coerces_supported_fields():
    payload = {
        "sku": " A1001 ",
        "original_sku": " OA1001 ",
        "cost": "199.50",
        "first_order_time": "2026/04/24 10:11:12",
        "color": "#N/A",
        "unknown": "ignored",
    }

    normalized = normalize_admin_payload(payload)

    assert normalized["sku"] == "A1001"
    assert normalized["original_sku"] == "OA1001"
    assert normalized["cost"] == Decimal("199.50")
    assert normalized["first_order_time"] == "2026-04-24"
    assert normalized["color"] is None
    assert "unknown" not in normalized


def test_build_admin_record_uses_manual_metadata_for_new_rows():
    record = build_admin_record("qbd_mens", {"sku": "A1001", "original_sku": "A1001"})

    assert record["source_workbook"] == "manual_admin"
    assert record["source_sheet"] == "qbd_mens"
    assert record["source_row_number"] == "manual"
    assert record["raw_payload"]["sku"] == "A1001"


def test_build_admin_record_preserves_existing_source_metadata():
    existing = {
        "source_workbook": "qbd_mens_25",
        "source_sheet": "25年春季款",
        "source_row_number": "18",
    }

    record = build_admin_record(
        "qbd_mens",
        {"sku": "A1001", "original_sku": "A1001"},
        existing_metadata=existing,
    )

    assert record["source_workbook"] == "qbd_mens_25"
    assert record["source_sheet"] == "25年春季款"
    assert record["source_row_number"] == "18"
```

- [ ] **Step 2: Run the tests to verify they fail**

Run:
```bash
python -m pytest tests/test_transform.py -v
```

Expected: FAIL with `ImportError` because `normalize_admin_payload` and `build_admin_record` do not exist yet.

- [ ] **Step 3: Write the minimal implementation**

Add explicit editable-column normalization helpers to `backend/transform/rows.py`.

```python
ADMIN_EDITABLE_COLUMNS = (
    "image_path",
    "sku",
    "original_sku",
    "group_name",
    "cost",
    "factory_sku",
    "color",
    "season_category",
    "year",
    "upper_material",
    "lining_material",
    "outsole_material",
    "insole_material",
    "execution_standard",
    "heel_height",
    "shoe_width",
    "shoe_length",
    "shaft_circumference",
    "shaft_height",
    "internal_height_increase",
    "internal_height_note",
    "upper_height",
    "toe_shape",
    "closure_type",
    "shoe_box_spec",
    "first_order_time",
)


def normalize_admin_payload(payload: dict[str, object]) -> dict[str, object]:
    normalized: dict[str, object] = {}
    for column in ADMIN_EDITABLE_COLUMNS:
        if column not in payload:
            continue
        value = payload[column]
        if column == "cost":
            normalized[column] = coerce_cost(value)
        elif column == "first_order_time":
            normalized[column] = normalize_first_order_time(value)
        else:
            normalized[column] = normalize_cell(value)
    return normalized


def build_admin_record(
    brand: str,
    payload: dict[str, object],
    *,
    existing_metadata: dict[str, object] | None = None,
) -> dict[str, object]:
    normalized = normalize_admin_payload(payload)
    metadata = existing_metadata or {
        "source_workbook": "manual_admin",
        "source_sheet": brand,
        "source_row_number": "manual",
    }
    return {
        **{column: normalized.get(column) for column in ADMIN_EDITABLE_COLUMNS},
        "source_workbook": metadata["source_workbook"],
        "source_sheet": metadata["source_sheet"],
        "source_row_number": metadata["source_row_number"],
        "raw_payload": normalized,
    }
```

- [ ] **Step 4: Run the tests to verify they pass**

Run:
```bash
python -m pytest tests/test_transform.py -v
```

Expected: PASS for existing importer tests and the three new admin-normalization tests.

- [ ] **Step 5: Commit**

```bash
git add transform/rows.py tests/test_transform.py
git commit -m "feat: add admin payload normalization helpers"
```

### Task 3: Add the product repository

**Files:**
- Create: `backend/storage/product_repository.py`
- Create: `backend/tests/conftest.py`
- Create: `backend/tests/test_product_repository.py`

- [ ] **Step 1: Write the failing repository tests**

```python
from storage.product_repository import ProductRepository
from transform.rows import build_admin_record


def test_list_products_filters_by_original_sku(repository: ProductRepository):
    repository.create_product("qbd_mens", build_admin_record("qbd_mens", {
        "sku": "A1001",
        "original_sku": "OA1001",
        "color": "黑色",
    }))
    repository.create_product("qbd_mens", build_admin_record("qbd_mens", {
        "sku": "B2002",
        "original_sku": "OB2002",
        "color": "白色",
    }))

    page = repository.list_products("qbd_mens", query="OA", page=1, page_size=20)

    assert page["total"] == 1
    assert page["items"][0]["original_sku"] == "OA1001"


def test_create_update_and_get_product(repository: ProductRepository):
    created = repository.create_product("qbd_mens", build_admin_record("qbd_mens", {
        "sku": "A1001",
        "original_sku": "OA1001",
        "color": "黑色",
    }))

    updated = repository.update_product(
        "qbd_mens",
        created["id"],
        build_admin_record(
            "qbd_mens",
            {"sku": "A1001", "original_sku": "OA1001", "color": "白金"},
            existing_metadata=created,
        ),
    )

    fetched = repository.get_product("qbd_mens", created["id"])

    assert updated["color"] == "白金"
    assert fetched["source_workbook"] == created["source_workbook"]


def test_delete_product_removes_row(repository: ProductRepository):
    created = repository.create_product("qbd_mens", build_admin_record("qbd_mens", {
        "sku": "A1001",
        "original_sku": "OA1001",
    }))

    deleted = repository.delete_product("qbd_mens", created["id"])

    assert deleted is True
    assert repository.get_product("qbd_mens", created["id"]) is None
```

Add `backend/tests/conftest.py` with a fixture that recreates the four product tables inside `TEST_DATABASE_URL` before each test module.

```python
import os

import pytest
from sqlalchemy import create_engine

from domain.schema import METADATA
from storage.product_repository import ProductRepository


@pytest.fixture
def repository():
    database_url = os.environ["TEST_DATABASE_URL"]
    engine = create_engine(database_url, future=True)
    METADATA.drop_all(engine)
    METADATA.create_all(engine)
    try:
        yield ProductRepository(database_url)
    finally:
        METADATA.drop_all(engine)
```

- [ ] **Step 2: Run the tests to verify they fail**

Run:
```bash
TEST_DATABASE_URL="postgresql+psycopg://postgres:12345678@127.0.0.1:5432/commodity_department_test" python -m pytest tests/test_product_repository.py -v
```

Expected: FAIL with `ModuleNotFoundError` because `storage.product_repository` does not exist yet.

- [ ] **Step 3: Write the minimal implementation**

Create `backend/storage/product_repository.py`.

```python
from __future__ import annotations

from sqlalchemy import delete, func, insert, select, update
from sqlalchemy.engine import create_engine

from domain.schema import PRODUCT_TABLES


class ProductRepository:
    def __init__(self, database_url: str):
        self.engine = create_engine(database_url, future=True)

    def _table(self, brand: str):
        return PRODUCT_TABLES[brand]

    def list_products(self, brand: str, *, query: str | None, page: int, page_size: int) -> dict[str, object]:
        table = self._table(brand)
        conditions = []
        if query:
            conditions.append(table.c.original_sku.ilike(f"%{query}%"))
        base = select(table).order_by(table.c.id.desc())
        count = select(func.count()).select_from(table)
        for condition in conditions:
            base = base.where(condition)
            count = count.where(condition)
        offset = (page - 1) * page_size
        with self.engine.begin() as connection:
            items = [dict(row._mapping) for row in connection.execute(base.limit(page_size).offset(offset))]
            total = connection.execute(count).scalar_one()
        return {"items": items, "total": total, "page": page, "page_size": page_size}

    def get_product(self, brand: str, product_id: int) -> dict[str, object] | None:
        table = self._table(brand)
        statement = select(table).where(table.c.id == product_id)
        with self.engine.begin() as connection:
            row = connection.execute(statement).mappings().first()
        return dict(row) if row else None

    def create_product(self, brand: str, record: dict[str, object]) -> dict[str, object]:
        table = self._table(brand)
        statement = insert(table).values(record).returning(table)
        with self.engine.begin() as connection:
            row = connection.execute(statement).mappings().one()
        return dict(row)

    def update_product(self, brand: str, product_id: int, record: dict[str, object]) -> dict[str, object] | None:
        table = self._table(brand)
        statement = update(table).where(table.c.id == product_id).values(record).returning(table)
        with self.engine.begin() as connection:
            row = connection.execute(statement).mappings().first()
        return dict(row) if row else None

    def delete_product(self, brand: str, product_id: int) -> bool:
        table = self._table(brand)
        statement = delete(table).where(table.c.id == product_id)
        with self.engine.begin() as connection:
            result = connection.execute(statement)
        return result.rowcount > 0
```

- [ ] **Step 4: Run the tests to verify they pass**

Run:
```bash
TEST_DATABASE_URL="postgresql+psycopg://postgres:12345678@127.0.0.1:5432/commodity_department_test" python -m pytest tests/test_product_repository.py -v
```

Expected: PASS for search, CRUD, and delete coverage.

- [ ] **Step 5: Commit**

```bash
git add storage/product_repository.py tests/conftest.py tests/test_product_repository.py
git commit -m "feat: add product repository"
```

### Task 4: Add the FastAPI app and routes

**Files:**
- Create: `backend/api/__init__.py`
- Create: `backend/api/app.py`
- Create: `backend/api/schemas.py`
- Create: `backend/api/routes/__init__.py`
- Create: `backend/api/routes/products.py`
- Create: `backend/api/routes/images.py`
- Create: `backend/api_main.py`
- Create: `backend/tests/test_api_products.py`
- Create: `backend/tests/test_api_images.py`

- [ ] **Step 1: Write the failing API tests**

```python
from fastapi.testclient import TestClient

from api.app import create_app
from transform.rows import build_admin_record


def test_get_products_returns_paginated_rows(test_app_client: TestClient, seeded_repository):
    seeded_repository.create_product("qbd_mens", build_admin_record("qbd_mens", {
        "sku": "A1001",
        "original_sku": "OA1001",
    }))

    response = test_app_client.get("/products", params={"brand": "qbd_mens", "page": 1, "page_size": 20})

    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 1
    assert body["items"][0]["brand"] == "qbd_mens"


def test_post_images_lookup_prefers_original_sku(test_app_client: TestClient):
    response = test_app_client.post(
        "/images/lookup",
        json={"brand": "qbd_mens", "original_sku": "ABC123", "sku": "FALLBACK123"},
    )

    assert response.status_code == 200
    assert response.json()["matched_by"] == "original_sku"


def test_put_products_returns_404_for_missing_row(test_app_client: TestClient):
    response = test_app_client.put(
        "/products/qbd_mens/99999",
        json={"brand": "qbd_mens", "payload": {"sku": "A1001", "original_sku": "OA1001"}},
    )

    assert response.status_code == 404
```

Use `backend/tests/conftest.py` to add a `test_app_client` fixture with temp image directories and a repository bound to `TEST_DATABASE_URL`.

```python
import os
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine

import config as config_module
from api.app import create_app
from config import load_settings
from domain.schema import METADATA
from storage.product_repository import ProductRepository


@pytest.fixture
def repository(monkeypatch, tmp_path: Path):
    database_url = os.environ["TEST_DATABASE_URL"]
    engine = create_engine(database_url, future=True)
    METADATA.drop_all(engine)
    METADATA.create_all(engine)

    backend_root = tmp_path / "backend-root"
    backend_root.mkdir()
    monkeypatch.setattr(config_module, "BACKEND_ROOT", backend_root)
    monkeypatch.setenv("DATABASE_URL", database_url)
    monkeypatch.setenv("FRONTEND_ORIGIN", "http://localhost:3000")
    monkeypatch.setenv("EXCEL_SOURCE_ROOT", str(tmp_path / "excel"))
    monkeypatch.setenv("QBD_IMAGE_ROOT", str(tmp_path / "qbd-images"))
    monkeypatch.setenv("YANDOU_IMAGE_ROOT", str(tmp_path / "yandou-images"))
    monkeypatch.setenv("YIBAN_IMAGE_ROOT", str(tmp_path / "yiban-images"))

    for directory in ["excel", "qbd-images", "yandou-images", "yiban-images"]:
        (tmp_path / directory).mkdir()

    try:
        yield ProductRepository(database_url)
    finally:
        METADATA.drop_all(engine)


@pytest.fixture
def seeded_repository(repository: ProductRepository) -> ProductRepository:
    return repository


@pytest.fixture
def test_app_client(monkeypatch, tmp_path: Path, repository: ProductRepository):
    qbd_image = tmp_path / "qbd-images" / "ABC123.jpg"
    qbd_image.write_text("x", encoding="utf-8")

    settings = load_settings(require_database=False)
    app = create_app(settings=settings, repository=repository)
    return TestClient(app)
```

- [ ] **Step 2: Run the tests to verify they fail**

Run:
```bash
TEST_DATABASE_URL="postgresql+psycopg://postgres:12345678@127.0.0.1:5432/commodity_department_test" python -m pytest tests/test_api_products.py tests/test_api_images.py -v
```

Expected: FAIL with `ModuleNotFoundError` because `api.app` and route modules do not exist yet.

- [ ] **Step 3: Write the minimal implementation**

Create `backend/api/schemas.py` with strict request/response models.

```python
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

BrandKey = Literal["qbd_mens", "qbd_womens", "yandou", "yiban"]


class ProductPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")
    image_path: str | None = None
    sku: str | None = None
    original_sku: str | None = None
    group_name: str | None = None
    cost: str | None = None
    factory_sku: str | None = None
    color: str | None = None
    season_category: str | None = None
    year: str | None = None
    upper_material: str | None = None
    lining_material: str | None = None
    outsole_material: str | None = None
    insole_material: str | None = None
    execution_standard: str | None = None
    heel_height: str | None = None
    shoe_width: str | None = None
    shoe_length: str | None = None
    shaft_circumference: str | None = None
    shaft_height: str | None = None
    internal_height_increase: str | None = None
    internal_height_note: str | None = None
    upper_height: str | None = None
    toe_shape: str | None = None
    closure_type: str | None = None
    shoe_box_spec: str | None = None
    first_order_time: str | None = None


class ProductWriteRequest(BaseModel):
    brand: BrandKey
    payload: ProductPayload


class ImageLookupRequest(BaseModel):
    brand: BrandKey
    original_sku: str | None = None
    sku: str | None = None
```

Create `backend/api/app.py` with an overridable app factory. Do **not** instantiate the app at module import time; tests must be able to import `create_app` without requiring a real `DATABASE_URL`.

```python
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from domain.sources import IMAGE_BRAND_KEYS, TABLE_NAMES
from fileio.image_matcher import ImageMatcher
from storage.product_repository import ProductRepository
from api.routes.images import router as images_router
from api.routes.products import router as products_router


def create_app(*, settings, repository=None, image_matchers=None) -> FastAPI:
    if settings.database_url is None and repository is None:
        raise ValueError("database_url is required when repository is not provided")

    resolved_repository = repository or ProductRepository(settings.database_url)
    resolved_matchers = image_matchers or {
        brand: ImageMatcher(settings.image_roots[IMAGE_BRAND_KEYS[brand]])
        for brand in TABLE_NAMES
    }

    app = FastAPI(title="Hede Product Admin API")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[settings.frontend_origin],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.state.settings = settings
    app.state.repository = resolved_repository
    app.state.image_matchers = resolved_matchers
    app.include_router(products_router)
    app.include_router(images_router)
    return app
```

Create `backend/api/routes/products.py` and `backend/api/routes/images.py`.

```python
from fastapi import APIRouter, HTTPException, Request

from api.schemas import ImageLookupRequest, ProductWriteRequest
from transform.rows import build_admin_record

router = APIRouter()


@router.get("/products")
def list_products(request: Request, brand: str, query: str | None = None, page: int = 1, page_size: int = 20):
    payload = request.app.state.repository.list_products(brand, query=query, page=page, page_size=page_size)
    payload["items"] = [{**item, "brand": brand} for item in payload["items"]]
    return payload


@router.get("/products/{brand}/{product_id}")
def get_product(request: Request, brand: str, product_id: int):
    item = request.app.state.repository.get_product(brand, product_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Product not found")
    return {**item, "brand": brand}


@router.post("/products")
def create_product(request: Request, body: ProductWriteRequest):
    record = build_admin_record(body.brand, body.payload.model_dump(exclude_none=False))
    item = request.app.state.repository.create_product(body.brand, record)
    return {"item": {**item, "brand": body.brand}, "message": "Product created"}


@router.put("/products/{brand}/{product_id}")
def update_product(request: Request, brand: str, product_id: int, body: ProductWriteRequest):
    existing = request.app.state.repository.get_product(brand, product_id)
    if existing is None:
        raise HTTPException(status_code=404, detail="Product not found")
    record = build_admin_record(brand, body.payload.model_dump(exclude_none=False), existing_metadata=existing)
    item = request.app.state.repository.update_product(brand, product_id, record)
    return {"item": {**item, "brand": brand}, "message": "Product updated"}


@router.delete("/products/{brand}/{product_id}")
def delete_product(request: Request, brand: str, product_id: int):
    deleted = request.app.state.repository.delete_product(brand, product_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Product not found")
    return {"message": "Product deleted"}
```

```python
@router.post("/images/lookup")
def lookup_image(request: Request, body: ImageLookupRequest):
    matchers = request.app.state.image_matchers
    if body.original_sku:
        image_path = matchers[body.brand].find(body.original_sku)
        if image_path:
            return {
                "found": True,
                "image_path": image_path,
                "matched_by": "original_sku",
                "message": "Image found",
            }
    if body.sku:
        image_path = matchers[body.brand].find(body.sku)
        if image_path:
            return {
                "found": True,
                "image_path": image_path,
                "matched_by": "sku",
                "message": "Image found",
            }
    return {
        "found": False,
        "image_path": None,
        "matched_by": "none",
        "message": "Image not found",
    }
```

Create `backend/api_main.py`.

```python
from api.app import create_app
from config import load_settings

settings = load_settings(require_database=True)
app = create_app(settings=settings)
```

- [ ] **Step 4: Run the tests and a manual smoke check**

Run:
```bash
TEST_DATABASE_URL="postgresql+psycopg://postgres:12345678@127.0.0.1:5432/commodity_department_test" python -m pytest tests/test_api_products.py tests/test_api_images.py -v
uvicorn api_main:app --reload
```

Expected:
- pytest PASS
- Uvicorn starts on `http://127.0.0.1:8000`
- `GET /products?brand=qbd_mens&page=1&page_size=20` returns JSON

- [ ] **Step 5: Commit**

```bash
git add api api_main.py tests/test_api_products.py tests/test_api_images.py
git commit -m "feat: add product admin api"
```

## Chunk 2: Frontend foundation

### Task 5: Add frontend test harness, env ignore, and shadcn primitives

**Files:**
- Modify: `.gitignore`
- Modify: `frontend/package.json`
- Create: `frontend/vitest.config.ts`
- Create: `frontend/vitest.setup.ts`
- Create: `frontend/components/ui/input.tsx`
- Create: `frontend/components/ui/tabs.tsx`
- Create: `frontend/components/ui/dialog.tsx`
- Create: `frontend/components/ui/label.tsx`
- Create: `frontend/components/ui/table.tsx`
- Create: `frontend/components/ui/alert.tsx`
- Create: `frontend/components/ui/select.tsx`
- Create: `frontend/components/product-admin/product-admin-page.tsx`
- Create: `frontend/components/product-admin/product-admin-page.test.tsx`
- Modify: `frontend/app/page.tsx`

- [ ] **Step 1: Write the failing frontend smoke test**

```tsx
import { render, screen } from "@testing-library/react"

import { ProductAdminPage } from "@/components/product-admin/product-admin-page"


test("renders the admin heading and default brand tab", () => {
  render(<ProductAdminPage />)

  expect(screen.getByRole("heading", { name: "商品管理" })).toBeInTheDocument()
  expect(screen.getByRole("tab", { name: "千百度男鞋" })).toBeInTheDocument()
})
```

- [ ] **Step 2: Run the test to verify it fails**

Run:
```bash
pnpm exec vitest run components/product-admin/product-admin-page.test.tsx
```

Expected: FAIL because Vitest is not configured and `ProductAdminPage` does not exist yet.

- [ ] **Step 3: Add the harness and minimal page shell**

Install test tooling and generate the shadcn primitives.

```bash
pnpm add -D vitest jsdom @testing-library/react @testing-library/jest-dom @testing-library/user-event
pnpm dlx shadcn@latest add input tabs dialog label table alert select
```

Update `.gitignore`.

```gitignore
frontend/.env.local
```

Update `frontend/package.json`.

```json
{
  "scripts": {
    "dev": "next dev --turbopack",
    "build": "next build",
    "lint": "eslint",
    "format": "prettier --write \"**/*.{ts,tsx}\"",
    "typecheck": "tsc --noEmit",
    "test": "vitest run",
    "test:watch": "vitest"
  }
}
```

Create `frontend/vitest.config.ts` and `frontend/vitest.setup.ts`.

```ts
import path from "node:path"
import { defineConfig } from "vitest/config"

export default defineConfig({
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: ["./vitest.setup.ts"],
  },
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "."),
    },
  },
})
```

```ts
import "@testing-library/jest-dom/vitest"
```

Create the minimal page wrapper.

```tsx
// frontend/components/product-admin/product-admin-page.tsx
"use client"

export function ProductAdminPage() {
  return (
    <div className="flex min-h-svh flex-col gap-4 p-6">
      <h1 className="text-2xl font-semibold">商品管理</h1>
      <div role="tablist">
        <button role="tab">千百度男鞋</button>
        <button role="tab">千百度女鞋</button>
        <button role="tab">烟斗</button>
        <button role="tab">伊伴</button>
      </div>
    </div>
  )
}
```

```tsx
// frontend/app/page.tsx
import { ProductAdminPage } from "@/components/product-admin/product-admin-page"

export default function Page() {
  return <ProductAdminPage />
}
```

- [ ] **Step 4: Run the smoke test to verify it passes**

Run:
```bash
pnpm exec vitest run components/product-admin/product-admin-page.test.tsx
```

Expected: PASS with the heading and default brand tab rendered.

- [ ] **Step 5: Commit**

```bash
git add ../.gitignore package.json vitest.config.ts vitest.setup.ts app/page.tsx components/ui components/product-admin/product-admin-page.tsx components/product-admin/product-admin-page.test.tsx
git commit -m "feat: add frontend admin page scaffold"
```

### Task 6: Add shared frontend brand/types/API modules

**Files:**
- Create: `frontend/lib/brands.ts`
- Create: `frontend/lib/types.ts`
- Create: `frontend/lib/api.ts`
- Create: `frontend/lib/api.test.ts`

- [ ] **Step 1: Write the failing API client tests**

```tsx
import { beforeEach, expect, test, vi } from "vitest"

import { ApiError, listProducts, lookupImage } from "@/lib/api"

beforeEach(() => {
  vi.restoreAllMocks()
})

test("listProducts serializes brand query and pagination", async () => {
  const fetchMock = vi.spyOn(global, "fetch").mockResolvedValue(
    new Response(JSON.stringify({ items: [], total: 0, page: 1, page_size: 20 }), {
      status: 200,
      headers: { "Content-Type": "application/json" },
    }),
  )

  await listProducts({ brand: "qbd_mens", query: "OA", page: 1, pageSize: 20 })

  expect(fetchMock).toHaveBeenCalledWith(
    "http://127.0.0.1:8000/products?brand=qbd_mens&query=OA&page=1&page_size=20",
    expect.any(Object),
  )
})

test("lookupImage throws ApiError on non-2xx responses", async () => {
  vi.spyOn(global, "fetch").mockResolvedValue(new Response("boom", { status: 500 }))

  await expect(lookupImage({ brand: "qbd_mens", originalSku: "ABC123", sku: null })).rejects.toBeInstanceOf(ApiError)
})
```

- [ ] **Step 2: Run the tests to verify they fail**

Run:
```bash
pnpm exec vitest run lib/api.test.ts
```

Expected: FAIL because `frontend/lib/api.ts` does not exist yet.

- [ ] **Step 3: Write the minimal implementation**

Create `frontend/lib/brands.ts`.

```ts
export const BRANDS = [
  { key: "qbd_mens", label: "千百度男鞋" },
  { key: "qbd_womens", label: "千百度女鞋" },
  { key: "yandou", label: "烟斗" },
  { key: "yiban", label: "伊伴" },
] as const

export type BrandKey = (typeof BRANDS)[number]["key"]
```

Create `frontend/lib/types.ts`.

```ts
import type { BrandKey } from "@/lib/brands"

export type ProductItem = {
  id: number
  brand: BrandKey
  image_path: string | null
  sku: string | null
  original_sku: string | null
  color: string | null
  year: string | null
  season_category: string | null
  cost: string | null
  toe_shape: string | null
  execution_standard: string | null
  first_order_time: string | null
  source_workbook: string
  source_sheet: string
  source_row_number: string
}

export type ProductListResponse = {
  items: ProductItem[]
  total: number
  page: number
  page_size: number
}

export type ImageLookupResult = {
  found: boolean
  image_path: string | null
  matched_by: "original_sku" | "sku" | "none"
  message: string
}
```

Create `frontend/lib/api.ts`.

```ts
import type { BrandKey } from "@/lib/brands"
import type { ImageLookupResult, ProductItem, ProductListResponse } from "@/lib/types"

const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://127.0.0.1:8000"

export class ApiError extends Error {
  constructor(public status: number, message: string) {
    super(message)
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...(init?.headers ?? {}),
    },
  })

  if (!response.ok) {
    throw new ApiError(response.status, await response.text())
  }

  return (await response.json()) as T
}

export function listProducts(params: { brand: BrandKey; query: string; page: number; pageSize: number }) {
  const search = new URLSearchParams({
    brand: params.brand,
    query: params.query,
    page: String(params.page),
    page_size: String(params.pageSize),
  })
  return request<ProductListResponse>(`/products?${search.toString()}`)
}

export function getProduct(brand: BrandKey, id: number) {
  return request<ProductItem>(`/products/${brand}/${id}`)
}

export function createProduct(brand: BrandKey, payload: Record<string, unknown>) {
  return request<{ item: ProductItem; message: string }>("/products", {
    method: "POST",
    body: JSON.stringify({ brand, payload }),
  })
}

export function updateProduct(brand: BrandKey, id: number, payload: Record<string, unknown>) {
  return request<{ item: ProductItem; message: string }>(`/products/${brand}/${id}`, {
    method: "PUT",
    body: JSON.stringify({ brand, payload }),
  })
}

export function deleteProduct(brand: BrandKey, id: number) {
  return request<{ message: string }>(`/products/${brand}/${id}`, { method: "DELETE" })
}

export function lookupImage(params: { brand: BrandKey; originalSku: string | null; sku: string | null }) {
  return request<ImageLookupResult>("/images/lookup", {
    method: "POST",
    body: JSON.stringify({
      brand: params.brand,
      original_sku: params.originalSku,
      sku: params.sku,
    }),
  })
}
```

- [ ] **Step 4: Run the tests to verify they pass**

Run:
```bash
pnpm exec vitest run lib/api.test.ts
```

Expected: PASS for URL serialization and error handling.

- [ ] **Step 5: Commit**

```bash
git add lib/brands.ts lib/types.ts lib/api.ts lib/api.test.ts
git commit -m "feat: add frontend product api client"
```

### Task 7: Build the tabs, search, and list page

**Files:**
- Create: `frontend/components/product-admin/product-toolbar.tsx`
- Create: `frontend/components/product-admin/product-tabs.tsx`
- Create: `frontend/components/product-admin/product-table.tsx`
- Modify: `frontend/components/product-admin/product-admin-page.tsx`
- Modify: `frontend/components/product-admin/product-admin-page.test.tsx`
- Modify: `frontend/app/page.tsx`

- [ ] **Step 1: Expand the failing page tests**

```tsx
import userEvent from "@testing-library/user-event"
import { render, screen, waitFor } from "@testing-library/react"

import { ProductAdminPage } from "@/components/product-admin/product-admin-page"


test("loads qbd_mens rows on first render", async () => {
  const fetchMock = vi.spyOn(global, "fetch")
    .mockResolvedValueOnce(new Response(JSON.stringify({ items: [], total: 0, page: 1, page_size: 20 }), { status: 200 }))

  render(<ProductAdminPage />)

  await waitFor(() => {
    expect(fetchMock).toHaveBeenCalledWith(
      expect.stringContaining("brand=qbd_mens"),
      expect.any(Object),
    )
  })
})


test("switching tabs fetches the selected brand", async () => {
  const user = userEvent.setup()
  const fetchMock = vi.spyOn(global, "fetch")
    .mockResolvedValue(new Response(JSON.stringify({ items: [], total: 0, page: 1, page_size: 20 }), { status: 200 }))

  render(<ProductAdminPage />)
  await user.click(await screen.findByRole("tab", { name: "千百度女鞋" }))

  await waitFor(() => {
    expect(fetchMock).toHaveBeenLastCalledWith(
      expect.stringContaining("brand=qbd_womens"),
      expect.any(Object),
    )
  })
})


test("search submits the current tab brand", async () => {
  const user = userEvent.setup()
  const fetchMock = vi.spyOn(global, "fetch")
    .mockResolvedValue(new Response(JSON.stringify({ items: [], total: 0, page: 1, page_size: 20 }), { status: 200 }))

  render(<ProductAdminPage />)
  await user.type(screen.getByLabelText("原始货号"), "OA1001")
  await user.click(screen.getByRole("button", { name: "搜索" }))

  await waitFor(() => {
    expect(fetchMock).toHaveBeenLastCalledWith(
      expect.stringContaining("brand=qbd_mens&query=OA1001"),
      expect.any(Object),
    )
  })
})
```

- [ ] **Step 2: Run the tests to verify they fail**

Run:
```bash
pnpm exec vitest run components/product-admin/product-admin-page.test.tsx
```

Expected: FAIL because the page shell does not fetch or render the search UI yet.

- [ ] **Step 3: Write the minimal implementation**

Create `product-toolbar.tsx`.

```tsx
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"

export function ProductToolbar(props: {
  searchQuery: string
  onSearchQueryChange: (value: string) => void
  onSearch: () => void
  onClear: () => void
  onRefresh: () => void
  onCreate: () => void
}) {
  return (
    <div className="flex flex-col gap-3 md:flex-row md:items-end md:justify-between">
      <div className="flex-1">
        <label className="mb-2 block text-sm font-medium" htmlFor="original-sku-search">
          原始货号
        </label>
        <div className="flex gap-2">
          <Input id="original-sku-search" value={props.searchQuery} onChange={(event) => props.onSearchQueryChange(event.target.value)} />
          <Button onClick={props.onSearch}>搜索</Button>
          <Button variant="outline" onClick={props.onClear}>清空</Button>
        </div>
      </div>
      <div className="flex gap-2">
        <Button variant="outline" onClick={props.onRefresh}>刷新</Button>
        <Button onClick={props.onCreate}>新增商品</Button>
      </div>
    </div>
  )
}
```

Create `product-tabs.tsx` and `product-table.tsx`, then wire `ProductAdminPage` to `listProducts`.

```tsx
"use client"

import { useEffect, useState } from "react"

import { listProducts } from "@/lib/api"
import { BRANDS, type BrandKey } from "@/lib/brands"
import type { ProductItem } from "@/lib/types"
import { ProductTable } from "@/components/product-admin/product-table"
import { ProductTabs } from "@/components/product-admin/product-tabs"
import { ProductToolbar } from "@/components/product-admin/product-toolbar"

export function ProductAdminPage() {
  const [activeBrand, setActiveBrand] = useState<BrandKey>("qbd_mens")
  const [searchQuery, setSearchQuery] = useState("")
  const [submittedQuery, setSubmittedQuery] = useState("")
  const [page, setPage] = useState(1)
  const pageSize = 20
  const [reloadToken, setReloadToken] = useState(0)
  const [items, setItems] = useState<ProductItem[]>([])
  const [total, setTotal] = useState(0)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false
    setLoading(true)
    setError(null)

    listProducts({ brand: activeBrand, query: submittedQuery, page, pageSize })
      .then((response) => {
        if (cancelled) return
        setItems(response.items)
        setTotal(response.total)
      })
      .catch((reason) => {
        if (cancelled) return
        setError(reason instanceof Error ? reason.message : "加载失败")
      })
      .finally(() => {
        if (!cancelled) setLoading(false)
      })

    return () => {
      cancelled = true
    }
  }, [activeBrand, submittedQuery, page, pageSize, reloadToken])

  return (
    <div className="flex min-h-svh flex-col gap-6 p-6">
      <h1 className="text-2xl font-semibold">商品管理</h1>
      <ProductToolbar
        searchQuery={searchQuery}
        onSearchQueryChange={setSearchQuery}
        onSearch={() => {
          setPage(1)
          setSubmittedQuery(searchQuery)
        }}
        onClear={() => {
          setSearchQuery("")
          setSubmittedQuery("")
          setPage(1)
        }}
        onRefresh={() => setReloadToken((current) => current + 1)}
        onCreate={() => {}}
      />
      <ProductTabs brands={BRANDS} activeBrand={activeBrand} onBrandChange={(brand) => {
        setActiveBrand(brand)
        setPage(1)
      }} />
      <ProductTable items={items} total={total} page={page} pageSize={pageSize} loading={loading} error={error} onPageChange={setPage} />
    </div>
  )
}
```

- [ ] **Step 4: Run tests, typecheck, and lint**

Run:
```bash
pnpm exec vitest run components/product-admin/product-admin-page.test.tsx
pnpm typecheck
pnpm lint
```

Expected: PASS for the page tests, TypeScript, and ESLint.

- [ ] **Step 5: Commit**

```bash
git add app/page.tsx components/product-admin/product-admin-page.tsx components/product-admin/product-admin-page.test.tsx components/product-admin/product-toolbar.tsx components/product-admin/product-tabs.tsx components/product-admin/product-table.tsx
git commit -m "feat: add product list and search ui"
```

## Chunk 3: CRUD dialogs and integration

### Task 8: Add the create/edit dialog and image lookup flow

**Files:**
- Create: `frontend/components/product-admin/product-form-dialog.tsx`
- Create: `frontend/components/product-admin/image-lookup-status.tsx`
- Create: `frontend/components/product-admin/product-form-dialog.test.tsx`
- Modify: `frontend/components/product-admin/product-admin-page.tsx`
- Modify: `frontend/lib/api.ts`
- Modify: `frontend/lib/types.ts`

- [ ] **Step 1: Write the failing dialog tests**

```tsx
import userEvent from "@testing-library/user-event"
import { render, screen, waitFor } from "@testing-library/react"

import { ProductFormDialog } from "@/components/product-admin/product-form-dialog"


test("create mode requires selecting a brand before saving", async () => {
  const user = userEvent.setup()
  render(
    <ProductFormDialog
      open
      mode="create"
      brand={null}
      product={null}
      onOpenChange={() => {}}
      onSaved={() => {}}
    />,
  )

  await user.click(screen.getByRole("button", { name: "保存" }))

  expect(screen.getByText("请选择品牌")).toBeInTheDocument()
})


test("lookup prefers original_sku and fills image_path on success", async () => {
  const user = userEvent.setup()
  const fetchMock = vi.spyOn(global, "fetch")
    .mockResolvedValueOnce(new Response(JSON.stringify({
      found: true,
      image_path: "//server/images/ABC123.jpg",
      matched_by: "original_sku",
      message: "Image found",
    }), { status: 200 }))

  render(
    <ProductFormDialog
      open
      mode="create"
      brand="qbd_mens"
      product={null}
      onOpenChange={() => {}}
      onSaved={() => {}}
    />,
  )

  await user.type(screen.getByLabelText("原始货号"), "ABC123")
  await user.click(screen.getByRole("button", { name: "查找图片" }))

  await waitFor(() => {
    expect(fetchMock).toHaveBeenCalledWith(
      expect.stringContaining("/images/lookup"),
      expect.any(Object),
    )
    expect(screen.getByDisplayValue("//server/images/ABC123.jpg")).toBeInTheDocument()
  })
})


test("lookup shows a warning when no image exists", async () => {
  const user = userEvent.setup()
  vi.spyOn(global, "fetch").mockResolvedValueOnce(new Response(JSON.stringify({
    found: false,
    image_path: null,
    matched_by: "none",
    message: "Image not found",
  }), { status: 200 }))

  render(
    <ProductFormDialog
      open
      mode="create"
      brand="qbd_mens"
      product={null}
      onOpenChange={() => {}}
      onSaved={() => {}}
    />,
  )

  await user.type(screen.getByLabelText("货号"), "MISS001")
  await user.click(screen.getByRole("button", { name: "查找图片" }))

  expect(await screen.findByText("Image not found")).toBeInTheDocument()
})
```

- [ ] **Step 2: Run the tests to verify they fail**

Run:
```bash
pnpm exec vitest run components/product-admin/product-form-dialog.test.tsx
```

Expected: FAIL because the form dialog and image lookup UI do not exist yet.

- [ ] **Step 3: Write the minimal implementation**

Create `product-form-dialog.tsx` with controlled local form state and image lookup.

```tsx
"use client"

import { useEffect, useState } from "react"

import { Button } from "@/components/ui/button"
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select"
import { createProduct, lookupImage, updateProduct } from "@/lib/api"
import { BRANDS, type BrandKey } from "@/lib/brands"
import type { ProductItem } from "@/lib/types"
import { ImageLookupStatus } from "@/components/product-admin/image-lookup-status"

const EMPTY_FORM = {
  image_path: "",
  sku: "",
  original_sku: "",
  color: "",
  year: "",
  season_category: "",
  cost: "",
  toe_shape: "",
  execution_standard: "",
  first_order_time: "",
}

export function ProductFormDialog(props: {
  open: boolean
  mode: "create" | "edit"
  brand: BrandKey | null
  product: ProductItem | null
  onOpenChange: (open: boolean) => void
  onSaved: () => void
}) {
  const [selectedBrand, setSelectedBrand] = useState<BrandKey | null>(props.brand)
  const [form, setForm] = useState(EMPTY_FORM)
  const [error, setError] = useState<string | null>(null)
  const [lookupMessage, setLookupMessage] = useState<string | null>(null)
  const [lookupVariant, setLookupVariant] = useState<"default" | "warning">("default")

  useEffect(() => {
    setSelectedBrand(props.brand)
    setError(null)
    setLookupMessage(null)
    setForm(
      props.product
        ? {
            image_path: props.product.image_path ?? "",
            sku: props.product.sku ?? "",
            original_sku: props.product.original_sku ?? "",
            color: props.product.color ?? "",
            year: props.product.year ?? "",
            season_category: props.product.season_category ?? "",
            cost: props.product.cost ?? "",
            toe_shape: props.product.toe_shape ?? "",
            execution_standard: props.product.execution_standard ?? "",
            first_order_time: props.product.first_order_time ?? "",
          }
        : EMPTY_FORM,
    )
  }, [props.brand, props.product])

  async function onLookupImage() {
    if (!selectedBrand) {
      setError("请选择品牌")
      return
    }

    setError(null)
    const result = await lookupImage({
      brand: selectedBrand,
      originalSku: form.original_sku || null,
      sku: form.sku || null,
    })
    setLookupMessage(result.message)
    setLookupVariant(result.found ? "default" : "warning")
    if (result.image_path) {
      setForm((current) => ({ ...current, image_path: result.image_path ?? "" }))
    }
  }

  async function onSave() {
    if (!selectedBrand) {
      setError("请选择品牌")
      return
    }

    setError(null)
    const payload = {
      ...form,
      image_path: form.image_path || null,
    }

    if (props.mode === "create") {
      await createProduct(selectedBrand, payload)
    } else if (props.product) {
      await updateProduct(selectedBrand, props.product.id, payload)
    }

    props.onSaved()
    props.onOpenChange(false)
  }

  return (
    <Dialog open={props.open} onOpenChange={props.onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{props.mode === "create" ? "新增商品" : "编辑商品"}</DialogTitle>
        </DialogHeader>

        <div className="grid gap-4">
          <div className="grid gap-2">
            <Label htmlFor="brand">品牌</Label>
            <Select
              value={selectedBrand ?? undefined}
              onValueChange={(value) => setSelectedBrand(value as BrandKey)}
              disabled={props.mode === "edit"}
            >
              <SelectTrigger id="brand">
                <SelectValue placeholder="请选择品牌" />
              </SelectTrigger>
              <SelectContent>
                {BRANDS.map((brand) => (
                  <SelectItem key={brand.key} value={brand.key}>
                    {brand.label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          <div className="grid gap-2">
            <Label htmlFor="original_sku">原始货号</Label>
            <Input id="original_sku" value={form.original_sku} onChange={(event) => setForm((current) => ({ ...current, original_sku: event.target.value }))} />
          </div>

          <div className="grid gap-2">
            <Label htmlFor="sku">货号</Label>
            <Input id="sku" value={form.sku} onChange={(event) => setForm((current) => ({ ...current, sku: event.target.value }))} />
          </div>

          <div className="grid gap-2">
            <Label htmlFor="image_path">图片路径</Label>
            <Input id="image_path" value={form.image_path} onChange={(event) => setForm((current) => ({ ...current, image_path: event.target.value }))} />
          </div>

          <Button type="button" variant="outline" onClick={() => void onLookupImage()}>
            查找图片
          </Button>

          <ImageLookupStatus message={lookupMessage} variant={lookupVariant} />
          {error ? <p className="text-sm text-destructive">{error}</p> : null}
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={() => props.onOpenChange(false)}>取消</Button>
          <Button onClick={() => void onSave()}>保存</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
```

Wire `ProductAdminPage` so `新增商品` opens create mode and row `编辑` opens edit mode.

- [ ] **Step 4: Run the tests to verify they pass**

Run:
```bash
pnpm exec vitest run components/product-admin/product-form-dialog.test.tsx
pnpm exec vitest run components/product-admin/product-admin-page.test.tsx
```

Expected: PASS for brand selection, lookup success, and warning coverage.

- [ ] **Step 5: Commit**

```bash
git add components/product-admin/product-form-dialog.tsx components/product-admin/product-form-dialog.test.tsx components/product-admin/image-lookup-status.tsx components/product-admin/product-admin-page.tsx lib/api.ts lib/types.ts
git commit -m "feat: add product edit dialog and image lookup"
```

### Task 9: Add delete confirmation and refresh behavior

**Files:**
- Create: `frontend/components/product-admin/delete-product-dialog.tsx`
- Modify: `frontend/components/product-admin/product-table.tsx`
- Modify: `frontend/components/product-admin/product-admin-page.tsx`
- Modify: `frontend/components/product-admin/product-admin-page.test.tsx`

- [ ] **Step 1: Write the failing delete-flow tests**

```tsx
test("delete confirmation calls deleteProduct and reloads the current page", async () => {
  const user = userEvent.setup()
  vi.spyOn(global, "fetch")
    .mockResolvedValueOnce(new Response(JSON.stringify({
      items: [{ id: 1, brand: "qbd_mens", sku: "A1001", original_sku: "OA1001", image_path: null, color: null, year: null, season_category: null, cost: null, toe_shape: null, execution_standard: null, first_order_time: null, source_workbook: "manual_admin", source_sheet: "qbd_mens", source_row_number: "manual" }],
      total: 1,
      page: 1,
      page_size: 20,
    }), { status: 200 }))
    .mockResolvedValueOnce(new Response(JSON.stringify({ message: "Product deleted" }), { status: 200 }))
    .mockResolvedValueOnce(new Response(JSON.stringify({ items: [], total: 0, page: 1, page_size: 20 }), { status: 200 }))

  render(<ProductAdminPage />)
  await user.click(await screen.findByRole("button", { name: "删除" }))
  await user.click(screen.getByRole("button", { name: "确认删除" }))

  await waitFor(() => {
    expect(global.fetch).toHaveBeenCalledWith(
      expect.stringContaining("/products/qbd_mens/1"),
      expect.objectContaining({ method: "DELETE" }),
    )
  })
})
```

- [ ] **Step 2: Run the tests to verify they fail**

Run:
```bash
pnpm exec vitest run components/product-admin/product-admin-page.test.tsx
```

Expected: FAIL because there is no delete dialog or delete callback yet.

- [ ] **Step 3: Write the minimal implementation**

Create `delete-product-dialog.tsx`.

```tsx
import { Button } from "@/components/ui/button"
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog"
import type { ProductItem } from "@/lib/types"

export function DeleteProductDialog(props: {
  open: boolean
  product: ProductItem | null
  onOpenChange: (open: boolean) => void
  onConfirm: () => Promise<void>
}) {
  return (
    <Dialog open={props.open} onOpenChange={props.onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>确认删除</DialogTitle>
        </DialogHeader>
        <div className="space-y-1 text-sm text-muted-foreground">
          <p>品牌：{props.product?.brand}</p>
          <p>原始货号：{props.product?.original_sku ?? "-"}</p>
          <p>货号：{props.product?.sku ?? "-"}</p>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => props.onOpenChange(false)}>取消</Button>
          <Button variant="destructive" onClick={() => void props.onConfirm()}>确认删除</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
```

Update `ProductAdminPage` to keep `deletingProduct` state, call `deleteProduct`, and reload the page. If the current page becomes empty and `page > 1`, decrement the page before reloading.

- [ ] **Step 4: Run the tests to verify they pass**

Run:
```bash
pnpm exec vitest run components/product-admin/product-admin-page.test.tsx
pnpm typecheck
pnpm lint
```

Expected: PASS for delete coverage, typecheck, and lint.

- [ ] **Step 5: Commit**

```bash
git add components/product-admin/delete-product-dialog.tsx components/product-admin/product-table.tsx components/product-admin/product-admin-page.tsx components/product-admin/product-admin-page.test.tsx
git commit -m "feat: add product deletion flow"
```

### Task 10: Run the full verification and manual smoke test

**Files:**
- Modify only if fixes are required by the verification runs.

- [ ] **Step 1: Run the full backend test suite**

Run:
```bash
TEST_DATABASE_URL="postgresql+psycopg://postgres:12345678@127.0.0.1:5432/commodity_department_test" python -m pytest tests/test_config.py tests/test_transform.py tests/test_product_repository.py tests/test_api_products.py tests/test_api_images.py -v
```

Expected: PASS for config, transform, repository, products API, and image lookup API.

- [ ] **Step 2: Run the full frontend verification**

Run:
```bash
pnpm test
pnpm typecheck
pnpm lint
```

Expected: PASS for Vitest, TypeScript, and ESLint.

- [ ] **Step 3: Run the app manually**

Backend:
```bash
uvicorn api_main:app --reload
```

Frontend (separate terminal):
```bash
pnpm dev
```

Expected:
- backend listening at `http://127.0.0.1:8000`
- frontend listening at `http://localhost:3000`
- no CORS errors in the browser console

- [ ] **Step 4: Execute the manual smoke checklist**

Verify in the browser:

- [ ] Tab switch between 千百度男鞋 / 千百度女鞋 / 烟斗 / 伊伴 loads the correct brand data.
- [ ] Searching `original_sku` only filters the current brand tab.
- [ ] Creating a product requires selecting a brand first.
- [ ] Image lookup fills `image_path` when a matching file exists.
- [ ] Image lookup shows a warning and still allows save when no file exists.
- [ ] Editing a row updates the table immediately after save.
- [ ] Deleting the last row on a page either refreshes the page or moves back one page.

- [ ] **Step 5: Commit**

```bash
git add .
git commit -m "feat: add product admin ui and api"
```

## Review checkpoints

- After finishing **Chunk 1**, run the plan-document-reviewer flow against only Chunk 1.
- After finishing **Chunk 2**, run the plan-document-reviewer flow against only Chunk 2.
- After finishing **Chunk 3**, run the plan-document-reviewer flow against only Chunk 3.
- Do not start the next chunk until the current chunk review is approved.
