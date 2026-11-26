"""On-demand evidence for one original-code group."""
from collections import defaultdict
from datetime import timedelta

from sqlalchemy import inspect, text

from domain.factory_channel_sales import platform_name, shop_channel_key
from domain.stock_alerts import ArchiveMatcher, code, launch_day
from domain.stock_portfolio import group_key
from storage.seasonal_analysis_facts import _indexed_sales_codes
from storage.stock_alert_facts import _sales_dates
from storage.stock_replenishment_facts import _catalog

WINDOWS = (1, 3, 7, 15, 30)


def _sales(connection, inspector, matcher, keys, brand, codes, today):
    sources = ("jst_daily_sales", "vip_daily_sales")
    if not all(inspector.has_table(name) for name in sources):
        return {"cutoff": None, "windows": {}, "channels": []}
    ends = [connection.execute(text(f"SELECT max(sales_date) FROM {name}")).scalar() for name in sources]
    if not all(ends):
        return {"cutoff": None, "windows": {}, "channels": []}
    end = min(today - timedelta(days=1), *ends)
    start = end - timedelta(days=29)
    dates = [set(_sales_dates(connection, name, end, start)) for name in sources]
    covered = dates[0] & dates[1]
    complete = {n: all(end - timedelta(days=d) in covered for d in range(n)) for n in WINDOWS}
    mappings = {}
    if inspector.has_table("product_goods_shop_channel_mappings"):
        mappings = {shop_channel_key(shop): platform_name(channel) for shop, channel in connection.execute(text(
            "SELECT shop_name, channel FROM product_goods_shop_channel_mappings WHERE brand = :brand"), {"brand": brand})}
    params = {"start": start, "end": end, "codes": codes}
    totals = defaultdict(lambda: defaultdict(lambda: [0, 0, 0]))
    vip_days = set()
    skipped = 0
    with connection.execute(text("""SELECT sales_date, goods_code, style_code, sum(sales_quantity)
        FROM vip_daily_sales WHERE sales_date BETWEEN :start AND :end
          AND (goods_code = ANY(:codes) OR style_code = ANY(:codes))
        GROUP BY sales_date, goods_code, style_code"""), params) as rows:
        for day, goods, style, quantity in rows:
            key = matcher.resolve(goods, style)
            if key is None:
                skipped += 1
            if key not in keys or not quantity:
                continue
            vip_days.add((key, day))
            for n in WINDOWS:
                if complete[n] and (end-day).days < n:
                    totals[("唯品", "唯品商品日销")][n][0] += max(0, int(quantity))
                    totals[("唯品", "唯品商品日销")][n][2] += int(quantity)
    with connection.execute(text("""SELECT sales_date, product_code, style_code, channel,
            sum(greatest(coalesce(sales_quantity,0),0)), sum(coalesce(return_quantity,0)),
            sum(coalesce(net_sales_quantity,0))
        FROM jst_daily_sales WHERE sales_date BETWEEN :start AND :end
          AND (product_code = ANY(:codes) OR style_code = ANY(:codes))
          AND coalesce(channel,'') NOT ILIKE '%采购%' AND coalesce(channel,'') NOT ILIKE '%-公司'
          AND coalesce(channel,'') NOT ILIKE '%VMI%'
        GROUP BY sales_date, product_code, style_code, channel"""), params) as rows:
        for day, sku, style, shop, gross, returns, net in rows:
            key = matcher.resolve(sku, style)
            if key is None:
                skipped += 1
            platform = platform_name(shop, mappings)
            if platform == "其他" and "抖音" in (shop or ""):
                platform = "抖音"
            if key not in keys or (platform == "唯品" and (key, day) in vip_days) or not (gross or returns or net):
                continue
            for n in WINDOWS:
                if complete[n] and (end-day).days < n:
                    cells = totals[(platform, shop or "未识别店铺")][n]
                    for index, value in enumerate((gross, returns, net)):
                        cells[index] += int(value or 0)
    def metrics(values, has_returns):
        return {"gross": values[0], "returns": values[1] if has_returns else None, "net": values[2]}
    return {"cutoff": end, "windows": complete, "unmatched": skipped,
            "channels": [{"platform": platform, "shop": shop, "windows": {
                n: metrics(values[n], shop != "唯品商品日销") if complete[n] else None for n in WINDOWS}}
                for (platform, shop), values in sorted(totals.items())]}


