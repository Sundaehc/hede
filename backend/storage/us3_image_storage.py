from __future__ import annotations

import json
import logging
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any
from urllib.parse import urlparse

from config import BACKEND_ROOT
from fileio.image_paths import normalized_relative_image_path

if TYPE_CHECKING:
    from config import Settings


DEFAULT_MANIFEST_PATH = BACKEND_ROOT / ".us3_image_sync_manifest.json"
SUCCESS_STATUS_CODES = {200, 204, 206}


class US3ImageStorageError(RuntimeError):
    pass


@dataclass(frozen=True)
class US3Endpoint:
    suffix: str
    use_https: bool


def parse_us3_endpoint(endpoint: str, bucket: str) -> US3Endpoint:
    raw = endpoint.strip().rstrip("/")
    if not raw:
        raise ValueError("UCLOUD_US3_ENDPOINT is empty")

    parsed = urlparse(raw if "://" in raw else f"https://{raw.lstrip('.')}")
    host = (parsed.hostname or "").strip().lower()
    normalized_bucket = bucket.strip().lower()
    if not host or not normalized_bucket:
        raise ValueError("Invalid US3 endpoint or bucket")

    bucket_prefix = f"{normalized_bucket}."
    if host.startswith(bucket_prefix):
        suffix = f".{host[len(bucket_prefix):]}"
    elif host.endswith(".ufileos.com") and host.count(".") == 2:
        suffix = f".{host}"
    else:
        raise ValueError(
            "UCLOUD_US3_ENDPOINT must be the bucket domain, for example "
            f"https://{normalized_bucket}.cn-sh2.ufileos.com"
        )

    return US3Endpoint(suffix=suffix, use_https=parsed.scheme.lower() != "http")


def us3_object_key(*, brand: str, relative_path: str | Path, prefix: str = "") -> str:
    normalized_brand = brand.strip().strip("/")
    allowed_brand_characters = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-"
    if not normalized_brand or any(char not in allowed_brand_characters for char in normalized_brand):
        raise ValueError("Invalid image brand")

    normalized_path = normalized_relative_image_path(relative_path)
    parts = [part for part in (prefix.strip().strip("/"), normalized_brand, normalized_path) if part]
    return "/".join(parts)


class UCloudUS3ImageStorage:
    def __init__(
        self,
        *,
        public_key: str,
        private_key: str,
        bucket: str,
        endpoint: str,
        image_prefix: str = "",
        signed_url_expires: int = 3600,
        timeout_seconds: int = 60,
        manifest_path: Path = DEFAULT_MANIFEST_PATH,
    ) -> None:
        from ufile import config as ufile_config
        from ufile import filemanager
        from ufile import logger as ufile_logger

        endpoint_config = parse_us3_endpoint(endpoint, bucket)
        # The upstream SDK logs the Authorization header at INFO level.
        ufile_logger.logger.setLevel(logging.WARNING)
        ufile_config.set_default(
            connection_timeout=timeout_seconds,
            expires=signed_url_expires,
            md5=True,
            open_ssl=endpoint_config.use_https,
        )
        self.bucket = bucket.strip()
        self.image_prefix = image_prefix.strip().strip("/")
        self.signed_url_expires = signed_url_expires
        self.manifest_path = manifest_path
        self._manager = filemanager.FileManager(
            public_key.strip(),
            private_key.strip(),
            upload_suffix=endpoint_config.suffix,
            download_suffix=endpoint_config.suffix,
        )
        self._manifest_lock = threading.Lock()
        self._manifest_mtime_ns: int | None = None
        self._synced_keys: set[str] = set()

    @classmethod
    def from_settings(
        cls,
        settings: Settings,
        *,
        manifest_path: Path = DEFAULT_MANIFEST_PATH,
    ) -> UCloudUS3ImageStorage | None:
        if not settings.ucloud_us3_configured:
            return None
        assert settings.ucloud_us3_public_key is not None
        assert settings.ucloud_us3_private_key is not None
        assert settings.ucloud_us3_bucket is not None
        assert settings.ucloud_us3_endpoint is not None
        return cls(
            public_key=settings.ucloud_us3_public_key,
            private_key=settings.ucloud_us3_private_key,
            bucket=settings.ucloud_us3_bucket,
            endpoint=settings.ucloud_us3_endpoint,
            image_prefix=settings.ucloud_us3_image_prefix,
            signed_url_expires=settings.ucloud_us3_signed_url_expires,
            timeout_seconds=settings.ucloud_us3_timeout_seconds,
            manifest_path=manifest_path,
        )

    def object_key(self, brand: str, relative_path: str | Path) -> str:
        return us3_object_key(
            brand=brand,
            relative_path=relative_path,
            prefix=self.image_prefix,
        )

    def private_download_url(self, object_key: str) -> str:
        return self._manager.private_download_url(
            self.bucket,
            object_key,
            expires=self.signed_url_expires,
            internal=True,
        )

    def upload_file(self, source_path: Path, object_key: str) -> None:
        result, response = self._manager.putfile(self.bucket, object_key, str(source_path))
        status_code = int(getattr(response, "status_code", 0) or 0)
        if status_code not in SUCCESS_STATUS_CODES:
            detail = result if result else getattr(response, "error", None)
            raise US3ImageStorageError(
                f"US3 upload failed for {object_key}: HTTP {status_code}; {detail or 'unknown error'}"
            )

    def has_synced_object(self, object_key: str) -> bool:
        self._reload_manifest_if_changed()
        return object_key in self._synced_keys

    def _reload_manifest_if_changed(self) -> None:
        try:
            mtime_ns = self.manifest_path.stat().st_mtime_ns
        except OSError:
            mtime_ns = None
        if mtime_ns == self._manifest_mtime_ns:
            return

        with self._manifest_lock:
            try:
                payload: Any = json.loads(self.manifest_path.read_text(encoding="utf-8"))
                objects = payload.get("objects", {}) if isinstance(payload, dict) else {}
                self._synced_keys = set(objects) if isinstance(objects, dict) else set()
            except (OSError, json.JSONDecodeError):
                self._synced_keys = set()
            self._manifest_mtime_ns = mtime_ns
