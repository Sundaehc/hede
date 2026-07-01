from __future__ import annotations

import io

from openpyxl import Workbook

from api.routes.inventory import (
    _group_purchase_import_rows_by_summary,
    _missing_purchase_order_import_fields,
    _purchase_order_import_has_size_columns,
    _read_purchase_import_rows,
)


def _sample_purchase_workbook() -> bytes:
    workbook = Workbook()
    worksheet = workbook.active
    worksheet.append(["供货单位", "商品编码", "数量", "摘要", "采购日期", "协议到货日期", "收货仓库", "经办人"])
    worksheet.append([
        "友宝保罗（千百度）",
        "C5563406D8080240",
        6,
        "26.06.29友宝保罗（千百度）新款下单160双 未打",
        "2026/6/29",
        "2026/7/15",
        "赫德仙岩仓",
        "陈希华",
    ])
    worksheet.append([
        "友宝保罗（千百度）",
        "C5563406D8080245",
        10,
        "26.06.29友宝保罗（千百度）新款下单160双 未打",
        "2026/6/29",
        "2026/7/15",
        "赫德仙岩仓",
        "陈希华",
    ])
    buffer = io.BytesIO()
    workbook.save(buffer)
    return buffer.getvalue()


def _legacy_size_column_workbook() -> bytes:
    workbook = Workbook()
    worksheet = workbook.active
    worksheet.append(["商品编码", "220", "225"])
    worksheet.append(["C5563406D8080", 6, 10])
    buffer = io.BytesIO()
    workbook.save(buffer)
    return buffer.getvalue()


def _legacy_single_document_workbook() -> bytes:
    workbook = Workbook()
    worksheet = workbook.active
    worksheet.append(["商品编码", "数量"])
    worksheet.append(["C5563406D8080240", 6])
    buffer = io.BytesIO()
    workbook.save(buffer)
    return buffer.getvalue()


def test_purchase_import_rows_include_document_fields_and_group_by_summary() -> None:
    rows, sheet_name = _read_purchase_import_rows(_sample_purchase_workbook())
    groups = _group_purchase_import_rows_by_summary(rows, "")

    assert sheet_name == "Sheet"
    assert len(rows) == 2
    assert rows[0]["product_code"] == "C5563406D8080240"
    assert rows[0]["quantity"] == "6"
    assert rows[0]["date"] == "2026-06-29"
    assert rows[0]["delivery_date"] == "2026-07-15"
    assert rows[0]["supplier"] == "友宝保罗（千百度）"
    assert rows[0]["warehouse"] == "赫德仙岩仓"
    assert rows[0]["handler"] == "陈希华"

    assert len(groups) == 1
    assert groups[0]["fields"]["summary"] == "26.06.29友宝保罗（千百度）新款下单160双 未打"
    assert len(groups[0]["rows"]) == 2


def test_purchase_order_import_rejects_legacy_single_document_template() -> None:
    rows, _ = _read_purchase_import_rows(_legacy_single_document_workbook())

    assert _missing_purchase_order_import_fields(rows) == [
        "supplier",
        "summary",
        "date",
        "delivery_date",
        "warehouse",
        "handler",
    ]


def test_purchase_order_import_rejects_legacy_size_column_template() -> None:
    rows, _ = _read_purchase_import_rows(_legacy_size_column_workbook())

    assert _purchase_order_import_has_size_columns(rows) is True
