from __future__ import annotations

from decimal import Decimal

from scripts.import_ni_product_archive_from_desktop import (
    NI_COST_PRESET_PRICE_NAME,
    PRICE_COST_HEADERS,
    _decimal,
    _year_from_launch_date,
)


def test_ni_import_parses_year_from_launch_date() -> None:
    assert _year_from_launch_date("2025-05-06") == "2025"
    assert _year_from_launch_date("") == ""


def test_ni_import_parses_cost_unit_price_as_decimal() -> None:
    assert _decimal("123.45") == Decimal("123.45")
    assert _decimal("") is None


def test_ni_import_uses_preset_price_as_cost_source() -> None:
    assert PRICE_COST_HEADERS == ("预设售价",)
    assert NI_COST_PRESET_PRICE_NAME == "成本价"
