"""Quarterly launch cohorts. Unknown data is never interpreted as zero sales."""
from datetime import date, timedelta
from decimal import Decimal


def quarter_bounds(year, quarter):
    start = date(year, (quarter - 1) * 3 + 1, 1)
    end = date(year + 1, 1, 1) if quarter == 4 else date(year, quarter * 3 + 1, 1)
    return start, end


def _ratio(numerator, denominator):
    return round(float(Decimal(numerator) * 100 / Decimal(denominator)), 2) if denominator > 0 else None


def _summary(products, quarter, cutoff, coverage, brand_gross, purchase_ready):
    # New launches after the sales cutoff still count as seasonal products,
    # but have no sales observation window in this historical total.
    sales_products = [p for p in products if cutoff and p["launch_date"] <= cutoff.isoformat()]
    complete = cutoff is not None and coverage and all(p["sales_complete"] for p in sales_products)
    sell_through_complete = complete and all(p["sales_complete"] for p in products)
    received = sum(Decimal(p["received"][quarter - 1]) for p in products)
    inbound = sum(Decimal(p["inbound"][quarter - 1]) for p in products)
    net = sum(p["net"] for p in sales_products)
    gross = sum(p["gross"] for p in sales_products)
    return {
        "product_count": len(products), "gross_sales": gross if complete else None,
        "net_sales": net if complete else None,
        "sales_share": _ratio(gross, brand_gross) if complete else None,
        "inbound_quantity": str(inbound) if purchase_ready and cutoff else None,
        "received_quantity": str(received) if purchase_ready and cutoff else None,
        "sell_through_rate": _ratio(net, received) if sell_through_complete and purchase_ready and all(Decimal(p["received"][quarter-1]) > 0 for p in products) else None,
        "single_order_count": sum(p["order_state"] == "single" for p in products),
        "multiple_order_count": sum(p["order_state"] == "multiple" for p in products),
        "unknown_order_count": sum(p["order_state"] == "unknown" for p in products),
    }


