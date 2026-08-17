from __future__ import annotations

from sqlalchemy import select, text

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
        "size_range": "手工尺码组",
        "season_category": "秋季",
        "year": "26年秋季款",
        "product_name": "桌面品名",
        "product_model": "桌面型号",
        "supplier_name": "档案供应商",
        "category": "男鞋",
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
        "size_range": "源文件尺码组",
        "season_category": None,
        "year": "",
        "product_name": "源文件品名",
        "product_model": "源文件型号",
        "supplier_name": "源文件供应商",
        "category": "女鞋",
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

    assert rows["CUR-001"]["color"] == "旧颜色"
    assert rows["CUR-001"]["color_code"] == "OLD"
    assert rows["CUR-001"]["source_workbook"] == "daily"
    assert rows["CUR-001"]["launch_date"] == "2026-04-01"
    assert rows["CUR-001"]["image_path"] == "//images/cur.jpg"
    assert rows["CUR-001"]["size_range"] == "手工尺码组"
    assert rows["CUR-001"]["season_category"] == "秋季"
    assert rows["CUR-001"]["year"] == "26年秋季款"
    assert rows["CUR-001"]["product_name"] == "桌面品名"
    assert rows["CUR-001"]["product_model"] == "桌面型号"
    assert rows["CUR-001"]["supplier_name"] == "档案供应商"
    assert rows["CUR-001"]["category"] == "男鞋"

    assert rows["OLD-001"]["color"] == "旧年份颜色"
    assert rows["OLD-001"]["color_code"] == "KEEP"
    assert rows["OLD-001"]["source_workbook"] == "manual"
    assert rows["OLD-001"]["launch_date"] == "2025-09-01"

    assert rows["NEW-2026"]["color"] == "新增颜色"
    assert rows["NEW-2026"]["color_code"] == "N1"


def test_sync_brand_rows_preserves_yandou_product_model_from_archive(test_database_url: str, recreate_tables):
    database = Database(test_database_url)
    table = PRODUCT_TABLES["yandou"]
    existing = {
        "source_workbook": "legacy",
        "source_sheet": "legacy",
        "source_row_number": "1",
        "raw_payload": {},
        "sku": "YD-001",
        "original_sku": "YD-001",
        "launch_date": "2026-04-01",
        "product_model": "男式休闲鞋",
    }
    incoming = {
        "source_workbook": "管家婆",
        "source_sheet": "商品信息",
        "source_row_number": "2",
        "raw_payload": {"产品型号": "二型半"},
        "sku": "YD-001",
        "original_sku": "YD-001",
        "launch_date": "2026-04-01",
        "product_model": "二型半",
    }

    database.replace_brand_rows("yandou", [existing])
    database.sync_brand_rows(
        "yandou",
        [incoming],
        refresh_launch_year=2026,
    )

    with database.engine.connect() as connection:
        row = connection.execute(select(table).where(table.c.sku == "YD-001")).mappings().one()

    assert row["product_model"] == "男式休闲鞋"


def test_sync_yandou_product_models_fills_blank_archive_value_from_latest_gj_source(test_database_url: str, recreate_tables):
    database = Database(test_database_url)
    table = PRODUCT_TABLES["yandou"]
    database.replace_brand_rows("yandou", [{
        "source_workbook": "legacy",
        "source_sheet": "legacy",
        "source_row_number": "1",
        "raw_payload": {},
        "sku": "YD-MODEL-001",
        "original_sku": "YD-MODEL-001",
        "product_model": "",
    }])
    with database.engine.begin() as connection:
        connection.execute(text("""
            INSERT INTO gj_merged_product_info (
                source_date, source_date_value, fine_table_brand, source_workbook,
                source_sheet, source_row_number, raw_payload, goods_code
            ) VALUES (
                '2026-08-10', '2026-08-10', 'yandou', '管家婆',
                '商品信息', '1', CAST('{"产品型号": "二型半"}' AS json), 'YD-MODEL-001'
            )
        """))

    assert database.sync_yandou_product_models() == 1

    with database.engine.connect() as connection:
        row = connection.execute(select(table).where(table.c.sku == "YD-MODEL-001")).mappings().one()

    assert row["product_model"] == "二型半"
