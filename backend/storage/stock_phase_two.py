"""On-demand phase two sources and preparation records."""
from collections import defaultdict
from datetime import timedelta
from decimal import Decimal
import re

from sqlalchemy import BigInteger, CheckConstraint, Column, Date, DateTime, Index, JSON, Numeric, Table, Text, func, inspect, select, text
from sqlalchemy.dialects.postgresql import insert

from domain.factory_channel_sales import is_clearance_channel, platform_name, shop_channel_key
from domain.stock_alerts import ArchiveMatcher, code, launch_day
from domain.stock_phase_two import allocation_heel, allocation_seasons, arrival_status, choose_weights
from domain.stock_portfolio import group_key
from storage.seasonal_analysis_facts import _indexed_sales_codes
from storage.stock_alert_facts import _sales_dates
from storage.stock_operating_rules import META
from storage.stock_replenishment_facts import _catalog

BASELINES = Table("stock_size_baselines", META,
    Column("brand", Text, primary_key=True), Column("category", Text, primary_key=True),
    Column("size_group", Text, primary_key=True), Column("weights", JSON, nullable=False),
    Column("updated_by", BigInteger, nullable=False), Column("updated_at", DateTime(timezone=True), nullable=False, server_default=func.now()),
)
SCOPED_BASELINES = Table(
    "stock_scoped_size_baselines", META,
    Column("brand", Text, primary_key=True), Column("category", Text, primary_key=True),
    Column("size_group", Text, primary_key=True), Column("season", Text, primary_key=True),
    Column("heel", Text, primary_key=True), Column("weights", JSON, nullable=False),
    Column("updated_by", BigInteger, nullable=False),
    Column("updated_at", DateTime(timezone=True), nullable=False, server_default=func.now()),
)
CAMPAIGNS = Table("stock_demand_campaigns", META,
    Column("id", BigInteger, primary_key=True, autoincrement=True), Column("brand", Text, nullable=False, index=True),
    Column("name", Text, nullable=False), Column("start_date", Date, nullable=False), Column("end_date", Date, nullable=False),
    Column("factor", Numeric(6, 3), nullable=False), Column("created_by", BigInteger, nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False, server_default=func.now()),
    CheckConstraint("start_date <= end_date AND factor > 0"),
)
ARRIVALS = Table("stock_confirmed_arrivals", META,
    Column("brand", Text, primary_key=True), Column("order_id", BigInteger, primary_key=True),
    Column("product_id", BigInteger, primary_key=True), Column("eta", Date), Column("sizes", JSON, nullable=False),
    Column("receipt_basis", JSON, nullable=False), Column("note", Text, nullable=False), Column("updated_by", BigInteger, nullable=False),
    Column("updated_at", DateTime(timezone=True), nullable=False, server_default=func.now()),
)
RECOVERY = Table("stock_clearance_recoveries", META,
    Column("brand", Text, primary_key=True), Column("week_start", Date, primary_key=True), Column("product_id", BigInteger, primary_key=True),
    Column("amount", Numeric(18, 2), nullable=False), Column("reference", Text, nullable=False),
    Column("updated_by", BigInteger, nullable=False), Column("updated_at", DateTime(timezone=True), nullable=False, server_default=func.now()),
    CheckConstraint("amount >= 0"),
)


ORDER_LINKS = Table("stock_purchase_order_links", META,
    Column("order_id", BigInteger, primary_key=True, autoincrement=False),
    Column("external_number", Text, nullable=False, unique=True),
    Column("note", Text, nullable=False),
    Column("updated_by", BigInteger, nullable=False),
    Column("updated_at", DateTime(timezone=True), nullable=False, server_default=func.now()),
)

Index("ix_stock_arrivals_brand_eta", ARRIVALS.c.brand, ARRIVALS.c.eta)


def recovery_summary(connection, brand, first, product_ids):
    if not product_ids:
        return {"recovery_amount": None, "recovery_covered": 0, "clearance_products": 0}
    amount, count = connection.execute(select(func.sum(RECOVERY.c.amount), func.count())
        .where(RECOVERY.c.brand == brand, RECOVERY.c.week_start == first,
               RECOVERY.c.product_id.in_(product_ids))).one()
    return {"recovery_amount": format(amount, ".2f") if amount is not None else None,
            "recovery_covered": count, "clearance_products": len(product_ids)}


def save_record(connection, table, keys, values):
    stmt = insert(table).values(**keys, **values)
    return dict(connection.execute(stmt.on_conflict_do_update(index_elements=list(keys),
        set_={**values, "updated_at": func.now()}).returning(table)).mappings().one())


