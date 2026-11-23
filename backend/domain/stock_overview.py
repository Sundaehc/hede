from collections import Counter, defaultdict
from datetime import timedelta
from fractions import Fraction
from math import ceil, floor
import re

from domain.stock_alerts import evaluate_alert, launch_day, resolve_rule
from domain.stock_replenishment import evaluate_replenishment

PRIORITY = {"clearance": 1, "zero": 2, "replenish": 3, "slow": 4, "review": 5}
BUCKETS = ("selling", "next_season", "size_imbalance", "clearance", "watch", "review")


def _units(value):
    return int(value or 0)


# Archive labels include 26年冬季款 and 2026冬季款; exit policy keys use a four-digit year.
_STYLE_YEAR = re.compile(r"((?:20|21)[0-9]{2}|[0-9]{2})(?:\s*年)?(?:\s*[春夏秋冬]{1,2}季?款)?")


def _scope(item):
    match = _STYLE_YEAR.fullmatch(str(item.get("year") or "").strip())
    year = match[1] if match else ""
    if len(year) == 2:
        year = "20" + year
    season = str(item.get("season") or "").strip()
    return year, season if season != "0" else ""


def _recent(item, facts, window, channel):
    return item[f"{channel}_{window}"] if facts.get("window_complete", {}).get(str(window)) and not item["ambiguous_sales"] else None


def _clearance(item, history, plan, today, recent, replenish_names):
    if not plan:
        return None, None
    exit_date = launch_day(plan["exit_date"])
    remaining_days = (exit_date - today).days
    if remaining_days > plan["lead_days"]:
        return None, None
    if any(recent[f"regular_{window}"] is None for window in (7, 30)):
        return None, "缺少完整近销，无法估计退出前可消化数量"
    if item["size_issues"] or item["negative_sizes"] or not item["sizes"] or not item.get("launch_date"):
        return None, "上市时间或尺码库存待核对，暂不计算清货量"
    current = _units(item["available_quantity"])
    if plan["target_rate"] == 100:
        gap = current  # All remaining sellable stock must exit; lifetime receipts are not required.
    else:
        if not history or history["sales_issues"] or history["inbound_issues"] or not _units(history["purchase_received_reference"]):
            return None, "累计入库或销售覆盖不足，不能按目标售罄率计算清货量"
        received = _units(history["purchase_received_reference"])
        gap = min(current, max(0, ceil(Fraction(received * plan["target_rate"], 100)) - _units(history["net_sales"])))
    regular = max(Fraction(0), min(Fraction(recent["regular_7"], 7), Fraction(recent["regular_30"], 30)))
    forecast = floor(regular * max(0, remaining_days))
    extra = max(0, gap - forecast)
    if not extra:
        return None, None
    # Preserve enough stock for the projected normal sales, and never propose clearing a size being replenished.
    stock = {size["name"]: _units(item["stock_by_size"].get(size["name"])) for size in item["sizes"]}
    ratios = item.get("ratios", {})
    if forecast and (not ratios or set(stock) != set(ratios) or not sum(ratios.values())):
        return None, "未配置完整尺码配比，无法估计应为正常销售保留哪些尺码"
    reserved = {name: ceil(Fraction(forecast * ratios[name], sum(ratios.values()))) if forecast else 0 for name in stock}
    sizes = []
    for name in sorted(stock, key=lambda key: (ratios.get(key, 0), -stock[key], key)):
        quantity = min(extra, max(0, stock[name] - reserved[name]))
        if name not in replenish_names and quantity > 0:
            sizes.append({"name": name, "available": stock[name], "quantity": quantity})
            extra -= quantity
    if not sizes:
        return None, "需退出的数量与尺码保留或补货建议冲突，请人工分配"
    return {"kind": "clearance", "reason": f"计划 {exit_date.isoformat()} 退出；达标缺口 {gap} 双，预计正常净销 {forecast} 双"
            + (f"；另有 {extra} 双需人工核对" if extra else ""), "quantity": sum(s["quantity"] for s in sizes),
            "sizes": sizes, "due_date": max(today, exit_date).isoformat(), "channel": plan["channel"],
            "target_rate": plan["target_rate"], "plan_version": plan["version"]}, None


