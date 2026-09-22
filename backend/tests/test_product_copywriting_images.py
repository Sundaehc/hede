import base64
import hashlib
import io
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from fastapi import HTTPException

from api import product_copywriting_images as images


PNG_BYTES = base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+aQ3sAAAAASUVORK5CYII=")


@pytest.fixture
def settings(tmp_path):
    root = tmp_path / "product-images"
    root.mkdir()
    return SimpleNamespace(image_roots={"cbanner": root}, ucloud_us3_configured=False)


@pytest.fixture
def product(settings):
    path = settings.image_roots["cbanner"] / "RM363238D45.png"
    path.write_bytes(PNG_BYTES)
    return {"sku": "RM363238D45", "image_path": str(path)}


def test_local_image_uses_bytes_not_internal_path(settings, product):
    image = images.load_product_copywriting_image(settings, "cbanner_womens", product)
    assert base64.b64decode(image.data_url.partition(",")[2]) == PNG_BYTES
    assert image.data_url.startswith("data:image/png;base64,")
    assert image.metadata() == {
        "sha256": hashlib.sha256(PNG_BYTES).hexdigest(),
        "media_type": "image/png", "size_bytes": len(PNG_BYTES),
    }
    assert product["image_path"] not in image.data_url


def test_legacy_share_alias_reads_only_the_configured_root(settings, product, tmp_path):
    product["image_path"] = str(tmp_path / "old-share" / "product-images" / "RM363238D45.png")
    assert images.load_product_copywriting_image(settings, "cbanner_mens", product).sha256 == hashlib.sha256(PNG_BYTES).hexdigest()


@pytest.mark.parametrize("kind", ["missing", "outside", "traversal", "alternate-stream", "not-found", "unsupported", "empty"])
def test_invalid_image_never_returns_a_text_only_fallback(settings, product, tmp_path, kind):
    if kind == "missing":
        product["image_path"] = None
    elif kind == "outside":
        product["image_path"] = str(tmp_path / "private.png")
    elif kind == "traversal":
        product["image_path"] = str(settings.image_roots["cbanner"] / ".." / "private.png")
    elif kind == "alternate-stream":
        product["image_path"] += ":private"
    elif kind == "not-found":
        product["image_path"] = str(settings.image_roots["cbanner"] / "absent.png")
    else:
        Path(product["image_path"]).write_bytes(b"<html>private</html>" if kind == "unsupported" else b"")
    with pytest.raises(HTTPException) as caught:
        images.load_product_copywriting_image(settings, "cbanner_womens", product)
    assert caught.value.status_code == 422
    assert "private" not in caught.value.detail
    assert str(tmp_path) not in caught.value.detail


def test_missing_image_root_reports_configuration_error(product):
    with pytest.raises(HTTPException) as caught:
        images.load_product_copywriting_image(SimpleNamespace(image_roots={}), "cbanner_womens", product)
    assert caught.value.status_code == 503


def test_image_size_limit_is_bounded(settings, product, monkeypatch):
    monkeypatch.setattr(images, "MAX_IMAGE_BYTES", len(PNG_BYTES) - 1)
    with pytest.raises(HTTPException) as caught:
        images.load_product_copywriting_image(settings, "cbanner_womens", product)
    assert caught.value.status_code == 422
    assert "10MB" in caught.value.detail


@pytest.mark.parametrize("raw,media_type", [(b"\xff\xd8\xff\xe0image", "image/jpeg"), (b"RIFF\x04\x00\x00\x00WEBPimage", "image/webp")])
def test_image_type_comes_from_bytes_not_filename(settings, product, raw, media_type):
    Path(product["image_path"]).write_bytes(raw)
    assert images.load_product_copywriting_image(settings, "cbanner_womens", product).media_type == media_type


def configure_cloud(monkeypatch, settings, *, url="https://bucket.example.test/image.png?signature=private", synced=True):
    settings.ucloud_us3_configured = True
    storage = Mock()
    storage.object_key.return_value = "products/cbanner_womens/RM363238D45.png"
    storage.has_synced_object.return_value = synced
    storage.private_download_url.return_value = url
    monkeypatch.setattr(images.UCloudUS3ImageStorage, "from_settings", Mock(return_value=storage))
    opener = Mock(return_value=io.BytesIO(PNG_BYTES))
    monkeypatch.setattr(images._image_opener, "open", opener)
    return storage, opener


def test_synced_cloud_image_is_downloaded_without_forwarding_signatures(settings, product, monkeypatch):
    storage, opener = configure_cloud(monkeypatch, settings)
    monkeypatch.setattr(Path, "open", Mock(side_effect=AssertionError("must not read local file")))
    image = images.load_product_copywriting_image(settings, "cbanner_womens", product)
    assert base64.b64decode(image.data_url.partition(",")[2]) == PNG_BYTES
    assert "signature" not in image.data_url
    storage.object_key.assert_called_once_with("cbanner_womens", "RM363238D45.png")
    request = opener.call_args.args[0]
    assert request.get_method() == "GET"
    assert request.get_header("Authorization") is None
    assert opener.call_args.kwargs["timeout"] == 20


@pytest.mark.parametrize("url", ["http://bucket.example.test/image.png", "file:///private", "https://user:private@bucket.example.test/image.png"])
def test_unsafe_cloud_url_uses_local_image_without_request(settings, product, monkeypatch, url):
    _, opener = configure_cloud(monkeypatch, settings, url=url)
    assert images.load_product_copywriting_image(settings, "cbanner_womens", product).media_type == "image/png"
    opener.assert_not_called()


def test_cloud_failure_falls_back_to_local_without_leaking_error(settings, product, monkeypatch):
    _, opener = configure_cloud(monkeypatch, settings)
    opener.side_effect = OSError("signature=private")
    assert images.load_product_copywriting_image(settings, "cbanner_womens", product).media_type == "image/png"
    monkeypatch.setattr(Path, "open", Mock(side_effect=PermissionError("private path")))
    with pytest.raises(HTTPException) as caught:
        images.load_product_copywriting_image(settings, "cbanner_womens", product)
    assert caught.value.status_code == 503
    assert "private" not in caught.value.detail


def test_unsynced_image_does_not_request_cloud(settings, product, monkeypatch):
    storage, opener = configure_cloud(monkeypatch, settings, synced=False)
    assert images.load_product_copywriting_image(settings, "cbanner_womens", product).media_type == "image/png"
    storage.private_download_url.assert_not_called()
    opener.assert_not_called()


def test_image_download_never_follows_redirects():
    assert images._NoImageRedirect().redirect_request(None, None, 307, "redirect", {}, "https://other.test/private") is None
