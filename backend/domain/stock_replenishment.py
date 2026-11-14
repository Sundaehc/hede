"""Replenishment estimates. MOQ is a supplier total, never a per-style floor."""
from collections import defaultdict
from decimal import Decimal
from fractions import Fraction
from math import ceil


def _number(value):
    return Decimal(str(value or 0))


def _days(stock, demand):
    if demand <= 0:
        return None
    value = Fraction(max(_number(stock), Decimal(0))) / demand
    return str((Decimal(value.numerator) / value.denominator).quantize(Decimal("0.1")))


def evaluate_replenishment(item, rule, *, deduct_transit=False):
    issues = list(item["issues"])
    daily = Fraction(max(_number(item["net_sales"]), Decimal(0))) / item["observation_days"] if item["observation_days"] else Fraction(0)
    stock_days = _days(item["available_quantity"], daily) if not issues else None
    if not item["supplier"]:
        issues.append("商品档案未填写供应商")
    elif not rule:
        issues.append("请填写供应商交期、合计起订量及尺码配比")
    ratios = (rule or {}).get("size_ratios", {}).get(item["size_group"], {})
    size_names = [size["name"] for size in item["sizes"]]
    if not size_names:
        issues.append("商品尺码组缺失或没有尺码")
    elif rule and (set(ratios) != set(size_names) or not any(ratios.values())):
        issues.append("请补齐当前尺码组的配比（尺码组变动后需重新保存）")
    issues.extend(item["size_issues"])
    details, quantity = [], 0
    if not issues:
        ratio_total = sum(ratios.values())
        for name in size_names:
            demand = daily * ratios[name] / ratio_total
            available = max(_number(item["stock_by_size"].get(name)), Decimal(0))
            transit = max(_number(item["transit_by_size"].get(name)), Decimal(0))
            inventory = available + (transit if deduct_transit else Decimal(0))
            shortage = max(demand * (rule["lead_days"] + rule["cover_days"]) - Fraction(inventory), Fraction(0))
            suggested = ceil(shortage)
            quantity += suggested
            # In-transit has no ETA: current-stock risk must not disappear when it is deducted.
            at_risk = demand > 0 and Fraction(available) <= demand * rule["lead_days"]
            details.append({"name": name, "ratio": ratios[name], "available_quantity": str(available),
                            "purchase_in_transit": str(transit), "daily_demand": str((Decimal(demand.numerator) / demand.denominator).quantize(Decimal("0.01"))),
                            "stock_days": _days(available, demand), "at_risk": at_risk, "suggested_quantity": suggested})
    return {**item, "daily_sales": str((Decimal(daily.numerator) / daily.denominator).quantize(Decimal("0.01"))) if not item["issues"] else None,
            "stock_days": stock_days, "suggested_quantity": quantity if not issues else None,
            "size_details": details, "pending_reasons": list(dict.fromkeys(issues)),
            "lead_days": rule["lead_days"] if rule else None, "cover_days": rule["cover_days"] if rule else None}


def select_replenishment(facts, rules, *, supplier="", query="", status="suggested", page=1, page_size=25, deduct_transit=False):
    # Evaluate the whole brand before filters/pagination so a supplier's MOQ is stable.
    evaluated = [evaluate_replenishment(item, rules.get(item["supplier"]), deduct_transit=deduct_transit) for item in facts["items"]]
    supplier_totals = defaultdict(lambda: {"suggested_quantity": 0, "pending_products": 0, "suggested_products": 0})
    for item in evaluated:
        if not item["supplier"]:
            continue
        total = supplier_totals[item["supplier"]]
        total["pending_products"] += bool(item["pending_reasons"])
        total["suggested_quantity"] += item["suggested_quantity"] or 0
        total["suggested_products"] += (item["suggested_quantity"] or 0) > 0
    summaries = []
    for name, total in sorted(supplier_totals.items()):
        minimum = rules.get(name, {}).get("min_order_qty")
        gap = max(0, minimum - total["suggested_quantity"]) if minimum is not None else None
        summaries.append({"supplier": name, **total, "min_order_qty": minimum, "moq_gap": gap,
                          "meets_moq": gap == 0 if minimum is not None else None})
    lookup = {item["supplier"]: item for item in summaries}
    counts, filtered, total_quantity = {"suggested": 0, "pending": 0, "all": 0}, [], 0
    needle = query.strip().casefold()
    for item in evaluated:
        if supplier and item["supplier"] != supplier:
            continue
        if needle and not any(needle in str(item.get(field) or "").casefold() for field in ("sku", "original_sku", "product_name", "color", "supplier")):
            continue
        flags = {"suggested": (item["suggested_quantity"] or 0) > 0, "pending": bool(item["pending_reasons"]), "all": True}
        for key, flag in flags.items():
            counts[key] += int(flag)
        total_quantity += item["suggested_quantity"] or 0
        if flags[status]:
            filtered.append({**item, "supplier_summary": lookup.get(item["supplier"])})
    filtered.sort(key=lambda item: (-(item["suggested_quantity"] or 0), item["sku"], item["id"]))
    total = len(filtered)
    page = min(page, max(1, (total + page_size - 1) // page_size))
    return {**{key: value for key, value in facts.items() if key != "items"},
            "items": filtered[(page - 1) * page_size:page * page_size], "total": total, "page": page, "page_size": page_size,
            "counts": counts, "suggested_quantity": total_quantity,
            "supplier_summaries": [item for item in summaries if not supplier or item["supplier"] == supplier]}
