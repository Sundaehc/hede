"""Shared exit policies and weekly inventory observations."""
from collections import OrderedDict, defaultdict
from datetime import datetime, timedelta, timezone
from threading import Lock
from time import monotonic
from zlib import compress, decompress

import orjson

from sqlalchemy import (CheckConstraint, Column, Date, DateTime, Integer, MetaData, Table, Text, insert,
                        inspect, select, text, update)
from sqlalchemy.exc import IntegrityError

from domain.stock_alerts import ArchiveMatcher
from domain.stock_overview import build_overview
from storage.stock_alert_facts import _load as _load_history, _sales_dates
from storage.stock_alert_rules import RuleConflict
from storage.stock_replenishment_facts import _catalog, _load as _load_recent

POLICIES = Table("stock_overview_exit_policies", MetaData(),
    Column("brand", Text, primary_key=True), Column("year", Text, primary_key=True), Column("season", Text, primary_key=True),
    Column("sale_start", Date), Column("exit_date", Date, nullable=False), Column("lead_days", Integer, nullable=False),
    Column("target_rate", Integer, nullable=False), Column("channel", Text, nullable=False),
    Column("version", Integer, nullable=False), Column("updated_by", Integer, nullable=False),
    Column("updated_at", DateTime(timezone=True), nullable=False),
    CheckConstraint("sale_start IS NULL OR sale_start <= exit_date"),
    CheckConstraint("lead_days BETWEEN 1 AND 365"), CheckConstraint("target_rate BETWEEN 1 AND 100"))


class StockOverviewPolicyRepository:
    def __init__(self, engine):
        self.engine = engine

    def create_tables(self):
        POLICIES.create(self.engine, checkfirst=True)

    def list_rules(self, brand):
        columns = [POLICIES.c[key] for key in ("year", "season", "sale_start", "exit_date", "lead_days", "target_rate", "channel", "version")]
        with self.engine.connect() as connection:
            return {(row["year"], row["season"]): dict(row) for row in connection.execute(
                select(*columns).where(POLICIES.c.brand == brand)).mappings()}

    def save(self, *, brand, year, season, version, user_id, **fields):
        scope = (POLICIES.c.brand == brand, POLICIES.c.year == year, POLICIES.c.season == season)
        values = dict(**fields, version=version + 1, updated_by=user_id, updated_at=datetime.now(timezone.utc))
        try:
            with self.engine.begin() as connection:
                if version == 0:
                    connection.execute(insert(POLICIES).values(brand=brand, year=year, season=season, **values))
                elif connection.execute(update(POLICIES).where(*scope, POLICIES.c.version == version).values(**values)).rowcount != 1:
                    raise RuleConflict("规则版本已变化，请重新打开设置后保存")
        except IntegrityError:
            raise RuleConflict("该范围已有规则，请重新打开设置后保存") from None


# Calculations are never returned before permissions are checked by the route.
# Keep facts and rule-dependent results separate so changing a rule does not scan sources again.
_TTL = 120
_MAX_ENTRIES = 4
_MAX_BYTES = 8 * 1024 * 1024
_lock = Lock()
_cache = OrderedDict()
_builders = {}


def _overview_facts(repository, brand, today):
    with repository.engine.connect().execution_options(isolation_level="REPEATABLE READ") as conn, conn.begin():
        conn.exec_driver_sql("SET TRANSACTION READ ONLY")
        conn.exec_driver_sql("SET LOCAL statement_timeout = '25s'")
        shared = {}
        recent = _load_recent(conn, repository, brand, today, 30, overview=True, shared=shared)
        historic = _load_history(conn, repository, brand, today, shared=shared, verify_zero=True) if shared else recent
        return recent, historic


