from __future__ import annotations

import logging
import mimetypes
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, HTTPException, Request
from fastapi.responses import FileResponse

from api.fine_table_cache import clear_fine_table_cache
from api.product_goods_cache import clear_product_goods_cache
from api.operation_log_utils import actor_from_request
from api.schemas import BrandKey, ImageLookupRequest, MatchSkuRequest
from domain.sources import IMAGE_BRAND_KEYS, TABLE_NAMES
from fileio.image_matcher import ImageMatcher
from storage.product_image_refresh import get_image_refresh_status, run_product_image_refresh


router = APIRouter()
logger = logging.getLogger(__name__)

MIME_MAP = {
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".webp": "image/webp",
    ".bmp": "image/bmp",
}


def image_url_for(brand: str, image_path: str | None, settings) -> str | None:
    if not image_path:
        return None

    brand_key = IMAGE_BRAND_KEYS.get(brand, brand)
    root = settings.image_roots.get(brand_key)
    if not root:
        return None
    try:
        rel = Path(image_path).relative_to(root)
        return f"/images/serve/{brand}/{rel.as_posix()}"
    except ValueError:
        return None


def get_image_matcher(request: Request, brand: str) -> ImageMatcher | None:
    if brand not in TABLE_NAMES:
        return None
    matchers = request.app.state.image_matchers
    matcher = matchers.get(brand)
    if matcher is not None:
        return matcher

    settings = request.app.state.settings
    image_brand = IMAGE_BRAND_KEYS[brand]
    root = settings.image_roots.get(image_brand)
    if root is None:
        return None
    try:
        matcher = ImageMatcher(root)
    except Exception:
        logger.exception("Failed to build image matcher for brand %s", brand)
        return None
    matchers[brand] = matcher
    return matcher


def find_image_safely(matcher: ImageMatcher, sku: object, *, refresh_on_missing: bool = False) -> str | None:
    try:
        if refresh_on_missing:
            return matcher.find_with_refresh(sku)
        return matcher.find(sku)
    except Exception:
        logger.exception("Failed to lookup product image for %s", sku)
        return None


@router.get("/images/serve/{brand}/{image_path:path}")
def serve_image(brand: str, image_path: str, request: Request):
    settings = request.app.state.settings

    brand_key = brand
    if brand_key not in settings.image_roots:
        if brand_key in TABLE_NAMES:
            brand_key = IMAGE_BRAND_KEYS.get(brand_key, brand_key)

    root = settings.image_roots.get(brand_key)
    if root is None:
        raise HTTPException(status_code=404, detail="Unknown brand")

    full_path = (Path(root) / image_path).resolve()
    try:
        full_path.relative_to(Path(root).resolve())
    except ValueError:
        raise HTTPException(status_code=403, detail="Path traversal denied")

    if not full_path.exists() or not full_path.is_file():
        raise HTTPException(status_code=404, detail="Image not found")

    suffix = full_path.suffix.lower()
    media_type = MIME_MAP.get(suffix) or mimetypes.guess_type(str(full_path))[0] or "application/octet-stream"
    return FileResponse(str(full_path), media_type=media_type)


@router.post("/images/lookup")
def lookup_image(request: Request, body: ImageLookupRequest):
    matcher = get_image_matcher(request, body.brand)
    if matcher is None:
        raise HTTPException(status_code=400, detail=f"Unknown image brand: {body.brand}")

    if body.original_sku:
        image_path = find_image_safely(matcher, body.original_sku, refresh_on_missing=True)
        if image_path:
            return {
                "found": True,
                "image_path": image_path,
                "matched_by": "original_sku",
                "message": "Image found",
            }

    if body.sku:
        image_path = find_image_safely(matcher, body.sku, refresh_on_missing=True)
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


@router.post("/images/match-sku")
def match_sku_image(request: Request, body: MatchSkuRequest):
    settings = request.app.state.settings
    sku = body.sku.strip()
    if not sku:
        return {"found": False, "image_url": None, "brand": None}

    for brand in TABLE_NAMES:
        matcher = get_image_matcher(request, brand)
        if matcher is None:
            continue
        image_path = find_image_safely(matcher, sku)
        if image_path:
            url = image_url_for(brand, image_path, settings)
            return {"found": True, "image_url": url, "brand": brand}

    return {"found": False, "image_url": None, "brand": None}


@router.post("/images/refresh-product-images")
def refresh_product_images(
    request: Request,
    background_tasks: BackgroundTasks,
    brand: BrandKey | None = None,
    overwrite: bool = False,
):
    repository = request.app.state.repository
    settings = request.app.state.settings
    actor = actor_from_request(request)
    operation_log_repository = getattr(request.app.state, "operation_log_repository", None)
    status = get_image_refresh_status()
    if status.get("in_progress"):
        return {
            "accepted": False,
            "in_progress": True,
            "message": "已有图片刷新任务正在运行，请稍后查看状态",
            "status": status,
        }

    def run_and_log_refresh() -> None:
        result = run_product_image_refresh(
            settings=settings,
            repository=repository,
            brand=brand,
            overwrite=overwrite,
        )
        if operation_log_repository is not None:
            operation_log_repository.create_log(
                module="product",
                action="refresh_images",
                entity_type="product_image",
                entity_label=brand or "全部品牌",
                summary=result.get("message") or "刷新商品图片",
                after_data=result,
                user=actor,
            )

    background_tasks.add_task(run_and_log_refresh)
    clear_fine_table_cache()
    clear_product_goods_cache()
    return {
        "accepted": True,
        "in_progress": True,
        "message": "图片刷新任务已提交，后台会自动扫描图片目录并回写缺失图片",
        "status": status,
    }


@router.get("/images/refresh-product-images/status")
def get_refresh_product_images_status():
    return get_image_refresh_status()