def analyze_quarter(facts, *, year, quarter, season="", query="", status="all", page=1, page_size=25):
    end_source = date.fromisoformat(facts["sales_end"]) if facts["sales_end"] else None
    business_day = date.fromisoformat(facts["business_date"])
    observation_end = business_day - timedelta(days=1)
    markers = {date.fromisoformat(day) for day in facts["sales_dates"]}
    sales = facts["sales"]
    needle = query.strip().casefold()
    def matches(product):
        return (not season or product["season"] == season) and (not needle or any(
            needle in str(product.get(field) or "").casefold()
            for field in ("sku", "original_sku", "product_name", "color")))

    filtered = [p for p in facts["products"] if matches(p)]
    period_start, period_exclusive_end = quarter_bounds(year, quarter)
    period_end = min(end_source, period_exclusive_end-timedelta(days=1)) if end_source and end_source >= period_start else None
    period_complete = bool(period_end) and all(period_start+timedelta(days=n) in markers for n in range((period_end-period_start).days+1))
    summaries, selected, activity, trend = [], [], [], []
    for q in range(1, 5):
        start, exclusive_end = quarter_bounds(year, q)
        cutoff = min(end_source, exclusive_end - timedelta(days=1)) if end_source and end_source >= start else None
        expected = set(start + timedelta(days=n) for n in range((cutoff - start).days + 1)) if cutoff else set()
        missing = sorted(expected - markers)
        products = []
        for source in filtered:
            launch = date.fromisoformat(source["launch_date"])
            if not start <= launch < exclusive_end or launch > observation_end:
                continue
            item = dict(source)
            entries = sales.get(str(item["id"]), [])
            entries = [(date.fromisoformat(day), gross, net) for day, gross, net in entries if cutoff and launch.isoformat() <= day <= cutoff.isoformat()]
            gross, net = sum(e[1] for e in entries), sum(e[2] for e in entries)
            own_missing = sum(launch <= day <= cutoff for day in missing) if cutoff else 0
            sales_ready = bool(cutoff and cutoff >= launch)
            orders = item["orders"][q - 1]
            item.update(gross=gross, net=net, listed_days=max(0, (cutoff-launch).days+1) if cutoff else 0,
                        order_state=("unknown" if not facts["purchase_ready"] or item["unknown_orders"][q-1] or not orders
                                     else "single" if len(orders) == 1 else "multiple"),
                        sales_complete=sales_ready and not own_missing and not item.get("sales_ambiguous"), pending_reasons=[])
            if not sales_ready:
                item["pending_reasons"].append("日销尚未覆盖上市日期")
            if item.get("sales_ambiguous"):
                item["pending_reasons"].append("重复货号导致销售无法唯一关联")
            if own_missing:
                item["pending_reasons"].append(f"上市后日销缺少 {own_missing} 天")
            if not facts["purchase_ready"]:
                item["pending_reasons"].append("缺少采购入库参考数据")
            elif Decimal(item["received"][q-1]) <= 0:
                item["pending_reasons"].append("缺少有效采购入库参考量")
            if item["order_state"] == "unknown":
                item["pending_reasons"].append("采购单号不完整，无法判断是否补货")
            products.append(item)
        summary = _summary(products, q, cutoff, bool(cutoff) and not missing,
                           sum(row[1] for row in facts["brand_sales"] if start.isoformat() <= row[0] <= (cutoff.isoformat() if cutoff else "")),
                           facts["purchase_ready"])
        cross_period_products = [p for p in filtered if date.fromisoformat(p["launch_date"]) >= start
                                 and date.fromisoformat(p["launch_date"]) < exclusive_end
                                 and period_end and p["launch_date"] <= period_end.isoformat()]
        period_net = sum(net for p in cross_period_products for day, _, net in sales.get(str(p["id"]), [])
                         if max(period_start.isoformat(), p["launch_date"]) <= day <= period_end.isoformat())
        summary["period_net_sales"] = period_net if period_complete and not any(p.get("sales_ambiguous") for p in cross_period_products) else None
        summary.update(quarter=q, cutoff=cutoff.isoformat() if cutoff else None, missing_days=len(missing),
                       state="not_started" if not cutoff else "incomplete" if missing else "available")
        summaries.append(summary)
        if q != quarter:
            continue
        selected = products
        for days in (3, 7, 15):
            eligible = [p for p in products if end_source and (end_source-date.fromisoformat(p["launch_date"])).days+1 >= days]
            valid, active = 0, 0
            for p in eligible:
                launch = date.fromisoformat(p["launch_date"])
                finish = launch + timedelta(days=days-1)
                if p.get("sales_ambiguous") or any(launch+timedelta(days=n) not in markers for n in range(days)):
                    continue
                valid += 1
                active += any(launch.isoformat() <= day <= finish.isoformat() and gross > 0
                              for day, gross, _ in sales.get(str(p["id"]), []))
            activity.append({"days": days, "eligible": len(eligible), "valid": valid, "active": active,
                             "pending": len(eligible)-valid, "immature": len(products)-len(eligible),
                             "rate": _ratio(active, valid)})
        daily = {day.isoformat(): [0, 0] for day in sorted(expected)}
        for p in products:
            for day, gross, net in sales.get(str(p["id"]), []):
                if day in daily and day >= p["launch_date"]:
                    daily[day][0] += gross
                    daily[day][1] += net
        ambiguous_sales = any(p.get("sales_ambiguous") for p in products if cutoff and p["launch_date"] <= cutoff.isoformat())
        trend = [{"date": day, "gross": None if date.fromisoformat(day) in missing or ambiguous_sales else values[0],
                  "net": None if date.fromisoformat(day) in missing or ambiguous_sales else values[1]} for day, values in daily.items()]
    groups = []
    for state in ("single", "multiple", "unknown"):
        members = [p for p in selected if p["order_state"] == state]
        groups.append({"order_state": state, **_summary(members, quarter,
            date.fromisoformat(summaries[quarter-1]["cutoff"]) if summaries[quarter-1]["cutoff"] else None,
            summaries[quarter-1]["state"] == "available", 0, facts["purchase_ready"])})
    selected.sort(key=lambda p: (-p["net"], p["sku"], p["id"]))
    evidence = facts.get("zero_sales_evidence", {})
    confirmed_candidates = set(facts.get("zero_candidates", ()))
    zero_rows = [p for p in selected if p["id"] in confirmed_candidates and p["sales_complete"]
                 and p["gross"] == 0 and str(p["id"]) not in evidence]
    arrivals = [p for p in facts.get("arrivals", ()) if matches(p)
                and period_start.isoformat() <= p["first_inbound_date"] < period_exclusive_end.isoformat()]
    arrivals.sort(key=lambda p: (-date.fromisoformat(p["first_inbound_date"]).toordinal(), p["sku"], p["id"]))
    lists = {"all": selected, "single": [p for p in selected if p["order_state"] == "single"],
             "pending": [p for p in selected if p["pending_reasons"]], "zero": zero_rows, "arrivals": arrivals}
    counts = {key: len(values) for key, values in lists.items()}
    rows = lists[status]
    total = len(rows)
    page = min(page, max(1, (total + page_size - 1) // page_size))
    items = []
    for p in rows[(page-1)*page_size:page*page_size]:
        if status == "arrivals":
            items.append({**p, "launch_date": None, "listed_days": None, "order_state": "unknown",
                          "pending_reasons": ["上市日期无效" if p["invalid_launch"] else "档案未填上市日期"],
                          "inbound_dates": [p["first_inbound_date"]],
                          "gross_sales": None, "net_sales": None, "received_quantity": None,
                          "inbound_quantity": None, "sell_through_rate": None})
            continue
        received = Decimal(p["received"][quarter-1])
        items.append({key: p.get(key) for key in ("id", "sku", "original_sku", "product_name", "color", "season", "launch_date",
                      "listed_days", "available_quantity", "order_state", "pending_reasons")} | {
            "gross_sales": p["gross"] if p["sales_complete"] else None,
            "net_sales": p["net"] if p["sales_complete"] else None,
            "received_quantity": str(received) if facts["purchase_ready"] else None,
            "inbound_quantity": p["inbound"][quarter-1] if facts["purchase_ready"] else None,
            "inbound_dates": p.get("inbound_dates", [[], [], [], []])[quarter-1] if facts["purchase_ready"] else [],
            "sell_through_rate": _ratio(p["net"], received) if p["sales_complete"] and facts["purchase_ready"] else None,
        })
    return {
        "year": year, "quarter": quarter, "summary": summaries[quarter-1], "quarters": summaries, "activity": activity,
        "followup_ready": {"arrivals": bool(facts["stock_date"] and facts["purchase_ready"]),
                           "zero": bool(facts.get("zero_checked") and period_end and period_end.isoformat() in facts["sales_dates"])},
        "trend": trend, "order_groups": groups, "items": items, "total": total, "page": page, "page_size": page_size, "counts": counts,
        **{key: facts[key] for key in ("sales_end", "stock_date", "seasons", "years", "source_issues", "missing_launch_count",
                                     "unmatched_stock_rows", "unmatched_purchase_rows", "purchase_ready")},
    }
