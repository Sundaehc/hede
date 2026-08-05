from __future__ import annotations

from openpyxl import Workbook

from scripts.backfill_product_size_ranges import read_size_group_mappings


def _write_mapping_workbook(path, rows: list[tuple[str, str]]) -> None:
    workbook = Workbook()
    worksheet = workbook.active
    worksheet.append(["款式编码", "系统尺码名称"])
    for row in rows:
        worksheet.append(row)
    workbook.save(path)


def test_read_size_group_mappings_skips_zero_and_deduplicates(tmp_path) -> None:
    path = tmp_path / "size-groups.xlsx"
    _write_mapping_workbook(path, [
        ("A001", "女鞋尺码组220-250"),
        ("A001", "女鞋尺码组220-250"),
        ("A002", "0"),
    ])

    mappings, skipped = read_size_group_mappings(path)

    assert mappings == {"A001": "女鞋尺码组220-250"}
    assert skipped == 1


def test_read_size_group_mappings_rejects_conflicting_codes(tmp_path) -> None:
    path = tmp_path / "size-groups.xlsx"
    _write_mapping_workbook(path, [
        ("A001", "女鞋尺码组220-250"),
        ("A001", "男鞋尺码组240-270"),
    ])

    try:
        read_size_group_mappings(path)
    except ValueError as error:
        assert "多个尺码段" in str(error)
    else:
        raise AssertionError("expected conflicting size-group mapping to fail")
