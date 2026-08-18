from datetime import date

from scripts.backfill_product_goods_annual_sales import (
    BrandMatcher,
    _longest_prefix,
    _prefix_index,
    _rows_to_write,
    _target_years,
)


def test_longest_prefix_prefers_the_more_specific_product_code():
    index = _prefix_index(["A100", "A1001"])

    assert _longest_prefix("A1001-39", index) == "A1001"


def test_brand_matcher_uses_unique_style_code_when_product_code_is_unavailable():
    matcher = BrandMatcher(
        product_ids={"A100": 1},
        original_skus={"A100": "STYLE-1"},
        style_codes={"STYLE-1": "A100"},
        prefix_index=_prefix_index(["A100"]),
    )

    assert matcher.resolve("", "STYLE-1") == "A100"


def test_target_years_keeps_requested_year_even_when_authoritative_rows_exist():
    targets = _target_years({2026})

    assert targets["cbanner_womens"]["year"] == {2026}
    assert targets["cbanner_womens"]["month"] == {2026}


def test_rows_to_write_only_skips_the_exact_authoritative_product_period():
    matcher = BrandMatcher(
        product_ids={"A100": 1},
        original_skus={"A100": "STYLE-1"},
        style_codes={"STYLE-1": "A100"},
        prefix_index=_prefix_index(["A100"]),
    )
    totals = {
        ("cbanner_womens", "month", date(2026, 7, 1), "A100"): 5,
        ("cbanner_womens", "month", date(2026, 8, 1), "A100"): 8,
    }

    rows = _rows_to_write(
        totals,
        {"cbanner_womens": matcher},
        daily_as_of_date=date(2026, 8, 18),
        authoritative_period_keys={
            ("cbanner_womens", "month", date(2026, 7, 1), "A100")
        },
    )

    assert len(rows) == 1
    assert rows[0]["period_start"] == date(2026, 8, 1)
    assert rows[0]["sales_quantity"] == 8
