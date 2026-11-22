"""Bounded read-only facts for quarterly launch analysis; no stock or order writes."""
from collections import OrderedDict, defaultdict
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from threading import Lock
from time import monotonic

import orjson
from sqlalchemy import inspect, select, text
from sqlalchemy.exc import OperationalError

from domain.seasonal_analysis import quarter_bounds
from domain.stock_alerts import ArchiveMatcher, code, launch_day
from domain.size_group_schema import SIZE_GROUPS_TABLE, SIZE_GROUP_ITEMS_TABLE
from storage.stock_alert_facts import _sales_dates

_cache, _lock, _build_lock = OrderedDict(), Lock(), Lock()
TTL, MAX_BYTES = 120, 8 * 1024 * 1024


def _catalog(connection, repository, brand, inspector):
    all_products = []
    fields = ("id", "sku", "original_sku", "product_name", "color", "color_code",
              "barcode_build_rule", "size_range", "launch_date", "season_category")
    for key in repository.product_archive_brands():
        table = repository._table_for_brand(key)
        if not inspector.has_table(table.name):
            continue
        # Other brands are needed only to reject code collisions. Their display
        # fields and launch history do not participate in the selected cohorts.
        selected_fields = fields if key == brand else ("id", "sku", "original_sku", "color_code", "barcode_build_rule", "size_range")
        for row in connection.execute(select(*(table.c[f] for f in selected_fields)).where(table.c.deleted_at.is_(None))).mappings():
            item = dict(row) | {"brand": key}
            all_products.append(item)
    sizes = defaultdict(set)
    for group, barcode in connection.execute(select(SIZE_GROUPS_TABLE.c.name, SIZE_GROUP_ITEMS_TABLE.c.barcode)
            .join(SIZE_GROUP_ITEMS_TABLE, SIZE_GROUP_ITEMS_TABLE.c.size_group_id == SIZE_GROUPS_TABLE.c.id)):
        if str(barcode or "").strip():
            sizes[group].add(str(barcode).strip().upper())
    return ArchiveMatcher(all_products, sizes), all_products


def _receipt_references(connection, matcher, keys):
    codes = matcher.source_codes(keys)
    if not codes:
        return
    with connection.execute(text(
        "SELECT goods_code, style_color_code, original_sku, first_inbound_date FROM mv_jst_purchase_inbound_age_reference "
        "WHERE upper(trim(goods_code))=ANY(:codes) OR upper(trim(style_color_code))=ANY(:codes) "
        "OR upper(trim(original_sku))=ANY(:codes)"), {"codes": codes}) as rows:
        for row in rows.mappings():
            key = matcher.resolve(row["goods_code"], row["style_color_code"], row["original_sku"])
            if key in keys:
                yield key, row


def _receipt_codes(connection, matcher, keys):
    return sorted({row["goods_code"] for _, row in _receipt_references(connection, matcher, keys)})


