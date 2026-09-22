from pathlib import Path

import config as config_module
from config import DEFAULT_FRONTEND_ORIGIN, load_settings


def _set_required_path_env(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("EXCEL_ROOT", str(tmp_path / "excel"))
    monkeypatch.setenv("CBANNER_IMAGE_ROOT", str(tmp_path / "cbanner-images"))
    monkeypatch.setenv("YANDOU_IMAGE_ROOT", str(tmp_path / "yandou-images"))
    monkeypatch.setenv("EBLAN_IMAGE_ROOT", str(tmp_path / "eblan-images"))


def test_doubao_settings_default_model_and_private_key(monkeypatch, tmp_path):
    monkeypatch.setattr(config_module, "BACKEND_ROOT", tmp_path)
    _set_required_path_env(monkeypatch, tmp_path)
    monkeypatch.setenv("ARK_API_KEY", " test-secret ")
    monkeypatch.delenv("DOUBAO_TEXT_MODEL", raising=False)
    monkeypatch.delenv("DOUBAO_TIMEOUT_SECONDS", raising=False)
    monkeypatch.delenv("DOUBAO_PROVIDER", raising=False)
    monkeypatch.delenv("DOUBAO_BASE_URL", raising=False)
    settings = load_settings(require_database=False)
    assert settings.ark_api_key == "test-secret"
    assert "test-secret" not in repr(settings)
    assert settings.doubao_text_model == "doubao-seed-2-1-pro-260915"
    assert settings.doubao_timeout_seconds == 90
    assert settings.doubao_provider == "ark"
    assert settings.doubao_base_url == ""


def test_doubao_settings_read_custom_provider_and_base_url_from_dotenv(monkeypatch, tmp_path):
    monkeypatch.setattr(config_module, "BACKEND_ROOT", tmp_path)
    _set_required_path_env(monkeypatch, tmp_path)
    for name in ("ARK_API_KEY", "DOUBAO_PROVIDER", "DOUBAO_BASE_URL", "DOUBAO_TEXT_MODEL"):
        monkeypatch.delenv(name, raising=False)
    (tmp_path / ".env").write_text(
        "ARK_API_KEY=custom-secret\nDOUBAO_PROVIDER= CUSTOM \nDOUBAO_BASE_URL=https://model.pardx.cn\nDOUBAO_TEXT_MODEL=custom-doubao\n",
        encoding="utf-8",
    )
    settings = load_settings(require_database=False)
    assert settings.ark_api_key == "custom-secret"
    assert "custom-secret" not in repr(settings)
    assert settings.doubao_provider == "custom"
    assert settings.doubao_base_url == "https://model.pardx.cn"
    assert settings.doubao_text_model == "custom-doubao"


def test_doubao_settings_allow_endpoint_override_without_api_key(monkeypatch, tmp_path):
    monkeypatch.setattr(config_module, "BACKEND_ROOT", tmp_path)
    _set_required_path_env(monkeypatch, tmp_path)
    monkeypatch.delenv("ARK_API_KEY", raising=False)
    monkeypatch.setenv("DOUBAO_TEXT_MODEL", "ep-custom")
    monkeypatch.setenv("DOUBAO_TIMEOUT_SECONDS", "120")
    settings = load_settings(require_database=False)
    assert settings.ark_api_key is None
    assert settings.doubao_text_model == "ep-custom"
    assert settings.doubao_timeout_seconds == 120


def test_doubao_timeout_can_exceed_gateway_timeout_for_background_jobs(monkeypatch, tmp_path):
    monkeypatch.setattr(config_module, "BACKEND_ROOT", tmp_path)
    _set_required_path_env(monkeypatch, tmp_path)
    monkeypatch.setenv("DOUBAO_TIMEOUT_SECONDS", "180")
    assert load_settings(require_database=False).doubao_timeout_seconds == 180


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


def test_load_settings_reads_request_rate_limit_configuration(monkeypatch, tmp_path: Path):
    monkeypatch.setattr(config_module, "BACKEND_ROOT", tmp_path)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    _set_required_path_env(monkeypatch, tmp_path)
    monkeypatch.setenv("REQUEST_RATE_LIMIT_ENABLED", "false")
    monkeypatch.setenv("REQUEST_RATE_LIMIT_REQUESTS", "80")
    monkeypatch.setenv("REQUEST_RATE_LIMIT_WINDOW_SECONDS", "30")
    monkeypatch.setenv("REQUEST_RATE_LIMIT_BURST", "10")
    monkeypatch.setenv("REQUEST_RATE_LIMIT_TRUSTED_PROXY_IPS", "127.0.0.1, 10.0.0.1")

    settings = load_settings(require_database=False)

    assert settings.request_rate_limit_enabled is False
    assert settings.request_rate_limit_requests == 80
    assert settings.request_rate_limit_window_seconds == 30
    assert settings.request_rate_limit_burst == 10
    assert settings.request_rate_limit_trusted_proxy_ips == ("127.0.0.1", "10.0.0.1")
