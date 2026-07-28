from datetime import date
from pathlib import Path

import pytest

from scripts import import_vip_daily


class FakeRepository:
    def import_all(self, directory: Path, *, replace_existing: bool):
        return {"success": True, "total_imported": 1}


class FakeSettings:
    database_url = "postgresql://unused"
    vip_data_roots = (Path("C:/vip/available"), Path("C:/vip/missing"))


def test_import_fails_when_a_configured_source_directory_is_missing(monkeypatch):
    today_directory = date.today().strftime("%m.%d")
    monkeypatch.setattr(import_vip_daily, "load_settings", lambda: FakeSettings())
    monkeypatch.setattr(import_vip_daily, "VipRepository", lambda database_url: FakeRepository())
    monkeypatch.setattr(Path, "exists", lambda path: str(path).endswith(f"available\\{today_directory}"))

    with pytest.raises(SystemExit, match="导入不完整"):
        import_vip_daily.main()
