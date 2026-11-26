"""Inventory planning calculations; quantities remain in pairs."""
from collections import Counter
from datetime import timedelta
from decimal import Decimal, ROUND_CEILING
from fractions import Fraction
import re

from domain.stock_portfolio import SEASONS, sale_seasons

MIN_SIZE_SAMPLE = 20
MIN_SIZE_COVERAGE = Fraction(4, 5)


def allocation_seasons(value):
    seasons = sale_seasons(value)
    if not seasons:
        return ("",)
    if all(season in SEASONS for season in seasons):
        return tuple(dict.fromkeys(("".join(seasons), *seasons)))
    return seasons


def allocation_heel(rear_height, height, category):
    rear_height = str(rear_height or "").strip()
    for value in (rear_height, category or ""):
        match = re.search(r"超高跟|高跟|中跟|低跟|平跟", value)
        if match:
            return match[0]
    for value in (height, rear_height):
        value = str(value or "").strip()
        match = re.fullmatch(r"(?:约\s*)?([0-9]+(?:\.[0-9]+)?)\s*(cm|mm|厘米|毫米)?", value, re.IGNORECASE)
        if match:
            measured = Decimal(match[1])
            unit = (match[2] or "").lower()
            if measured > 0:
                cm = measured / 10 if unit in {"mm", "毫米"} else measured
                return f"{cm.normalize():f} cm"
    return ""


def choose_weights(sizes, sales, known_volume, sales_volume, covered, baseline):
    usable = {size: max(0, sales.get(size, 0)) for size in sizes}
    matched = sum(usable.values())
    if covered and matched >= MIN_SIZE_SAMPLE and sales_volume > 0 and known_volume >= sales_volume * MIN_SIZE_COVERAGE:
        return usable, "same_product"
    if baseline and set(baseline) == set(sizes) and any(baseline.values()):
        return baseline, "category"
    return {}, "manual"


def allocate(sizes, weights, on_hand, total):
    """Add pairs to the most underrepresented sizes without moving existing stock."""
    target = {size: 0 for size in sizes}
    usable = {size: Fraction(weights.get(size, 0)) for size in sizes if weights.get(size, 0) > 0}
    if not usable:
        return None
    # Find the weighted target level with current stock as a lower bound.
    # Removing already-overstocked (including zero-weight) sizes avoids negative buys.
    remaining = set(usable)
    while remaining:
        level = Fraction(total + sum(max(0, on_hand.get(size, 0)) for size in remaining)) / sum(usable[size] for size in remaining)
        overstocked = {size for size in remaining if level * usable[size] < max(0, on_hand.get(size, 0))}
        if not overstocked:
            break
        remaining -= overstocked
    ideal = {size: level * usable[size] - max(0, on_hand.get(size, 0)) for size in remaining}
    for size, quantity in ideal.items():
        target[size] = int(quantity)
    ranked = sorted((size for size in sizes if size in ideal), key=lambda size: -(ideal[size] - target[size]))
    for size in ranked[:total - sum(target.values())]:
        target[size] += 1
    return target


def reliable_transit(sizes, confirmations, source_transit, today, need_by):
    """Confirmations are a dated subset of the ERP in-transit figure, never extra inventory."""
    eligible = Counter()
    for row in confirmations:
        if row["credible"] and today <= row["eta"] <= need_by:
            for size, quantity in row["sizes"].items():
                eligible[size] += quantity
    return {size: min(eligible[size], max(0, source_transit.get(size, 0))) for size in sizes}


def forecast(net_sales, observed_days, today, need_by, campaign=None):
    if net_sales is None or not observed_days:
        return {"normal": None, "campaign": None, "days": None, "campaign_days": 0}
    days = (need_by - today).days + 1
    overlap = 0
    factor = Decimal(1)
    if campaign:
        start, end = max(today, campaign["start_date"]), min(need_by, campaign["end_date"])
        overlap = max(0, (end - start).days + 1)
        factor = Decimal(campaign["factor"])
    daily = Decimal(max(0, net_sales)) / observed_days
    def demand(n):
        return int((daily * n).to_integral_value(rounding=ROUND_CEILING))
    return {"normal": demand(days), "campaign": demand(days - overlap + overlap * factor) if campaign else None,
            "days": days, "campaign_days": overlap}


def arrival_status(today, due, ordered, received, has_receipt_source):
    if has_receipt_source and ordered > 0 and received >= ordered:
        return "received"
    if due is None:
        return "unknown"
    if due < today:
        return "overdue"
    if due <= today + timedelta(days=2):
        return "due_soon"
    return "scheduled"

