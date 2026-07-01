from __future__ import annotations

from sqlalchemy import select

from domain.schema import PRODUCT_TABLES
from storage.db import Database


def test_insert_new_brand_rows_does_not_overwrite_existing_products(test_database_url: str, recreate_tables):
    database = Database(test_database_url)
    table = PRODUCT_TABLES["cbanner_mens"]

    original = {
        "source_workbook": "manual",
        "source_sheet": "manual",
        "source_row_number": "1",
        "raw_payload": {},
        "sku": "KEEP-001",
        "original_sku": "KEEP-001",
        "color": "手动颜色",
        "color_code": "M1",
    }
    incoming_existing = {
        "source_workbook": "daily",
        "source_sheet": "daily",
        "source_row_number": "2",
        "raw_payload": {},
        "sku": "KEEP-001",
        "original_sku": "KEEP-001",
        "color": "源文件颜色",
        "color_code": "S1",
    }
    incoming_new = {
        "source_workbook": "daily",
        "source_sheet": "daily",
        "source_row_number": "3",
        "raw_payload": {},
        "sku": "NEW-001",
        "original_sku": "NEW-001",
        "color": "新增颜色",
        "color_code": "N1",
    }

    assert database.replace_brand_rows("cbanner_mens", [original]) == 1
    assert database.insert_new_brand_rows("cbanner_mens", [incoming_existing, incoming_new]) == 1

    with database.engine.connect() as connection:
        rows = {
            row["sku"]: dict(row)
            for row in connection.execute(select(table).order_by(table.c.sku)).mappings()
        }

    assert rows["KEEP-001"]["color"] == "手动颜色"
    assert rows["KEEP-001"]["color_code"] == "M1"
    assert rows["KEEP-001"]["source_workbook"] == "manual"
    assert rows["NEW-001"]["color"] == "新增颜色"
    assert rows["NEW-001"]["color_code"] == "N1"
