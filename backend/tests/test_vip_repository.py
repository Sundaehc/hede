from datetime import datetime
from pathlib import Path

from openpyxl import Workbook

from domain.vip_schema import VIP_DAILY_TABLE
from domain.vip_sources import JST_MONTHLY_ORDERS_COLUMN_ALIASES
from storage.vip_repository import VipRepository


class _Result:
    rowcount = 2


class _Connection:
    def __init__(self) -> None:
        self.statements: list[tuple[object, object | None]] = []

    def execute(self, statement, parameters=None):
        self.statements.append((statement, parameters))
        return _Result()


class _Begin:
    def __init__(self, connection: _Connection) -> None:
        self.connection = connection

    def __enter__(self) -> _Connection:
        return self.connection

    def __exit__(self, *_args) -> None:
        return None


class _Engine:
    def __init__(self) -> None:
        self.connection = _Connection()

    def begin(self) -> _Begin:
        return _Begin(self.connection)


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


def test_monthly_order_import_replaces_only_source_date_window(tmp_path: Path):
    order_time_header = next(
        header
        for header, field in JST_MONTHLY_ORDERS_COLUMN_ALIASES.items()
        if field == "order_time"
    )
    source_file = tmp_path / "monthly-orders.xlsx"
    workbook = Workbook()
    worksheet = workbook.active
    worksheet.append([order_time_header])
    worksheet.append(["2026-06-08 23:59:59"])
    worksheet.append(["2026-09-07 00:00:01"])
    workbook.save(source_file)

    repository = VipRepository("sqlite://")
    engine = _Engine()
    repository.engine = engine

    result = repository.import_monthly_order(source_file)

    delete_statements = [
        statement
        for statement, _ in engine.connection.statements
        if getattr(statement, "is_delete", False)
    ]
    assert len(delete_statements) == 2
    dated_parameters = list(delete_statements[0].compile().params.values())
    assert datetime(2026, 6, 8) in dated_parameters
    assert datetime(2026, 9, 8) in dated_parameters
    assert result["window_start"] == "2026-06-08"
    assert result["window_end"] == "2026-09-07"
    assert result["deleted"] == 4
