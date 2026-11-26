"""Shared stock operating decisions and portfolio grouping."""
from collections import defaultdict
from math import ceil
import re

from domain.stock_alerts import code, launch_day

SEASONS = ("春", "夏", "秋", "冬")
UNKNOWN = "__unknown__"
_YEAR = re.compile(r"((?:20|21)[0-9]{2}|[0-9]{2})(?:\s*年)?(?:\s*[春夏秋冬]{1,2}季?款)?")


def style_year(value):
    match = _YEAR.fullmatch(str(value or "").strip())
    if not match:
        return ""
    year = match[1]
    return "20" + year if len(year) == 2 else year


def sale_seasons(value):
    value = str(value or "").strip()
    if value in {"四季", "四季款", "全年", "全年款", "全季", "全季款"}:
        return SEASONS
    if re.fullmatch(r"[春夏秋冬季款、/／+＋\s]+", value):
        return tuple(season for season in SEASONS if season in value)
    return (value,) if value and value != "0" else ()


def _portfolio_category(item):
    name = str(item.get("product_name") or "").strip()
    return name if name and name != "0" else UNKNOWN


def scope_matches(item, year="", season="", category=""):
    def match(value, options):
        return not value or (not options if value == UNKNOWN else value in options)

    year_value = style_year(item.get("year"))
    return (match(year, (year_value,) if year_value else ())
            and match(season, sale_seasons(item.get("season")))
            and (not category or category == _portfolio_category(item)))


def group_key(item):
    original = code(item.get("original_sku"))
    # A missing parent cannot silently merge with a different product's original code.
    return f"original:{original}" if original else f"product:{item['id']}"


def exit_window(plan, today):
    if not plan:
        return False, False
    exit_date = launch_day(plan["exit_date"])
    sale_start = launch_day(plan.get("sale_start"))
    next_season = bool(sale_start and today < sale_start <= exit_date)
    return next_season, not next_season and (exit_date - today).days <= plan["lead_days"]


def replenishment_block(item, policies, decisions, today):
    if decisions.get(item["id"], {}).get("confirmed"):
        return "商品组已确认清仓"
    season = str(item.get("season") or "").strip()
    plan = policies.get((style_year(item.get("year")), season))
    next_season, exiting = exit_window(plan, today)
    if exiting:
        return "已进入库存退出期"
    if next_season:
        return "未到再次开售日"
    return None


def portfolio_page(rows, *, year="", season="", category="", query="", status="", page=1, size=20):
    years, seasons, categories = set(), set(), set()
    groups = {}
    totals = defaultdict(int)
    received, net, covered = 0, 0, 0
    needle = query.strip().casefold()
    hits = set()
    if needle:
        hits = {group_key(row) for row in rows
                if any(needle in str(row.get(field) or "").casefold()
                       for field in ("sku", "original_sku", "product_name", "color"))}
    for row in rows:
        years.add(style_year(row.get("year")) or UNKNOWN)
        seasons.update(sale_seasons(row.get("season")) or (UNKNOWN,))
        categories.add(_portfolio_category(row))
        if not scope_matches(row, year, season, category):
            continue
        key = group_key(row)
        if needle and key not in hits:
            continue
        units = row["available_quantity"]
        tag = row["status"]
        totals[tag] += units
        if row.get("historic_received"):
            received += row["historic_received"]
            net += row["historic_net"]
            covered += 1
        if status and status != tag:
            continue
        group = groups.setdefault(key, {"product_id": row["id"], "sku": row["original_sku"] or row["sku"],
                                      "product_name": row["product_name"], "available_quantity": 0,
                                      "children": 0, "confirmed_clearance_quantity": 0, "statuses": set()})
        group["available_quantity"] += units
        group["children"] += 1
        group["statuses"].add(tag)
        if tag == "confirmed":
            group["confirmed_clearance_quantity"] += units
    total = len(groups)
    page = min(page, max(1, ceil(total / size)))
    items = sorted(groups.values(), key=lambda row: (-row["available_quantity"], row["sku"], row["product_id"]))
    result = items[(page-1)*size:page*size]
    for row in result:
        row["statuses"] = sorted(row["statuses"])
    return {"items": result, "total": total, "page": page, "page_size": size, "totals": dict(totals),
            "years": sorted(years - {UNKNOWN}, reverse=True) + ([UNKNOWN] if UNKNOWN in years else []),
            "seasons": sorted(seasons), "categories": sorted(categories),
            "sell_through": round(100 * net / received, 2) if received else None,
            "sell_through_covered": covered}

