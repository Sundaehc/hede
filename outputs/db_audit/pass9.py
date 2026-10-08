"""Ninth pass: do the never-analyzed tables actually have column statistics?"""
from __future__ import annotations

import sys
from pathlib import Path

import psycopg
from psycopg.rows import dict_row

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from audit import database_url  # noqa: E402

OUT: list[str] = []
(HERE / "findings9.txt").write_text("", encoding="utf-8")


def p(s: str = "") -> None:
    OUT.append(s)
    with open(HERE / "findings9.txt", "a", encoding="utf-8") as fh:
        fh.write(s + "\n")


TABLES = [
    "fine_table_snapshot_payloads", "fine_table_snapshot_metrics", "fine_table_snapshot_refs_2026",
    "fine_table_snapshot_refs_2025", "fine_table_snapshot_refs_2024", "jst_product_profiles",
    "product_goods_historical_sales_2025", "product_goods_historical_sales_2024",
    "product_size_group_mappings", "gj_merged_product_info", "jst_product_price",
    "jst_daily_stock", "vip_product_ops_snapshots", "vip_product_daily_snapshots",
    "jst_purchase_inbound_daily", "jst_aftersale_returns_2024", "jst_aftersale_returns_2025",
    "jst_daily_sales_2026", "product_goods_detail_snapshots_2026",
]

with psycopg.connect(database_url(), autocommit=True) as conn:
    p("## COLUMN STATISTICS PRESENCE (pg_stats) vs pg_stat_user_tables counters")
    p(f"  {'table':<42} {'cols':>5} {'cols_with_stats':>15} {'rows_in_pg_statistic':>20} {'reltuples':>12}")
    for t in TABLES:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute("""
                SELECT (SELECT count(*) FROM pg_attribute a
                         WHERE a.attrelid = ('public.'||%s)::regclass AND a.attnum>0 AND NOT a.attisdropped) AS cols,
                       (SELECT count(*) FROM pg_stats s
                         WHERE s.schemaname='public' AND s.tablename=%s) AS with_stats,
                       (SELECT count(*) FROM pg_statistic st
                         WHERE st.starelid = ('public.'||%s)::regclass) AS stat_rows,
                       (SELECT c.reltuples::bigint FROM pg_class c
                         WHERE c.oid = ('public.'||%s)::regclass) AS reltuples
            """, (t, t, t, t))
            r = cur.fetchone()
        flag = ""
        if r["cols"] and r["with_stats"] == 0:
            flag = "   <-- NO COLUMN STATISTICS"
        elif r["cols"] and r["with_stats"] < r["cols"] * 0.5:
            flag = "   <-- partial statistics"
        p(f"  {t:<42} {r['cols']:>5} {r['with_stats']:>15} {r['stat_rows']:>20} "
          f"{r['reltuples']:>12,}{flag}")
    p()

    p("## STATS-FRESHNESS WINDOW")
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute("SELECT stats_reset FROM pg_stat_wal")
        p(f"  pg_stat_wal.stats_reset (server start proxy) = {cur.fetchone()['stats_reset']}")
        cur.execute("SELECT pg_postmaster_start_time()")
        p(f"  postmaster start time                        = {cur.fetchone()['pg_postmaster_start_time']}")
        cur.execute("SELECT now()")
        p(f"  now                                          = {cur.fetchone()['now']}")
    p()

    p("## TABLES WHOSE reltuples DISAGREES WITH THE EXACT COUNT BY >20%")
    for t in ("jst_product_profiles", "fine_table_snapshot_refs_2026"):
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(f'SELECT count(*) AS exact FROM public."{t}"')
            exact = cur.fetchone()["exact"]
            cur.execute("SELECT reltuples::bigint AS est FROM pg_class WHERE oid=('public.'||%s)::regclass", (t,))
            est = cur.fetchone()["est"]
        p(f"  {t:<42} exact={exact:>10,} reltuples={est:>10,} delta={100.0*(exact-est)/max(exact,1):+.1f}%")
    p()

print(f"[written] {HERE / 'findings9.txt'} sections={len(OUT)}")