def campaigns(connection, brand, today):
    return [dict(row) for row in connection.execute(select(CAMPAIGNS).where(CAMPAIGNS.c.brand == brand,
        CAMPAIGNS.c.end_date >= today).order_by(CAMPAIGNS.c.start_date, CAMPAIGNS.c.id).limit(100)).mappings()]


def _live_matcher(connection, repository, inspector, *, allocation=False):
    products, groups = _catalog(connection, repository, overview=True, inspector=inspector, allocation=allocation)
    return ArchiveMatcher(products, {name: {size["barcode"] for size in sizes if size["barcode"]}
        for name, sizes in groups.items()}), groups


def _size_from_source(sizes, spec, value, product, *, explicit=False):
    entered = code(spec)
    explicit_matches = {size["name"] for size in sizes if entered and entered in {code(size["name"]), size["barcode"]}}
    if not explicit and not explicit_matches and entered:
        # Color/spec sometimes contains more than one numeric token. Only a unique
        # configured size may be used and any barcode disagreement stays unknown.
        tail = entered.replace("；", ";").rsplit(";", 1)[-1].strip()
        explicit_matches = {size["name"] for size in sizes if tail in {code(size["name"]), size["barcode"]}}
        if not explicit_matches:
            explicit_matches = {size["name"] for size in sizes if re.search(
                r"(?<![0-9])" + re.escape(code(size["name"])) + r"(?![0-9])", tail)}
    raw = code(value)
    prefix = product["barcode_base"]
    suffix = raw[len(prefix):] if prefix and raw.startswith(prefix) else ""
    by_barcode = {size["name"] for size in sizes if suffix and size["barcode"] == suffix}
    matches = explicit_matches & by_barcode if explicit_matches and by_barcode else explicit_matches or by_barcode
    return next(iter(matches)) if len(matches) == 1 else None


def _size_sales(connection, inspector, matcher, key, sizes, codes, today):
    sources = ("jst_daily_sales", "vip_daily_sales")
    empty = {"sales_start": None, "cutoff": None, "sales": {}, "sales_total": 0, "sales_complete": False,
             "sales_days": 0, "known_volume": 0, "sales_volume": 0}
    if not all(inspector.has_table(name) for name in sources):
        return empty

    yesterday = today - timedelta(days=1)
    window = timedelta(days=29)
    first = yesterday - window
    jst_dates, vip_dates = (set(_sales_dates(connection, table, yesterday, first)) for table in sources)
    common_days = jst_dates & vip_dates
    if not common_days:
        return empty

    end = max(common_days)
    launch = launch_day(matcher.products[key].get("launch_date"))
    start = max(end - window, launch) if launch else end - window
    if start > end:
        return {**empty, "cutoff": end}
    if start < first:
        # Late feeds shift the window back. Verify the additional days before using it.
        earlier_jst, earlier_vip = (
            set(_sales_dates(connection, table, first - timedelta(days=1), start)) for table in sources
        )
        common_days.update(earlier_jst & earlier_vip)
    days = (end - start).days + 1
    covered = sum(start <= day <= end for day in common_days) == days
    mappings = {}
    if inspector.has_table("product_goods_shop_channel_mappings"):
        mappings = {shop_channel_key(shop): platform_name(channel) for shop, channel in connection.execute(text(
            "SELECT shop_name, channel FROM product_goods_shop_channel_mappings WHERE brand=:brand"), {"brand": key[0]})}
    product = matcher.products[key]
    params = {"start": start, "end": end, "codes": codes}
    sales = defaultdict(int)
    total, volume, known = 0, 0, 0
    vip_days = set()
    rows = connection.execute(text("""SELECT sales_date, goods_code, style_code, size_name, barcode, sum(sales_quantity)
        FROM vip_daily_sales WHERE sales_date BETWEEN :start AND :end
        AND (goods_code=ANY(:codes) OR style_code=ANY(:codes))
        GROUP BY sales_date, goods_code, style_code, size_name, barcode"""), params)
    for day, goods, style, spec, barcode, quantity in rows:
        if not quantity or matcher.resolve(barcode or goods, goods, style) != key:
            continue
        vip_days.add(day)
        total += int(quantity)
        volume += abs(int(quantity))
        if (size := _size_from_source(sizes, spec, barcode or goods, product, explicit=True)) is not None:
            sales[size] += int(quantity)
            known += abs(int(quantity))
    rows = connection.execute(text("""SELECT sales_date, product_code, style_code, color_spec, channel, barcode, sum(net_sales_quantity)
        FROM jst_daily_sales WHERE sales_date BETWEEN :start AND :end
        AND (product_code=ANY(:codes) OR style_code=ANY(:codes))
        AND coalesce(channel,'') NOT ILIKE '%采购%' AND coalesce(channel,'') NOT ILIKE '%-公司'
        AND coalesce(channel,'') NOT ILIKE '%VMI%'
        GROUP BY sales_date, product_code, style_code, color_spec, channel, barcode"""), params)
    for day, goods, style, spec, channel, barcode, quantity in rows:
        if not quantity or matcher.resolve(barcode or goods, goods, style) != key:
            continue
        platform = platform_name(channel, mappings)
        if is_clearance_channel(channel, platform) or (platform == "唯品" and day in vip_days):
            continue
        total += int(quantity)
        volume += abs(int(quantity))
        if (size := _size_from_source(sizes, spec, barcode or goods, product)) is not None:
            sales[size] += int(quantity)
            known += abs(int(quantity))
    return {"sales_start": start, "cutoff": end, "sales": dict(sales), "sales_total": total,
            "sales_complete": covered, "sales_days": days, "known_volume": known, "sales_volume": volume}