def _load(connection, repository, brand, year, today, *, zero_quarter=None):
    inspector = inspect(connection)
    matcher, all_products = _catalog(connection, repository, brand, inspector)
    years, missing_launch = {today.year}, 0
    for item in all_products:
        if item["brand"] == brand:
            launch = launch_day(item.get("launch_date"))
            if not launch:
                missing_launch += 1
            elif launch.year <= today.year:
                years.add(launch.year)
    del all_products
    products, undated = {}, {}
    for key, item in matcher.products.items():
        if key[0] != brand:
            continue
        launch = launch_day(item.get("launch_date"))
        display = {name: item.get(name) for name in ("id", "sku", "original_sku", "product_name", "color")} | {
            "season": item.get("season_category") or "", "available_quantity": None}
        if not launch:
            undated[key] = display | {"invalid_launch": bool(str(item.get("launch_date") or "").strip())}
        elif launch.year == year:
            products[key] = display | {"launch_date": launch.isoformat(), "received": ["0"] * 4, "inbound": ["0"] * 4,
                "orders": [set() for _ in range(4)], "unknown_orders": [False] * 4,
                "inbound_dates": [set() for _ in range(4)]}
    result = {"business_date": today.isoformat(), "products": list(products.values()), "sales": {}, "brand_sales": [], "sales_dates": [], "sales_end": None,
              "stock_date": None, "purchase_ready": all(inspector.has_table(name) for name in ("v_jst_purchase_inbound_age_candidates", "mv_jst_purchase_inbound_age_reference")),
              "arrivals": [], "zero_checked": False, "zero_sales_evidence": {},
              "seasons": sorted({p["season"] for p in (*products.values(), *undated.values()) if p["season"]}),
              "years": sorted(years | {year}, reverse=True), "missing_launch_count": missing_launch,
              "unmatched_stock_rows": 0, "unmatched_purchase_rows": 0,
              "source_issues": [
                  "到货待补上市日期按已导入采购记录中的首次入库日期归季，要求当前仍有可售库存；不计入季度新品指标。",
                  "上市满15天零动销按季度统计日判断，要求上市后日销完整且当前仍有可售库存；全退回不等于零动销。",
                  "新品按档案上市日期归入自然季度，统计单位为档案款色；已售罄商品仍参与分析。季节为独立筛选。",
                  "动销率观察上市当日起的3/7/15个自然日，可跨季度和跨年观察，仅计算已满观察期且日销完整的款色，销售后全退回仍算有动销。",
                  "参考售罄率＝净销量÷截至该季统计日的累计正向采购入库量；含上市前备货及后续补货，采购退货未完整扣除，唯品日销未单列退货。",
                  "仅首单按已导入范围内的唯一采购单号识别，拆单、合单及历史覆盖不足可能影响判断；缺失单号列为待核对，不等同确认从未补货。",
                  "各季销售统计至该季末或日销截止日；库存始终展示当前快照，不代表历史季末库存。季度销售占比以该品牌已匹配档案的同季度销售双数为分母，不把归属不明销量混入品牌。",
              ]}
    required = ("factory_channel_sales_daily_summaries", "jst_daily_sales", "vip_daily_sales")
    if all(inspector.has_table(name) for name in required):
        ends = [connection.execute(text(f"SELECT max(sales_date) FROM {name}")).scalar() for name in required[1:]]
        if all(ends):
            date_end = min(ends)
            result["sales_end"] = min(today-timedelta(days=1), date_end).isoformat()
            start = quarter_bounds(year, 1)[0]
            end = min(date_end, today-timedelta(days=1), quarter_bounds(year, 4)[1]+timedelta(days=13))
            if start <= end:
                coverage = [set(_sales_dates(connection, name, end, start)) for name in required[1:]]
                # One indexed marker lookup per day avoids scanning every
                # product/channel row just to discover covered dates.
                markers = set(connection.execute(text("""SELECT CAST(day AS date) FROM
                    generate_series(CAST(:start AS date), CAST(:end AS date), INTERVAL '1 day') day
                    WHERE EXISTS (SELECT 1 FROM factory_channel_sales_daily_summaries f
                        WHERE f.brand=:brand AND f.sales_date=CAST(day AS date)
                        AND f.product_code='' AND f.channel_group='' AND f.match_status='date_marker')"""),
                    {"brand": brand, "start": start, "end": end}).scalars())
                result["sales_dates"] = [d.isoformat() for d in sorted(markers.intersection(*coverage))]
                by_sku = defaultdict(list)
                for identity, product in matcher.products.items():
                    if identity[0] == brand:
                        by_sku[product["sku"]].append(product["id"])
                for p in products.values():
                    if len(by_sku[p["sku"]]) > 1:
                        p["sales_ambiguous"] = True
                brand_sales = defaultdict(lambda: [0, 0])
                sales = defaultdict(list)
                unmatched_sales = 0
                # Aggregate the brand denominator in SQL; only transfer daily
                # product rows needed by this year's cohorts or ambiguity notice.
                sales_codes = sorted({p["sku"] for p in products.values()}
                                     | {sku for sku, ids in by_sku.items() if len(ids) > 1})
                with connection.execute(text("""SELECT sales_date,
                    sum(gross_quantity) AS gross, sum(quantity) AS net FROM factory_channel_sales_daily_summaries
                    WHERE brand=:brand AND match_status='matched' AND sales_date>=:start AND sales_date<=:end
                    GROUP BY sales_date""").execution_options(yield_per=5000), {"brand": brand, "start": start, "end": end}) as rows:
                    for row in rows.mappings():
                        brand_sales[row["sales_date"].isoformat()] = [int(row["gross"] or 0), int(row["net"] or 0)]
                with connection.execute(text("""SELECT product_code, sales_date,
                    sum(gross_quantity) AS gross, sum(quantity) AS net FROM factory_channel_sales_daily_summaries
                    WHERE brand=:brand AND match_status='matched' AND sales_date>=:start AND sales_date<=:end
                    AND product_code=ANY(:codes) GROUP BY product_code, sales_date""").execution_options(yield_per=5000),
                    {"brand": brand, "start": start, "end": end, "codes": sales_codes}) as rows:
                    for row in rows.mappings():
                        day = row["sales_date"].isoformat()
                        gross, net = int(row["gross"] or 0), int(row["net"] or 0)
                        candidates = by_sku.get(row["product_code"], [])
                        if len(candidates) == 1 and (brand, candidates[0]) in products:
                            sales[str(candidates[0])].append([day, gross, net])
                        elif len(candidates) > 1:
                            unmatched_sales += 1
                result["sales"], result["brand_sales"] = {key: sorted(values) for key, values in sales.items()}, [[day, *values] for day, values in sorted(brand_sales.items())]
                if unmatched_sales:
                    result["source_issues"].append(f"{unmatched_sales} 组销售关联到重复货号，相关款色需核对。")
                    ambiguous_ids = {key for values in by_sku.values() if len(values) > 1 for key in values}
                    for p in products.values():
                        if p["id"] in ambiguous_ids:
                            p["sales_ambiguous"] = True
    result["source_issues"].append("销量复用渠道日汇总，商品新增或改号后需等待原有汇总重建；未匹配商品不计入分子、分母。历史日销不完整时不显示确定销量。")
    if not result["sales_end"]:
        result["source_issues"].append("缺少日销来源或最新日期，暂不计算销量和动销率。")
    # Keep the full matcher to reject cross-brand collisions, but only fetch
    # source candidates for selected cohorts, then resolve every returned row.
    awaiting = {}
    if result["purchase_ready"] and undated:
        first = {}
        receipt_end = min(today, quarter_bounds(year, 4)[1]-timedelta(days=1))
        if receipt_end >= quarter_bounds(year, 1)[0]:
            for key, row in _receipt_references(connection, matcher, undated):
                day = row["first_inbound_date"]
                if day and day <= receipt_end:
                    first[key] = min(first.get(key, day), day)
        awaiting = {key: undated[key] | {"first_inbound_date": day.isoformat()}
                    for key, day in first.items() if day.year == year}
    stock_products = products | awaiting
    source_codes = matcher.source_codes(stock_products)
    if inspector.has_table("jst_full_stock"):
        day = connection.execute(text("SELECT max(sync_date) FROM jst_full_stock")).scalar()
        result["stock_date"] = day.isoformat() if day else None
        if day and source_codes:
            quantities = defaultdict(Decimal)
            null_stock = set()
            with connection.execute(text("""SELECT product_code, style_code,
                CASE WHEN count(available_qty) = count(*) THEN sum(available_qty) END AS quantity
                FROM jst_full_stock WHERE sync_date=:day
                AND (upper(trim(product_code))=ANY(:codes) OR upper(trim(style_code))=ANY(:codes))
                GROUP BY product_code, style_code""").execution_options(yield_per=5000), {"day": day, "codes": source_codes}) as rows:
                for row in rows.mappings():
                    identity = matcher.resolve(row["product_code"], row["style_code"])
                    if identity is None:
                        result["unmatched_stock_rows"] += 1
                    elif identity in stock_products:
                        if row["quantity"] is None:
                            null_stock.add(identity)
                        else:
                            quantities[identity] += Decimal(row["quantity"])
            for identity, quantity in quantities.items():
                if identity not in null_stock:
                    stock_products[identity]["available_quantity"] = str(quantity)
    result["arrivals"] = [p for p in awaiting.values() if Decimal(p["available_quantity"] or 0) > 0]
    if products and result["purchase_ready"] and result["sales_end"]:
        sales_end = date.fromisoformat(result["sales_end"])
        codes = _receipt_codes(connection, matcher, products)
        parameters = {"end": min(sales_end, quarter_bounds(year, 4)[1]-timedelta(days=1)),
                      "start": quarter_bounds(year, 1)[0],
                      **{f"q{q}": quarter_bounds(year, q)[0] for q in (2,3,4)}}
        period = "CASE WHEN inbound_date<:start THEN 0 WHEN inbound_date<:q2 THEN 1 WHEN inbound_date<:q3 THEN 2 WHEN inbound_date<:q4 THEN 3 ELSE 4 END"
        sql = """SELECT goods_code, style_color_code, original_sku, """ + period + """ AS period,
            sum(quantity) AS quantity, array_agg(DISTINCT inbound_date) AS inbound_dates,
            array_agg(DISTINCT nullif(trim(purchase_order_id),'')) AS orders,
            count(*) FILTER (WHERE nullif(trim(purchase_order_id),'') IS NULL) AS unknown_orders
            FROM v_jst_purchase_inbound_age_candidates
            WHERE inbound_date<=:end AND goods_code=ANY(:codes)
            GROUP BY goods_code, style_color_code, original_sku, """ + period
        for offset in range(0, len(codes), 1000):
            with connection.execute(text(sql),
                    parameters | {"codes": codes[offset:offset+1000]}) as rows:
                for row in rows.mappings():
                    identity = matcher.resolve(row["goods_code"], row["style_color_code"], row["original_sku"])
                    if identity not in products:
                        result["unmatched_purchase_rows"] += 1
                        continue
                    item, period_index = products[identity], row["period"]
                    for q in range(max(1, period_index), 5):
                        item["received"][q-1] = str(Decimal(item["received"][q-1]) + Decimal(row["quantity"]))
                        if period_index == q:
                            item["inbound"][q-1] = str(Decimal(item["inbound"][q-1]) + Decimal(row["quantity"]))
                        item["inbound_dates"][q-1].update(day.isoformat() for day in row["inbound_dates"])
                        item["orders"][q-1].update(order for order in (row["orders"] or []) if order)
                        item["unknown_orders"][q-1] |= row["unknown_orders"] > 0
    if zero_quarter is not None:
        connection.execution_options(stream_results=False, yield_per=None)
        try:
            with connection.begin_nested():
                connection.execute(text("SET LOCAL statement_timeout = '5s'"))
                _verify_zero_sales(connection, inspector, matcher, products, result, year, zero_quarter)
                connection.execute(text("SET LOCAL statement_timeout = '25s'"))
        except OperationalError as error:
            if getattr(error.orig, "sqlstate", None) != "57014":
                raise
            result["zero_checked"] = False
            result["zero_candidates"] = []
            result["source_issues"].append("零动销原始日销核对超时，其他季度指标仍可查看。")
    if not result["purchase_ready"]:
        result["source_issues"].append("采购入库候选视图尚未就绪，进货、售罄和首单判断暂不可用。")
    for item in products.values():
        item["orders"] = [sorted(orders) for orders in item["orders"]]
        item["inbound_dates"] = [sorted(days, reverse=True) for days in item["inbound_dates"]]
    return result


