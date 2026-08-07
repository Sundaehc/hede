from __future__ import annotations

from decimal import Decimal

from domain.ni_gendered_costs import (
    FEMALE_KEY,
    MALE_KEY,
    build_gender_costs,
    gender_for_size,
    price_for_sizes,
    split_sizes_by_gender,
)


GENDER_COSTS = {FEMALE_KEY: "178", MALE_KEY: "190"}


def test_build_gender_costs_supports_the_two_ni_source_conventions() -> None:
    costs = build_gender_costs({
        "NIA2253A020115": {"工厂进货价": Decimal("178"), "预设售价3": Decimal("190")},
        "NI24Q4A020115": {"工厂进货价": Decimal("195"), "男码价格": Decimal("318.47")},
        "NI24Q3A030101": {"工厂进货价": Decimal("220")},
    })

    assert costs == {
        "NIA2253A020115": {FEMALE_KEY: Decimal("178"), MALE_KEY: Decimal("190")},
        "NI24Q4A020115": {FEMALE_KEY: Decimal("195"), MALE_KEY: Decimal("318.47")},
    }


def test_ni_gendered_cost_uses_eu_and_millimeter_sizes() -> None:
    assert gender_for_size("36") == FEMALE_KEY
    assert gender_for_size("230") == FEMALE_KEY
    assert gender_for_size("42") == MALE_KEY
    assert gender_for_size("260") == MALE_KEY
    assert price_for_sizes(GENDER_COSTS, {"36": "2"}) == Decimal("178")
    assert price_for_sizes(GENDER_COSTS, {"42": "1"}) == Decimal("190")


def test_ni_gendered_cost_splits_mixed_size_details() -> None:
    assert split_sizes_by_gender({"36": "2", "42": "1"}) == {
        FEMALE_KEY: {"36": Decimal("2")},
        MALE_KEY: {"42": Decimal("1")},
    }
    assert price_for_sizes(GENDER_COSTS, {"36": "2", "42": "1"}) is None