def _order_progress(connection, inspector, matcher, brand, groups, today, *, product_id=None, shortlist=None):
    if not all(inspector.has_table(name) for name in ("product_archive_identities", "inventory_details", "inventory_records")):
        return None
    # Order detail identities are brand-scoped; never infer a shipment from the order date.
    conditions = ["p.brand=:brand", "p.is_active", "r.deleted_at IS NULL", "r.document_type='进货订单'"]
    params = {"brand": brand}
    if product_id is not None:
        conditions.append("p.source_product_id=:product")
        params["product"] = product_id
    if shortlist is not None:
        conditions.append("p.source_product_id=ANY(:products)")
        params["products"] = sorted(shortlist)
    rows = connection.execute(text("""SELECT r.id, r.document_number, r.date_value, r.extra_fields, r.supplier,
                    p.source_product_id, d.quantity, d.size_quantities
                FROM product_archive_identities p JOIN inventory_details d ON d.product_identity_id=p.id
                JOIN inventory_records r ON r.id=d.document_id WHERE """ + " AND ".join(conditions)
                + " ORDER BY r.date_value NULLS LAST, r.id"), params).mappings()
    orders, history = {}, defaultdict(list)
    for row in rows:
        sku_id = row["source_product_id"]
        product = matcher.products.get((brand, sku_id))
        if product is None:
            continue
        number = row["document_number"]
        key = (row["id"], sku_id)
        extra = row["extra_fields"] if isinstance(row["extra_fields"], dict) else {}
        if key not in orders:
            orders[key] = {"id": row["id"], "product_id": sku_id, "sku": product["sku"],
                "supplier": row["supplier"], "number": number, "date": row["date_value"],
                "due": launch_day(extra.get("delivery_date") or extra.get("到货日期")),
                "ordered": Decimal(0), "ordered_sizes": defaultdict(int), "received": Decimal(0),
                "received_sizes": defaultdict(int), "unknown_product": False, "unknown_sizes": False,
                "invalid_order_sizes": False}
            history[sku_id].append(orders[key])
        order = orders[key]
        order["ordered"] += Decimal(row["quantity"] or 0)
        raw_sizes = row["size_quantities"]
        for name, qty in raw_sizes.items() if isinstance(raw_sizes, dict) else ():
            if qty is None or qty == "":
                continue
            try:
                quantity = Decimal(str(qty))
                if quantity.is_finite() and quantity >= 0 and quantity == quantity.to_integral_value():
                    order["ordered_sizes"][str(name).strip()] += int(quantity)
                    continue
            except (ArithmeticError, ValueError):
                pass
            order["invalid_order_sizes"] = True
    numbers = {order["number"] for order in orders.values() if order["number"]}
    number_ids = {}
    if numbers:
        number_ids = {number: order_id for number, order_id in connection.execute(text("""
            SELECT document_number, min(id) FROM inventory_records
            WHERE document_type='进货订单' AND document_number=ANY(:numbers) AND deleted_at IS NULL
            GROUP BY document_number HAVING count(*)=1"""), {"numbers": sorted(numbers)})}
    order_ids = {order["id"] for order in orders.values()}
    references = dict(connection.execute(select(ORDER_LINKS.c.order_id, ORDER_LINKS.c.external_number)
        .where(ORDER_LINKS.c.order_id.in_(order_ids))).all()) if order_ids else {}
    # A number explicitly assigned elsewhere must never also match by document number.
    mapped_numbers = set(connection.scalars(select(ORDER_LINKS.c.external_number)
        .where(ORDER_LINKS.c.external_number.in_(numbers)))) if numbers else set()
    receipt_links = {number: order_id for number, order_id in number_ids.items()
                     if order_id not in references and number not in mapped_numbers}
    receipt_links.update({reference: order_id for order_id, reference in references.items()})
    matched_receipts = set()
    has_receipts = inspector.has_table("v_jst_purchase_inbound_age_candidates")
    if has_receipts and receipt_links:
        receipts = connection.execute(text("""SELECT purchase_order_id, goods_code, style_color_code, size, inbound_date, sum(quantity) AS quantity
            FROM v_jst_purchase_inbound_age_candidates WHERE purchase_order_id=ANY(:numbers) AND inbound_date <= :today
            GROUP BY purchase_order_id, goods_code, style_color_code, size, inbound_date"""),
            {"numbers": sorted(receipt_links), "today": today}).mappings()
        unresolved = set()
        for row in receipts:
            order_id = receipt_links[row["purchase_order_id"]]
            matched_receipts.add((order_id, row["purchase_order_id"]))
            identity = matcher.resolve(row["goods_code"], row["style_color_code"])
            if identity is None:
                unresolved.add(order_id)
            if identity is None or identity[0] != brand:
                continue
            order = orders.get((order_id, identity[1]))
            if order is None:
                continue
            if not order["date"] or row["inbound_date"] < order["date"]:
                unresolved.add(order_id)
                continue
            order["received"] += row["quantity"]
            product = matcher.products[identity]
            size = _size_from_source(groups.get(product.get("size_range"), []), row["size"], row["goods_code"], product, explicit=True)
            if not size or row["quantity"] != int(row["quantity"]):
                order["unknown_sizes"] = True
            else:
                order["received_sizes"][size] += int(row["quantity"])
        for order in orders.values():
            order["unknown_product"] = order["id"] in unresolved
    confirmed_query = select(ARRIVALS).where(ARRIVALS.c.brand == brand)
    if product_id is not None:
        confirmed_query = confirmed_query.where(ARRIVALS.c.product_id == product_id)
    confirmed = {(row["order_id"], row["product_id"]): {"eta": row["eta"], "sizes": row["sizes"],
                  "note": row["note"], "receipt_basis": row["receipt_basis"]}
                 for row in connection.execute(confirmed_query).mappings()}
    for entries in history.values():
        first = entries[0]
        starts_known = (all(order["date"] for order in entries) and number_ids.get(first["number"]) == first["id"]
                        and (len(entries) == 1 or first["date"] != entries[1]["date"]))
        for order in entries:
            order["kind"] = "待核对"
            if starts_known and number_ids.get(order["number"]) == order["id"]:
                order["kind"] = "首单" if order["id"] == first["id"] else "补单"
    for key, order in orders.items():
        external = references.get(order["id"])
        reference = external or order["number"]
        has_link = bool(has_receipts and receipt_links.get(reference) == order["id"] and order["date"]
                        and not order["unknown_product"] and (external or (order["id"], reference) in matched_receipts))
        order["external_number"] = external
        order["receipts_verified"] = has_link
        order["status"] = arrival_status(today, order["due"], order["ordered"], order["received"], has_link)
        order["remaining"] = max(Decimal(0), order["ordered"] - order["received"]) if has_link else None
        order["received"] = order["received"] if has_link else None
        configured = {size["name"] for size in groups.get(matcher.products[(brand, key[1])].get("size_range"), [])}
        ordered_sizes = {size: qty for size, qty in order["ordered_sizes"].items() if qty}
        order["remaining_sizes"] = (
            {size: qty - order["received_sizes"][size] for size, qty in ordered_sizes.items()}
            if has_link and not order["unknown_sizes"] and not order["invalid_order_sizes"] and ordered_sizes.keys() <= configured
            and sum(ordered_sizes.values()) == order["ordered"]
            and all(qty <= ordered_sizes.get(size, 0) for size, qty in order["received_sizes"].items()) else {}
        )
        entry = confirmed.get(key)
        if entry is not None:
            basis = entry.pop("receipt_basis")
            entry["sizes"] = {size: max(0, quantity - max(0, order["received_sizes"][size] - basis.get(size, 0)))
                              for size, quantity in entry["sizes"].items()}
            entry["credible"] = bool(entry["eta"] and entry["eta"] >= today and order["remaining_sizes"]
                and any(entry["sizes"].values()) and order["received_sizes"].keys() >= {
                    size for size in basis if basis[size]
                } and all(order["received_sizes"][size] >= quantity for size, quantity in basis.items())
                and all(qty <= order["remaining_sizes"].get(size, 0) for size, qty in entry["sizes"].items()))
        order["confirmation"] = entry
        order["receipt_basis"] = {size: order["received_sizes"][size] for size in order["remaining_sizes"]}
        for internal in ("ordered_sizes", "received_sizes", "unknown_sizes", "unknown_product", "invalid_order_sizes"):
            del order[internal]
    return list(orders.values())


