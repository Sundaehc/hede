from __future__ import annotations

import mimetypes
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, HTTPException, Request
from fastapi.responses import FileResponse

from api.fine_table_cache import clear_fine_table_cache
from api.schemas import BrandKey, ImageLookupRequest, MatchSkuRequest
from storage.product_image_refresh import get_image_refresh_status, run_product_image_refresh


router = APIRouter()

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
    from domain.sources import IMAGE_BRAND_KEYS

    brand_key = IMAGE_BRAND_KEYS.get(brand, brand)
    root = settings.image_roots.get(brand_key)
    if not root:
        return None
    try:
        rel = Path(image_path).relative_to(root)
        return f"/images/serve/{brand}/{rel.as_posix()}"
    except ValueError:
        return None


@router.get("/images/serve/{brand}/{image_path:path}")
def serve_image(brand: str, image_path: str, request: Request):
    settings = request.app.state.settings
    from domain.sources import IMAGE_BRAND_KEYS, TABLE_NAMES

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
    matcher = request.app.state.image_matchers.get(body.brand)
    if matcher is None:
        raise HTTPException(status_code=400, detail=f"Unknown image brand: {body.brand}")

    if body.original_sku:
        image_path = matcher.find(body.original_sku)
        if image_path:
            return {
                "found": True,
                "image_path": image_path,
                "matched_by": "original_sku",
                "message": "Image found",
            }

    if body.sku:
        image_path = matcher.find(body.sku)
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
    matchers = request.app.state.image_matchers
    sku = body.sku.strip()
    if not sku:
        return {"found": False, "image_url": None, "brand": None}

    for brand, matcher in matchers.items():
        image_path = matcher.find(sku)
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
    status = get_image_refresh_status()
    if status.get("in_progress"):
        return {
            "accepted": False,
            "in_progress": True,
            "message": "已有图片刷新任务正在运行，请稍后查看状态",
            "status": status,
        }

    background_tasks.add_task(
        run_product_image_refresh,
        settings=settings,
        repository=repository,
        brand=brand,
        overwrite=overwrite,
    )
    clear_fine_table_cache()
    return {
        "accepted": True,
        "in_progress": True,
        "message": "图片刷新任务已提交，后台会自动扫描图片目录并回写缺失图片",
        "status": status,
    }


@router.get("/images/refresh-product-images/status")
def get_refresh_product_images_status():
    return get_image_refresh_status()
