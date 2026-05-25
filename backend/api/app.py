from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.routes.images import router as images_router
from api.routes.fine_table import router as fine_table_router
from api.routes.import_export import router as import_export_router
from api.routes.inventory import router as inventory_router
from api.routes.products import router as products_router
from api.routes.suppliers import router as suppliers_router
from api.routes.warehouses import router as warehouses_router
from domain.sources import IMAGE_BRAND_KEYS, TABLE_NAMES
from fileio.image_matcher import ImageMatcher
from storage.inventory_repository import InventoryRepository
from storage.product_repository import ProductRepository


def create_app(*, settings, repository=None, image_matchers=None, inventory_repository=None) -> FastAPI:
    if settings.database_url is None and (repository is None or inventory_repository is None):
        raise ValueError("database_url is required when repository is not provided")

    resolved_repository = repository or ProductRepository(settings.database_url)
    resolved_inventory_repository = inventory_repository or InventoryRepository(settings.database_url)
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
    app.state.inventory_repository = resolved_inventory_repository
    app.state.image_matchers = resolved_matchers
    app.include_router(products_router)
    app.include_router(fine_table_router)
    app.include_router(images_router)
    app.include_router(import_export_router)
    app.include_router(inventory_router)
    app.include_router(suppliers_router)
    app.include_router(warehouses_router)
    return app