def arrival_board(connection, repository, brand, today, scope):
    inspector = inspect(connection)
    matcher, groups = _live_matcher(connection, repository, inspector)
    shortlist = None
    if scope == "confirmed":
        if not inspector.has_table("v_jst_purchase_inbound_age_candidates"):
            return None
        shortlist = set(connection.scalars(select(ARRIVALS.c.product_id).where(
            ARRIVALS.c.brand == brand, ARRIVALS.c.eta.between(today, today + timedelta(days=2)))))
        if not shortlist:
            return []
    orders = _order_progress(connection, inspector, matcher, brand, groups, today, shortlist=shortlist)
    if orders is None:
        return None
    if scope == "confirmed":
        return sorted((order for order in orders if order["confirmation"] and order["confirmation"]["credible"]
                       and order["confirmation"]["eta"] <= today + timedelta(days=2)),
                      key=lambda order: (order["confirmation"]["eta"], order["id"], order["sku"]))
    return sorted((order for order in orders if order["status"] == scope),
                  key=lambda order: (order["due"], order["id"], order["sku"]))


def _saved_profiles(connection, brand, size_group, season, heel):
    table = SCOPED_BASELINES if season or heel else BASELINES
    condition = (table.c.brand == brand, table.c.size_group == size_group)
    if table is SCOPED_BASELINES:
        condition += (table.c.season == season, table.c.heel == heel)
    return {name: weights for name, weights in connection.execute(select(table.c.category, table.c.weights).where(*condition))}


