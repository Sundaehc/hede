from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.auth_middleware import auth_middleware
from api.routes.auth import router as auth_router
from api.routes.images import router as images_router
from api.routes.fine_table import router as fine_table_router
from api.routes.import_export import router as import_export_router
from api.routes.inventory import router as inventory_router
from api.routes.operation_logs import router as operation_logs_router
from api.routes.products import router as products_router
from api.routes.suppliers import router as suppliers_router
from api.routes.warehouses import router as warehouses_router
from storage.auth_repository import AuthRepository
from storage.inventory_repository import InventoryRepository
from storage.operation_log_repository import OperationLogRepository
from storage.product_repository import ProductRepository


def create_app(*, settings, repository=None, image_matchers=None, inventory_repository=None, auth_repository=None, operation_log_repository=None) -> FastAPI:
    if settings.database_url is None and (repository is None or inventory_repository is None):
        raise ValueError("database_url is required when repository is not provided")

    resolved_repository = repository or ProductRepository(settings.database_url)
    resolved_inventory_repository = inventory_repository or InventoryRepository(settings.database_url)
    resolved_auth_repository = auth_repository or AuthRepository(settings.database_url)
    resolved_operation_log_repository = operation_log_repository or OperationLogRepository(settings.database_url)
    resolved_matchers = image_matchers if image_matchers is not None else {}

    app = FastAPI(title="Hede Product Admin API")
    app.middleware("http")(auth_middleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[settings.frontend_origin],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.state.settings = settings
    if hasattr(resolved_inventory_repository, "create_tables"):
        resolved_inventory_repository.create_tables()
    app.state.repository = resolved_repository
    app.state.inventory_repository = resolved_inventory_repository
    app.state.auth_repository = resolved_auth_repository
    app.state.operation_log_repository = resolved_operation_log_repository
    resolved_auth_repository.create_tables()
    resolved_operation_log_repository.create_tables()
    app.state.image_matchers = resolved_matchers
    app.include_router(auth_router)
    app.include_router(products_router)
    app.include_router(fine_table_router)
    app.include_router(images_router)
    app.include_router(import_export_router)
    app.include_router(inventory_router)
    app.include_router(operation_logs_router)
    app.include_router(suppliers_router)
    app.include_router(warehouses_router)
    return app