def load_stock_overview(repository, brand, today, *, refresh, read_rules):
    """Reuse compressed source and result snapshots across pages and filters."""
    key = (repository.engine, brand, today)
    started = monotonic()
    with _lock:
        lock, users = _builders.get(key, (Lock(), 0))
        _builders[key] = lock, users + 1
    try:
        with lock:
            with _lock:
                entry = _cache.get(key)
                if entry:
                    _cache.move_to_end(key)
            fresh = entry and monotonic() - entry[0] < _TTL and (not refresh or entry[0] >= started)
            loaded_at, sources, old_rules, output, _ = entry if fresh else (0, None, None, None, 0)
            alert_rules, supplier_rules, policies = read_rules()
            rules = (alert_rules, supplier_rules, policies)
            if rules == old_rules:
                return orjson.loads(decompress(output)), policies
            if sources is None:
                facts = _overview_facts(repository, brand, today)
                loaded_at = monotonic()
                sources = compress(orjson.dumps(facts), level=1)
            else:
                facts = orjson.loads(decompress(sources))
            result = build_overview(*facts, alert_rules, supplier_rules, policies, today)
            output = compress(orjson.dumps(result), level=1)
            footprint = len(sources) + len(output)
            with _lock:
                _cache.pop(key, None)
                if footprint <= _MAX_BYTES:
                    _cache[key] = (loaded_at, sources, rules, output, footprint)
                while len(_cache) > _MAX_ENTRIES or sum(item[-1] for item in _cache.values()) > _MAX_BYTES:
                    _cache.popitem(last=False)
            return result, policies
    finally:
        with _lock:
            _, users = _builders[key]
            if users == 1:
                del _builders[key]
            else:
                _builders[key] = lock, users - 1


def weekly_observations(repository, brand, week_start, week_end, completed, clearance):
    result = {"net_sales": None, "clearance_net_sales": None, "stock_change": None, "recovery_amount": None}
    if not completed:
        return result
    before, after = week_start - timedelta(days=1), week_end
    with repository.engine.connect().execution_options(isolation_level="REPEATABLE READ") as conn, conn.begin():
        conn.execute(text("SET TRANSACTION READ ONLY"))
        conn.execute(text("SET LOCAL statement_timeout = '12s'"))
        inspector = inspect(conn)
        products, sizes = _catalog(conn, repository)
        matcher = ArchiveMatcher(products, {name: {size["barcode"] for size in group if size["barcode"]} for name, group in sizes.items()})
        selected = {(brand, item) for item in completed}
        selected_clearance = {(brand, item) for item in clearance}
        by_sku = defaultdict(set)
        for key, product in matcher.products.items():
            if key[0] == brand:
                by_sku[product["sku"]].add(key)
        if not selected.issubset(matcher.products) or any(by_sku[matcher.products[key]["sku"]] != {key} for key in selected):
            return result
        if all(inspector.has_table(name) for name in ("jst_daily_sales", "vip_daily_sales", "factory_channel_sales_daily_summaries")):
            params = {"brand": brand, "first": week_start, "last": week_end}
            dates = [len(_sales_dates(conn, name, week_end, week_start)) for name in ("jst_daily_sales", "vip_daily_sales")]
            dates.append(conn.execute(text("SELECT COUNT(DISTINCT sales_date) FROM factory_channel_sales_daily_summaries "
                "WHERE brand = :brand AND match_status = 'date_marker' AND sales_date BETWEEN :first AND :last"), params).scalar())
            if dates == [7, 7, 7]:
                rows = conn.execute(text("""SELECT product_code, sum(quantity) AS net,
                    sum(quantity) FILTER (WHERE channel_group = 'clearance') AS clearance
                    FROM factory_channel_sales_daily_summaries WHERE brand = :brand AND match_status = 'matched'
                    AND sales_date BETWEEN :first AND :last AND product_code = ANY(:codes) GROUP BY product_code"""),
                    {**params, "codes": [matcher.products[key]["sku"] for key in selected]}).mappings()
                result["net_sales"], result["clearance_net_sales"] = 0, 0 if selected_clearance else None
                clearance_skus = {matcher.products[key]["sku"] for key in selected_clearance}
                for row in rows:
                    result["net_sales"] += int(row["net"] or 0)
                    if row["product_code"] in clearance_skus:
                        result["clearance_net_sales"] += int(row["clearance"] or 0)
        if inspector.has_table("jst_size_stock_snapshots"):
            codes = matcher.source_codes(selected)
            rows = conn.execute(text("""SELECT snapshot_date, product_code, size, stock_qty FROM jst_size_stock_snapshots
                WHERE snapshot_date IN (:before, :after) AND product_code = ANY(:codes)"""),
                {"before": before, "after": after, "codes": codes}).mappings()
            stock = defaultdict(lambda: defaultdict(int))
            for row in rows:
                identity = matcher.resolve(row["product_code"])
                if identity in selected:
                    stock[row["snapshot_date"]][identity] += int(row["stock_qty"])
            if stock[before].keys() == selected == stock[after].keys():
                result["stock_change"] = sum(stock[after].values()) - sum(stock[before].values())
        return result
