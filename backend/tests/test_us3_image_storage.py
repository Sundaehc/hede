from __future__ import annotations

from types import SimpleNamespace

import pytest

from storage.product_image_sync import run_product_image_us3_sync
from storage.us3_image_storage import parse_us3_endpoint, us3_object_key


def test_parse_us3_endpoint_extracts_bucket_host_suffix():
    endpoint = parse_us3_endpoint(
        "https://hede-img.cn-sh2.ufileos.com",
        "hede-img",
    )

    assert endpoint.suffix == ".cn-sh2.ufileos.com"
    assert endpoint.use_https is True


def test_us3_object_key_uses_brand_directory_and_rejects_traversal():
    assert us3_object_key(
        brand="cbanner_womens",
        relative_path="spring/QC153883D54.jpg",
    ) == "cbanner_womens/spring/QC153883D54.jpg"

    with pytest.raises(ValueError):
        us3_object_key(brand="cbanner_womens", relative_path="../secret.jpg")


def test_product_image_sync_uploads_only_new_or_changed_files(tmp_path):
    image_root = tmp_path / "images"
    image_root.mkdir()
    source_path = image_root / "QC153883D54.jpg"
    source_path.write_bytes(b"first")
    manifest_path = tmp_path / "manifest.json"

    class RepositoryStub:
        def product_archive_brands(self):
            return ["cbanner_womens"]

        def list_product_image_sources(self, brands):
            assert brands == ["cbanner_womens"]
            return [{"brand": "cbanner_womens", "image_path": str(source_path)}]

    class StorageStub:
        def __init__(self):
            self.uploaded = []

        def object_key(self, brand, relative_path):
            return us3_object_key(brand=brand, relative_path=relative_path)

        def upload_file(self, path, object_key):
            self.uploaded.append((path, object_key))

    settings = SimpleNamespace(
        image_roots={"cbanner": image_root},
        ucloud_us3_sync_workers=2,
    )
    repository = RepositoryStub()
    storage = StorageStub()

    first = run_product_image_us3_sync(
        settings=settings,
        repository=repository,
        manifest_path=manifest_path,
        storage=storage,
    )
    second = run_product_image_us3_sync(
        settings=settings,
        repository=repository,
        manifest_path=manifest_path,
        storage=storage,
    )
    source_path.write_bytes(b"changed-size")
    third = run_product_image_us3_sync(
        settings=settings,
        repository=repository,
        manifest_path=manifest_path,
        storage=storage,
    )

    assert first["uploaded"] == 1
    assert second["uploaded"] == 0
    assert second["skipped_unchanged"] == 1
    assert third["uploaded"] == 1
    assert [item[1] for item in storage.uploaded] == [
        "cbanner_womens/QC153883D54.jpg",
        "cbanner_womens/QC153883D54.jpg",
    ]