def _verify_zero_sales(connection, inspector, matcher, products, facts, year, quarter):
    # Channel rollups can omit raw positive sales, including same-day full
    # returns. Confirm candidate products against both sales feeds.
    if not facts["sales_end"] or not facts["stock_date"]:
        return
    end = date.fromisoformat(facts["sales_end"])
    begin, after = quarter_bounds(year, quarter)
    cutoff = min(end, after-timedelta(days=1))
    targets = {}
    covered = set(facts["sales_dates"])
    for key, p in products.items():
        launch = date.fromisoformat(p["launch_date"])
        if (launch < begin or (cutoff-launch).days < 15 or Decimal(p["available_quantity"] or 0) <= 0
                or p.get("sales_ambiguous") or not matcher.source_codes((key,))):
            continue
        if any((launch+timedelta(days=n)).isoformat() not in covered for n in range((cutoff-launch).days+1)):
            continue
        if any(gross > 0 and p["launch_date"] <= day <= cutoff.isoformat()
               for day, gross, _ in facts["sales"].get(str(p["id"]), ())):
            continue
        targets[key] = (launch, cutoff)
    found = _zero_sales_evidence(connection, inspector, matcher, targets)
    if found is None:
        return
    facts["zero_checked"] = True
    facts["zero_candidates"] = [key[1] for key in targets]
    for candidate in found:
        facts["zero_sales_evidence"][str(candidate[1])] = True


