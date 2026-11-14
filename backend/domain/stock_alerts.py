"""Stock alert decisions, with explicit data gaps and scoped rules."""
from collections import defaultdict
from datetime import date, datetime
from decimal import Decimal
import re

from domain.product_defaults import apply_product_defaults
from domain.product_size_code import build_product_size_code

DEFAULT_RULES = {"zero": {"age_days": 15, "rate": "20"}, "slow": {"age_days": 60, "rate": "20"}}


def code(value):
    return str(value or "").strip().upper()


def launch_day(value):
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    match = re.fullmatch(r"(\d{4})[-/.年](\d{1,2})[-/.月](\d{1,2})(?:日)?(?:[ T].*)?", str(value or "").strip())
    try:
        return date(*map(int, match.groups())) if match else None
    except ValueError:
        return None


class ArchiveMatcher:
    def __init__(self, products, sizes):
        self.products, self.aliases, self.prefixes = {}, defaultdict(set), defaultdict(list)
        self.short_prefixes, self.sizes = [], sizes
        for source in products:
            item = dict(source)
            apply_product_defaults(item["brand"], item)
            key, sku = (item["brand"], item["id"]), code(item.get("sku"))
            if not sku:
                continue
            base = code(build_product_size_code(sku, item.get("color_code"), "", item.get("barcode_build_rule")))
            item["barcode_base"] = base
            self.products[key] = item
            for alias in {sku, base, code(item.get("original_sku"))} - {""}:
                self.aliases[alias].add(key)
            entry = (base, key, str(item.get("size_range") or ""))
            (self.short_prefixes if len(base) < 4 else self.prefixes[base[:4]]).append(entry)

    def resolve(self, product_code, *styles):
        value = code(product_code)
        matches = set(self.aliases.get(value, ()))
        if not matches:
            for base, key, group in (*self.prefixes.get(value[:4], ()), *self.short_prefixes):
                if value.startswith(base) and value[len(base):] in self.sizes.get(group, set()):
                    matches.add(key)
        if matches:
            return next(iter(matches)) if len(matches) == 1 else None
        for style in styles:
            matches = self.aliases.get(code(style), set())
            if matches:
                return next(iter(matches)) if len(matches) == 1 else None
        return None

    def source_codes(self, keys):
        result = set()
        for key in keys:
            item = self.products[key]
            for alias in (code(item["sku"]), item["barcode_base"], code(item.get("original_sku"))):
                if self.aliases.get(alias) == {key}:
                    result.add(alias)
            result.update(item["barcode_base"] + size for size in self.sizes.get(str(item.get("size_range") or ""), ()))
        return sorted(result)


def resolve_rule(rules, kind, season):
    exact = rules.get((kind, season))
    inherited = rules.get((kind, "")) if season else None
    effective = exact or inherited or DEFAULT_RULES[kind]
    return {"age_days": effective["age_days"], "rate": str(effective["rate"]),
            "version": exact["version"] if exact else 0,
            "source": "season" if exact and season else "brand" if exact or inherited else "default"}


def evaluate_alert(item, kind, rule):
    age = item["listed_days"]
    reasons = list(item["sales_issues"])
    received = Decimal(item["purchase_received_reference"])
    if kind == "slow" and age is not None and age >= rule["age_days"]:
        reasons.extend(item.get("inbound_issues", []))
        if received <= 0:
            reasons.append("缺少有效采购入库数量，无法计算售罄率")
    qualifies = not reasons and age is not None and age >= rule["age_days"]
    if kind == "zero":
        qualifies = qualifies and Decimal(item["gross_sales"]) == 0
    else:
        qualifies = qualifies and received > 0 and Decimal(item["net_sales"]) * 100 < Decimal(rule["rate"]) * received
    return {**item, "warning": bool(qualifies), "pending_reasons": reasons,
            "rule_age_days": rule["age_days"], "rule_rate": rule["rate"], "rule_source": rule["source"]}


def select_alerts(facts, *, rules, kind, status, season, query, page, page_size):
    needle = query.strip().casefold()
    rows, counts, warning_stock, checked = [], {"warning": 0, "pending": 0}, Decimal(0), 0
    for source in facts["items"]:
        if Decimal(source["available_quantity"]) <= 0 or (season and source["season"] != season):
            continue
        if needle and not any(needle in str(source.get(field) or "").casefold() for field in ("sku", "original_sku", "product_name", "color")):
            continue
        checked += 1
        item = evaluate_alert(source, kind, resolve_rule(rules, kind, source["season"] or ""))
        flags = {"warning": item["warning"], "pending": bool(item["pending_reasons"])}
        for key, value in flags.items():
            counts[key] += int(value)
        if item["warning"]:
            warning_stock += Decimal(item["available_quantity"])
        if flags[status]:
            rows.append(item)
    rows.sort(key=lambda item: (-Decimal(item["available_quantity"]), item["sku"], item["id"]))
    total = len(rows)
    page = min(page, max(1, (total + page_size - 1) // page_size))
    return {**{key: value for key, value in facts.items() if key != "items"},
            "items": rows[(page - 1) * page_size:page * page_size], "total": total, "page": page, "page_size": page_size,
            "counts": counts, "warning_stock": str(warning_stock), "stock_products": checked,
            "rule": resolve_rule(rules, kind, season)}