def _allocation_references(connection, inspector, matcher, key, sizes, scope, today, category, product_id):
    brand, target_id = key
    product = matcher.products[key]
    profiles = _saved_profiles(connection, brand, scope["size_group"], scope["allocation_season"], scope["heel_group"])
    names = scope["sizes"]
    profiles = {name: weights for name, weights in profiles.items() if set(weights) == set(names) and any(weights.values())}
    family = group_key(product)
    siblings = {
        candidate_id: item for (candidate_brand, candidate_id), item in matcher.products.items()
        if candidate_brand == brand and candidate_id != target_id and group_key(item) == family
        and code(item.get("color") or item.get("color_code"))
        and code(item.get("color") or item.get("color_code")) != code(product.get("color") or product.get("color_code"))
        and item.get("size_range") == scope["size_group"]
        and allocation_heel(item.get("rear_heel_height"), item.get("heel_height"), item.get("product_name")) == scope["heel_group"]
        and scope["allocation_season"] in allocation_seasons(item.get("season_category"))
    } if family.startswith("original:") and names and scope["allocation_season"] and scope["heel_group"] else {}
    reference = None
    cross_product = product_id is not None or (category is not None and category != scope["category"])
    if cross_product and (not scope["allocation_season"] or not scope["heel_group"]):
        return {"reference_error": "请先完善销售季节和跟高，再引用其他款色或近品类"}
    if category is not None:
        if category not in profiles:
            return {"reference_error": "所选品类没有当前销售季节、跟高和尺码组的配比"}
        reference = {"kind": "category" if category == scope["category"] else "related_category",
                     "label": category, "weights": profiles[category]}
    if product_id is not None:
        sibling = siblings.get(product_id)
        if sibling is None:
            return {"reference_error": "所选款色不属于同原始货号，或销售季节、跟高档、尺码组不一致"}
        ref_key = (brand, product_id)
        codes = _indexed_sales_codes(matcher, (ref_key,), matcher.source_codes((ref_key,)))
        sample = _size_sales(connection, inspector, matcher, ref_key, sizes, codes, today)
        weights, _ = choose_weights(names, sample["sales"], sample["known_volume"], sample["sales_volume"],
                                    sample["sales_complete"], None)
        reference = {"kind": "other_color", "label": sibling["sku"], "color": sibling.get("color") or sibling.get("color_code"),
                     "weights": weights, "sales": sample["sales"] if sample["sales_complete"] else None,
                     "sales_start": sample["sales_start"], "cutoff": sample["cutoff"]}
    baseline = profiles.get(scope["category"])
    legacy_baseline = None
    if baseline is None and (scope["allocation_season"] or scope["heel_group"]):
        legacy_baseline = connection.scalar(select(BASELINES.c.weights).where(
            BASELINES.c.brand == brand, BASELINES.c.size_group == scope["size_group"],
            BASELINES.c.category == scope["category"],
        ))
    return {
        "baseline": baseline,
        "legacy_baseline": legacy_baseline,
        "related_categories": sorted(name for name in profiles if name != scope["category"])
                              if names and scope["allocation_season"] and scope["heel_group"] else [],
        "other_colors": [{"id": candidate_id, "sku": item["sku"], "color": item.get("color") or item.get("color_code")}
                         for candidate_id, item in sorted(siblings.items(), key=lambda row: row[1]["sku"])],
        "reference": reference,
    }


