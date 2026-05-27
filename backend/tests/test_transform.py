from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from transform.rows import (
    ADMIN_EDITABLE_COLUMNS,
    ADMIN_FIELD_NORMALIZERS,
    build_admin_record,
    build_canonical_row,
    normalize_admin_payload,
)



def test_admin_normalization_helpers_cover_only_special_admin_fields():
    assert set(ADMIN_FIELD_NORMALIZERS) == {"cost", "first_order_time"}
    assert set(ADMIN_FIELD_NORMALIZERS).issubset(ADMIN_EDITABLE_COLUMNS)
    assert {"image_path", "first_order_time"}.issubset(ADMIN_EDITABLE_COLUMNS)



def test_build_canonical_row_uses_original_sku_when_sku_missing():
    row = {
        "原始货号": "A1001",
        "成本": "199.50",
        "颜色": "黑色",
    }

    canonical = build_canonical_row(
        row,
        workbook_key="cbanner_mens_25",
        sheet_name="25年春季款",
        row_number=2,
        image_path="//server/images/A1001.jpg",
    )

    assert canonical is not None
    assert canonical["sku"] == "A1001"
    assert canonical["original_sku"] == "A1001"
    assert canonical["cost"] == Decimal("199.50")
    assert canonical["season_category"] == "spring"
    assert canonical["year"] == "2025"
    assert canonical["image_path"] == "//server/images/A1001.jpg"



def test_build_canonical_row_normalizes_numeric_sku_values():
    row = {
        "货号": 12345.0,
        "原始货号": 12345.0,
    }

    canonical = build_canonical_row(
        row,
        workbook_key="cbanner_mens_21_24",
        sheet_name="千百度",
        row_number=2,
        image_path=None,
    )

    assert canonical is not None
    assert canonical["sku"] == "12345"
    assert canonical["original_sku"] == "12345"



def test_build_canonical_row_converts_na_values_to_null():
    row = {
        "货号": "C3003",
        "颜色": "#N/A",
        "成本": "#N/A",
    }

    canonical = build_canonical_row(
        row,
        workbook_key="cbanner_womens",
        sheet_name="千百度",
        row_number=2,
        image_path=None,
    )

    assert canonical is not None
    assert canonical["color"] is None
    assert canonical["cost"] is None
    assert canonical["raw_payload"]["颜色"] is None
    assert canonical["raw_payload"]["成本"] is None



def test_build_canonical_row_converts_first_order_time_to_date_only():
    row = {
        "货号": "D4004",
        "首单时间": datetime(2026, 4, 23, 15, 16, 17),
    }

    canonical = build_canonical_row(
        row,
        workbook_key="cbanner_mens_26",
        sheet_name="26年春季款",
        row_number=2,
        image_path=None,
    )

    assert canonical is not None
    assert canonical["first_order_time"] == "2026-04-23"



def test_build_canonical_row_drops_time_only_first_order_time():
    row = {
        "货号": "D4005",
        "首单时间": "00:00:00",
    }

    canonical = build_canonical_row(
        row,
        workbook_key="yandou",
        sheet_name="烟斗",
        row_number=2,
        image_path=None,
    )

    assert canonical is not None
    assert canonical["first_order_time"] is None



def test_build_canonical_row_preserves_existing_importer_fallback_for_malformed_first_order_time():
    row = {
        "货号": "D4006",
        "首单时间": "bad-date-value",
    }

    canonical = build_canonical_row(
        row,
        workbook_key="cbanner_mens_26",
        sheet_name="26年春季款",
        row_number=2,
        image_path=None,
    )

    assert canonical is not None
    assert canonical["first_order_time"] == "bad-date-v"



def test_build_canonical_row_uses_full_year_from_sheet_name():
    row = {
        "货号": "B2002",
    }

    canonical = build_canonical_row(
        row,
        workbook_key="eblan",
        sheet_name="2026",
        row_number=2,
        image_path=None,
    )

    assert canonical is not None
    assert canonical["year"] == "2026"



def test_build_canonical_row_skips_when_both_sku_fields_empty():
    row = {
        "颜色": "米白",
    }

    canonical = build_canonical_row(
        row,
        workbook_key="eblan",
        sheet_name="2025",
        row_number=3,
        image_path=None,
    )

    assert canonical is None



def test_build_canonical_row_maps_toe_shape_aliases():
    row = {
        "货号": "E5005",
        "鞋头款式": "方头",
    }

    canonical = build_canonical_row(
        row,
        workbook_key="cbanner_womens",
        sheet_name="千百度",
        row_number=2,
        image_path=None,
    )

    assert canonical is not None
    assert canonical["toe_shape"] == "方头"



def test_build_canonical_row_maps_execution_standard_alias():
    row = {
        "货号": "E5006",
        "执行标": "QB/T 1002",
    }

    canonical = build_canonical_row(
        row,
        workbook_key="cbanner_mens_21_24",
        sheet_name="千百度",
        row_number=2,
        image_path=None,
    )

    assert canonical is not None
    assert canonical["execution_standard"] == "QB/T 1002"



def test_normalize_admin_payload_keeps_only_editable_columns_and_normalizes_values():
    payload = {
        "sku": 1001.0,
        "original_sku": "  OR-1001  ",
        "cost": "1,299.50",
        "color": " #N/A ",
        "first_order_time": datetime(2026, 4, 23, 15, 16, 17),
        "shoe_box_spec": "  40x30x20  ",
        "source_workbook": "spreadsheet",
        "unknown_field": "ignored",
    }

    normalized = normalize_admin_payload(payload)

    assert normalized == {
        "sku": "1001",
        "original_sku": "OR-1001",
        "cost": Decimal("1299.50"),
        "color": None,
        "first_order_time": "2026-04-23",
        "shoe_box_spec": "40x30x20",
    }



def test_build_admin_record_sets_manual_metadata_and_raw_payload_from_normalized_payload():
    payload = {
        "sku": "  SKU-1  ",
        "cost": "88.00",
        "first_order_time": "2026/4/5 10:00:00",
        "source_row_number": "ignored",
    }

    record = build_admin_record("cbanner_womens", payload)

    assert record["sku"] == "SKU-1"
    assert record["cost"] == Decimal("88.00")
    assert record["first_order_time"] == "2026-04-05"
    assert record["source_workbook"] == "manual_admin"
    assert record["source_sheet"] == "cbanner_womens"
    assert record["source_row_number"] == "manual"
    assert record["raw_payload"] == {
        "sku": "SKU-1",
        "cost": Decimal("88.00"),
        "first_order_time": "2026-04-05",
    }



def test_build_admin_record_preserves_existing_source_metadata_when_supplied():
    payload = {
        "sku": "SKU-2",
        "color": "  黑色  ",
        "unknown": "ignored",
    }
    existing_metadata = {
        "source_workbook": "imported-book",
        "source_sheet": "Sheet1",
        "source_row_number": "42",
    }

    record = build_admin_record("eblan", payload, existing_metadata=existing_metadata)

    assert record["sku"] == "SKU-2"
    assert record["color"] == "黑色"
    assert record["source_workbook"] == "imported-book"
    assert record["source_sheet"] == "Sheet1"
    assert record["source_row_number"] == "42"
    assert record["raw_payload"] == {
        "sku": "SKU-2",
        "color": "黑色",
    }



def test_normalize_admin_payload_drops_malformed_special_fields():
    payload = {
        "sku": "SKU-3",
        "cost": "not-a-number",
        "first_order_time": "bad-date-value",
    }

    normalized = normalize_admin_payload(payload)

    assert normalized == {
        "sku": "SKU-3",
        "cost": None,
        "first_order_time": None,
    }
