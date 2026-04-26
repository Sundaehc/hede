from pathlib import Path

import config as config_module
from config import DEFAULT_EXCEL_ROOT, DEFAULT_FRONTEND_ORIGIN, load_settings


def test_load_settings_allows_missing_database_for_dry_run(monkeypatch, tmp_path: Path):
    monkeypatch.setattr(config_module, "BACKEND_ROOT", tmp_path)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    settings = load_settings(require_database=False)
    assert settings.database_url is None


def test_load_settings_defaults_frontend_origin_for_dry_run(monkeypatch, tmp_path: Path):
    monkeypatch.setattr(config_module, "BACKEND_ROOT", tmp_path)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("FRONTEND_ORIGIN", raising=False)

    settings = load_settings(require_database=False)

    assert settings.frontend_origin == DEFAULT_FRONTEND_ORIGIN


def test_load_settings_reads_frontend_origin_from_env(monkeypatch, tmp_path: Path):
    monkeypatch.setattr(config_module, "BACKEND_ROOT", tmp_path)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setenv("FRONTEND_ORIGIN", "https://admin.example.com")

    settings = load_settings(require_database=False)

    assert settings.frontend_origin == "https://admin.example.com"


def test_load_settings_reads_excel_root_from_env(monkeypatch, tmp_path: Path):
    monkeypatch.setattr(config_module, "BACKEND_ROOT", tmp_path)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("EXCEL_SOURCE_ROOT", raising=False)

    override_root = tmp_path / "excel-source"
    monkeypatch.setenv("EXCEL_SOURCE_ROOT", str(override_root))

    settings = load_settings(require_database=False)

    assert settings.excel_root == override_root
    assert settings.excel_root != DEFAULT_EXCEL_ROOT
