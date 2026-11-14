"""Bounded, read-only recent sales and size stock; no raw sales-detail scans."""
from collections import OrderedDict, defaultdict
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from threading import Lock
from time import monotonic

import orjson
from sqlalchemy import inspect, select, text

from domain.size_group_schema import SIZE_GROUPS_TABLE, SIZE_GROUP_ITEMS_TABLE
from domain.product_defaults import apply_product_defaults
from domain.stock_alerts import ArchiveMatcher, code, launch_day

_cache, _lock, _build_lock = OrderedDict(), Lock(), Lock()
TTL, MAX_BYTES = 120, 8 * 1024 * 1024


def _catalog(connection, repository):
    products, groups = [], defaultdict(list)
    inspector = inspect(connection)
    for brand in repository.product_archive_brands():
        table = repository._table_for_brand(brand)
        if not inspector.has_table(table.name):
            continue
        fields = ("id", "sku", "original_sku", "product_name", "color", "color_code", "barcode_build_rule",
                  "size_range", "supplier_name", "launch_date")
        for row in connection.execute(select(*(table.c[field] for field in fields)).where(table.c.deleted_at.is_(None))).mappings():
            item = {**dict(row), "brand": brand}
            apply_product_defaults(brand, item)
            if code(item.get("sku")):
                products.append(item)
    if inspector.has_table(SIZE_GROUPS_TABLE.name) and inspector.has_table(SIZE_GROUP_ITEMS_TABLE.name):
        rows = connection.execute(select(SIZE_GROUPS_TABLE.c.name, SIZE_GROUP_ITEMS_TABLE.c.size_name,
            SIZE_GROUP_ITEMS_TABLE.c.barcode).join(SIZE_GROUP_ITEMS_TABLE,
            SIZE_GROUP_ITEMS_TABLE.c.size_group_id == SIZE_GROUPS_TABLE.c.id)
            .order_by(SIZE_GROUPS_TABLE.c.name, SIZE_GROUP_ITEMS_TABLE.c.sort_order, SIZE_GROUP_ITEMS_TABLE.c.id))
        for group, name, barcode in rows:
            groups[group].append({"name": str(name), "barcode": code(barcode)})
    return products, dict(groups)


def supplier_catalog(repository, brand):
    with repository.engine.connect() as connection:
        products, groups = _catalog(connection, repository)
    suppliers = defaultdict(set)
    for item in products:
        supplier = str(item.get("supplier_name") or "").strip()
        if item["brand"] == brand and supplier:
            suppliers[supplier].add(str(item.get("size_range") or ""))
    return {supplier: {group: groups.get(group, []) for group in sorted(names)}
            for supplier, names in sorted(suppliers.items())}