def build_overview(facts, alerts, alert_rules, supplier_rules, plans, today):
    stock_date, sales_end = launch_day(facts.get("stock_date")), launch_day(facts.get("sales_end"))
    aligned = bool(stock_date == today and sales_end == today - timedelta(days=1))
    same_sources = facts.get("stock_date") == alerts.get("stock_date") and facts.get("sales_end") == alerts.get("sales_end")
    history = {item["id"]: item for item in alerts["items"]} if same_sources else {}
    available, counts = Counter(), Counter()
    totals = defaultdict(int)
    ambiguous = any(item["ambiguous_sales"] for item in facts["items"])
    full_stock_scope = all(item["seen"] and _units(item["available_quantity"]) >= 0 for item in facts["items"])
    metrics = [(f"{channel}_{window}", window, channel) for window in (7, 30) for channel in ("regular", "clearance")]
    covered_sales = {key: facts.get("window_complete", {}).get(str(window)) and not ambiguous for key, window, _ in metrics}
    recommendations = []
    scopes = set()
    for item in facts["items"]:
        current = _units(item["available_quantity"])
        recent = {key: _recent(item, facts, window, channel) for key, window, channel in metrics}
        for key, value in recent.items():
            totals[key] += value or 0
        year, season = _scope(item)
        if year and season:
            scopes.add((year, season))
        plan = plans.get((year, season))
        prior = history.get(item["id"])
        issues = []
        actions = []
        common = {key: item.get(key) for key in ("id", "brand", "sku", "original_sku", "product_name", "color", "season", "year", "upper_material", "launch_date")}
        common.update(available_quantity=current, **recent,
                      first_inbound_date=prior.get("first_inbound_date") if prior else None,
                      last_inbound_date=prior.get("last_inbound_date") if prior else None,
                      sell_through_rate=prior.get("sell_through_rate") if prior and not prior["sales_issues"] else None,
                      exit_date=launch_day(plan["exit_date"]).isoformat() if plan else None,
                      stock_date=facts.get("stock_date"), sales_end=facts.get("sales_end"))
        if not aligned:
            issues.append("库存须更新至今日、日销须覆盖至昨日")
        issues.extend(item["issues"])
        issues.extend(item["size_issues"])
        if item["negative_sizes"] or current < 0:
            issues.append("出现负可售库存，先核对库存")
        if current > 0 and not item.get("launch_date"):
            issues.append("有可售库存，但档案上市日期待核对")
        if current > 0 and not same_sources:
            issues.append("生命周期历史与当前快照尚未对齐")
        if current > 0 and any(recent[f"regular_{window}"] is None for window in (7, 30)):
            issues.append("近 7 ／ 30 天非清仓有日销缺口或货号歧义")
        stock_usable = aligned and item["seen"] and not item["issues"] and not item["negative_sizes"] and current >= 0
        supplier = supplier_rules.get(item["supplier"])
        ratios = (supplier or {}).get("size_ratios", {}).get(item["size_group"], {})
        peak = max(ratios.values(), default=0)
        core = {name for name, weight in ratios.items() if weight == peak and peak > 0}
        next_start = launch_day(plan.get("sale_start")) if plan else None
        next_season = bool(next_start and today < next_start <= launch_day(plan["exit_date"]))
        live_performance = (recent["regular_7"] or 0) > 0 and (recent["regular_30"] or 0) > 0
        replenishment = []
        if stock_usable and live_performance and item.get("launch_date") and not next_season and core and supplier:
            # Use normal-channel demand so clearance sales cannot drive replenishment.
            listed_days = (sales_end - launch_day(item["launch_date"])).days + 1 if item.get("launch_date") else 0
            fact = {**item, "net_sales": recent["regular_30"], "observation_days": min(30, max(0, listed_days))}
            computed = evaluate_replenishment(fact, supplier)
            replenishment = [{"name": size["name"], "available": _units(size["available_quantity"]), "quantity": size["suggested_quantity"]}
                for size in computed["size_details"] if size["name"] in core and size["name"] in item["explicit_sizes"]
                and size["at_risk"] and size["suggested_quantity"] > 0]
        if stock_usable and current > 0 and prior:
            for kind in ("zero", "slow"):
                candidate = evaluate_alert(prior, kind, resolve_rule(alert_rules, kind, season))
                if not candidate["warning"]:
                    continue
                if kind == "zero":
                    if not prior.get("zero_confirmed"):
                        issues.append("渠道汇总无销量，未通过原始日销的零动销确认")
                        break
                    reason = f"档案上市满 {candidate['rule_age_days']} 天未见销售；核对渠道上架、曝光和核心尺码"
                elif live_performance or next_season or recent["regular_7"] is None or recent["regular_30"] is None:
                    continue
                else:
                    reason = f"参考售罄率低于 {candidate['rule_rate']}%，且近期非清仓净销未同时为正；复核是否需退出"
                actions.append({"kind": kind, "reason": reason, "quantity": None, "sizes": [],
                                "due_date": (today + timedelta(days=2 if kind == 'zero' else 5)).isoformat(), "channel": None,
                                "rule_age_days": candidate["rule_age_days"], "rule_rate": candidate["rule_rate"]})
                break
        if stock_usable and (current > 0 or replenishment):
            exiting = bool(plan and not next_season and (launch_day(plan["exit_date"]) - today).days <= plan["lead_days"])
            if exiting and current > 0:
                # An exit policy takes precedence over placing new orders for the same style.
                clearance, issue = _clearance({**item, "ratios": ratios}, prior, plan, today, recent,
                                              {size["name"] for size in replenishment})
                if clearance:
                    actions.append(clearance)
                if issue:
                    issues.append(issue)
                if clearance:
                    actions = [action for action in actions if action["kind"] != "slow"]
            elif actions and actions[0]["kind"] == "slow" and not plan:
                issues.append("尚未配置该年份和季节的退出规则")
        else:
            exiting = False
        if replenishment and exiting:
            issues.append("已进入退出处理期且核心尺码偏紧，请复核保留量；不继续推荐补货")
        if replenishment and not exiting:
            actions.append({"kind": "replenish", "reason": "核心尺码现货不足以覆盖交期，建议按供应商配比复核补码",
                            "quantity": sum(size["quantity"] for size in replenishment), "sizes": replenishment,
                            "due_date": today.isoformat(), "channel": None})
        kinds = {action["kind"] for action in actions}
        low_sizes = {size["name"] for size in replenishment}
        other_stock = sum(max(0, _units(value)) for name, value in item["stock_by_size"].items() if name not in core)
        if current > 0:
            bucket = ("review" if not stock_usable else "clearance" if "clearance" in kinds else
                      "next_season" if next_season else "size_imbalance" if low_sizes and other_stock else
                      "review" if issues and not actions else "selling" if live_performance and not actions else "watch")
            available[bucket] += current
            counts[bucket] += 1
        if issues and (current != 0 or recent["regular_30"] or recent["clearance_30"] or actions):
            actions.append({"kind": "review", "reason": "；".join(dict.fromkeys(issues)), "quantity": None, "sizes": [], "due_date": None, "channel": None})
        for action in actions:
            size_names = {size["name"] for size in action["sizes"]}
            size_inventory = [{"name": size["name"], "available": _units(item["stock_by_size"].get(size["name"])) if size["name"] in item["explicit_sizes"] else None,
                               "core": size["name"] in core, "in_action": size["name"] in size_names} for size in item["sizes"]]
            recommendations.append({**common, **action, "size_inventory": size_inventory})
    recommendations.sort(key=lambda row: (PRIORITY[row["kind"]], row["due_date"] or "9999", -(row["quantity"] or max(row["available_quantity"], 0)), row["sku"], row["id"]))
    stock = sum(available.values()) if stock_date else None
    sales = {key: totals[key] if valid else None for key, valid in covered_sales.items()}
    sales["total_30"] = sales["regular_30"] + sales["clearance_30"] if sales["regular_30"] is not None else None
    sales["coverage_days"] = (round(stock * 30 / sales["total_30"], 1)
        if aligned and full_stock_scope and stock is not None and sales["total_30"] and sales["total_30"] > 0 else None)
    return {"recommendations": recommendations, "inventory": {"available": stock,
            "buckets": [{"key": key, "units": available[key], "styles": counts[key]} for key in BUCKETS] if stock is not None else [], **sales},
            "scopes": [{"year": year, "season": season} for year, season in sorted(scopes | set(plans), reverse=True)],
            "sources": {"stock_date": facts.get("stock_date"), "sales_end": facts.get("sales_end"), "aligned": aligned,
                        "history_aligned": same_sources, "scope_complete": bool(stock_date and full_stock_scope),
                        "unmatched_stock_rows": facts.get("unmatched_stock_rows", 0)}}
