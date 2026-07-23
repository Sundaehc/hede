from datetime import date

from scripts.backfill_product_goods_manual_fields_history import workbook_business_date


def test_workbook_business_date_uses_parent_year_and_filename_day(tmp_path):
    path = tmp_path / "2026年" / "7月份" / "赫德货品表（千百度男鞋）7.22.xlsx"
    path.parent.mkdir(parents=True)
    path.touch()

    assert workbook_business_date(path) == date(2026, 7, 22)


def test_workbook_business_date_uses_month_folder_when_filename_has_no_day(tmp_path):
    path = tmp_path / "2025.6" / "赫德货品表（千百度）.xlsx"
    path.parent.mkdir(parents=True)
    path.touch()

    assert workbook_business_date(path) == date(2025, 6, 1)