def _load(connection, repository, brand, today, window_days):
    products, groups = _catalog(connection, repository)
    matcher = ArchiveMatcher(products, {name: {size["barcode"] for size in sizes if size["barcode"]} for name, sizes in groups.items()})
    del products
    selected = {key: value for key, value in matcher.products.items() if key[0] == brand}
    catalog = defaultdict(set)
    for item in selected.values():
        supplier = str(item.get("supplier_name") or "").strip()
        if supplier:
            catalog[supplier].add(str(item.get("size_range") or ""))
    options = {supplier: {group: groups.get(group, []) for group in sorted(names)} for supplier, names in sorted(catalog.items())}
    required = ("jst_full_stock", "jst_daily_sales", "vip_daily_sales", "factory_channel_sales_daily_summaries")
    inspector = inspect(connection)
    missing = [name for name in required if not inspector.has_table(name)]
    base = {"window_days": window_days, "supplier_options": options, "stock_date": None, "sales_start": None,
            "sales_end": None, "ready": False, "unmatched_stock_rows": 0, "source_issues": []}
    if missing:
        return {**base, "items": [], "source_issues": ["缺少数据源：" + "、".join(missing)]}
    stock_date = launch_day(connection.execute(text("SELECT max(sync_date) FROM jst_full_stock")).scalar())
    ends = [launch_day(connection.execute(text(f"SELECT max(sales_date) FROM {name}")).scalar())
            for name in ("jst_daily_sales", "vip_daily_sales")]
    end = min(today - timedelta(days=1), stock_date - timedelta(days=1), *ends) if stock_date and all(ends) else None
    start = end - timedelta(days=window_days - 1) if end else None
    covered = {}
    if end:
        for name in ("jst_daily_sales", "vip_daily_sales", "factory_channel_sales_daily_summaries"):
            condition = " AND brand = :brand AND match_status = 'date_marker'" if name.endswith("summaries") else ""
            covered[name] = {launch_day(day) for day in connection.execute(text(
                f"SELECT DISTINCT sales_date FROM {name} WHERE sales_date BETWEEN :start AND :end{condition}"),
                {"start": start, "end": end, "brand": brand}).scalars()}
    stocks, stock_sizes, transits, transit_sizes = (defaultdict(Decimal) for _ in range(4))
    seen, size_issues, unmatched = set(), defaultdict(set), 0
    rows = connection.execution_options(stream_results=True).execute(text("""SELECT product_code, style_code, size,
        sum(available_qty) AS available, sum(purchase_in_transit_qty) AS transit
        FROM jst_full_stock WHERE sync_date = :day GROUP BY product_code, style_code, size"""), {"day": stock_date})
    for row in rows.mappings():
        identity = matcher.resolve(row["product_code"], row["style_code"])
        if identity is None:
            unmatched += 1
            continue
        if identity not in selected:
            continue
        item = selected[identity]
        seen.add(identity)
        available, transit = (Decimal(str(row[field] or 0)) for field in ("available", "transit"))
        stocks[identity] += available
        transits[identity] += transit
        sizes = groups.get(str(item.get("size_range") or ""), [])
        raw_size = code(row["size"])
        named = {size["name"] for size in sizes if raw_size and raw_size in {code(size["name"]), size["barcode"]}}
        raw_code, prefix = code(row["product_code"]), item["barcode_base"]
        suffix = raw_code[len(prefix):] if raw_code.startswith(prefix) else ""
        encoded = {size["name"] for size in sizes if suffix and size["barcode"] == suffix}
        # Explicit size and rule-based barcode parsing must agree when both resolve.
        matches = named & encoded if named and encoded else named or encoded
        if len(matches) != 1:
            if available or transit:
                size_issues[identity].add("库存明细的尺码无法唯一匹配，请核对尺码组与条码规则")
        else:
            size_name = next(iter(matches))
            stock_sizes[identity, size_name] += available
            transit_sizes[identity, size_name] += transit
    rows.close()
    sku_keys = {item["sku"]: key for key, item in selected.items()}
    sales, returns = defaultdict(Decimal), defaultdict(Decimal)
    if end:
        rows = connection.execution_options(stream_results=True).execute(text("""SELECT product_code, sales_date,
            sum(quantity) AS net, sum(return_quantity) AS returns FROM factory_channel_sales_daily_summaries
            WHERE brand = :brand AND match_status = 'matched' AND sales_date BETWEEN :start AND :end
            GROUP BY product_code, sales_date"""), {"brand": brand, "start": start, "end": end})
        for row in rows.mappings():
            identity = sku_keys.get(row["product_code"])
            if identity is None:
                continue
            launch = launch_day(selected[identity].get("launch_date"))
            if launch and launch_day(row["sales_date"]) < launch:
                continue
            sales[identity] += Decimal(str(row["net"] or 0))
            returns[identity] += Decimal(str(row["returns"] or 0))
        rows.close()
    items = []
    for identity, item in selected.items():
        # Include sold-out products with recent sales, as well as stock/in-transit.
        if not (stocks[identity] or transits[identity] or sales[identity] or returns[identity]):
            continue
        launch, issues = launch_day(item.get("launch_date")), []
        item_start = max(start, launch) if start and launch else start
        observation_days = (end - item_start).days + 1 if end and item_start and item_start <= end else 0
        if not stock_date or identity not in seen:
            issues.append("缺少该商品的库存快照明细")
        if not end:
            issues.append("缺少有效日销截止日")
        elif not observation_days:
            issues.append("上市时间晚于日销截止日")
        else:
            for name, label in (("jst_daily_sales", "聚水潭日销"), ("vip_daily_sales", "唯品日销"),
                                ("factory_channel_sales_daily_summaries", "日销计算汇总")):
                count = sum(item_start <= day <= end for day in covered[name] if day)
                if count < observation_days:
                    issues.append(f"{label}缺少 {observation_days - count} 天")
        group = str(item.get("size_range") or "")
        sizes = groups.get(group, [])
        items.append({"id": item["id"], "brand": brand, "sku": item["sku"], "original_sku": item.get("original_sku"),
                      "product_name": item.get("product_name"), "color": item.get("color"),
                      "supplier": str(item.get("supplier_name") or "").strip(), "size_group": group, "sizes": sizes,
                      "available_quantity": str(stocks[identity]), "purchase_in_transit": str(transits[identity]),
                      "stock_by_size": {size["name"]: str(stock_sizes[identity, size["name"]]) for size in sizes},
                      "transit_by_size": {size["name"]: str(transit_sizes[identity, size["name"]]) for size in sizes},
                      "net_sales": str(sales[identity]), "sales_returns": str(returns[identity]),
                      "observation_days": observation_days, "issues": issues, "size_issues": sorted(size_issues[identity])})
    notices = ["近 7/15/30 天净销量来自聚水潭、唯品日销生成的渠道日汇总，沿用唯品同商品同日去重；唯品日销未单列退货。",
               "分码日需求按使用者填写的尺码配比估算，并非实际尺码销量；近期无正净销量时不生成补货量。",
               "需求覆盖供应商交期加到货后的备货天数。按尺码目标需求减去库存，缺口逐码向上取整。",
               "在途仅展示聚水潭采购在途，不含调拨、退货在途；没有明确到货日期，默认不抵扣。勾选抵扣表示假设全部在途能按时到货。",
               "起订量按当前品牌同一供应商全部商品的有效补货建议合计，与搜索、分页无关；未达起订量只提示差额，不自动凑单。",
               "新增商品或修改货号后，历史销量匹配需等待已有渠道日汇总重建，本页刷新不会重建来源数据。"]
    if stock_date and stock_date < today:
        notices.append(f"库存快照为 {stock_date}，预计可售天数从该快照起算，请核对库存时效。")
    if end and end < today - timedelta(days=1):
        notices.append(f"销量截至 {end}，未更新至昨日，结果仅供参考。")
    return {**base, "items": items, "stock_date": str(stock_date) if stock_date else None,
            "sales_start": str(start) if start else None, "sales_end": str(end) if end else None,
            "ready": bool(stock_date and end), "unmatched_stock_rows": unmatched, "source_issues": notices}


def load_replenishment_facts(repository, brand, *, window_days=30, refresh=False, today=None):
    today = today or datetime.now(timezone(timedelta(hours=8))).date()
    key = id(repository.engine), brand, today, window_days

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
            result = _load(connection, repository, brand, today, window_days)
        encoded = orjson.dumps(result)
        with _lock:
            _cache.pop(key, None)
            if len(encoded) <= MAX_BYTES:
                _cache[key] = monotonic(), encoded
            while _cache and (len(_cache) > 4 or sum(len(entry[1]) for entry in _cache.values()) > MAX_BYTES):
                _cache.popitem(last=False)
        return result
