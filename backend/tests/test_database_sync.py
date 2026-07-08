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


def test_sync_brand_rows_refreshes_current_launch_year_only(test_database_url: str, recreate_tables):
    database = Database(test_database_url)
    table = PRODUCT_TABLES["cbanner_mens"]

    current_year_existing = {
        "source_workbook": "manual",
        "source_sheet": "manual",
        "source_row_number": "1",
        "raw_payload": {},
        "sku": "CUR-001",
        "original_sku": "CUR-001",
        "color": "旧颜色",
        "color_code": "OLD",
        "launch_date": "2026-03-01",
        "image_path": "//images/cur.jpg",
    }
    old_year_existing = {
        "source_workbook": "manual",
        "source_sheet": "manual",
        "source_row_number": "2",
        "raw_payload": {},
        "sku": "OLD-001",
        "original_sku": "OLD-001",
        "color": "旧年份颜色",
        "color_code": "KEEP",
        "launch_date": "2025-09-01",
    }
    incoming_current = {
        "source_workbook": "daily",
        "source_sheet": "daily",
        "source_row_number": "3",
        "raw_payload": {"color": "新颜色"},
        "sku": "CUR-001",
        "original_sku": "CUR-001",
        "color": "新颜色",
        "color_code": "NEW",
        "launch_date": "2026-04-01",
        "image_path": None,
    }
    incoming_old = {
        "source_workbook": "daily",
        "source_sheet": "daily",
        "source_row_number": "4",
        "raw_payload": {},
        "sku": "OLD-001",
        "original_sku": "OLD-001",
        "color": "不应覆盖",
        "color_code": "BAD",
        "launch_date": "2025-10-01",
    }
    incoming_new = {
        "source_workbook": "daily",
        "source_sheet": "daily",
        "source_row_number": "5",
        "raw_payload": {},
        "sku": "NEW-2026",
        "original_sku": "NEW-2026",
        "color": "新增颜色",
        "color_code": "N1",
        "launch_date": "2026-05-01",
    }

    assert database.replace_brand_rows("cbanner_mens", [current_year_existing, old_year_existing]) == 2
    assert database.sync_brand_rows(
        "cbanner_mens",
        [incoming_current, incoming_old, incoming_new],
        refresh_launch_year=2026,
    ) == 2

    with database.engine.connect() as connection:
        rows = {
            row["sku"]: dict(row)
            for row in connection.execute(select(table).order_by(table.c.sku)).mappings()
        }

    assert rows["CUR-001"]["color"] == "新颜色"
    assert rows["CUR-001"]["color_code"] == "NEW"
    assert rows["CUR-001"]["source_workbook"] == "daily"
    assert rows["CUR-001"]["launch_date"] == "2026-04-01"
    assert rows["CUR-001"]["image_path"] == "//images/cur.jpg"

    assert rows["OLD-001"]["color"] == "旧年份颜色"
    assert rows["OLD-001"]["color_code"] == "KEEP"
    assert rows["OLD-001"]["source_workbook"] == "manual"
    assert rows["OLD-001"]["launch_date"] == "2025-09-01"

    assert rows["NEW-2026"]["color"] == "新增颜色"
    assert rows["NEW-2026"]["color_code"] == "N1"
