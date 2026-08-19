from __future__ import annotations

from decimal import Decimal
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

import pytest
from openpyxl import Workbook

from storage.dewu_order_repository import (
    DEWU_ORDER_HEADER_MAP,
    DewuOrderSource,
    parse_dewu_order_workbook,
)


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
