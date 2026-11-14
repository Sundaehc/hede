"""Read-only, bounded stock alert facts using existing compact summaries."""
from bisect import bisect_left, bisect_right
from collections import OrderedDict, defaultdict
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from threading import Lock
from time import monotonic
import json

import orjson
from sqlalchemy import inspect, select, text

from domain.stock_alerts import ArchiveMatcher, launch_day
from domain.size_group_schema import SIZE_GROUPS_TABLE, SIZE_GROUP_ITEMS_TABLE

_cache, _lock, _build_lock = OrderedDict(), Lock(), Lock()
TTL, MAX_BYTES = 120, 8 * 1024 * 1024


def _sales_dates(connection, name, end):
    first = connection.execute(text(f"SELECT min(sales_date) FROM {name}")).scalar()
    if not first or first > end:
        return []
    return list(connection.execute(text(f"""SELECT CAST(day AS date) FROM
        generate_series(CAST(:start AS date), CAST(:end AS date), INTERVAL '1 day') day
        WHERE EXISTS (SELECT 1 FROM {name} f WHERE f.sales_date = CAST(day AS date)) ORDER BY day"""),
        {"start": first, "end": end}).scalars())


def _load(connection, repository, brand, today):
    inspector = inspect(connection)
    required = ("jst_full_stock", "jst_daily_sales", "vip_daily_sales", "factory_channel_sales_daily_summaries")
    missing = [name for name in required if not inspector.has_table(name)]
    if missing:
        return {"items": [], "seasons": [], "stock_date": None, "sales_end": None, "ready": False,
                "unmatched_stock_rows": 0, "source_issues": ["缺少数据源：" + "、".join(missing)]}
    products = []
    for key in repository.product_archive_brands():
        table = repository._table_for_brand(key)
        if inspector.has_table(table.name):
            fields = ("id", "sku", "original_sku", "product_name", "color", "color_code", "barcode_build_rule", "size_range", "launch_date", "season_category", "year")
            products.extend({**dict(row), "brand": key} for row in connection.execute(
                select(*(table.c[field] for field in fields)).where(table.c.deleted_at.is_(None))).mappings())
    sizes = defaultdict(set)
    for group, barcode in connection.execute(select(SIZE_GROUPS_TABLE.c.name, SIZE_GROUP_ITEMS_TABLE.c.barcode)
            .join(SIZE_GROUP_ITEMS_TABLE, SIZE_GROUP_ITEMS_TABLE.c.size_group_id == SIZE_GROUPS_TABLE.c.id)):
        if str(barcode or "").strip():
            sizes[group].add(str(barcode).strip().upper())
    matcher = ArchiveMatcher(products, sizes)
    del products
    stock_date = connection.execute(text("SELECT max(sync_date) FROM jst_full_stock")).scalar()
    ends = [connection.execute(text(f"SELECT max(sales_date) FROM {name}")).scalar() for name in ("jst_daily_sales", "vip_daily_sales")]
    end = min([today - timedelta(days=1), *ends]) if all(ends) else None
    stock, unmatched = defaultdict(Decimal), 0
    rows = connection.execution_options(stream_results=True).execute(text("""SELECT product_code, style_code,
        sum(available_qty) AS quantity FROM jst_full_stock WHERE sync_date = :day AND available_qty <> 0
        GROUP BY product_code, style_code"""), {"day": stock_date})
    for row in rows.mappings():
        identity = matcher.resolve(row["product_code"], row["style_code"])
        if identity is None:
            unmatched += 1
        elif identity[0] == brand:
            stock[identity] += Decimal(row["quantity"])
    rows.close()
    selected = {key: matcher.products[key] for key, quantity in stock.items() if quantity > 0}
    inbounds = defaultdict(lambda: {"first": None, "last": None, "quantity": Decimal(0)})
    if selected and inspector.has_table("mv_jst_purchase_inbound_age_reference"):
        codes = matcher.source_codes(selected)
        rows = connection.execution_options(stream_results=True).execute(text("""SELECT goods_code, style_color_code,
            original_sku, first_inbound_date, last_inbound_date, received_quantity
            FROM mv_jst_purchase_inbound_age_reference
            WHERE style_color_code = ANY(:codes) OR goods_code = ANY(:codes) OR original_sku = ANY(:codes)"""), {"codes": codes})
        for row in rows.mappings():
            identity = matcher.resolve(row["goods_code"], row["style_color_code"], row["original_sku"])
            if identity not in selected:
                continue
            target = inbounds[identity]
            for field, operation, source in (("first", min, "first_inbound_date"), ("last", max, "last_inbound_date")):
                dates = [value for value in (target[field], row[source]) if value]
                target[field] = operation(dates) if dates else None
            target["quantity"] += Decimal(row["received_quantity"] or 0)
        rows.close()
    launches = {key: launch_day(item.get("launch_date")) for key, item in selected.items()}
    sales = {}
    if end and selected:
        cohort = [{"sku": item["sku"], "launch_date": launches[key].isoformat()} for key, item in selected.items()
                  if launches[key] and launches[key] <= end]
        rows = connection.execute(text("""WITH cohort AS (
            SELECT * FROM jsonb_to_recordset(CAST(:cohort AS jsonb)) AS p(sku text, launch_date date))
            SELECT f.product_code, sum(f.quantity) AS net, sum(f.gross_quantity) AS gross,
                sum(f.return_quantity) AS returns, max(f.sales_date) FILTER (WHERE f.gross_quantity > 0) AS last
            FROM factory_channel_sales_daily_summaries f JOIN cohort p ON p.sku = f.product_code
            WHERE f.brand = :brand AND f.match_status = 'matched' AND f.sales_date >= p.launch_date AND f.sales_date <= :end
            GROUP BY f.product_code"""), {"cohort": json.dumps(cohort), "brand": brand, "end": end})
        sales = {row["product_code"]: dict(row) for row in rows.mappings()}
    coverage = {name: _sales_dates(connection, name, end) if end else [] for name in ("jst_daily_sales", "vip_daily_sales")}
    summary_dates = sorted(set(connection.execute(text("""SELECT sales_date FROM factory_channel_sales_daily_summaries
        WHERE brand = :brand AND match_status = 'date_marker' AND sales_date <= :end"""), {"brand": brand, "end": end}).scalars())) if end else []
    result = []
    for key, item in selected.items():
        launch, inbound = launches[key], inbounds[key]
        sale = sales.get(item["sku"], {"net": 0, "gross": 0, "returns": 0, "last": None})
        issues, inbound_issues = [], []
        if launch is None:
            issues.append("上市时间缺失或格式无效")
        elif end is None:
            issues.append("缺少日销数据")
        elif launch > end:
            issues.append("上市时间晚于日销截止日")
        else:
            expected = (end - launch).days + 1
            for dates, label in [(coverage["jst_daily_sales"], "聚水潭日销"), (coverage["vip_daily_sales"], "唯品日销"), (summary_dates, "日销计算汇总")]:
                missing_days = expected - (bisect_right(dates, end) - bisect_left(dates, launch))
                if missing_days:
                    issues.append(f"{label}缺少 {missing_days} 天")
        rate = Decimal(sale["net"]) / inbound["quantity"] * 100 if inbound["quantity"] > 0 else None
        if inbound["last"] and end and inbound["last"] > end:
            rate = None
            inbound_issues.append("最近采购入库晚于日销截止日，需等待数据对齐")
        result.append({"id": item["id"], "brand": brand, "sku": item["sku"], "original_sku": item.get("original_sku"),
            "product_name": item.get("product_name"), "color": item.get("color"), "year": item.get("year"), "season": item.get("season_category"),
            "launch_date": str(launch) if launch else None, "listed_days": (end - launch).days if launch and end and launch <= end else None,
            "first_inbound_date": str(inbound["first"]) if inbound["first"] else None, "last_inbound_date": str(inbound["last"]) if inbound["last"] else None,
            "available_quantity": str(stock[key]), "purchase_received_reference": str(inbound["quantity"]), "gross_sales": str(sale["gross"]),
            "net_sales": str(sale["net"]), "sales_returns": str(sale["returns"]), "last_sales_date": str(sale["last"]) if sale["last"] else None,
            "sell_through_rate": str(rate.quantize(Decimal("0.01"))) if rate is not None else None,
            "sales_issues": issues, "inbound_issues": inbound_issues})
    notices = ["上市时间取商品档案，平台上架时间尚未接入；上市天数算至日销截止日。采购首入、末入单独展示，不代表现存商品的准确实物库龄。",
               "采购退货数量目前缺失，售罄率以历史正向采购入库量（含补货）为分母，仅供参考，需核对后处理。",
               "销量复用聚水潭、唯品日销生成的渠道日汇总，唯品同商品同日去重；唯品日销未单列退货。",
               "新增商品或修改货号后，历史销售识别需等待渠道日汇总重新生成；本页刷新仅重新查询现有汇总。"]
    if end and end < today - timedelta(days=1):
        notices.append(f"日销尚未更新至昨日，当前按 {end} 判断。")
    if stock_date and stock_date < today:
        notices.append(f"库存尚未同步至今日，当前取 {stock_date} 快照。")
    if not summary_dates:
        notices.append("本品牌尚无已生成的渠道日汇总，相关商品列入数据待核对。")
    return {"items": result, "stock_date": str(stock_date) if stock_date else None, "sales_end": str(end) if end else None,
            "ready": bool(stock_date and end), "seasons": sorted({item["season"] for item in result if item["season"]}),
            "source_issues": notices, "unmatched_stock_rows": unmatched}


def load_stock_alert_facts(repository, brand, *, refresh=False, today=None):
    today = today or datetime.now(timezone(timedelta(hours=8))).date()
    key = (id(repository.engine), brand, today)
    def cached():
        with _lock:
            hit = _cache.get(key)
            if hit and monotonic() - hit[0] < TTL:
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
            result = _load(connection, repository, brand, today)
        encoded = orjson.dumps(result)
        with _lock:
            _cache.pop(key, None)
            if len(encoded) <= MAX_BYTES:
                _cache[key] = (monotonic(), encoded)
            while _cache and (len(_cache) > 4 or sum(len(entry[1]) for entry in _cache.values()) > MAX_BYTES):
                _cache.popitem(last=False)
        return result