def planning_facts(connection, repository, brand, product_id, today, *, show_orders=True, full=True,
                   include_confirmations=True, season=None, reference_category=None, reference_product_id=None):
    inspector = inspect(connection)
    matcher, groups = _live_matcher(connection, repository, inspector, allocation=full or not include_confirmations)
    key = (brand, product_id)
    product = matcher.products.get(key)
    if product is None:
        return None
    group = product.get("size_range") or ""
    categories = (product.get("product_name") or "").strip()
    sizes = groups.get(group, [])
    codes = _indexed_sales_codes(matcher, (key,), matcher.source_codes((key,)))
    names = [size["name"] for size in sizes]
    seasons = allocation_seasons(product.get("season_category"))
    if season is not None and season not in seasons:
        return {"reference_error": "请选择该款档案中的销售季节"}
    result = {"sku": product["sku"], "product_name": product.get("product_name"), "category": categories,
              "color": product.get("color") or product.get("color_code"),
              "size_group": group, "sizes": names, "year": product.get("year"), "season": product.get("season_category"),
              "allocation_season": season if season is not None else seasons[0], "allocation_seasons": seasons,
              "heel_group": allocation_heel(product.get("rear_heel_height"), product.get("heel_height"), categories)}
    orders = _order_progress(connection, inspector, matcher, brand, groups, today, product_id=product_id) if include_confirmations else None
    result["confirmations"] = [row["confirmation"] for row in (orders or []) if row["confirmation"] and row["confirmation"]["eta"]]
    result["orders"] = list(reversed(orders)) if show_orders and orders is not None else None
    if not full:
        return result
    stock, transit = defaultdict(int), defaultdict(int)
    stock_date = None
    stock_rows, unassigned_stock = 0, False
    if inspector.has_table("jst_full_stock"):
        stock_date = connection.execute(text("SELECT max(sync_date) FROM jst_full_stock")).scalar()
        for goods, style, spec, available, inbound in connection.execute(text("""SELECT product_code, style_code, size,
                sum(available_qty), sum(purchase_in_transit_qty) FROM jst_full_stock
                WHERE sync_date=:day AND (product_code=ANY(:codes) OR style_code=ANY(:codes))
                GROUP BY product_code, style_code, size"""), {"day": stock_date, "codes": codes}):
            identity = matcher.resolve(goods, style)
            if identity is None and (available or inbound):
                unassigned_stock = True
            if identity != key:
                continue
            stock_rows += 1
            size = _size_from_source(sizes, spec, goods, product, explicit=True)
            if size and available is not None and all(qty is None or (qty >= 0 and qty == int(qty)) for qty in (available, inbound)):
                stock[size] += int(available)
                if inbound is not None:
                    transit[size] += int(inbound)
            elif available is None or available or inbound:
                unassigned_stock = True
    size_sales = _size_sales(connection, inspector, matcher, key, sizes, codes, today)
    references = _allocation_references(connection, inspector, matcher, key, sizes, result, today,
                                        reference_category, reference_product_id)
    if "reference_error" in references:
        return references
    return result | {"stock_date": stock_date, "stock_ready": bool(stock_rows and sizes and not unassigned_stock and stock_date == today
        and all(quantity >= 0 for quantity in stock.values())), "stock": dict(stock), "source_transit": dict(transit),
        **size_sales, **references}