def _zero_sales_evidence(connection, inspector, matcher, targets):
    """Shared positive raw sales check for a bounded set of matched products."""
    jst_columns = {column["name"] for column in inspector.get_columns("jst_daily_sales")}
    vip_columns = {column["name"] for column in inspector.get_columns("vip_daily_sales")}
    if (not {"product_code", "style_code", "channel", "sales_quantity"} <= jst_columns
            or not {"goods_code", "style_code", "sales_quantity"} <= vip_columns):
        return None
    if not targets:
        return set()
    ambiguous_codes = defaultdict(set)
    for key in targets:
        product = matcher.products[key]
        for alias in {code(product["sku"]), code(product["original_sku"]), product["barcode_base"]} - {""}:
            if len(matcher.aliases[alias]) > 1:
                ambiguous_codes[alias].add(key)
    codes = sorted(set(matcher.source_codes(targets)) | ambiguous_codes.keys())
    params = {"start": min(window[0] for window in targets.values()),
              "end": max(window[1] for window in targets.values()), "codes": codes}
    # Daily-sales import strips surrounding whitespace. Preserve original
    # catalogue case variants while leaving the source columns indexable.
    params["codes"] = _indexed_sales_codes(matcher, targets, codes)
    found = set()
    for table, goods, extra in (("jst_daily_sales", "product_code", """
            AND coalesce(channel, '') NOT ILIKE '%采购%' AND coalesce(channel, '') NOT ILIKE '%-公司'
            AND coalesce(channel, '') NOT ILIKE '%VMI%'"""), ("vip_daily_sales", "goods_code", "")):
        for field in (goods, "style_code"):
            sql = f"""SELECT DISTINCT sales_date, {goods}, style_code FROM {table}
                WHERE sales_date BETWEEN :start AND :end AND sales_quantity > 0
                AND {field}=ANY(:codes) {extra}"""
            with connection.execute(text(sql).execution_options(yield_per=5000), params) as rows:
                for day, goods_code, style in rows:
                    key = matcher.resolve(goods_code, style)
                    possible = ((key,) if key is not None else
                                ambiguous_codes.get(code(goods_code), set()) | ambiguous_codes.get(code(style), set()))
                    for candidate in possible:
                        if candidate in targets and targets[candidate][0] <= day <= targets[candidate][1]:
                            found.add(candidate)
    return found


