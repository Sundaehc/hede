from pathlib import Path

from domain.vip_schema import VIP_DAILY_TABLE
from storage.vip_repository import VipRepository


def test_daily_report_upsert_uses_source_date_as_part_of_key(monkeypatch):
    repository = VipRepository("sqlite://")
    captured: dict[str, object] = {}

    monkeypatch.setattr("storage.vip_repository._report_type_from_filename", lambda _: "comparison")
    monkeypatch.setattr("storage.vip_repository._period_from_filename", lambda _: "3d")
    monkeypatch.setattr(
        repository,
        "_read_excel",
        lambda *_: [{"goods_id": "123", "date": "2026-07-20", "sales_volume": 1}],
    )

    def capture_upsert(table, rows, key_cols, update_cols):
        captured["table"] = table
        captured["rows"] = rows
        captured["key_cols"] = key_cols
        captured["update_cols"] = update_cols

    monkeypatch.setattr(repository, "_upsert", capture_upsert)

    repository.import_daily(Path("report.xlsx"), replace_existing=False)

    assert captured["table"] is VIP_DAILY_TABLE
    assert captured["key_cols"] == ["report_type", "period", "goods_id", "date"]
    assert "date" not in captured["update_cols"]
