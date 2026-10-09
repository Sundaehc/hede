"""Weekly missing-data / completeness review of the hede database.

Runs a curated battery of read-only completeness checks, compares the numbers with
the previous run (state file), and writes a Markdown report to the Desktop while
keeping a history copy under ``backend/logs/missing_data_reports/``.

    python -m scripts.review_missing_data
    python -m scripts.review_missing_data --days 90 --output-dir D:\\tmp

Design notes
------------
* Strictly read-only: no table, index or setting is ever modified.
* Checks are split into "required" columns (a value is expected; alert above a
  threshold) and "known" gaps (the column has always been empty; only a
  *worsening* delta versus the previous run is reported, so the same permanent
  finding is not repeated every week as if it were new).
* Row counts come from ``count(*)`` for small tables and from catalog statistics
  for the multi-gigabyte ones, so a weekly run never has to scan 20 GB tables.
  Which one was used is marked in the report.
* Date-coverage checks only look at a recent window, so old, already-explained
  holes do not alarm every week.
* Every check is individually guarded: a failing or slow check is reported as
  such instead of aborting the run.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

from sqlalchemy import create_engine
from domain.jst_monthly_order_identity import monthly_order_record_key_sql

BACKEND_ROOT = Path(__file__).resolve().parent.parent
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from config import load_settings  # noqa: E402

RED, YELLOW, GRAY, OK = "red", "yellow", "gray", "ok"
ICON = {RED: "🔴", YELLOW: "🟡", GRAY: "⚪", OK: "✅"}
IDENT = re.compile(r"^[a-z_][a-z0-9_]*$")

# Below this size a table gets an exact count(*); above it the catalog estimate
# is used instead (and the report says so).
EXACT_COUNT_LIMIT = 300 * 1024 * 1024

ROWCOUNT_TABLES = (
    # 核心业务表：数据丢失最敏感
    "inventory_records", "inventory_details", "suppliers", "warehouses",
    "cbanner_mens_products", "cbanner_womens_products", "yandou_products",
    "eblan_products", "smiley_products", "ni_products", "manual_product_archive_31",
    "product_archive_identities", "product_size_group_mappings", "product_goods_overrides",
    # 分析/快照大表
    "jst_monthly_orders", "jst_product_price", "jst_daily_stock", "jst_size_stock_snapshots",
    "jst_daily_sales", "jst_purchase_inbound_daily", "jst_full_stock", "jst_stock_summary",
    "jst_stock_summary_snapshots", "jst_size_stock", "jst_product_profiles",
    "jst_aftersale_returns", "vip_daily_sales", "vip_product_ops_snapshots",
    "vip_product_daily_snapshots", "vip_product_detail_daily", "vip_product_ops",
    "gj_merged_product_info", "dewu_orders", "fine_table_snapshot_refs", "fine_table_snapshot_batches",
    "product_goods_detail_snapshots", "product_goods_historical_orders",
    "product_goods_historical_sales", "product_tag_assignments", "operation_logs",
)
YEARLY_BASES = ("fine_table_snapshot_refs",)

# (table, date column, label, severity when gaps exist, must_be_daily)
DAILY_SERIES = (
    ("jst_daily_stock", "stock_date_value", "聚水潭库存快照", RED, True),
    ("jst_daily_sales", "sales_date", "聚水潭销售日报", RED, True),
    ("vip_daily_sales", "sales_date", "唯品会销售日报", RED, True),
    ("product_goods_detail_snapshots", "snapshot_date", "商品明细快照", RED, True),
    ("dewu_orders", "order_date", "得物订单", RED, True),
    ("fine_table_snapshot_refs", "snapshot_date", "精细表快照明细", RED, True),
    ("jst_purchase_inbound_daily", "inbound_date", "聚水潭采购入库日报", YELLOW, False),
    ("vip_product_daily_snapshots", "snapshot_date", "唯品会商品日快照", YELLOW, False),
)

ARCHIVE_TABLES = ("cbanner_mens_products", "cbanner_womens_products", "yandou_products",
                  "eblan_products", "smiley_products", "ni_products",
                  "manual_product_archive_31")

# mode="required": alert when missing% > threshold
# mode="known":    only alert when it worsens by more than `delta` percentage points
NULL_CHECKS: tuple[dict[str, Any], ...] = (
    dict(area="进销存", table="inventory_records", column="date_value",
         mode="required", threshold=0.5),
    dict(area="进销存", table="inventory_records", column="total_count", mode="known", delta=2),
    dict(area="进销存", table="inventory_records", column="supplier", mode="known", delta=2),
    dict(area="进销存", table="inventory_details", column="unit_price",
         mode="required", threshold=1),
    dict(area="进销存", table="inventory_details", column="amount",
         mode="required", threshold=1),
    dict(area="进销存", table="inventory_details", column="product_identity_id",
         mode="required", threshold=1),
    dict(area="进销存", table="inventory_details", column="product_code", mode="known", delta=1),
    dict(area="进销存", table="inventory_details", column="color_spec", mode="known", delta=1),
    *(
        dict(area="商品档案", table=t, column=c, mode=m, **kw)
        for t in ARCHIVE_TABLES
        for c, m, kw in (
            ("sku", "required", dict(threshold=0.1)),
            ("product_name", "required", dict(threshold=2)),
            ("cost", "required", dict(threshold=5)),
            ("image_path", "known", dict(delta=3)),
            ("product_level", "known", dict(delta=3)),
            ("group_name", "known", dict(delta=3)),
            ("category", "known", dict(delta=3)),
            ("last_imported_at", "known", dict(delta=5)),
        )
    ),
    dict(area="聚水潭订单", table="jst_monthly_orders_2026", column="order_time_at",
         mode="required", threshold=0.1),
    dict(area="聚水潭订单", table="jst_monthly_orders_2026", column="product_code",
         mode="required", threshold=1),
    dict(area="聚水潭订单", table="jst_monthly_orders_2026", column="cost_price",
         mode="known", delta=2),
    dict(area="聚水潭订单", table="jst_monthly_orders_2026", column="category",
         mode="known", delta=2),
    dict(area="聚水潭订单", table="jst_monthly_orders_2026", column="registered_qty",
         mode="known", delta=2),
    dict(area="聚水潭订单", table="jst_monthly_orders_2026", column="actual_return_qty",
         mode="known", delta=2),
    dict(area="聚水潭订单", table="jst_monthly_orders_2026", column="address",
         mode="known", delta=2),
    dict(area="聚水潭订单", table="jst_monthly_orders_2026", column="shop_style_code",
         mode="known", delta=2),
    dict(area="聚水潭价格", table="jst_product_price", column="latest_purchase_price",
         mode="known", delta=3, where="source_date_value >= current_date - 120"),
    dict(area="聚水潭价格", table="jst_product_price", column="cost_unit_price",
         mode="known", delta=3, where="source_date_value >= current_date - 120"),
    dict(area="聚水潭价格", table="jst_product_price", column="retail_price",
         mode="known", delta=3, where="source_date_value >= current_date - 120"),
    dict(area="聚水潭价格", table="jst_product_price", column="member_price",
         mode="known", delta=1, where="source_date_value >= current_date - 120"),
    dict(area="唯品会", table="vip_product_ops_snapshots", column="goods_code",
         mode="required", threshold=0.5, where="snapshot_date >= current_date - 60"),
    dict(area="唯品会", table="vip_product_ops_snapshots", column="goods_tag",
         mode="known", delta=2, where="snapshot_date >= current_date - 60"),
    dict(area="唯品会", table="vip_product_detail_daily", column="shop_code",
         mode="known", delta=2),
    dict(area="其它分析表", table="gj_merged_product_info", column="goods_code",
         mode="required", threshold=0.5, where="source_date_value >= current_date - 60"),
    dict(area="其它分析表", table="gj_merged_product_info", column="disabled_flag",
         mode="known", delta=2, where="source_date_value >= current_date - 60"),
    dict(area="其它分析表", table="jst_full_stock", column="safety_stock_min_qty",
         mode="known", delta=2),
    dict(area="其它分析表", table="jst_product_profiles", column="product_code",
         mode="required", threshold=0.5),
    dict(area="其它分析表", table="suppliers", column="name", mode="required", threshold=0.1),
    dict(area="其它分析表", table="suppliers", column="contact", mode="known", delta=3),
)


class Review:
    def __init__(self, conn, days: int, state: dict[str, Any]) -> None:
        self.conn = conn
        self.days = days
        self.state = state
        self.previous: dict[str, Any] = dict(state.get("values", {}))
        self.values: dict[str, Any] = {}
        self.rows: list[dict[str, Any]] = []
        self.failures: list[str] = []
        self.rowcount_mode: dict[str, str] = {}
        self.year = date.today().year

    # ---- primitives -------------------------------------------------------
    def scalar(self, sql: str) -> Any:
        result = self.conn.exec_driver_sql(sql)
        row = result.fetchone()
        result.close()
        return None if row is None else row[0]

    def one(self, sql: str) -> dict[str, Any]:
        result = self.conn.exec_driver_sql(sql)
        row = result.mappings().fetchone()
        result.close()
        return dict(row) if row else {}

    def rows_of(self, sql: str) -> list[Any]:
        result = self.conn.exec_driver_sql(sql)
        data = result.fetchall()
        result.close()
        return data

    def table_exists(self, name: str) -> bool:
        if not IDENT.match(name):
            return False
        return bool(self.scalar(f"SELECT to_regclass('public.{name}') IS NOT NULL"))

    def resolve(self, base: str) -> str | None:
        """Resolve a possibly year-suffixed table name to an existing table."""
        if base in YEARLY_BASES:
            for year in (self.year, self.year - 1, self.year - 2):
                candidate = f"{base}_{year}"
                if self.table_exists(candidate):
                    return candidate
            return None
        return base if self.table_exists(base) else None

    def add(self, area: str, name: str, status: str, detail: str, *,
            key: str | None = None, value: Any = None, note: str = "") -> None:
        if key is not None and value is not None:
            self.values[key] = value
        self.rows.append({"area": area, "name": name, "status": status,
                          "detail": detail, "note": note, "key": key})

    def delta_note(self, key: str, current: float, unit: str = "%") -> tuple[str, float]:
        old = self.previous.get(key)
        if old is None:
            return "首次记录", 0.0
        diff = current - float(old)
        if abs(diff) < 0.05:
            return "与上周持平", 0.0
        arrow = "↑" if diff > 0 else "↓"
        return f"上周 {float(old):.2f}{unit} → {arrow}{abs(diff):.2f}pp", diff

    # ---- checks -----------------------------------------------------------
    def check_rowcounts(self) -> None:
        """Detect data loss. Exact counts for small tables, catalog estimates for big ones."""
        area = "数据丢失监测"
        catalog = self.rows_of("""
            WITH parts AS (
              SELECT i.inhparent AS parent,
                     c.reltuples AS rt,
                     pg_total_relation_size(c.oid) AS bytes
              FROM pg_inherits i JOIN pg_class c ON c.oid = i.inhrelid
            )
            SELECT c.relname,
                   c.relkind::text AS kind,
                   c.reltuples::bigint AS own_rt,
                   pg_total_relation_size(c.oid) AS own_bytes,
                   COALESCE((SELECT sum(p.rt) FROM parts p WHERE p.parent = c.oid), 0)::bigint AS child_rt,
                   COALESCE((SELECT sum(p.bytes) FROM parts p WHERE p.parent = c.oid), 0) AS child_bytes,
                   COALESCE(s.n_live_tup, 0) AS live
            FROM pg_class c
            JOIN pg_namespace n ON n.oid = c.relnamespace
            LEFT JOIN pg_stat_user_tables s ON s.relid = c.oid
            WHERE n.nspname = 'public' AND c.relkind IN ('r', 'p')
        """)
        info = {r[0]: {"kind": r[1], "own_rt": int(r[2] or 0), "own_bytes": int(r[3] or 0),
                       "child_rt": int(r[4] or 0), "child_bytes": int(r[5] or 0),
                       "live": int(r[6] or 0)} for r in catalog}

        for base in ROWCOUNT_TABLES:
            table = self.resolve(base)
            if table is None:
                continue
            meta = info.get(table)
            if meta is None:
                continue
            if meta["kind"] == "p":
                bytes_total = meta["child_bytes"] + meta["own_bytes"]
                estimate = meta["child_rt"] or meta["live"]
            else:
                bytes_total = meta["own_bytes"]
                estimate = meta["own_rt"] if meta["own_rt"] >= 0 else meta["live"]
            if bytes_total < EXACT_COUNT_LIMIT:
                try:
                    count = int(self.scalar(f"SELECT count(*) FROM public.{table}") or 0)
                    mode = "精确"
                except Exception as exc:  # noqa: BLE001
                    self.failures.append(f"行数 {table}: {type(exc).__name__}: {exc}")
                    continue
            else:
                count = int(estimate)
                mode = "统计估算"
            self.rowcount_mode[table] = mode

            row_key = f"rows.{table}"
            size_key = f"bytes.{table}"
            old_rows = self.previous.get(row_key)
            old_size = self.previous.get(size_key)
            self.values[row_key] = count
            self.values[size_key] = bytes_total

            notes: list[str] = []
            status = OK
            if mode == "精确":
                if old_rows is not None:
                    old_rows = int(old_rows)
                    if count == 0 and old_rows > 0:
                        status = RED
                        notes.append(f"上周 {old_rows:,} → 本周 0")
                    elif old_rows > 0 and count < old_rows * 0.98:
                        status = RED
                        notes.append(f"较上周减少 {(old_rows - count) / old_rows * 100:.1f}%"
                                     f"（{old_rows:,} → {count:,}）")
                    elif old_rows > 0 and count > old_rows * 1.5:
                        status = YELLOW
                        notes.append(f"较上周增长 {count / old_rows * 100 - 100:.0f}%（疑似重复导入）")
                    else:
                        notes.append(f"较上周 {count - old_rows:+,}")
                else:
                    notes.append("首次记录")
            else:
                if old_rows is not None:
                    old_rows = int(old_rows)
                    if count == 0 and old_rows > 0:
                        status = RED
                        notes.append(f"估算值归零（上周 {old_rows:,}）")
                    elif old_rows > 0 and count < old_rows * 0.90:
                        status = YELLOW
                        notes.append(f"估算值较上周减少 {(old_rows - count) / old_rows * 100:.0f}%"
                                     f"（{old_rows:,} → {count:,}）")
                    else:
                        notes.append(f"估算值较上周 {count - old_rows:+,}")
                else:
                    notes.append("首次记录")

            if old_size is not None:
                old_size = int(old_size)
                if old_size > 0 and bytes_total < old_size * 0.70:
                    status = RED
                    notes.append(f"体积骤降 {(old_size - bytes_total) / old_size * 100:.0f}%"
                                 f"（{old_size / 1048576:.0f}MB → {bytes_total / 1048576:.0f}MB）")
            size_mb = bytes_total / 1048576
            label = f"{table}" + ("" if mode == "精确" else "（估算）")
            self.add(area, label, status,
                     f"{count:,} 行 / {size_mb:,.1f} MB" if size_mb < 1024
                     else f"{count:,} 行 / {size_mb / 1024:,.2f} GB",
                     key=row_key, value=count,
                     note="；".join(notes) + ("" if mode == "精确" else "；行数为目录估算值"))

    def check_null_columns(self) -> None:
        for spec in NULL_CHECKS:
            table, column, area = spec["table"], spec["column"], spec["area"]
            if not self.table_exists(table):
                continue
            label = f"{table}.{column}"
            where = spec.get("where")
            scope = "（近 120 天）" if where else ""
            try:
                total = int(self.scalar(
                    f"SELECT count(*) FROM public.{table}"
                    + (f" WHERE {where}" if where else "")) or 0)
                if total == 0:
                    self.add(area, label, GRAY, "无数据行", note="该范围内没有数据")
                    continue
                missing = int(self.scalar(
                    f"SELECT count(*) FROM public.{table} WHERE {column} IS NULL"
                    + (f" AND {where}" if where else "")) or 0)
            except Exception as exc:  # noqa: BLE001
                self.failures.append(f"空值 {label}: {type(exc).__name__}: {exc}")
                continue
            pct = missing / total * 100
            key = f"null.{table}.{column}" + ("~window" if where else "")
            detail = f"空值 {pct:.2f}%（{missing:,}/{total:,}）{scope}"
            if spec["mode"] == "required":
                threshold = float(spec["threshold"])
                if pct > threshold:
                    status = RED if pct > max(threshold * 5, 5) else YELLOW
                    note = f"超过阈值 {threshold}%"
                else:
                    status, note = OK, "正常"
                self.add(area, label, status, detail, key=key, value=round(pct, 4), note=note)
            else:
                note, diff = self.delta_note(key, pct)
                status = YELLOW if diff > float(spec["delta"]) else GRAY
                self.add(area, label, status, detail, key=key, value=round(pct, 4), note=note)

    def check_date_coverage(self) -> None:
        area = "日期断档"
        today = date.today()
        window_start = today - timedelta(days=self.days)
        for base, column, label, severity, must_be_daily in DAILY_SERIES:
            table = self.resolve(base)
            if table is None:
                continue
            try:
                info = self.one(
                    f"SELECT min({column}) AS lo, max({column}) AS hi "
                    f"FROM public.{table} WHERE {column} >= DATE '{window_start.isoformat()}'")
            except Exception as exc:  # noqa: BLE001
                self.failures.append(f"断档 {table}: {type(exc).__name__}: {exc}")
                continue
            lo, hi = info.get("lo"), info.get("hi")
            if lo is None:
                self.add(area, label, YELLOW, f"近 {self.days} 天无数据", note=f"{table}.{column}")
                continue
            end = min(hi, today - timedelta(days=1))
            if end < lo:
                self.add(area, label, GRAY, "窗口内仅今天有数据", note=f"{table}.{column}")
                continue
            try:
                gaps = [r[0] for r in self.rows_of(
                    "SELECT d::date FROM generate_series(DATE '{lo}', DATE '{end}', interval '1 day') d "
                    "WHERE d::date NOT IN (SELECT DISTINCT {col} FROM public.{tbl} "
                    "WHERE {col} BETWEEN DATE '{lo}' AND DATE '{end}') ORDER BY 1".format(
                        lo=lo.isoformat(), end=end.isoformat(), col=column, tbl=table))]
            except Exception as exc:  # noqa: BLE001
                self.failures.append(f"断档 {table}: {type(exc).__name__}: {exc}")
                continue
            span = (end - lo).days + 1
            key = f"gap.{table}"
            self.values[key] = len(gaps)
            tag = f"{table}.{column}"
            if gaps:
                shown = ", ".join(g.isoformat() for g in gaps[:12])
                more = f" …共 {len(gaps)} 天" if len(gaps) > 12 else ""
                status = severity if must_be_daily else (YELLOW if len(gaps) > span * 0.3 else GRAY)
                note = f"缺失：{shown}{more}"
                if not must_be_daily:
                    note += "｜该表为不定期采集，仅作记录"
                self.add(area, label, status, f"缺 {len(gaps)}/{span} 天", key=key,
                         value=len(gaps), note=note)
            else:
                self.add(area, label, OK, f"完整（{span} 天）", key=key, value=0,
                         note=f"无断档｜{tag}")

    def check_record_key(self) -> None:
        area = "去重键覆盖"
        table = "jst_monthly_orders"
        if not self.table_exists(table):
            return
        try:
            rows = self.rows_of(f"""
                SELECT to_char(date_trunc('month', order_time_at), 'YYYY-MM') AS mon,
                       count(*) AS total,
                       count(*) FILTER (WHERE record_key IS NULL OR btrim(record_key) = '') AS null_key
                FROM public.{table}
                WHERE order_time_at >= date_trunc('month', current_date) - interval '5 months'
                GROUP BY 1 ORDER BY 1
            """)
        except Exception as exc:  # noqa: BLE001
            self.failures.append(f"record_key: {type(exc).__name__}: {exc}")
            return
        this_month = today_month = date.today().strftime("%Y-%m")
        for mon, total, null_key in rows:
            total, null_key = int(total or 0), int(null_key or 0)
            if not total:
                continue
            pct = null_key / total * 100
            key = f"record_key.{mon}"
            status = RED if pct > 1 else OK
            if mon < today_month and pct > 1:
                status = RED          # 历史月份仍有缺失说明回填未做
            self.add(area, f"{table} {mon} 的 record_key", status,
                     f"缺失 {null_key:,}/{total:,}（{pct:.1f}%）", key=key,
                     value=round(pct, 3),
                     note="去重键未写入 → 唯一约束失效" if pct > 1 else "正常")
        try:
            dup = int(self.scalar(f"""
                SELECT COALESCE(SUM(c - 1), 0) FROM (
                  SELECT internal_order_id, product_code, order_time_at, count(*) AS c
                  FROM public.{table}
                  WHERE order_time_at >= date_trunc('month', current_date) - interval '2 months'
                  GROUP BY 1, 2, 3 HAVING count(*) > 1) x
            """) or 0)
            self.add(area, "疑似重复订单行（近 3 个月，按订单号+货号+下单时间）",
                     YELLOW if dup else OK, f"{dup:,} 行", key="record_key.dups", value=dup,
                     note="粗粒度匹配不代表重复，需结合内部子订单编号核对，禁止直接删除" if dup else "正常")
            exact = int(self.scalar(f"""
                SELECT COALESCE(SUM(c - 1), 0) FROM (
                  SELECT order_time_at, {monthly_order_record_key_sql()} AS expected_key, count(*) AS c
                  FROM public.{table} orders
                  WHERE order_time_at >= date_trunc('month', current_date) - interval '2 months'
                  GROUP BY 1, 2 HAVING count(*) > 1) duplicate_keys
            """) or 0)
            self.add(area, "订单去重键冲突（近 3 个月，含内部子订单编号）",
                     RED if exact else OK, f"{exact:,} 行", key="record_key.exact_dups", value=exact,
                     note="需核对业务数据后处理，不自动删除" if exact else "正常")
        except Exception as exc:  # noqa: BLE001
            self.failures.append(f"record_key dups: {type(exc).__name__}: {exc}")

    def check_foreign_keys(self) -> None:
        area = "引用完整性"
        fks = self.rows_of("""
            SELECT con.conname,
                   con.conrelid::regclass::text AS child,
                   con.confrelid::regclass::text AS parent,
                   (SELECT array_agg(a.attname ORDER BY k.ordinality)
                      FROM unnest(con.conkey) WITH ORDINALITY k(attnum, ordinality)
                      JOIN pg_attribute a ON a.attrelid = con.conrelid AND a.attnum = k.attnum) AS ccols,
                   (SELECT array_agg(a.attname ORDER BY k.ordinality)
                      FROM unnest(con.confkey) WITH ORDINALITY k(attnum, ordinality)
                      JOIN pg_attribute a ON a.attrelid = con.confrelid AND a.attnum = k.attnum) AS pcols
            FROM pg_constraint con
            JOIN pg_namespace n ON n.oid = con.connamespace
            WHERE con.contype = 'f' AND n.nspname = 'public'
        """)
        checked = 0
        total_orphans = 0
        bad: list[str] = []
        for conname, child_full, parent_full, ccols, pcols in fks:
            child = str(child_full).replace("public.", "").strip('"')
            parent = str(parent_full).replace("public.", "").strip('"')
            ccols = [c for c in (ccols or []) if IDENT.match(c)]
            pcols = [c for c in (pcols or []) if IDENT.match(c)]
            if not ccols or not pcols or not IDENT.match(child) or not IDENT.match(parent):
                continue
            guard = " AND ".join(f"c.{c} IS NOT NULL" for c in ccols)
            join = " AND ".join(f"p.{pc} = c.{cc}" for cc, pc in zip(ccols, pcols))
            try:
                orphans = int(self.scalar(
                    f"SELECT count(*) FROM public.{child} c WHERE {guard} "
                    f"AND NOT EXISTS (SELECT 1 FROM public.{parent} p WHERE {join})") or 0)
            except Exception as exc:  # noqa: BLE001
                self.failures.append(f"外键 {conname}: {type(exc).__name__}: {exc}")
                continue
            checked += 1
            if orphans:
                total_orphans += orphans
                bad.append(f"{child}.{conname}={orphans:,}")
        self.values["fk.orphans"] = total_orphans
        self.add(area, f"外键孤儿行（已检查 {checked}/{len(fks)} 个外键）",
                 RED if total_orphans else OK, f"{total_orphans:,} 行",
                 key="fk.orphans", value=total_orphans,
                 note="；".join(bad) if bad else "全部外键均无孤儿行")

    def check_inventory(self) -> None:
        area = "进销存勾稽"
        checks = (
            ("单据总数", "SELECT count(*) FROM public.inventory_records", GRAY, "inv.docs", None),
            ("已软删除单据",
             "SELECT count(*) FROM public.inventory_records WHERE deleted_at IS NOT NULL",
             GRAY, "inv.deleted_docs", None),
            ("无明细行的空单据",
             "SELECT count(*) FROM public.inventory_records r WHERE NOT EXISTS "
             "(SELECT 1 FROM public.inventory_details d WHERE d.document_id = r.id)",
             RED, "inv.empty_docs", 0),
            ("total_count 与明细合计不符（明细数量完整）",
             "SELECT count(*) FROM (SELECT r.id FROM public.inventory_records r "
             "JOIN public.inventory_details d ON d.document_id = r.id WHERE r.deleted_at IS NULL "
             "GROUP BY r.id, r.total_count HAVING count(*) FILTER (WHERE d.quantity IS NULL) = 0 "
             "AND r.total_count IS DISTINCT FROM COALESCE(SUM(d.quantity), 0)) x",
             YELLOW, "inv.qty_mismatch", 0),
            ("amount 与明细合计不符",
             "SELECT count(*) FROM (SELECT r.id FROM public.inventory_records r "
             "JOIN public.inventory_details d ON d.document_id = r.id WHERE r.deleted_at IS NULL "
             "GROUP BY r.id, r.amount "
             "HAVING r.amount IS DISTINCT FROM COALESCE(SUM(d.amount), 0)) x",
             YELLOW, "inv.amount_mismatch", 0),
            ("明细 amount ≠ 数量 × 单价",
             "SELECT count(*) FROM public.inventory_details WHERE quantity IS NOT NULL "
             "AND unit_price IS NOT NULL AND amount IS NOT NULL "
             "AND round(quantity * unit_price, 2) <> round(amount, 2)",
             YELLOW, "inv.line_math", 0),
            ("挂在已软删除单据下的明细行",
             "SELECT count(*) FROM public.inventory_details d "
             "JOIN public.inventory_records r ON r.id = d.document_id WHERE r.deleted_at IS NOT NULL",
             YELLOW, "inv.details_under_deleted", None),
            ("未关联商品身份的明细",
             "SELECT count(*) FROM public.inventory_details WHERE product_identity_id IS NULL",
             RED, "inv.no_identity", 0),
        )
        for label, sql, bad_status, key, limit in checks:
            try:
                value = int(self.scalar(sql) or 0)
            except Exception as exc:  # noqa: BLE001
                self.failures.append(f"{label}: {type(exc).__name__}: {exc}")
                continue
            if limit is None:
                status, note = bad_status, ""
            elif value > limit:
                status, note = bad_status, "需要处理"
            else:
                status, note = OK, "正常"
            self.add(area, label, status, f"{value:,}", key=key, value=value, note=note)

        try:
            union = " UNION ".join(
                f"SELECT sku AS s FROM public.{t} WHERE sku IS NOT NULL "
                f"UNION ALL SELECT original_sku FROM public.{t} WHERE original_sku IS NOT NULL"
                for t in ARCHIVE_TABLES)
            matchable = int(self.scalar(
                f"SELECT count(*) FROM public.inventory_details d "
                f"WHERE d.product_identity_id IS NULL AND d.product_code IS NOT NULL "
                f"AND EXISTS (SELECT 1 FROM ({union}) a WHERE a.s = d.product_code)") or 0)
            self.add(area, "↳ 其中货号在档案中（本应能匹配）",
                     RED if matchable else OK, f"{matchable:,}",
                     key="inv.matchable_no_identity", value=matchable,
                     note="触发器未解析出身份" if matchable else "正常")
        except Exception as exc:  # noqa: BLE001
            self.failures.append(f"identity matchable: {type(exc).__name__}: {exc}")

        try:
            amount = float(self.scalar(
                "SELECT COALESCE(SUM(d.amount), 0) FROM public.inventory_details d "
                "JOIN public.inventory_records r ON r.id = d.document_id "
                "WHERE r.deleted_at IS NOT NULL") or 0)
            self.add(area, "↳ 上述明细的金额合计", GRAY, f"{amount:,.2f}",
                     key="inv.details_under_deleted_amount", value=amount,
                     note="统计若未过滤 deleted_at 会虚增此金额")
        except Exception as exc:  # noqa: BLE001
            self.failures.append(f"deleted amount: {type(exc).__name__}: {exc}")

    def check_product_archives(self) -> None:
        area = "商品档案"
        try:
            union = " UNION ALL ".join(
                f"SELECT sku FROM public.{t} WHERE sku IS NOT NULL" for t in ARCHIVE_TABLES)
            info = self.one(f"SELECT count(*) AS total, count(DISTINCT sku) AS distinct_sku "
                            f"FROM ({union}) x")
            dup = int(info["total"]) - int(info["distinct_sku"])
            self.add(area, "跨品牌重复货号", YELLOW if dup else OK, f"{dup:,}",
                     key="arch.dup_sku", value=dup,
                     note="同一货号出现在多个品牌档案" if dup else "正常")
        except Exception as exc:  # noqa: BLE001
            self.failures.append(f"dup sku: {type(exc).__name__}: {exc}")

        try:
            union = " UNION ".join(
                f"SELECT sku FROM public.{t} WHERE sku IS NOT NULL" for t in ARCHIVE_TABLES)
            missing = int(self.scalar(
                f"SELECT count(*) FROM ({union}) a WHERE NOT EXISTS "
                f"(SELECT 1 FROM public.product_archive_identities i WHERE i.sku = a.sku)") or 0)
            self.add(area, "档案货号未登记到身份表", RED if missing else OK, f"{missing:,}",
                     key="arch.no_identity", value=missing,
                     note="需要回填" if missing else "正常")
        except Exception as exc:  # noqa: BLE001
            self.failures.append(f"archive identity: {type(exc).__name__}: {exc}")

        for table in ARCHIVE_TABLES:
            if not self.table_exists(table):
                continue
            try:
                info = self.one(
                    f"SELECT count(*) AS rows, "
                    f"count(*) FILTER (WHERE image_path IS NULL) AS no_image, "
                    f"max(last_imported_at) AS last_import, "
                    f"count(*) FILTER (WHERE last_imported_at IS NULL) AS no_ts "
                    f"FROM public.{table}")
            except Exception as exc:  # noqa: BLE001
                self.failures.append(f"{table}: {type(exc).__name__}: {exc}")
                continue
            rows = int(info["rows"] or 0)
            if rows == 0:
                continue
            pct = int(info["no_image"] or 0) / rows * 100
            key = f"arch.{table}.no_image_pct"
            note, diff = self.delta_note(key, pct)
            status = YELLOW if diff > 3 else GRAY
            if int(info["no_ts"] or 0) / rows > 0.5:
                note += f"｜{int(info['no_ts'] or 0):,} 行无导入时间戳"
            self.add(area, f"{table} 图片路径缺失", status,
                     f"{int(info['no_image'] or 0):,}/{rows:,}（{pct:.1f}%）",
                     key=key, value=round(pct, 3),
                     note=f"{note}｜最近导入：{info['last_import'] or '从未'}")

    def check_operations(self) -> None:
        area = "运维信号"
        try:
            size = self.scalar("SELECT pg_size_pretty(pg_database_size(current_database()))")
            self.add(area, "数据库大小", GRAY, str(size))
        except Exception as exc:  # noqa: BLE001
            self.failures.append(f"db size: {type(exc).__name__}: {exc}")

        try:
            stale = int(self.scalar("""
                SELECT count(*) FROM pg_class c
                JOIN pg_namespace n ON n.oid = c.relnamespace
                LEFT JOIN pg_stat_user_tables s ON s.relid = c.oid
                WHERE n.nspname = 'public' AND c.relkind = 'r'
                  AND pg_relation_size(c.oid) > 100 * 1024 * 1024
                  AND (s.last_analyze IS NULL OR s.last_analyze < now() - interval '7 days')
            """) or 0)
            self.add(area, "超过 7 天未 ANALYZE 的大表", YELLOW if stale else OK,
                     f"{stale} 张", key="ops.stale_stats", value=stale,
                     note="统计信息陈旧会拖慢查询计划" if stale else "正常")
        except Exception as exc:  # noqa: BLE001
            self.failures.append(f"stale stats: {type(exc).__name__}: {exc}")

        try:
            empties = []
            candidates = [r[0] for r in self.rows_of("""
                SELECT c.relname FROM pg_class c
                JOIN pg_namespace n ON n.oid = c.relnamespace
                WHERE c.relkind = 'r' AND n.nspname = 'public'
                  AND pg_relation_size(c.oid) < 200 * 1024 * 1024
                ORDER BY c.relname
            """)]
            for name in candidates:
                if not IDENT.match(name):
                    continue
                if int(self.scalar(f"SELECT count(*) FROM public.{name}") or 0) == 0:
                    empties.append(name)
            self.add(area, "精确为空的表", GRAY, f"{len(empties)} 张",
                     key="ops.empty_tables", value=len(empties),
                     note="、".join(empties) if empties else "无")
        except Exception as exc:  # noqa: BLE001
            self.failures.append(f"empty tables: {type(exc).__name__}: {exc}")

    # ---- rendering --------------------------------------------------------
    def render(self, started: datetime, duration: float, db_name: str) -> str:
        counts = {s: sum(1 for r in self.rows if r["status"] == s)
                  for s in (RED, YELLOW, GRAY, OK)}
        new_alerts = [r for r in self.rows
                      if r["status"] == RED and (r["key"] is None
                                                 or r["key"] not in self.previous)]
        lines: list[str] = []
        add = lines.append
        add("# 数据库缺失数据周报")
        add("")
        add(f"- **生成时间**：{started.strftime('%Y-%m-%d %H:%M:%S')}")
        add(f"- **数据库**：`{db_name}`")
        add(f"- **日期断档检查区间**：最近 {self.days} 天")
        add(f"- **耗时**：{duration:.1f} 秒 ｜ **检查项**：{len(self.rows)} 项")
        add("- **性质**：只读检查，未修改任何数据")
        add("")
        add("## 一、结论")
        add("")
        add(f"本次共检查 **{len(self.rows)}** 项：🔴 需要处理 **{counts[RED]}** 项、"
            f"🟡 需要关注 **{counts[YELLOW]}** 项、"
            f"⚪ 已知长期为空/仅记录 **{counts[GRAY]}** 项、✅ 正常 **{counts[OK]}** 项。")
        add("")
        if counts[RED]:
            add(f"**有 {counts[RED]} 项需要处理**（见第二节）。")
            if new_alerts:
                add("")
                if self.previous:
                    add("其中**本次新增**（上周没有记录到）：")
                else:
                    add("（本次为首次运行，没有历史基线，下列均记为新增）")
                add("")
                for r in new_alerts:
                    add(f"- **{r['name']}** — {r['detail']}｜{r['note']}")
        else:
            add("**没有需要处理的缺失数据问题。**")
        if self.failures:
            add("")
            add(f"> ⚠️ 有 {len(self.failures)} 项检查未能完成（超时或报错），见文末。")
        add("")
        add("> 图例：🔴 需要处理 ｜ 🟡 需要关注 ｜ ⚪ 已知长期为空（只关注是否恶化） ｜ ✅ 正常")
        add("")

        for status, title in ((RED, "二、🔴 需要处理"), (YELLOW, "三、🟡 需要关注"),
                              (GRAY, "四、⚪ 已知长期为空 / 仅作记录"),
                              (OK, "五、✅ 检查通过")):
            items = [r for r in self.rows if r["status"] == status]
            add(f"## {title}")
            add("")
            if not items:
                add("无。")
                add("")
                continue
            grouped: dict[str, list[dict[str, Any]]] = {}
            for r in items:
                grouped.setdefault(r["area"], []).append(r)
            for index, (area, group) in enumerate(grouped.items()):
                if index:
                    add("")
                add(f"**{area}**")
                add("")
                add("| 检查项 | 结果 | 说明 |")
                add("|---|---|---|")
                for r in group:
                    note = (r["note"] or "").replace("|", "＼|")
                    add(f"| {r['name']} | {r['detail']} | {note} |")
            add("")

        add("## 六、与上周对比（有变化的指标）")
        add("")
        changed = []
        for k, v in self.values.items():
            old = self.previous.get(k)
            if old is None:
                continue
            try:
                if abs(float(v) - float(old)) > 1e-9:
                    changed.append((k, old, v))
            except (TypeError, ValueError):
                continue
        if not changed:
            add("所有可比较指标与上周一致。")
        else:
            add("| 指标 | 上周 | 本周 |")
            add("|---|---|---|")
            for k, old, v in changed[:60]:
                add(f"| `{k}` | {old} | {v} |")
        add("")

        if self.failures:
            add("## 七、未完成的检查")
            add("")
            for f in self.failures:
                add(f"- {f}")
            add("")

        add("---")
        add("")
        add("*本报告由 Windows 计划任务 `HedeDatabaseMissingDataReview` 自动生成"
            "（每周一 00:00）。*")
        add("*运行日志：`backend/logs/missing_data_review.log`；"
            "历史报告：`backend/logs/missing_data_reports/`。*")
        return "\n".join(lines)


def _desktop_dir() -> Path:
    candidates = []
    profile = os.environ.get("USERPROFILE")
    if profile:
        candidates += [Path(profile) / "OneDrive" / "Desktop", Path(profile) / "Desktop"]
    candidates.append(Path.home() / "Desktop")
    candidates.append(Path.home() / "OneDrive" / "Desktop")
    for candidate in candidates:
        if candidate.is_dir():
            return candidate
    return BACKEND_ROOT / "logs" / "missing_data_reports"


def _load_state(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return {}


def _save_state(path: Path, state: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, path)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Weekly missing-data review")
    parser.add_argument("--output-dir", type=Path, default=None,
                        help="报告输出目录（默认写到桌面）")
    parser.add_argument("--days", type=int, default=90, help="日期断档回看天数")
    parser.add_argument("--state-file", type=Path,
                        default=BACKEND_ROOT / "logs" / "missing_data_review_state.json")
    parser.add_argument("--history-dir", type=Path,
                        default=BACKEND_ROOT / "logs" / "missing_data_reports")
    parser.add_argument("--statement-timeout-ms", type=int, default=300_000)
    parser.add_argument("--quiet", action="store_true")
    return parser


def main() -> int:
    args = _parser().parse_args()
    started = datetime.now()
    print(f"[{started.isoformat(timespec='seconds')}] missing-data review starting")

    settings = load_settings(require_database=True)
    assert settings.database_url is not None
    db_name = settings.database_url.rsplit("/", 1)[-1].split("?")[0]
    engine = create_engine(settings.database_url)
    state = _load_state(args.state_file)

    with engine.connect() as conn:
        conn = conn.execution_options(isolation_level="AUTOCOMMIT")
        conn.exec_driver_sql(f"SET statement_timeout = {int(args.statement_timeout_ms)}")
        review = Review(conn, args.days, state)
        for check in (review.check_rowcounts, review.check_null_columns,
                      review.check_date_coverage, review.check_record_key,
                      review.check_foreign_keys, review.check_inventory,
                      review.check_product_archives, review.check_operations):
            print(f"  running {check.__name__} ...", flush=True)
            try:
                check()
            except Exception as exc:  # noqa: BLE001
                review.failures.append(f"{check.__name__}: {type(exc).__name__}: {exc}")
                print(f"  !! {check.__name__} failed: {type(exc).__name__}: {exc}", flush=True)

    finished = datetime.now()
    duration = (finished - started).total_seconds()
    report = review.render(started, duration, db_name)

    filename = f"数据库缺失数据周报_{started.strftime('%Y-%m-%d')}.md"
    targets = [args.history_dir / filename, (args.output_dir or _desktop_dir()) / filename]
    written: list[Path] = []
    for target in targets:
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(report, encoding="utf-8-sig")
            written.append(target)
            print(f"[report] {target}", flush=True)
        except Exception as exc:  # noqa: BLE001
            print(f"[report] FAILED {target}: {type(exc).__name__}: {exc}", flush=True)

    history = list(state.get("history", []))
    history.append({"run": started.isoformat(timespec="seconds"),
                    "red": sum(1 for r in review.rows if r["status"] == RED),
                    "yellow": sum(1 for r in review.rows if r["status"] == YELLOW),
                    "failures": len(review.failures)})
    _save_state(args.state_file, {"last_run": started.isoformat(timespec="seconds"),
                                  "values": review.values, "history": history[-52:]})

    reds = sum(1 for r in review.rows if r["status"] == RED)
    yellows = sum(1 for r in review.rows if r["status"] == YELLOW)
    print(f"[{finished.isoformat(timespec='seconds')}] done in {duration:.1f}s "
          f"items={len(review.rows)} red={reds} yellow={yellows} "
          f"failures={len(review.failures)} reports={len(written)}")
    return 0 if written else 1


if __name__ == "__main__":
    raise SystemExit(main())
