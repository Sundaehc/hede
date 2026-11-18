"""Read one seasonal product's source records without expanding the list query."""
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from math import ceil

from sqlalchemy import inspect, text

from domain.factory_channel_sales import platform_name, shop_channel_key
from domain.seasonal_analysis import quarter_bounds
from domain.stock_alerts import launch_day
from storage.seasonal_analysis_facts import _catalog, _indexed_sales_codes, _receipt_references
from storage.stock_alert_facts import _sales_dates

RECEIPT_PAGE_SIZE = 20


def _receipts(connection, matcher, key, goods_codes, start, end, page, show_numbers):
    if end is None or end < start:
        return None
    references = []
    if goods_codes:
        with connection.execution_options(stream_results=True, yield_per=1000).execute(text("""SELECT DISTINCT
            goods_code, style_color_code, original_sku FROM v_jst_purchase_inbound_age_candidates
            WHERE inbound_date BETWEEN :start AND :end AND goods_code=ANY(:goods)"""),
            {"start": start, "end": end, "goods": goods_codes}) as rows:
            references = [tuple(row) for row in rows if matcher.resolve(*row) == key]
        connection.execution_options(stream_results=False, yield_per=None)
    if not references:
        return {"quantity": "0", "items": [], "total": 0, "page": 1, "pages": 1}
    params = {
        "goods": [row[0] for row in references], "styles": [row[1] for row in references],
        "originals": [row[2] for row in references], "start": start, "end": end,
        "limit": RECEIPT_PAGE_SIZE,
    }
    # Match the full code tuple. A goods code alone may be reused by another
    # style; it is an index filter, never the rule for including a row.
    eligible = """FROM v_jst_purchase_inbound_age_candidates r
        WHERE r.inbound_date BETWEEN :start AND :end AND r.goods_code=ANY(:goods)
        AND EXISTS (SELECT 1 FROM unnest(CAST(:goods AS text[]), CAST(:styles AS text[]),
            CAST(:originals AS text[])) AS m(goods, style, original)
            WHERE r.goods_code=m.goods AND r.style_color_code IS NOT DISTINCT FROM m.style
            AND r.original_sku IS NOT DISTINCT FROM m.original)"""
    grouping = " GROUP BY r.inbound_date, r.inbound_id, nullif(trim(r.purchase_order_id),'')"
    totals = connection.execute(text("SELECT count(*) AS total, coalesce(sum(quantity),0) AS quantity FROM ("
        "SELECT sum(r.quantity) AS quantity " + eligible + grouping + ") grouped"), params).mappings().one()
    pages = max(1, ceil(totals["total"] / RECEIPT_PAGE_SIZE))
    page = min(page, pages)
    rows = connection.execute(text("SELECT r.inbound_date, sum(r.quantity) AS quantity" +
        (", r.inbound_id, nullif(trim(r.purchase_order_id),'') AS purchase_order_id" if show_numbers else "") +
        " " + eligible + grouping + " ORDER BY r.inbound_date DESC, r.inbound_id, nullif(trim(r.purchase_order_id),'')"
        " LIMIT :limit OFFSET :offset"), params | {"offset": (page-1)*RECEIPT_PAGE_SIZE}).mappings()
    return {"quantity": str(totals["quantity"]), "total": totals["total"], "page": page, "pages": pages,
            "items": [dict(row) | {"quantity": str(row["quantity"])} for row in rows]}


