"""Weekly missing-data / completeness review of the hede database.

Runs a curated battery of read-only completeness checks, compares the numbers with
the previous run (state file), and writes a Markdown report to the Desktop while
keeping a history copy under ``backend/logs/missing_data_reports/``.

Usage:
    python -m scripts.review_missing_data
    python -m scripts.review_missing_data --output-dir D:\\tmp --days 120

Design notes
------------
* Everything here is read-only.  No table, index or setting is ever modified.
* Checks are split into "required" columns (a value is expected, alert above a
  threshold) and "known" gaps (the column has always been empty -- only a
  *worsening* delta versus the previous run is reported, so the weekly report
  does not repeat the same permanent findings forever).
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

from sqlalchemy import create_engine, text

BACKEND_ROOT = Path(__file__).resolve().parent.parent
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from config import load_settings  # noqa: E402

RED, YELLOW, GRAY, OK = "red", "yellow", "gray", "ok"
ICON = {RED: "🔴", YELLOW: "🟡", GRAY: "⚪", OK: "✅"}
RANK = {RED: 0, YELLOW: 1, GRAY: 2, OK: 3}

IDENT = re.compile(r"^[a-z_][a-z0-9_]*$")

# Tables whose row count is tracked run-over-run to catch data loss.
ROWCOUNT_TABLES = (
    "inventory_records", "inventory_details", "suppliers", "warehouses",
    "cbanner_mens_products", "cbanner_womens_products", "yandou_products",
    "eblan_products", "smiley_products", "ni_products", "manual_product_archive_31",
    "product_archive_identities", "product_size_group_mappings", "product_goods_overrides",
    "jst_monthly_orders", "jst_product_price", "jst_daily_stock", "jst_size_stock_snapshots",
    "jst_daily_sales", "jst_purchase_inbound_daily", "jst_full_stock", "jst_stock_summary",
    "jst_stock_summary_snapshots", "jst_size_stock", "jst_product_profiles",
    "jst_aftersale_returns", "vip_daily_sales", "vip_product_ops_snapshots",
    "vip_product_daily_snapshots", "vip_product_detail_daily", "vip_product_ops",
    "gj_merged_product_info", "dewu_orders", "fine_table_snapshot_refs",
    "fine_table_snapshot_batches", "fine_table_snapshot_payloads", "fine_table_snapshot_metrics",
    "product_goods_detail_snapshots", "product_goods_historical_orders",
    "product_goods_historical_sales", "product_tag_assignments", "operation_logs",
)

# Daily-granularity tables: (table, date column, label)
DAILY_SERIES = (
    ("jst_daily_stock", "stock_date_value", "聚水潭库存快照"),
    ("jst_daily_sales", "sales_date", "聚水潭销售日报"),
    ("jst_daily_sales_2026", "sales_date", "聚水潭销售日报(2026)"),
    ("vip_daily_sales", "sales_date", "唯品会销售日报"),
    ("vip_daily_sales_2026", "sales_date", "唯品会销售日报(2026)"),
    ("fine_table_snapshot_refs", "snapshot_date", "精细表快照明细"),
    ("product_goods_detail_snapshots", "snapshot_date", "商品明细快照"),
    ("vip_product_daily_snapshots", "snapshot_date", "唯品会商品日快照"),
    ("dewu_orders", "order_date", "得物订单"),
    ("product_goods_historical_orders", "order_date", "商品历史订单"),
    ("jst_purchase_inbound_daily", "inbound_date_value", "聚水潭采购入库日报"),
)

# Column-level NULL checks.
#   mode="required" -> alert when missing% > threshold
#   mode="known"    -> column has always been empty; alert only when it worsens
#                      by more than `delta` percentage points versus last run
NULL_CHECKS: tuple[dict[str, Any], ...] = (
    # --- 进销存（核心业务） ---
    dict(area="进销存", table="inventory_records", column="total_count", mode="known", delta=2),
    dict(area="进销存", table="inventory_records", column="supplier", mode="known", delta=2),
    dict(area="进销存", table="inventory_records", column="date_value", mode="required", threshold=0.5),
    dict(area="进销存", table="inventory_details", column="product_code", mode="known", delta=1),
    dict(area="进销存", table="inventory_details", column="unit_price", mode="required", threshold=1),
    dict(area="进销存", table="inventory_details", column="amount", mode="required", threshold=1),
    dict(area="进销存", table="inventory_details", column="product_identity_id", mode="required", threshold=1),
    dict(area="进销存", table="inventory_details", column="color_spec", mode="known", delta=1),
    # --- 商品档案 ---
    *(
        dict(area="商品档案", table=t, column=c, mode=m, **kw)
        for t in ("cbanner_mens_products", "cbanner_womens_products", "yandou_products",
                  "eblan_products", "smiley_products", "ni_products",
                  "manual_product_archive_31")
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
    # --- 聚水潭订单 ---
    *(
        dict(area="聚水潭订单", table=t, column=c, mode=m, **kw)
        for t in ("jst_monthly_orders_2026",)
        for c, m, kw in (
            ("record_key", "required", dict(threshold=1)),
            ("order_time_at", "required", dict(threshold=0.1)),
            ("product_code", "required", dict(threshold=1)),
            ("cost_price", "known", dict(delta=2)),
            ("category", "known", dict(delta=2)),
            ("registered_qty", "known", dict(delta=2)),
            ("actual_return_qty", "known", dict(delta=2)),
            ("address", "known", dict(delta=2)),
            ("shop_style_code", "known", dict(delta=2)),
        )
    ),
    # --- 价格 ---
    dict(area="聚水潭价格", table="jst_product_price", column="latest_purchase_price",
         mode="known", delta=3, where="source_date_value >= current_date - 120"),
    dict(area="聚水潭价格", table="jst_product_price", column="cost_unit_price",
         mode="known", delta=3, where="source_date_value >= current_date - 120"),
    dict(area="聚水潭价格", table="jst_product_price", column="retail_price",
         mode="known", delta=3, where="source_date_value >= current_date - 120"),
    dict(area="聚水潭价格", table="jst_product_price", column="member_price",
         mode="known", delta=1, where="source_date_value >= current_date - 120"),
    # --- 唯品会 ---
    dict(area="唯品会", table="vip_product_ops_snapshots", column="goods_tag",
         mode="known", delta=2, where="snapshot_date >= current_date - 60"),
    dict(area="唯品会", table="vip_product_ops_snapshots", column="goods_code",
         mode="required", threshold=0.5, where="snapshot_date >= current_date - 60"),
    dict(area="唯品会", table="vip_product_detail_daily", column="shop_code",
         mode="known", delta=2),
    # --- 其它分析表 ---
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
    """Collects check results and renders the Markdown report."""

    def __init__(self, conn, days: int, state: dict[str, Any]) -> None:
        self.conn = conn
        self.days = days
        self.state = state
        self.previous: dict[str, Any] = state.get("values", {})
        self.values: dict[str, Any] = {}
        self.rows: list[dict[str, Any]] = []
        self.failures: list[str] = []
        self.facts: dict[str, Any] = {}

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

    def table_exists(self, name: str) -> bool:
        assert IDENT.match(name), name
        return bool(self.scalar(f"SELECT to_regclass('public.{name}') IS NOT NULL"))

    def add(self, area: str, name: str, status: str, detail: str, *,
            key: str | None = None, value: Any = None, note: str = "") -> None:
        if key is not None and value is not None:
            self.values[key] = value
        self.rows.append({"area": area, "name": name, "status": status,
                          "detail": detail, "note": note})

    def prev(self, key: str) -> Any:
        return self.previous.get(key)

    def delta_note(self, key: str, current: float) -> tuple[str, bool]:
        """Return (text, worsened) comparing a percentage with the previous run."""
        old = self.prev(key)
        if old is None:
            return "首次记录", False
        diff = current - float(old)
        if abs(diff) < 0.05:
            return "与上周持平", False
        arrow = "↑" if diff > 0 else "↓"
        return f"上周 {float(old):.2f}% → {arrow}{abs(diff):.2f}pp", diff > 0

    # ---- checks -----------------------------------------------------------
    def check_rowcounts(self) -> None:
        area = "数据丢失监测"
        for table in ROWCOUNT_TABLES:
            if not self.table_exists(table):
                continue
            try:
                count = int(self.scalar(f"SELECT count(*) FROM public.{table}") or 0)
            except Exception as exc:  # noqa: BLE001
                self.failures.append(f"行数 {table}: {type(exc).__name__}: {exc}")
                continue
            key = f"rows.{table}"
            old = self.prev(key)
            if old is None:
                note = "首次记录"
                status = OK if count else YELLOW
            elif count == 0 and int(old) > 0:
                status, note = RED, f"上周 {int(old):,} → 本周 0（数据可能被清空）"
            elif int(old) > 0 and count < int(old) * 0.98:
                drop = (int(old) - count) / int(old) * 100
                status, note = RED, f"较上周减少 {drop:.1f}%（{int(old):,} → {count:,}）"
            elif int(old) > 0 and count > int(old) * 1.5:
                status, note = YELLOW, f"较上周增长 {count / int(old) * 100 - 100:.0f}%（可能重复导入）"
            else:
                status, note = OK, f"与上周持平（{count - int(old):+,}）"
            self.add(area, table, status, f"{count:,} 行", key=key, value=count, note=note)

    def check_null_columns(self) -> None:
        for spec in NULL_CHECKS:
            table, column = spec["table"], spec["column"]
            area = spec["area"]
            label = f"{table}.{column}"
            if not self.table_exists(table):
                continue
            try:
                total = int(self.scalar(
                    f"SELECT count(*) FROM public.{table}"
                    + (f" WHERE {spec['where']}" if spec.get("where") else "")) or 0)
            except Exception as exc:  # noqa: BLE001
                self.failures.append(f"空值 {label}: {type(exc).__name__}: {exc}")
                continue
            if total == 0:
                self.add(area, label, GRAY, "无数据行", note="表为空")
                continue
            try:
                missing = int(self.scalar(
                    f"SELECT count(*) FROM public.{table} WHERE {column} IS NULL"
                    + (f" AND {spec['where']}" if spec.get("where") else "")) or 0)
            except Exception as exc:  # noqa: BLE001
                self.failures.append(f"空值 {label}: {type(exc).__name__}: {exc}")
                continue
            pct = missing / total * 100
            key = f"null.{table}.{column}" + ("~window" if spec.get("where") else "")
            scope = "（近 120 天）" if spec.get("where") else ""
            if spec["mode"] == "required":
                threshold = float(spec["threshold"])
                if pct > threshold:
                    status = RED if pct > max(threshold * 5, 5) else YELLOW
                    note = f"超过阈值 {threshold}%"
                else:
                    status, note = OK, "正常"
                detail = f"空值 {pct:.2f}%（{missing:,}/{total:,}）{scope}"
                self.add(area, label, status, detail, key=key, value=round(pct, 4), note=note)
            else:
                note, worsened = self.delta_note(key, pct)
                status = YELLOW if worsened and pct - float(self.prev(key) or pct) > spec["delta"] else GRAY
                detail = f"空值 {pct:.2f}%（{missing:,}/{total:,}）{scope}"
                self.add(area, label, status, detail, key=key, value=round(pct, 4), note=note)

    def check_date_coverage(self) -> None:
        area = "日期断档"
        today = date.today()
        window_start = today - timedelta(days=self.days)
        for table, column, label in DAILY_SERIES:
            if not self.table_exists(table):
                continue
            try:
                info = self.one(
                    f"SELECT min({column}) AS lo, max({column}) AS hi, count(*) AS rows "
                    f"FROM public.{table} WHERE {column} >= DATE '{window_start.isoformat()}'")
            except Exception as exc:  # noqa: BLE001
                self.failures.append(f"断档 {table}: {type(exc).__name__}: {exc}")
                continue
            lo, hi = info.get("lo"), info.get("hi")
            if lo is None:
                self.add(area, label, YELLOW, f"近 {self.days} 天无数据",
                         note=f"{table}.{column}")
                continue
            # only judge up to yesterday: today's data may legitimately not be in yet
            end = min(hi, today - timedelta(days=1))
            if end < lo:
                self.add(area, label, GRAY, "窗口内仅今天有数据", note=f"{table}.{column}")
                continue
            try:
                gaps = [r[0] for r in self.conn.exec_driver_sql(
                    "SELECT d::date FROM generate_series(DATE '%s', DATE '%s', interval '1 day') d "
                    "WHERE d::date NOT IN (SELECT DISTINCT %s FROM public.%s "
                    "WHERE %s BETWEEN DATE '%s' AND DATE '%s') ORDER BY 1"
                    % (lo.isoformat(), end.isoformat(), column, table,
                       column, lo.isoformat(), end.isoformat())).fetchall()]
            except Exception as exc:  # noqa: BLE001
                self.failures.append(f"断档 {table}: {type(exc).__name__}: {exc}")
                continue
            span = (end - lo).days + 1
            key = f"gap.{table}"
            self.values[key] = len(gaps)
            if gaps:
                shown = ", ".join(g.isoformat() for g in gaps[:12])
                more = f" …等 {len(gaps)} 天" if len(gaps) > 12 else ""
                status = RED if len(gaps) >= 3 else YELLOW
                self.add(area, label, status, f"缺 {len(gaps)}/{span} 天", key=key,
                         value=len(gaps), note=f"缺失：{shown}{more}")
            else:
                self.add(area, label, OK, f"完整（{span} 天）", key=key, value=0,
                         note="无断档")

    def check_foreign_keys(self) -> None:
        area = "引用完整性"
        fks = self.conn.exec_driver_sql("""
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
        """).mappings().fetchall()
        total_orphans = 0
        bad: list[str] = []
        for fk in fks:
            ccols = [c for c in (fk["ccols"] or []) if IDENT.match(c)]
            pcols = [c for c in (fk["pcols"] or []) if IDENT.match(c)]
            if not ccols or not pcols:
                continue
            guard = " AND ".join(f"c.{c} IS NOT NULL" for c in ccols)
            join = " AND ".join(f"p.{pc} = c.{cc}" for cc, pc in zip(ccols, pcols))
            child = fk["child"].replace("public.", "")
            parent = fk["parent"].replace("public.", "")
            if not IDENT.match(child) or not IDENT.match(parent):
                continue
            try:
                orphans = int(self.scalar(
                    f"SELECT count(*) FROM public.{child} c WHERE {guard} "
                    f"AND NOT EXISTS (SELECT 1 FROM public.{parent} p WHERE {join})") or 0)
            except Exception as exc:  # noqa: BLE001
                self.failures.append(f"外键 {fk['conname']}: {type(exc).__name__}: {exc}")
                continue
            if orphans:
                total_orphans += orphans
                bad.append(f"{child}.{fk['conname']} = {orphans:,} 行")
        self.values["fk.orphans"] = total_orphans
        if bad:
            self.add(area, f"外键孤儿行（{len(fks)} 个外键）", RED,
                     f"{total_orphans:,} 行", key="fk.orphans", value=total_orphans,
                     note="；".join(bad))
        else:
            self.add(area, f"外键孤儿行（{len(fks)} 个外键）", OK, "0 行",
                     key="fk.orphans", value=0, note="全部外键均无孤儿行")

    def check_inventory(self) -> None:
        area = "进销存勾稽"
        checks = [
            ("单据总数", "SELECT count(*) FROM public.inventory_records", OK, "rows.inv_docs"),
            ("已软删除单据", "SELECT count(*) FROM public.inventory_records WHERE deleted_at IS NOT NULL",
             GRAY, "inv.deleted_docs"),
            ("无明细行的空单据",
             "SELECT count(*) FROM public.inventory_records r "
             "WHERE NOT EXISTS (SELECT 1 FROM public.inventory_details d WHERE d.document_id = r.id)",
             RED, "inv.empty_docs"),
            ("total_count 与明细合计不符（明细数量完整）",
             "SELECT count(*) FROM (SELECT r.id FROM public.inventory_records r "
             "JOIN public.inventory_details d ON d.document_id = r.id "
             "WHERE r.deleted_at IS NULL GROUP BY r.id, r.total_count "
             "HAVING count(*) FILTER (WHERE d.quantity IS NULL) = 0 "
             "AND r.total_count IS DISTINCT FROM COALESCE(SUM(d.quantity),0)) x",
             YELLOW, "inv.qty_mismatch"),
            ("amount 与明细合计不符",
             "SELECT count(*) FROM (SELECT r.id FROM public.inventory_records r "
             "JOIN public.inventory_details d ON d.document_id = r.id "
             "WHERE r.deleted_at IS NULL GROUP BY r.id, r.amount "
             "HAVING r.amount IS DISTINCT FROM COALESCE(SUM(d.amount),0)) x",
             YELLOW, "inv.amount_mismatch"),
            ("明细 amount ≠ 数量 × 单价",
             "SELECT count(*) FROM public.inventory_details WHERE quantity IS NOT NULL "
             "AND unit_price IS NOT NULL AND amount IS NOT NULL "
             "AND round(quantity * unit_price, 2) <> round(amount, 2)",
             YELLOW, "inv.line_math"),
            ("挂在已软删除单据下的明细行",
             "SELECT count(*) FROM public.inventory_details d "
             "JOIN public.inventory_records r ON r.id = d.document_id "
             "WHERE r.deleted_at IS NOT NULL", YELLOW, "inv.details_under_deleted"),
            ("未关联商品身份的明细",
             "SELECT count(*) FROM public.inventory_details WHERE product_identity_id IS NULL",
             RED, "inv.no_identity"),
        ]
        thresholds = {"inv.empty_docs": 0, "inv.no_identity": 0, "inv.qty_mismatch": 0,
                      "inv.amount_mismatch": 0, "inv.line_math": 0}
        for label, sql, bad_status, key in checks:
            try:
                value = int(self.scalar(sql) or 0)
            except Exception as exc:  # noqa: BLE001
                self.failures.append(f"{label}: {type(exc).__name__}: {exc}")
                continue
            limit = thresholds.get(key)
            if limit is None:
                status, note = GRAY, ""
            elif value > limit:
                status, note = bad_status, "需要处理"
            else:
                status, note = OK, "正常"
            self.add(area, label, status, f"{value:,}", key=key, value=value, note=note)

        # how many of the identity-less rows *could* have been matched
        try:
            union = " UNION ".join(
                f"SELECT sku AS s FROM public.{t} WHERE sku IS NOT NULL "
                f"UNION ALL SELECT original_sku FROM public.{t} WHERE original_sku IS NOT NULL"
                for t in ("cbanner_mens_products", "cbanner_womens_products", "yandou_products",
                          "eblan_products", "smiley_products", "ni_products",
                          "manual_product_archive_31"))
            matchable = int(self.scalar(
                f"SELECT count(*) FROM public.inventory_details d "
                f"WHERE d.product_identity_id IS NULL AND d.product_code IS NOT NULL "
                f"AND EXISTS (SELECT 1 FROM ({union}) a WHERE a.s = d.product_code)") or 0)
            self.add(area, "↳ 其中货号在档案中（本应能匹配）", RED if matchable else OK,
                     f"{matchable:,}", key="inv.matchable_no_identity", value=matchable,
                     note="触发器未解析出身份" if matchable else "正常")
        except Exception as exc:  # noqa: BLE001
            self.failures.append(f"identity matchable: {type(exc).__name__}: {exc}")

        try:
            amount = self.scalar(
                "SELECT COALESCE(SUM(d.amount),0) FROM public.inventory_details d "
                "JOIN public.inventory_records r ON r.id = d.document_id "
                "WHERE r.deleted_at IS NOT NULL") or 0
            self.add(area, "↳ 上述明细的金额合计", GRAY, f"{float(amount):,.2f}",
                     key="inv.details_under_deleted_amount", value=float(amount),
                     note="统计若未过滤 deleted_at 会虚增此金额")
        except Exception as exc:  # noqa: BLE001
            self.failures.append(f"deleted amount: {type(exc).__name__}: {exc}")

    def check_product_archives(self) -> None:
        area = "商品档案"
        archives = ("cbanner_mens_products", "cbanner_womens_products", "yandou_products",
                    "eblan_products", "smiley_products", "ni_products",
                    "manual_product_archive_31")
        try:
            union = " UNION ALL ".join(
                f"SELECT '{t}' AS brand, sku FROM public.{t} WHERE sku IS NOT NULL"
                for t in archives)
            info = self.one(f"SELECT count(*) AS total, count(DISTINCT sku) AS distinct_sku "
                            f"FROM ({union}) x")
            total, distinct = int(info["total"]), int(info["distinct_sku"])
            dup = total - distinct
            self.add(area, "跨品牌重复货号", YELLOW if dup else OK, f"{dup:,}",
                     key="arch.dup_sku", value=dup,
                     note="同一货号出现在多个品牌档案" if dup else "正常")
        except Exception as exc:  # noqa: BLE001
            self.failures.append(f"dup sku: {type(exc).__name__}: {exc}")

        try:
            missing = int(self.scalar(
                f"SELECT count(*) FROM ({' UNION '.join(f'SELECT sku FROM public.{t} WHERE sku IS NOT NULL' for t in archives)}) a "
                f"WHERE NOT EXISTS (SELECT 1 FROM public.product_archive_identities i WHERE i.sku = a.sku)") or 0)
            self.add(area, "档案货号未登记到身份表", RED if missing else OK, f"{missing:,}",
                     key="arch.no_identity", value=missing, note="正常" if not missing else "需回填")
        except Exception as exc:  # noqa: BLE001
            self.failures.append(f"archive identity: {type(exc).__name__}: {exc}")

        for table in archives:
            if not self.table_exists(table):
                continue
            try:
                info = self.one(
                    f"SELECT count(*) AS rows, "
                    f"count(*) FILTER (WHERE sku IS NULL) AS no_sku, "
                    f"count(*) FILTER (WHERE image_path IS NULL) AS no_image, "
                    f"max(last_imported_at) AS last_import "
                    f"FROM public.{table}")
            except Exception as exc:  # noqa: BLE001
                self.failures.append(f"{table}: {type(exc).__name__}: {exc}")
                continue
            rows = int(info["rows"] or 0)
            if rows == 0:
                continue
            no_image_pct = int(info["no_image"] or 0) / rows * 100
            key = f"arch.{table}.no_image_pct"
            note, worsened = self.delta_note(key, no_image_pct)
            self.add(area, f"{table} 图片路径缺失", YELLOW if worsened else GRAY,
                     f"{int(info['no_image'] or 0):,}/{rows:,}（{no_image_pct:.1f}%）",
                     key=key, value=round(no_image_pct, 3),
                     note=f"最近导入时间：{info['last_import'] or '从未'}")

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
                  AND (s.last_analyze IS NULL
                       OR s.last_analyze < now() - interval '7 days')
            """) or 0)
            self.add(area, "超过 7 天未 ANALYZE 的大表", YELLOW if stale else OK,
                     f"{stale} 张", key="ops.stale_stats", value=stale,
                     note="统计信息陈旧会让查询计划变差" if stale else "正常")
        except Exception as exc:  # noqa: BLE001
            self.failures.append(f"stale stats: {type(exc).__name__}: {exc}")

        try:
            empties = []
            for row in self.conn.exec_driver_sql("""
                SELECT c.relname FROM pg_class c
                JOIN pg_namespace n ON n.oid = c.relnamespace
                WHERE c.relkind = 'r' AND n.nspname = 'public'
                  AND pg_relation_size(c.oid) < 200 * 1024 * 1024
                ORDER BY c.relname
            """).fetchall():
                name = row[0]
                if not IDENT.match(name):
                    continue
                if int(self.scalar(f"SELECT count(*) FROM public.{name}") or 0) == 0:
                    empties.append(name)
            self.values["ops.empty_tables"] = len(empties)
            self.add(area, "精确为空的表", GRAY, f"{len(empties)} 张",
                     key="ops.empty_tables", value=len(empties),
                     note="、".join(empties) if empties else "无")
        except Exception as exc:  # noqa: BLE001
            self.failures.append(f"empty tables: {type(exc).__name__}: {exc}")

    def check_record_key(self) -> None:
        """The dedup key must keep being written; watch it per month."""
        area = "去重键覆盖"
        table = "jst_monthly_orders"
        if not self.table_exists(table):
            return
        try:
            rows = self.conn.exec_driver_sql(f"""
                SELECT to_char(date_trunc('month', order_time_at), 'YYYY-MM') AS mon,
                       count(*) AS rows,
                       count(*) FILTER (WHERE record_key IS NULL) AS null_key
                FROM public.{table}
                WHERE order_time_at >= date_trunc('month', current_date) - interval '5 months'
                GROUP BY 1 ORDER BY 1
            """).fetchall()
        except Exception as exc:  # noqa: BLE001
            self.failures.append(f"record_key: {type(exc).__name__}: {exc}")
            return
        worst = 0.0
        for mon, total, null_key in rows:
            total = int(total or 0)
            null_key = int(null_key or 0)
            if not total:
                continue
            pct = null_key / total * 100
            key = f"record_key.{mon}"
            self.values[key] = round(pct, 3)
            self.add(area, f"{table} {mon} record_key 缺失", RED if pct > 1 else OK,
                     f"{null_key:,}/{total:,}（{pct:.1f}%）",
                     key=key, value=round(pct, 3),
                     note="去重键未写入，唯一约束失效" if pct > 1 else "正常")
            if mon >= date.today().strftime("%Y-%m"):
                worst = max(worst, pct)
        # already-inserted duplicates among rows lacking the key
        try:
            dup = int(self.scalar(f"""
                SELECT COALESCE(SUM(c - 1), 0) FROM (
                  SELECT internal_order_id, product_code, order_time_at, count(*) AS c
                  FROM public.{table}
                  WHERE record_key IS NULL
                    AND order_time_at >= date_trunc('month', current_date) - interval '2 months'
                  GROUP BY 1,2,3 HAVING count(*) > 1) x
            """) or 0)
            self.add(area, "疑似重复订单行（近 3 个月，按订单号+货号+下单时间）",
                     RED if dup else OK, f"{dup:,} 行", key="record_key.dups", value=dup,
                     note="需要去重" if dup else "正常")
        except Exception as exc:  # noqa: BLE001
            self.failures.append(f"record_key dups: {type(exc).__name__}: {exc}")

    # ---- rendering --------------------------------------------------------
    def render(self, started: datetime, duration: float, db_name: str) -> str:
        counts = {s: sum(1 for r in self.rows if r["status"] == s)
                  for s in (RED, YELLOW, GRAY, OK)}
        new_alerts = [r for r in self.rows
                      if r["status"] == RED and r["name"] not in self.previous
                      and any(r["name"] == x for x in [])]  # placeholder, see below
        # "new" = red item whose numeric key is absent from the previous run
        new_alerts = []
        for r in self.rows:
            if r["status"] != RED:
                continue
            key = self._key_of(r)
            if key and key not in self.previous:
                new_alerts.append(r)
        lines: list[str] = []
        add = lines.append
        add("# 数据库缺失数据周报")
        add("")
        add(f"- **生成时间**：{started.strftime('%Y-%m-%d %H:%M:%S')}")
        add(f"- **数据库**：`{db_name}`")
        add(f"- **检查区间**：最近 {self.days} 天（日期断档部分）")
        add(f"- **耗时**：{duration:.1f} 秒 ｜ **检查项**：{len(self.rows)}")
        add("- **性质**：只读检查，未修改任何数据" if True else "")
        add("")
        add("## 一、结论")
        add("")
        add(f"本次共检查 **{len(self.rows)}** 项："
            f"🔴 {counts[RED]} 项、🟡 {counts[YELLOW]} 项、⚪ {counts[GRAY]} 项（已知长期为空）、"
            f"✅ {counts[OK]} 项。")
        add("")
        if counts[RED] == 0:
            add("**没有需要处理的缺失数据问题。**")
        else:
            add(f"**有 {counts[RED]} 项需要处理**，见第二节。")
            if new_alerts:
                add("")
                add("其中**本次新增**（上周没有记录到）：")
                for r in new_alerts:
                    add(f"- {r['name']} — {r['detail']}")
        add("")
        if self.failures:
            add(f"> ⚠️ 有 {len(self.failures)} 项检查未能完成（超时或报错），见文末。")
            add("")
        add("> 说明：🔴 需要处理 ｜ 🟡 需要关注 ｜ ⚪ 已知长期为空（只报变化） ｜ ✅ 正常")
        add("")

        for status, title in ((RED, "二、🔴 需要处理"), (YELLOW, "三、🟡 需要关注"),
                              (GRAY, "四、⚪ 已知长期为空（只关注是否恶化）"),
                              (OK, "五、✅ 检查通过")):
            items = [r for r in self.rows if r["status"] == status]
            add(f"## {title}")
            add("")
            if not items:
                add("无。")
                add("")
                continue
            current_area = None
            for r in items:
                if r["area"] != current_area:
                    current_area = r["area"]
                    add(f"**{current_area}**")
                    add("")
                    add("| 检查项 | 结果 | 说明 |")
                    add("|---|---|---|")
                note = r["note"].replace("|", "\\|") if r["note"] else ""
                add(f"| {r['name']} | {r['detail']} | {note} |")
                add("") if False else None
            add("")

        add("## 六、本周与上周对比")
        add("")
        changed = []
        for k, v in self.values.items():
            old = self.previous.get(k)
            if old is None or isinstance(v, (str,)) or isinstance(old, str):
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
        add("*本报告由计划任务 `HedeDatabaseMissingDataReview` 自动生成；"
            "明细日志见 `backend/logs/missing_data_review.log`。*")
        return "\n".join(x for x in lines if x is not None)

    def _key_of(self, row: dict[str, Any]) -> str | None:
        for k, v in self.values.items():
            if v == row.get("_value"):
                return k
        return None


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
                        help="报告输出目录（默认为桌面）")
    parser.add_argument("--days", type=int, default=90,
                        help="日期断档检查的回看天数（默认 90）")
    parser.add_argument("--state-file", type=Path,
                        default=BACKEND_ROOT / "logs" / "missing_data_review_state.json")
    parser.add_argument("--history-dir", type=Path,
                        default=BACKEND_ROOT / "logs" / "missing_data_reports")
    parser.add_argument("--statement-timeout-ms", type=int, default=300_000)
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
    review: Review | None = None

    with engine.connect() as conn:
        conn = conn.execution_options(isolation_level="AUTOCOMMIT")
        conn.exec_driver_sql(f"SET statement_timeout = {int(args.statement_timeout_ms)}")
        review = Review(conn, args.days, state)
        for check in (review.check_rowcounts, review.check_null_columns,
                      review.check_date_coverage, review.check_record_key,
                      review.check_foreign_keys, review.check_inventory,
                      review.check_product_archives, review.check_operations):
            name = check.__name__
            print(f"  running {name} ...")
            try:
                check()
            except Exception as exc:  # noqa: BLE001
                review.failures.append(f"{name}: {type(exc).__name__}: {exc}")
                print(f"  !! {name} failed: {type(exc).__name__}: {exc}")

    finished = datetime.now()
    duration = (finished - started).total_seconds()
    report = review.render(started, duration, db_name)

    args.history_dir.mkdir(parents=True, exist_ok=True)
    filename = f"数据库缺失数据周报_{started.strftime('%Y-%m-%d')}.md"
    for target in (args.history_dir / filename, (args.output_dir or _desktop_dir()) / filename):
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(report, encoding="utf-8-sig")
            print(f"[report] {target}")
        except Exception as exc:  # noqa: BLE001
            print(f"[report] FAILED to write {target}: {type(exc).__name__}: {exc}")

    history = state.get("history", [])
    history.append({"run": started.isoformat(timespec="seconds"),
                    "red": sum(1 for r in review.rows if r["status"] == RED),
                    "yellow": sum(1 for r in review.rows if r["status"] == YELLOW)})
    _save_state(args.state_file, {"last_run": started.isoformat(timespec="seconds"),
                                  "values": review.values, "history": history[-52:]})

    reds = sum(1 for r in review.rows if r["status"] == RED)
    print(f"[{finished.isoformat(timespec='seconds')}] done in {duration:.1f}s "
          f"red={reds} failures={len(review.failures)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())