def _indexed_sales_codes(matcher, keys, normalized):
    codes = set(normalized)
    codes.update(value.lower() for value in normalized)
    for key in keys:
        item = matcher.products[key]
        for value in (item["sku"], item.get("original_sku")):
            original = str(value or "").strip()
            if original and code(original) in codes:
                codes.add(original)
    return sorted(codes)


def load_seasonal_analysis_facts(repository, brand, year, *, refresh=False, today=None, zero_quarter=None):
    today = today or datetime.now(timezone(timedelta(hours=8))).date()
    key = (id(repository.engine), brand, year, today, zero_quarter)
    def cached():
        with _lock:
            hit = _cache.get(key)
            if hit and monotonic()-hit[0] < TTL:
                _cache.move_to_end(key)
                return orjson.loads(hit[1])
    if not refresh:
        hit = cached()
        if hit is not None:
            return hit
    with _build_lock:
        if not refresh:
            hit = cached()
            if hit is not None:
                return hit
        with repository.engine.connect().execution_options(isolation_level="REPEATABLE READ") as connection, connection.begin():
            connection.execute(text("SET TRANSACTION READ ONLY"))
            connection.execute(text("SET LOCAL statement_timeout = '25s'"))
            result = _load(connection, repository, brand, year, today, zero_quarter=zero_quarter)
        encoded = orjson.dumps(result)
        with _lock:
            _cache.pop(key, None)
            if len(encoded) <= MAX_BYTES:
                _cache[key] = (monotonic(), encoded)
            while _cache and (len(_cache)>4 or sum(len(value[1]) for value in _cache.values())>MAX_BYTES):
                _cache.popitem(last=False)
        return result
