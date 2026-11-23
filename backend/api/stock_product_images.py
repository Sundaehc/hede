"""Resolve archive photos for just the visible rows, separate from fact snapshots."""
from collections import defaultdict
import logging
from urllib.parse import quote

from fastapi import Request
from sqlalchemy.exc import SQLAlchemyError

from api.routes.images import image_url_for
from domain.sources import IMAGE_BRAND_KEYS

logger = logging.getLogger(__name__)


def add_stock_product_images(request: Request, rows: list[dict], *,
                             brand: str | None = None, id_key: str = "id") -> None:
    if not rows:
        return
    state = request.app.state
    settings = getattr(state, "settings", None)
    if settings is None:
        return
    roots = settings.image_roots
    by_brand = defaultdict(list)
    for row in rows:
        row["image_url"] = None
        key = brand or row["brand"]
        if IMAGE_BRAND_KEYS.get(key, key) in roots:
            by_brand[key].append(row)
    for key, items in by_brand.items():
        try:
            paths = state.repository.product_image_paths_by_id(key, {row[id_key] for row in items})
        except SQLAlchemyError:
            logger.warning("Could not load stock product images for %s", key, exc_info=True)
            continue
        urls = {product_id: image_url_for(key, path, settings) for product_id, path in paths.items()}
        for row in items:
            url = urls.get(row[id_key])
            row["image_url"] = quote(url, safe="/") if url else None
