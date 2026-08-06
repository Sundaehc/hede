from __future__ import annotations

from decimal import Decimal

from scripts.import_ni_product_archive_from_desktop import _year_from_launch_date, _decimal


def test_ni_import_parses_year_from_launch_date() -> None:
    assert _year_from_launch_date("2025-05-06") == "2025"
    assert _year_from_launch_date("") == ""


def test_ni_import_parses_cost_unit_price_as_decimal() -> None:
    assert _decimal("123.45") == Decimal("123.45")
    assert _decimal("") is None
