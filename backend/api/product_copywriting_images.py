from __future__ import annotations

import base64
import hashlib
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

from fastapi import HTTPException

from domain.sources import IMAGE_BRAND_KEYS
from fileio.image_paths import normalized_relative_image_path, relative_image_path
from storage.us3_image_storage import UCloudUS3ImageStorage


MAX_IMAGE_BYTES = 10 * 1024 * 1024


@dataclass(frozen=True)
class ProductCopywritingImage:
    data_url: str
    sha256: str
    media_type: str
    size_bytes: int

    def metadata(self) -> dict[str, object]:
        return {"sha256": self.sha256, "media_type": self.media_type, "size_bytes": self.size_bytes}


class _NoImageRedirect(HTTPRedirectHandler):
    def redirect_request(self, request, response, code, message, headers, new_url):
        return None


_image_opener = build_opener(_NoImageRedirect())


def _encode_image(raw: bytes) -> ProductCopywritingImage:
    if len(raw) > MAX_IMAGE_BYTES:
        raise HTTPException(status_code=422, detail="商品主图超过10MB，请压缩图片后重新生成")
    if raw.startswith(b"\xff\xd8\xff"):
        media_type = "image/jpeg"
    elif raw.startswith(b"\x89PNG\r\n\x1a\n"):
        media_type = "image/png"
    elif raw.startswith(b"RIFF") and raw[8:12] == b"WEBP":
        media_type = "image/webp"
    else:
        raise HTTPException(status_code=422, detail="商品主图为空或格式不支持，请使用JPEG、PNG或WebP图片")
    return ProductCopywritingImage(
        data_url=f"data:{media_type};base64,{base64.b64encode(raw).decode('ascii')}",
        sha256=hashlib.sha256(raw).hexdigest(),
        media_type=media_type,
        size_bytes=len(raw),
    )


def load_product_copywriting_image(settings, brand: str, item: dict) -> ProductCopywritingImage:
    image_path = str(item.get("image_path") or "").strip()
    if not image_path:
        raise HTTPException(status_code=422, detail="商品档案未关联主图，请补充图片后重新生成")
    root = getattr(settings, "image_roots", {}).get(IMAGE_BRAND_KEYS.get(brand, brand))
    if not root:
        raise HTTPException(status_code=503, detail="商品图片目录尚未配置，请联系管理员")
    try:
        root = Path(root)
        relative = relative_image_path(image_path, root)
        if relative is None:
            raise ValueError("image outside configured root")
        normalized = normalized_relative_image_path(relative)
        if ":" in normalized or "\x00" in normalized:
            raise ValueError("invalid image path")
    except (OSError, ValueError):
        raise HTTPException(status_code=422, detail="商品主图路径无效，请重新关联图片") from None

    if getattr(settings, "ucloud_us3_configured", False):
        try:
            storage = UCloudUS3ImageStorage.from_settings(settings)
            if storage is not None:
                object_key = storage.object_key(brand, normalized)
                if storage.has_synced_object(object_key):
                    image_url = storage.private_download_url(object_key)
                    parsed = urlsplit(image_url)
                    if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
                        raise ValueError("invalid image download URL")
                    with _image_opener.open(Request(image_url, method="GET"), timeout=20) as response:
                        return _encode_image(response.read(MAX_IMAGE_BYTES + 1))
        except HTTPException:
            raise
        except Exception:
            pass

    try:
        resolved_root = root.resolve()
        full_path = (root / normalized).resolve()
        full_path.relative_to(resolved_root)
        with full_path.open("rb") as image_file:
            raw = image_file.read(MAX_IMAGE_BYTES + 1)
    except ValueError:
        raise HTTPException(status_code=422, detail="商品主图路径超出图片目录，请重新关联图片") from None
    except FileNotFoundError:
        raise HTTPException(status_code=422, detail="商品主图文件不存在，请检查图片同步后重新生成") from None
    except OSError:
        raise HTTPException(status_code=503, detail="无法读取商品主图，请检查图片共享目录权限或存储服务") from None
    return _encode_image(raw)
