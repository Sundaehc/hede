"""Seventh pass: partitioned-index usage at parent level, aggregate per family."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import psycopg
from psycopg.rows import dict_row

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from audit import database_url  # noqa: E402

OUT: list[str] = []


def p(s: str = "") -> None:
    OUT.append(s)
    with open(HERE / "findings7.txt", "a", encoding="utf-8") as fh:
        fh.write(s + "\n")


(HERE / "findings7.txt").write_text("", encoding="utf-8")


with psycopg.connect(database_url(), autocommit=True) as conn:
    p("## PARTITIONED (PARENT) INDEXES: usage aggregated over children")
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute("""
            SELECT parent.relname AS parent_table,
                   pi.indexrelid::regclass::text AS parent_index,
                   pi.indisunique, pi.indisprimary,
                   pg_get_indexdef(pi.indexrelid) AS def,
                   pg_size_pretty(SUM(pg_relation_size(ci.indexrelid))) AS children_size,
                   COALESCE(SUM(si.idx_scan),0) AS child_scans,
                   count(*) AS n_children
            FROM pg_inherits inh
            JOIN pg_class parent ON parent.oid = inh.inhparent
            JOIN pg_index pi ON pi.indrelid = parent.oid
            JOIN pg_inherits ci_inh ON ci_inh.inhparent = pi.indexrelid
            JOIN pg_index ci ON ci.indexrelid = ci_inh.inhrelid
            LEFT JOIN pg_stat_user_indexes si ON si.indexrelid = ci.indexrelid
            JOIN pg_namespace n ON n.oid = parent.relnamespace
            WHERE parent.relkind = 'p' AND n.nspname = 'public'
            GROUP BY 1,2,3,4,5
            ORDER BY 1, SUM(pg_relation_size(ci.indexrelid)) DESC
        """)
        for r in cur.fetchall():
            flag = "   <-- ZERO SCANS" if r["child_scans"] == 0 else ""
            p(f"  {r['parent_table']:<35} {r['parent_index']:<58} children={r['n_children']} "
              f"size={r['children_size']:>9} scans={r['child_scans']:>12,} "
              f"unique={r['indisunique']}{flag}")
            p(f"        {r['def']}")
    p()

    p("## jst_aftersale_returns: per-index usage (standalone partitions, no parent index)")
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute("""
            SELECT s.relname AS tbl, s.indexrelname AS idx, s.idx_scan,
                   pg_size_pretty(pg_relation_size(s.indexrelid)) AS size,
                   pg_get_indexdef(s.indexrelid) AS def
            FROM pg_stat_user_indexes s
            WHERE s.relname LIKE 'jst_aftersale_returns_20%'
            ORDER BY s.relname, pg_relation_size(s.indexrelid) DESC
        """)
        for r in cur.fetchall():
            p(f"  {r['tbl']:<28} {r['idx']:<55} scans={r['idx_scan']:>7} {r['size']:>9}")
            p(f"        {r['def']}")
    p()

    p("## vip_daily_sales / jst_daily_sales / snapshots: per-index usage")
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute("""
            SELECT s.relname AS tbl, s.indexrelname AS idx, s.idx_scan,
                   pg_size_pretty(pg_relation_size(s.indexrelid)) AS size,
                   pg_get_indexdef(s.indexrelid) AS def
            FROM pg_stat_user_indexes s
            WHERE s.relname IN ('vip_daily_sales_2026','jst_daily_sales_2026',
                                'product_goods_detail_snapshots_2026','dewu_orders_2026',
                                'jst_daily_stock','jst_product_price','jst_size_stock_snapshots',
                                'gj_merged_product_info','vip_product_ops_snapshots')
            ORDER BY s.relname, pg_relation_size(s.indexrelid) DESC
        """)
        for r in cur.fetchall():
            p(f"  {r['tbl']:<35} {r['idx']:<58} scans={r['idx_scan']:>12,} {r['size']:>9}")
    p()

    p("## TABLES WITH ZERO-SCAN INDEXES: aggregate waste per table")
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute("""
            SELECT s.relname AS tbl,
                   count(*) AS unused_indexes,
                   pg_size_pretty(SUM(pg_relation_size(s.indexrelid))) AS unused_size,
                   (SELECT count(*) FROM pg_index i WHERE i.indrelid = s.relid) AS total_indexes,
                   pg_size_pretty(pg_total_relation_size(s.relid)) AS table_size
            FROM pg_stat_user_indexes s
            JOIN pg_index i ON i.indexrelid = s.indexrelid
            WHERE s.idx_scan = 0 AND NOT i.indisprimary AND NOT i.indisunique
            GROUP BY s.relname, s.relid
            ORDER BY SUM(pg_relation_size(s.indexrelid)) DESC LIMIT 20
        """)
        for r in cur.fetchall():
            p(f"  {r['tbl']:<45} unused={r['unused_indexes']:>2}/{r['total_indexes']:<2} "
              f"{r['unused_size']:>10} of {r['table_size']}")
    p()

    p("## SERVER GUCs THAT NEED A RESTART vs RELOAD")
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute("""
            SELECT name, setting, pending_restart, context
            FROM pg_settings
            WHERE name IN ('shared_buffers','shared_preload_libraries','max_connections',
                           'max_worker_processes','work_mem','maintenance_work_mem',
                           'effective_cache_size','max_wal_size','random_page_cost',
                           'effective_io_concurrency','autovacuum_max_workers','wal_compression',
                           'default_toast_compression','track_io_timing','autovacuum_vacuum_scale_factor',
                           'autovacuum_analyze_scale_factor','autovacuum_vacuum_cost_limit','jit')
            ORDER BY context, name
        """)
        for r in cur.fetchall():
            p(f"  {r['name']:<35} {str(r['setting']):<12} context={r['context']:<12} pending_restart={r['pending_restart']}")
    p()

    p("## DATABASE-LEVEL SETTINGS (ALTER DATABASE) IF ANY")
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute("""
            SELECT d.datname, r.rolname, s.setconfig
            FROM pg_db_role_setting s
            JOIN pg_database d ON d.oid = s.setdatabase
            LEFT JOIN pg_roles r ON r.oid = s.setrole
        """)
        for r in cur.fetchall():
            p(f"  db/role setting: db={r['datname']} role={r['rolname']} {r['setconfig']}")
        cur.execute("""
            SELECT rolname, rolconfig FROM pg_roles WHERE rolconfig IS NOT NULL
        """)
        for r in cur.fetchall():
            p(f"  role {r['rolname']}: {r['rolconfig']}")

(HERE / "findings7.txt").write_text("\n".join(OUT), encoding="utf-8")
print(f"[written] {HERE / 'findings7.txt'} sections={len(OUT)}")