def _channel_sales(connection, inspector, matcher, key, start, end):
    result = {"start": start, "end": end, "first_sale_date": None, "missing_days": None, "channels": []}
    if not start or not end or start > end:
        return result
    sources = ("jst_daily_sales", "vip_daily_sales")
    date_sets = [set(_sales_dates(connection, name, end, start)) for name in sources]
    covered = date_sets[0] & date_sets[1]
    result["missing_days"] = (end-start).days+1-len(covered)
    codes = matcher.source_codes((key,))
    if not codes:
        result["missing_days"] = None
        return result
    mappings = {}
    if inspector.has_table("product_goods_shop_channel_mappings"):
        for shop, channel in connection.execute(text("SELECT shop_name, channel FROM product_goods_shop_channel_mappings WHERE brand=:brand"), {"brand": key[0]}):
            if shop_channel_key(shop):
                mappings[shop_channel_key(shop)] = platform_name(channel)
    params = {"start": start, "end": end, "codes": _indexed_sales_codes(matcher, (key,), codes)}
    totals = defaultdict(lambda: [0, 0])
    vip_dates = set()
    positive_dates = set()
    def add(channel, day, gross, net):
        if not gross and not net:
            return
        totals[channel][0] += gross
        totals[channel][1] += net
        if gross > 0:
            positive_dates.add(day)

    with connection.execution_options(stream_results=True, yield_per=1000).execute(text("""SELECT
        sales_date, goods_code, style_code, sum(coalesce(sales_quantity,0)) AS quantity FROM vip_daily_sales
        WHERE sales_date BETWEEN :start AND :end AND coalesce(sales_quantity,0) <> 0
        AND (goods_code=ANY(:codes) OR style_code=ANY(:codes))
        GROUP BY sales_date, goods_code, style_code"""), params) as rows:
        for day, goods, style, quantity in rows:
            if matcher.resolve(goods, style) == key:
                vip_dates.add(day)
                add("唯品", day, max(0, int(quantity)), int(quantity))
    with connection.execution_options(stream_results=True, yield_per=1000).execute(text("""SELECT
        sales_date, product_code, style_code, channel,
        sum(greatest(coalesce(sales_quantity,0),0)) AS gross, sum(coalesce(net_sales_quantity,0)) AS net
        FROM jst_daily_sales WHERE sales_date BETWEEN :start AND :end
        AND (coalesce(sales_quantity,0) > 0 OR coalesce(net_sales_quantity,0) <> 0)
        AND (product_code=ANY(:codes) OR style_code=ANY(:codes))
        AND coalesce(channel,'') NOT ILIKE '%采购%' AND coalesce(channel,'') NOT ILIKE '%-公司'
        AND coalesce(channel,'') NOT ILIKE '%VMI%'
        GROUP BY sales_date, product_code, style_code, channel"""), params) as rows:
        for day, goods, style, raw_channel, gross, net in rows:
            channel = platform_name(raw_channel, mappings)
            if matcher.resolve(goods, style) == key and not (channel == "唯品" and day in vip_dates):
                add(channel, day, int(gross), int(net))
    first = min(positive_dates, default=None)
    # A sale after an earlier missing day is observed evidence, but not a confirmed first sale.
    if first and all(first - timedelta(days=n) in covered
                     for n in range((first-start).days+1)):
        result["first_sale_date"] = first
    result["channels"] = [{"channel": name, "gross_sales": gross, "net_sales": net}
                          for name, (gross, net) in sorted(totals.items(), key=lambda pair: (-pair[1][0], pair[0]))]
    return result


def load_seasonal_item_review(repository, brand, product_id, year, quarter, *, receipt_page,
                              show_receipt_numbers, today=None):
    today = today or datetime.now(timezone(timedelta(hours=8))).date()
    start, after = quarter_bounds(year, quarter)
    last_day = after-timedelta(days=1)
    key = (brand, product_id)
    with repository.engine.connect().execution_options(isolation_level="REPEATABLE READ") as connection, connection.begin():
        connection.execute(text("SET TRANSACTION READ ONLY"))
        connection.execute(text("SET LOCAL statement_timeout = '15s'"))
        inspector = inspect(connection)
        matcher, _ = _catalog(connection, repository, brand, inspector)
        product = matcher.products.get(key)
        if not product:
            return None
        launch = launch_day(product.get("launch_date"))
        if launch and not (start <= launch < after and launch < today):
            return None
        purchase_ready = all(inspector.has_table(name) for name in
                             ("mv_jst_purchase_inbound_age_reference", "v_jst_purchase_inbound_age_candidates"))
        receipt_codes = set()
        first = None
        if purchase_ready:
            for _, row in _receipt_references(connection, matcher, (key,)):
                receipt_codes.add(row["goods_code"])
                day = row["first_inbound_date"]
                if day and day <= min(today, last_day):
                    first = min(first, day) if first else day
        if not launch and not (first and start <= first < after):
            return None
        sources_ready = all(inspector.has_table(name) for name in ("jst_daily_sales", "vip_daily_sales"))
        cutoff = None
        if sources_ready:
            ends = [connection.execute(text(f"SELECT max(sales_date) FROM {name}")).scalar()
                    for name in ("jst_daily_sales", "vip_daily_sales")]
            if all(ends):
                cutoff = min(today-timedelta(days=1), last_day, *ends)
        receipt_end = cutoff if launch else min(today, last_day)
        receipts = _receipts(connection, matcher, key, sorted(receipt_codes), start, receipt_end,
                             receipt_page, show_receipt_numbers) if purchase_ready else None
        sales = _channel_sales(connection, inspector, matcher, key, launch or first, cutoff)
        return {"first_inbound_date": first, "launch_date": launch, "sales": sales, "receipts": receipts,
                "receipt_end": receipt_end, "show_receipt_numbers": show_receipt_numbers}
