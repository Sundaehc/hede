from datetime import date

from scripts.import_product_goods_historical_orders import _order_date
from scripts.import_product_goods_historical_orders_daily import _date_hint


def test_order_date_prefers_the_explicit_date_column():
    assert _order_date(
        (date(2024, 6, 5), "SKU", 3, "唯品", 2024, 6),
        {"date": 0, "year": 4, "month": 5},
    ) == date(2024, 6, 5)


def test_order_date_falls_back_to_year_and_month():
    assert _order_date(
        (None, "SKU", 3, "唯品", 2024, 6),
        {"date": 0, "year": 4, "month": 5},
    ) == date(2024, 6, 1)


def test_order_date_uses_year_and_month_when_the_recorded_date_is_inconsistent():
    assert _order_date(
        (date(2021, 1, 1), "SKU", 3, "唯品", 2024, 6),
        {"date": 0, "year": 4, "month": 5},
    ) == date(2024, 6, 1)


def test_workbook_date_hint_uses_the_filename_and_parent_year(tmp_path):
    workbook = tmp_path / "2026年" / "7月份" / "赫德货品表（千百度男鞋）7.22.xlsx"
    workbook.parent.mkdir(parents=True)
    workbook.touch()

    assert _date_hint(workbook) == date(2026, 7, 22)
