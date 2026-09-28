"""Incrementally synchronize product tags after the archive and image updates."""

from __future__ import annotations

from datetime import date

from domain.product_tag_generation import sync_changed_product_tags
from storage.product_repository import ProductRepository


TASK_NAME = "sync_product_tags_daily"


def run_daily_sync(settings, business_date: date) -> dict[str, int]:
    repository = ProductRepository(settings.database_url)
    try:
        return sync_changed_product_tags(repository, business_date)
    finally:
        repository.engine.dispose()
