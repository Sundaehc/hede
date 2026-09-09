from __future__ import annotations

import json
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from config import BACKEND_ROOT, Settings
from domain.sources import IMAGE_BRAND_KEYS
from fileio.image_paths import relative_image_path
from storage.product_repository import ProductRepository
from storage.us3_image_storage import DEFAULT_MANIFEST_PATH, UCloudUS3ImageStorage


def _load_manifest(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        payload = {}
    objects = payload.get("objects") if isinstance(payload, dict) else None
    return {
        "version": 1,
        "objects": objects if isinstance(objects, dict) else {},
    }


def _write_manifest(path: Path, manifest: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    manifest["updated_at"] = datetime.now(timezone.utc).isoformat()
    temporary_path = path.with_suffix(path.suffix + ".tmp")
    temporary_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary_path.replace(path)


def _source_signature(path: Path) -> dict[str, Any]:
    stat = path.stat()
    return {
        "source_path": str(path),
        "size": stat.st_size,
        "mtime_ns": stat.st_mtime_ns,
    }


def _same_source(previous: object, current: dict[str, Any]) -> bool:
    if not isinstance(previous, dict):
        return False
    return (
        previous.get("source_path") == current["source_path"]
        and previous.get("size") == current["size"]
        and previous.get("mtime_ns") == current["mtime_ns"]
    )


def _upload_with_retry(
    storage: UCloudUS3ImageStorage,
    source_path: Path,
    object_key: str,
    *,
    attempts: int = 3,
) -> None:
    last_error: Exception | None = None
    for attempt in range(1, attempts + 1):
        try:
            storage.upload_file(source_path, object_key)
            return
        except Exception as exc:
            last_error = exc
            if attempt < attempts:
                time.sleep(2 ** (attempt - 1))
    assert last_error is not None
    raise last_error


def run_product_image_us3_sync(
    *,
    settings: Settings,
    repository: ProductRepository,
    brands: Iterable[str] | None = None,
    force: bool = False,
    dry_run: bool = False,
    max_uploads: int | None = None,
    manifest_path: Path = DEFAULT_MANIFEST_PATH,
    storage: UCloudUS3ImageStorage | None = None,
) -> dict[str, Any]:
    resolved_storage = storage or UCloudUS3ImageStorage.from_settings(
        settings,
        manifest_path=manifest_path,
    )
    if resolved_storage is None:
        raise ValueError("UCloud US3 image storage is not fully configured")

    selected_brands = list(brands) if brands is not None else repository.product_archive_brands()
    source_rows = repository.list_product_image_sources(selected_brands)
    manifest = _load_manifest(manifest_path)
    manifest_objects: dict[str, Any] = manifest["objects"]

    candidates: list[tuple[str, Path, str, dict[str, Any]]] = []
    skipped_unchanged = 0
    missing = 0
    invalid = 0
    seen_keys: set[str] = set()

    for row in source_rows:
        brand = str(row.get("brand") or "").strip()
        source_value = str(row.get("image_path") or "").strip()
        image_brand = IMAGE_BRAND_KEYS.get(brand)
        root = settings.image_roots.get(image_brand) if image_brand else None
        if not brand or not source_value or root is None:
            invalid += 1
            continue

        stored_source_path = Path(source_value)
        relative_path = relative_image_path(stored_source_path, root)
        if relative_path is None:
            invalid += 1
            continue
        source_path = root / relative_path
        if not source_path.is_file() and stored_source_path.is_file():
            source_path = stored_source_path
        if not source_path.is_file():
            missing += 1
            continue

        try:
            object_key = resolved_storage.object_key(brand, relative_path)
            signature = _source_signature(source_path)
        except (OSError, ValueError):
            invalid += 1
            continue
        if object_key in seen_keys:
            continue
        seen_keys.add(object_key)
        if not force and _same_source(manifest_objects.get(object_key), signature):
            skipped_unchanged += 1
            continue
        candidates.append((brand, source_path, object_key, signature))

    total_candidates = len(candidates)
    if max_uploads is not None:
        candidates = candidates[: max(0, max_uploads)]

    result: dict[str, Any] = {
        "scanned": len(source_rows),
        "candidates": len(candidates),
        "total_candidates": total_candidates,
        "uploaded": 0,
        "skipped_unchanged": skipped_unchanged,
        "missing": missing,
        "invalid": invalid,
        "failed": 0,
        "errors": [],
        "dry_run": dry_run,
    }
    if dry_run or not candidates:
        return result

    workers = max(1, settings.ucloud_us3_sync_workers)
    with ThreadPoolExecutor(max_workers=workers, thread_name_prefix="us3-image-upload") as executor:
        futures = {
            executor.submit(_upload_with_retry, resolved_storage, source_path, object_key): (
                brand,
                object_key,
                signature,
            )
            for brand, source_path, object_key, signature in candidates
        }
        for future in as_completed(futures):
            brand, object_key, signature = futures[future]
            try:
                future.result()
            except Exception as exc:
                result["failed"] += 1
                if len(result["errors"]) < 20:
                    result["errors"].append(
                        {"brand": brand, "object_key": object_key, "error": str(exc)}
                    )
                continue
            manifest_objects[object_key] = signature
            result["uploaded"] += 1

    _write_manifest(manifest_path, manifest)
    return result
