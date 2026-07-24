from __future__ import annotations

from contextlib import asynccontextmanager
from copy import deepcopy
import logging
from threading import Thread
from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.openapi.docs import get_redoc_html, get_swagger_ui_html
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware

from api.auth_middleware import auth_middleware
from api.routes.auth import router as auth_router
from api.routes.images import router as images_router
from api.routes.fine_table import router as fine_table_router
from api.routes.import_export import router as import_export_router
from api.routes.inventory import router as inventory_router
from api.routes.operation_logs import router as operation_logs_router
from api.routes.products import router as products_router
from api.routes.product_goods import (
    list_product_goods,
    router as product_goods_router,
)
from api.routes.suppliers import router as suppliers_router
from api.routes.warehouses import router as warehouses_router
from storage.auth_repository import AuthRepository
from storage.inventory_repository import InventoryRepository
from storage.operation_log_repository import OperationLogRepository
from storage.product_repository import ProductRepository


PUBLIC_DOC_METHODS = {"get", "head"}
PUBLIC_DOC_EXCLUDED_PREFIXES = (
    "/auth",
    "/operation-logs",
    "/public",
    "/docs",
    "/redoc",
    "/openapi.json",
)
PUBLIC_DOC_EXCLUDED_KEYWORDS = (
    "admin",
    "import",
    "export",
    "recycle-bin",
    "refresh-product-images",
)
logger = logging.getLogger(__name__)


def _warm_default_product_goods_page(app: FastAPI) -> None:
    """Populate the default goods-detail page cache without delaying startup."""
    try:
        list_product_goods(
            SimpleNamespace(app=app),
            brand="cbanner_mens",
            view="goods",
            page=1,
            page_size=50,
        )
    except Exception:
        logger.exception("Failed to warm the default product-goods page cache")


@asynccontextmanager
async def _app_lifespan(app: FastAPI):
    Thread(
        target=_warm_default_product_goods_page,
        args=(app,),
        name="product-goods-cache-warmup",
        daemon=True,
    ).start()
    yield


def _is_public_read_path(path: str) -> bool:
    if any(path == prefix or path.startswith(prefix + "/") for prefix in PUBLIC_DOC_EXCLUDED_PREFIXES):
        return False
    return not any(keyword in path for keyword in PUBLIC_DOC_EXCLUDED_KEYWORDS)


def _public_read_openapi_schema(app: FastAPI) -> dict[str, object]:
    schema = deepcopy(app.openapi())
    paths = schema.get("paths")
    if not isinstance(paths, dict):
        return schema

    filtered_paths: dict[str, object] = {}
    for path, path_item in paths.items():
        if not isinstance(path, str) or not isinstance(path_item, dict):
            continue
        if not _is_public_read_path(path):
            continue

        filtered_item = {
            method: operation
            for method, operation in path_item.items()
            if method.lower() in PUBLIC_DOC_METHODS
        }
        if filtered_item:
            filtered_paths[path] = filtered_item

    schema["paths"] = filtered_paths
    schema["info"] = {
        **(schema.get("info") if isinstance(schema.get("info"), dict) else {}),
        "title": "Hede Product Admin API - Public Read Only",
        "description": "只读接口文档，仅包含 GET/HEAD 查询类接口；完整接口请登录后查看 /docs。",
    }
    return schema


def _add_public_docs_routes(app: FastAPI) -> None:
    @app.get("/public/openapi.json", include_in_schema=False)
    def public_openapi():
        return JSONResponse(_public_read_openapi_schema(app))

    @app.get("/public/docs", include_in_schema=False)
    def public_docs():
        return get_swagger_ui_html(
            openapi_url="/public/openapi.json",
            title="Hede Product Admin API - Public Read Only",
        )

    @app.get("/public/redoc", include_in_schema=False)
    def public_redoc():
        return get_redoc_html(
            openapi_url="/public/openapi.json",
            title="Hede Product Admin API - Public Read Only",
        )


def create_app(*, settings, repository=None, image_matchers=None, inventory_repository=None, auth_repository=None, operation_log_repository=None) -> FastAPI:
    if settings.database_url is None and (repository is None or inventory_repository is None):
        raise ValueError("database_url is required when repository is not provided")

    resolved_repository = repository or ProductRepository(settings.database_url)
    resolved_inventory_repository = inventory_repository or InventoryRepository(settings.database_url)
    resolved_auth_repository = auth_repository or AuthRepository(settings.database_url)
    resolved_operation_log_repository = operation_log_repository or OperationLogRepository(settings.database_url)
    resolved_matchers = image_matchers if image_matchers is not None else {}

    app = FastAPI(title="Hede Product Admin API", lifespan=_app_lifespan)
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
    app.include_router(product_goods_router)
    app.include_router(fine_table_router)
    app.include_router(images_router)
    app.include_router(import_export_router)
    app.include_router(inventory_router)
    app.include_router(operation_logs_router)
    app.include_router(suppliers_router)
    app.include_router(warehouses_router)
    _add_public_docs_routes(app)
    return app
