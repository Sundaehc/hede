from __future__ import annotations

from datetime import date
from decimal import Decimal
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

import pytest
from openpyxl import Workbook

from storage.dewu_order_repository import (
    DEWU_ORDER_HEADER_MAP,
    DewuOrderRepository,
    DewuOrderSource,
    parse_dewu_order_workbook,
)


class _Result:
    rowcount = 3


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


def _robot_style_workbook(path: Path) -> None:
    normal_path = path.with_name("normal.xlsx")
    workbook = Workbook()
    worksheet = workbook.active
    worksheet.title = "sheet1"
    headers = list(DEWU_ORDER_HEADER_MAP)
    worksheet.append(headers)
    row = [None] * len(headers)
    values = {
        "订单号": "110210000000000001",
        "spuID": 8975477,
        "skuID": 666090493,
        "货号": "QH941651D66",
        "规格": "白灰色 38",
        "数量": 1,
        "出价金额（元）": "360.25",
        "预计收入金额（元）": "268.20",
        "订单状态": "待卖家发货",
        "买家下单时间": "2026-08-19 10:25:08",
    }
    for header, value in values.items():
        row[headers.index(header)] = value
    worksheet.append(row)
    workbook.save(normal_path)

    with ZipFile(normal_path, "r") as source_zip, ZipFile(path, "w", ZIP_DEFLATED) as target_zip:
        for item in source_zip.infolist():
            data = source_zip.read(item.filename)
            if item.filename == "xl/worksheets/sheet1.xml":
                data = data.replace(b'<dimension ref="A1:BK2"/>', b'<dimension ref="A1"/>')
            target_zip.writestr(item, data)
    normal_path.unlink()


def test_parse_dewu_order_workbook_handles_incorrect_a1_dimension(tmp_path: Path):
    source_file = tmp_path / "千百度得物订单.xlsx"
    _robot_style_workbook(source_file)

    rows = parse_dewu_order_workbook(
        source_file,
        DewuOrderSource("cbanner", "千百度", source_file.name),
    )

    assert len(rows) == 1
    assert rows[0]["order_number"] == "110210000000000001"
    assert rows[0]["spu_id"] == "8975477"
    assert rows[0]["sku_id"] == "666090493"
    assert rows[0]["quantity"] == 1
    assert rows[0]["bid_amount"] == Decimal("360.25")
    assert rows[0]["estimated_income_amount"] == Decimal("268.20")
    assert rows[0]["order_date"].isoformat() == "2026-08-19"
    assert rows[0]["source_row_number"] == 2


def test_parse_dewu_order_workbook_rejects_missing_required_headers(tmp_path: Path):
    source_file = tmp_path / "伊伴得物订单.xlsx"
    workbook = Workbook()
    workbook.active.append(["订单号"])
    workbook.active.append(["1"])
    workbook.save(source_file)

    with pytest.raises(ValueError, match="缺少字段"):
        parse_dewu_order_workbook(
            source_file,
            DewuOrderSource("eblan", "伊伴", source_file.name),
        )


def test_import_all_replaces_independent_brand_date_windows(monkeypatch, tmp_path: Path):
    source_rows = {
        "cbanner": [
            {"order_number": "C1", "order_date": date(2026, 6, 10)},
            {"order_number": "C2", "order_date": date(2026, 9, 8)},
        ],
        "eblan": [
            {"order_number": "E1", "order_date": date(2026, 7, 1)},
            {"order_number": "E2", "order_date": date(2026, 9, 9)},
        ],
        "yandou": [],
        "smiley": [{"order_number": "S1", "order_date": date(2026, 8, 1)}],
    }
    monkeypatch.setattr(
        "storage.dewu_order_repository.parse_dewu_order_workbook",
        lambda _file, source: source_rows[source.brand_group],
    )

    repository = DewuOrderRepository("sqlite://")
    engine = _Engine()
    repository.engine = engine
    monkeypatch.setattr(repository, "ensure_table", lambda: None)

    result = repository.import_all(tmp_path)

    dated_deletes = [
        statement
        for statement, _ in engine.connection.statements
        if getattr(statement, "is_delete", False)
        and "order_date IS NULL" not in str(statement)
    ]
    assert len(dated_deletes) == 3
    assert result["windows"]["cbanner"]["start"] == "2026-06-10"
    assert result["windows"]["cbanner"]["end"] == "2026-09-08"
    assert result["windows"]["eblan"]["start"] == "2026-07-01"
    assert result["windows"]["eblan"]["end"] == "2026-09-09"
    assert "yandou" not in result["windows"]
    assert result["deleted_counts"]["yandou"] == 0


def test_import_all_rejects_nonempty_source_without_valid_dates(monkeypatch, tmp_path: Path):
    monkeypatch.setattr(
        "storage.dewu_order_repository.parse_dewu_order_workbook",
        lambda _file, source: [{"order_number": "1", "order_date": None}]
        if source.brand_group == "cbanner"
        else [],
    )

    repository = DewuOrderRepository("sqlite://")

    with pytest.raises(ValueError, match="没有有效的买家下单时间"):
        repository.import_all(tmp_path)
