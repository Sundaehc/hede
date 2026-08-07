"""NI products whose cost varies by the gendered size range."""
from __future__ import annotations

from decimal import Decimal, InvalidOperation
import re
from typing import Mapping


GENDER_COSTS_FIELD = "gender_costs"
FEMALE_KEY = "女"
MALE_KEY = "男"

# NI's source workbook uses both names for the male price.  The latter is the
# label used by the two NIA2253 rows in the current export.
FEMALE_PRICE_NAME = "工厂进货价"
MALE_PRICE_NAMES = ("男码价格", "预设售价3")
NI_MILLIMETER_TO_EU = {
    str(millimeter): str(eu)
    for millimeter, eu in zip(range(220, 286, 5), range(34, 48))
}


def _decimal(value: object) -> Decimal | None:
    if value in (None, ""):
        return None
    try:
        return Decimal(str(value).replace(",", "").strip())
    except (InvalidOperation, ValueError):
        return None


def normalize_gender_costs(value: object) -> dict[str, Decimal]:
    if not isinstance(value, Mapping):
        return {}
    result: dict[str, Decimal] = {}
    for key in (FEMALE_KEY, MALE_KEY, "female", "male"):
        price = _decimal(value.get(key))
        if price is not None and price > 0:
            result[FEMALE_KEY if key in (FEMALE_KEY, "female") else MALE_KEY] = price
    return result


def build_gender_costs(price_rows: Mapping[str, Mapping[str, object]]) -> dict[str, dict[str, Decimal]]:
    """Build only complete, genuinely different female/male price pairs."""
    result: dict[str, dict[str, Decimal]] = {}
    for code, rows in price_rows.items():
        female = _decimal(rows.get(FEMALE_PRICE_NAME))
        male = next((_decimal(rows.get(name)) for name in MALE_PRICE_NAMES if rows.get(name) not in (None, "")), None)
        if female is None or male is None or female == male:
            continue
        result[str(code).strip()] = {FEMALE_KEY: female, MALE_KEY: male}
    return result


def _size_number(value: object) -> Decimal | None:
    text = str(value or "").strip().replace(" ", "")
    if not text:
        return None
    match = re.fullmatch(r"(\d+(?:\.\d+)?)", text)
    if match:
        number = Decimal(match.group(1))
        if text in NI_MILLIMETER_TO_EU:
            return Decimal(NI_MILLIMETER_TO_EU[text])
        return number
    combined = re.fullmatch(r"(\d+(?:\.\d+)?)[-~～－—至/／](\d+(?:\.\d+)?)", text)
    if combined:
        start = _size_number(combined.group(1))
        end = _size_number(combined.group(2))
        if start is not None and end is not None:
            return (start + end) / 2
    return None


def gender_for_size(value: object) -> str | None:
    """Return the NI price band for an EU/millimetre size.

    NI women's sizes are 35-39 and men's sizes start at 40.  A combined size
    crossing 39/40 is intentionally left unresolved rather than mispriced.
    """
    text = str(value or "").strip().replace(" ", "")
    combined = re.fullmatch(r"(\d+(?:\.\d+)?)[-~～－—至/／](\d+(?:\.\d+)?)", text)
    if combined:
        start = _size_number(combined.group(1))
        end = _size_number(combined.group(2))
        if start is None or end is None:
            return None
        if end <= 39:
            return FEMALE_KEY
        if start >= 40:
            return MALE_KEY
        return None
    number = _size_number(text)
    if number is None:
        return None
    if number <= 39:
        return FEMALE_KEY
    if number >= 40:
        return MALE_KEY
    return None


def price_for_sizes(gender_costs: object, size_quantities: Mapping[object, object] | None) -> Decimal | None:
    costs = normalize_gender_costs(gender_costs)
    if not costs or not size_quantities:
        return None
    genders = {
        gender
        for size, quantity in size_quantities.items()
        if _decimal(quantity) not in (None, Decimal("0"))
        and (gender := gender_for_size(size)) is not None
    }
    if len(genders) != 1:
        return None
    return costs.get(next(iter(genders)))


def split_sizes_by_gender(size_quantities: Mapping[object, object]) -> dict[str, dict[str, Decimal]]:
    grouped: dict[str, dict[str, Decimal]] = {FEMALE_KEY: {}, MALE_KEY: {}}
    for size, quantity in size_quantities.items():
        decimal_quantity = _decimal(quantity)
        gender = gender_for_size(size)
        if decimal_quantity is None or decimal_quantity == 0 or gender is None:
            continue
        grouped[gender][str(size)] = decimal_quantity
    return {gender: values for gender, values in grouped.items() if values}
