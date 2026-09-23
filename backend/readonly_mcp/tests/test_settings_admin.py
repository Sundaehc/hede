import os
import sys
from unittest.mock import Mock

import pytest

from readonly_mcp import admin
from readonly_mcp import settings as settings_module
from readonly_mcp.settings import MCPSettings


def set_connections(monkeypatch):
    for profile in ("PRODUCTS", "DESIGN", "CONTROL"):
        monkeypatch.setenv(f"MCP_{profile}_DATABASE_URL", f"postgresql+psycopg://hede_mcp_{profile.lower()}:private@127.0.0.1:5432/hede")


def test_settings_do_not_fall_back_to_admin_database(monkeypatch, tmp_path):
    monkeypatch.setattr(settings_module, "BACKEND_ROOT", tmp_path)
    for profile in ("PRODUCTS", "DESIGN", "CONTROL"):
        monkeypatch.delenv(f"MCP_{profile}_DATABASE_URL", raising=False)
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://admin:private@127.0.0.1/hede")
    with pytest.raises(ValueError, match="专用"):
        MCPSettings.load()


@pytest.mark.parametrize("change", [
    {"MCP_ALLOWED_HOSTS": "*"}, {"MCP_ALLOWED_ORIGINS": "https://*"}, {"MCP_PORT": "80"},
    {"MCP_CONTROL_DATABASE_URL": "postgresql+psycopg://hede_mcp_control:private@elsewhere/hede"},
    {"MCP_PRODUCTS_DATABASE_URL": "sqlite://"},
])
def test_unsafe_config_is_rejected(monkeypatch, tmp_path, change):
    monkeypatch.setattr(settings_module, "BACKEND_ROOT", tmp_path)
    set_connections(monkeypatch)
    for name, value in change.items():
        monkeypatch.setenv(name, value)
    with pytest.raises(ValueError):
        MCPSettings.load()


def test_settings_repr_hides_passwords(monkeypatch, tmp_path):
    monkeypatch.setattr(settings_module, "BACKEND_ROOT", tmp_path)
    set_connections(monkeypatch)
    assert "private" not in repr(MCPSettings.load())


@pytest.fixture
def admin_environment(monkeypatch, tmp_path):
    monkeypatch.setattr(admin, "BACKEND_ROOT", tmp_path)
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://admin:original-secret@127.0.0.1/hede")
    monkeypatch.setattr(sys, "argv", ["admin", "setup", "--execute"])
    engine = Mock()
    monkeypatch.setattr(admin, "create_engine", Mock(return_value=engine))
    original = "DATABASE_URL=private-original\nARK_API_KEY=keep-unchanged\n"
    path = tmp_path / ".env"
    path.write_text(original, encoding="utf-8")
    return tmp_path, path, original, engine


def test_setup_appends_credentials_without_printing_or_modifying_existing_values(admin_environment, monkeypatch, capsys):
    _, path, original, _ = admin_environment
    setup = Mock(side_effect=lambda engine, passwords, finalize: (finalize() or {"created_roles": list(admin.ROLES)}))
    monkeypatch.setattr(admin, "setup", setup)
    admin.main()
    content = path.read_text(encoding="utf-8")
    assert content.startswith(original.rstrip() + "\n\n")
    assert content.count("MCP_PRODUCTS_DATABASE_URL=") == 1
    output = capsys.readouterr().out
    assert "original-secret" not in output and "keep-unchanged" not in output
    for password in setup.call_args.args[1].values():
        assert password not in output


def test_setup_never_deletes_an_existing_recovery_file(admin_environment, monkeypatch):
    root, path, original, _ = admin_environment
    recovery = root / ".env.mcp-pending"
    recovery.write_text("existing-sensitive-recovery", encoding="utf-8")
    setup = Mock()
    monkeypatch.setattr(admin, "setup", setup)
    with pytest.raises(FileExistsError):
        admin.main()
    assert recovery.read_text(encoding="utf-8") == "existing-sensitive-recovery"
    assert path.read_text(encoding="utf-8") == original
    setup.assert_not_called()


def test_setup_failure_cleans_only_its_own_recovery_file(admin_environment, monkeypatch):
    root, path, original, _ = admin_environment
    monkeypatch.setattr(admin, "setup", Mock(side_effect=RuntimeError("database failure")))
    with pytest.raises(RuntimeError):
        admin.main()
    assert path.read_text(encoding="utf-8") == original
    assert not (root / ".env.mcp-pending").exists()


def test_concurrent_env_edit_is_not_overwritten(admin_environment, monkeypatch):
    root, path, original, _ = admin_environment
    def setup(engine, passwords, finalize):
        path.write_text(original + "USER_EDIT=preserved\n", encoding="utf-8")
        finalize()
    monkeypatch.setattr(admin, "setup", setup)
    with pytest.raises(ValueError, match="已改变"):
        admin.main()
    assert "USER_EDIT=preserved" in path.read_text(encoding="utf-8")
    assert not (root / ".env.mcp-pending").exists()


def test_env_edit_after_commit_keeps_recovery_credentials(admin_environment, monkeypatch):
    root, path, original, _ = admin_environment
    def setup(engine, passwords, finalize):
        finalize()
        path.write_text(original + "USER_EDIT=after-commit\n", encoding="utf-8")
        return {"created_roles": list(admin.ROLES)}
    monkeypatch.setattr(admin, "setup", setup)
    with pytest.raises(ValueError, match="凭证保存在"):
        admin.main()
    assert "USER_EDIT=after-commit" in path.read_text(encoding="utf-8")
    assert "MCP_PRODUCTS_DATABASE_URL=" in (root / ".env.mcp-pending").read_text(encoding="utf-8")