def _purchase_history(connection, inspector, matcher, keys, codes, brand, can_view_inventory, can_view_purchases, today):
    receipts, orders = None, None
    if inspector.has_table("mv_jst_purchase_inbound_age_reference"):
        receipts = defaultdict(lambda: {"first": None, "last": None, "quantity": 0})
        start = today - timedelta(days=89)
        if can_view_inventory and inspector.has_table("v_jst_purchase_inbound_age_candidates"):
            receipt_rows = connection.execute(text("""SELECT goods_code, style_color_code, original_sku,
                inbound_date, inbound_id, purchase_order_id, sum(quantity) AS quantity
                FROM v_jst_purchase_inbound_age_candidates
                WHERE inbound_date BETWEEN :start AND :end AND goods_code = ANY(:codes)
                GROUP BY goods_code, style_color_code, original_sku, inbound_date, inbound_id, purchase_order_id
                ORDER BY inbound_date DESC, inbound_id"""),
                {"codes": codes, "start": start, "end": today}).mappings()
            documents = defaultdict(int)
            for row in receipt_rows:
                key = matcher.resolve(row["goods_code"], row["style_color_code"], row["original_sku"])
                if key in keys:
                    documents[(key[1], row["inbound_date"], row["inbound_id"], row["purchase_order_id"])] += int(row["quantity"] or 0)
            receipts_detail = [{"product_id": i, "date": day, "inbound_id": inbound, "purchase_order_id": purchase, "quantity": qty}
                               for (i, day, inbound, purchase), qty in list(documents.items())[:25]]
        else:
            receipts_detail = None
        for row in connection.execute(text("""SELECT goods_code, style_color_code, original_sku,
                first_inbound_date, last_inbound_date, received_quantity
                FROM mv_jst_purchase_inbound_age_reference WHERE goods_code = ANY(:codes)
                OR style_color_code = ANY(:codes) OR original_sku = ANY(:codes)"""), {"codes": codes}).mappings():
            key = matcher.resolve(row["goods_code"], row["style_color_code"], row["original_sku"])
            if key not in keys:
                continue
            total = receipts[key[1]]
            total["quantity"] += int(row["received_quantity"] or 0)
            first = row["first_inbound_date"]
            last = row["last_inbound_date"]
            if first and (total["first"] is None or first < total["first"]):
                total["first"] = first
            if last and (total["last"] is None or last > total["last"]):
                total["last"] = last
        receipts = {"by_product": dict(receipts), "recent": receipts_detail}
    if can_view_purchases and all(inspector.has_table(name) for name in ("inventory_records", "inventory_details", "product_archive_identities")):
        orders = []
        rows = connection.execute(text("""SELECT r.id, r.document_number, r.date_value, r.extra_fields,
                p.source_product_id, sum(d.quantity) AS quantity
            FROM product_archive_identities p JOIN inventory_details d ON d.product_identity_id = p.id
                JOIN inventory_records r ON r.id = d.document_id
            WHERE p.brand = :brand AND p.is_active AND p.source_product_id = ANY(:ids)
                AND r.deleted_at IS NULL AND r.document_type = '进货订单'
            GROUP BY r.id, p.source_product_id ORDER BY r.date_value DESC NULLS LAST, r.id DESC, p.source_product_id LIMIT 25"""),
            {"brand": brand, "ids": sorted(i for _, i in keys)}).mappings()
        for row in rows:
            extra = row["extra_fields"] if isinstance(row["extra_fields"], dict) else {}
            orders.append({"id": row["id"], "product_id": row["source_product_id"],
                           "number": row["document_number"], "date": row["date_value"],
                           "delivery_date": launch_day(extra.get("delivery_date") or extra.get("到货日期")),
                           "quantity": float(row["quantity"] or 0)})
    return receipts, orders


def load_portfolio_detail(repository, brand, product_id, decisions, *, can_view_inventory, can_view_purchases, today):
    with repository.engine.connect().execution_options(isolation_level="REPEATABLE READ") as connection, connection.begin():
        connection.exec_driver_sql("SET TRANSACTION READ ONLY")
        connection.exec_driver_sql("SET LOCAL statement_timeout = '15s'")
        inspector = inspect(connection)
        products, groups = _catalog(connection, repository, overview=True, inspector=inspector)
        matcher = ArchiveMatcher(products, {name: {size["barcode"] for size in sizes if size["barcode"]}
                                            for name, sizes in groups.items()})
        product = matcher.products.get((brand, product_id))
        if not product:
            return None
        parent = group_key(product)
        keys = {key for key, item in matcher.products.items() if key[0] == brand and group_key(item) == parent}
        searchable = set(matcher.source_codes(keys))
        # Include shared original codes as candidates; resolve each row only once.
        searchable.update(code(matcher.products[key].get("original_sku")) for key in keys)
        searchable.discard("")
        codes = _indexed_sales_codes(matcher, keys, searchable)
        stock = defaultdict(dict)
        stock_date, unmatched = None, 0
        if inspector.has_table("jst_full_stock"):
            stock_date = connection.execute(text("SELECT max(sync_date) FROM jst_full_stock")).scalar()
            if stock_date and codes:
                rows = connection.execute(text("""SELECT product_code, style_code, size, warehouse_name,
                        sum(available_qty) AS qty, sum(purchase_in_transit_qty) AS transit
                    FROM jst_full_stock WHERE sync_date = :day
                        AND (product_code = ANY(:codes) OR style_code = ANY(:codes))
                    GROUP BY product_code, style_code, size, warehouse_name"""), {"day": stock_date, "codes": codes}).mappings()
                for row in rows:
                    key = matcher.resolve(row["product_code"], row["style_code"])
                    if key is None:
                        unmatched += 1
                    if key not in keys:
                        continue
                    slot = (row["size"] or "未标尺码", row["warehouse_name"] or "未标分仓")
                    values = stock[key].setdefault(slot, [0, 0])
                    values[0] += int(row["qty"] or 0)
                    values[1] += int(row["transit"] or 0)
        children = []
        for key in sorted(keys, key=lambda key: (matcher.products[key]["sku"], key[1])):
            item = matcher.products[key]
            slots = stock.get(key)
            children.append({field: item.get(field) for field in ("id", "sku", "original_sku", "product_name", "color",
                "launch_date", "year", "season_category", "category")} | {
                "available_quantity": sum(value[0] for value in slots.values()) if slots else None,
                "purchase_in_transit": sum(value[1] for value in slots.values()) if slots else None,
                "stock": [{"size": size, "warehouse": warehouse, "available": value[0], "transit": value[1]}
                          for (size, warehouse), value in sorted((slots or {}).items())],
                "clearance": decisions.get(key[1]),
            })
        receipts, orders = _purchase_history(connection, inspector, matcher, keys, codes, brand,
                                             can_view_inventory, can_view_purchases, today)
        return {"original_sku": product.get("original_sku"), "stock_date": stock_date, "unmatched_stock": unmatched,
                "items": children, "sales": _sales(connection, inspector, matcher, keys, brand, codes, today),
                "receipts": receipts, "orders": orders}

