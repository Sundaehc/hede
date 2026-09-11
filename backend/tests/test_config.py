from pathlib import Path

import config as config_module
from config import DEFAULT_FRONTEND_ORIGIN, load_settings


def _set_required_path_env(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("EXCEL_ROOT", str(tmp_path / "excel"))
    monkeypatch.setenv("CBANNER_IMAGE_ROOT", str(tmp_path / "cbanner-images"))
    monkeypatch.setenv("YANDOU_IMAGE_ROOT", str(tmp_path / "yandou-images"))
    monkeypatch.setenv("EBLAN_IMAGE_ROOT", str(tmp_path / "eblan-images"))


def test_load_settings_allows_missing_database_for_dry_run(monkeypatch, tmp_path: Path):
    monkeypatch.setattr(config_module, "BACKEND_ROOT", tmp_path)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    _set_required_path_env(monkeypatch, tmp_path)

    settings = load_settings(require_database=False)

    assert settings.database_url is None


def test_load_settings_defaults_frontend_origin_for_dry_run(monkeypatch, tmp_path: Path):
    monkeypatch.setattr(config_module, "BACKEND_ROOT", tmp_path)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("FRONTEND_ORIGIN", raising=False)
    _set_required_path_env(monkeypatch, tmp_path)

    settings = load_settings(require_database=False)

    assert settings.frontend_origin == DEFAULT_FRONTEND_ORIGIN


def test_load_settings_reads_frontend_origin_from_env(monkeypatch, tmp_path: Path):
    monkeypatch.setattr(config_module, "BACKEND_ROOT", tmp_path)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setenv("FRONTEND_ORIGIN", "https://admin.example.com")
    _set_required_path_env(monkeypatch, tmp_path)

    settings = load_settings(require_database=False)

    assert settings.frontend_origin == "https://admin.example.com"
    assert settings.frontend_origins == ("https://admin.example.com",)


def test_load_settings_supports_multiple_frontend_origins(monkeypatch, tmp_path: Path):
    monkeypatch.setattr(config_module, "BACKEND_ROOT", tmp_path)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setenv(
        "FRONTEND_ORIGIN",
        "https://platform.example.com, http://192.168.10.80:3001/",
    )
    _set_required_path_env(monkeypatch, tmp_path)

    settings = load_settings(require_database=False)

    assert settings.frontend_origins == (
        "https://platform.example.com",
        "http://192.168.10.80:3001",
    )


def test_load_settings_reads_excel_root_from_env(monkeypatch, tmp_path: Path):
    monkeypatch.setattr(config_module, "BACKEND_ROOT", tmp_path)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    _set_required_path_env(monkeypatch, tmp_path)

    override_root = tmp_path / "excel-source"
    monkeypatch.setenv("EXCEL_ROOT", str(override_root))

    settings = load_settings(require_database=False)

    assert settings.excel_root == override_root


def test_load_settings_reads_us3_image_configuration(monkeypatch, tmp_path: Path):
    monkeypatch.setattr(config_module, "BACKEND_ROOT", tmp_path)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    _set_required_path_env(monkeypatch, tmp_path)
    monkeypatch.setenv("UCLOUD_US3_PUBLIC_KEY", "public")
    monkeypatch.setenv("UCLOUD_US3_PRIVATE_KEY", "private")
    monkeypatch.setenv("UCLOUD_US3_BUCKET", "hede-img")
    monkeypatch.setenv("UCLOUD_US3_ENDPOINT", "https://hede-img.cn-sh2.ufileos.com")
    monkeypatch.setenv("UCLOUD_US3_SIGNED_URL_EXPIRES", "7200")

    settings = load_settings(require_database=False)

    assert settings.ucloud_us3_configured is True
    assert settings.ucloud_us3_bucket == "hede-img"
    assert settings.ucloud_us3_signed_url_expires == 7200
