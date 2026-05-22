from __future__ import annotations

import json
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from config import BACKEND_ROOT, Settings
from domain.sources import IMAGE_BRAND_KEYS, TABLE_NAMES
from fileio.image_matcher import ImageMatcher
from storage.product_repository import ProductRepository


STATUS_PATH = BACKEND_ROOT / ".image_refresh_status.json"
_LOCK = threading.Lock()


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _read_status() -> dict[str, Any]:
    if not STATUS_PATH.exists():
        return {"in_progress": False, "runs": []}
    try:
        return json.loads(STATUS_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"in_progress": False, "runs": []}


def _write_status(status: dict[str, Any]) -> None:
    tmp_path = STATUS_PATH.with_suffix(".tmp")
    tmp_path.write_text(json.dumps(status, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp_path.replace(STATUS_PATH)


def get_image_refresh_status() -> dict[str, Any]:
    return _read_status()


def run_product_image_refresh(
    *,
    settings: Settings,
    repository: ProductRepository,
    brand: str | None = None,
    overwrite: bool = False,
) -> dict[str, Any]:
    run_id = uuid.uuid4().hex
    brands = [brand] if brand else list(TABLE_NAMES)

    if not _LOCK.acquire(blocking=False):
        status = _read_status()
        return {
            "accepted": False,
            "in_progress": True,
            "message": "已有图片刷新任务正在运行",
            "status": status,
        }

    started_at = _now_iso()
    status = _read_status()
    status.update(
        {
            "in_progress": True,
            "current_run": {
                "id": run_id,
                "brands": brands,
                "overwrite": overwrite,
                "started_at": started_at,
                "status": "running",
            },
        }
    )
    _write_status(status)

    try:
        results: dict[str, dict[str, int]] = {}
        for brand_key in brands:
            image_brand = IMAGE_BRAND_KEYS[brand_key]
            matcher = ImageMatcher(settings.image_roots[image_brand])
            results[brand_key] = repository.refresh_image_paths(
                brand_key,
                matcher.find,
                overwrite=overwrite,
            )

        total_updated = sum(result["updated"] for result in results.values())
        total_scanned = sum(result["scanned"] for result in results.values())
        finished_run = {
            "id": run_id,
            "brands": brands,
            "overwrite": overwrite,
            "started_at": started_at,
            "finished_at": _now_iso(),
            "status": "completed",
            "scanned": total_scanned,
            "updated": total_updated,
            "results": results,
            "message": f"图片刷新完成：扫描 {total_scanned} 条，更新 {total_updated} 条",
        }
    except Exception as exc:
        finished_run = {
            "id": run_id,
            "brands": brands,
            "overwrite": overwrite,
            "started_at": started_at,
            "finished_at": _now_iso(),
            "status": "failed",
            "error": str(exc),
            "message": "图片刷新失败",
        }
    finally:
        status = _read_status()
        runs = [finished_run, *status.get("runs", [])][:20]
        status.update(
            {
                "in_progress": False,
                "current_run": None,
                "last_run": finished_run,
                "runs": runs,
            }
        )
        _write_status(status)
        _LOCK.release()

    return {
        "accepted": True,
        "in_progress": False,
        **finished_run,
    }
