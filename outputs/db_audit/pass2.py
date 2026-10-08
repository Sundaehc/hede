"""Second pass: precise checks that the first pass could only estimate."""
from __future__ import annotations

import json
import re
from collections import defaultdict
from pathlib import Path

import psycopg
from psycopg.rows import dict_row

HERE = Path(__file__).resolve().parent
RAW = json.loads((HERE / "raw.json").read_text(encoding="utf-8"))
AUDIT = Path(__file__).resolve().parent / "audit.py"
import sys

sys.path.insert(0, str(AUDIT.parent))
from audit import database_url  # noqa: E402

OUT: list[str] = []


def p(s: str = "") -> None:
    OUT.append(s)
    with open(HERE / "findings2.txt", "a", encoding="utf-8") as fh:
        fh.write(s + "\n")


def mb(n) -> str:
    try:
        return f"{float(n) / 1048576:,.1f}MB"
    except Exception:
        return str(n)


WATCH = [
    "fine_table_snapshot_refs_2024",
    "fine_table_snapshot_refs_2025",
    "fine_table_snapshot_refs_2026",
    "jst_product_profiles",
    "product_goods_historical_sales_2024",
    "product_goods_historical_sales_2025",
    "product_size_group_mappings",
    "product_goods_historical_orders_2024",
    "product_goods_historical_orders_2025",
    "fine_table_snapshot_payloads",
    "jst_purchase_backup_20260926_164350",
    "jst_purchase_restore_20260926_164350",
    "jst_monthly_orders_2024",
    "jst_aftersale_returns_2024",
    "dewu_orders_2026",
    "vip_daily_sales_2026",
    "product_goods_detail_snapshots_2026",
]

(HERE / "findings2.txt").write_text("", encoding="utf-8")

with psycopg.connect(database_url(), autocommit=True) as conn:
    p("## EXACT COUNTS, PARTITION STATUS, BLOAT FOR WATCHED TABLES")
    p(f"{'table':<45} {'exact_rows':>12} {'relpages':>10} {'reltuples':>12} part parent")
    for t in WATCH:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                SELECT c.relname, c.relispartition, c.relpages, c.reltuples::bigint AS reltuples,
                       inh.inhparent::regclass::text AS parent, c.relfilenode
                FROM pg_class c LEFT JOIN pg_inherits inh ON inh.inhrelid = c.oid
                WHERE c.relname = %s AND c.relkind IN ('r','p') AND c.relnamespace = 'public'::regnamespace
                """,
                (t,),
            )
            meta = cur.fetchone()
        if not meta:
            p(f"{t:<45} (not found)")
            continue
        if meta["relpages"] * 8192 > 2 * 1024**3:
            n = f"(skipped:{meta['reltuples']})"
        else:
            with conn.cursor() as cur:
                cur.execute(f'SELECT count(*) FROM public."{t}"')
                n = cur.fetchone()[0]
        p(f"{t:<45} {str(n):>20} {meta['relpages']:>10} {meta['reltuples']:>12} "
          f"{'partition of ' + meta['parent'] if meta['relispartition'] else 'standalone'}")
    p()

    p("## PARTITIONED PARENTS: PK / UNIQUE / PARTITION COVERAGE")
    grab_sql = """
        SELECT parent.relname AS parent_table,
               (SELECT count(*) FROM pg_index i WHERE i.indrelid = parent.oid AND i.indisprimary) AS has_pk,
               (SELECT count(*) FROM pg_index i WHERE i.indrelid = parent.oid AND i.indisunique) AS has_unique,
               (SELECT count(*) FROM pg_inherits inh WHERE inh.inhparent = parent.oid) AS n_parts,
               pg_get_expr(parent.relpartbound, parent.oid) AS bound
        FROM pg_class parent
        JOIN pg_namespace n ON n.oid = parent.relnamespace
        WHERE parent.relkind = 'p' AND n.nspname = 'public'
        ORDER BY parent.relname
    """
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(grab_sql)
        for r in cur.fetchall():
            p(f"  {r['parent_table']:<40} pk={r['has_pk']} unique={r['has_unique']} parts={r['n_parts']}")
    p()

    p("## PARTITION CHILD INDEXES: is indisprimary propagated?")
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute("""
            SELECT i.indexrelid::regclass::text AS idx, i.indisprimary, i.indisunique,
                   i.indisvalid, parent.relname AS parent_tbl
            FROM pg_index i
            JOIN pg_class c ON c.oid = i.indrelid
            JOIN pg_inherits inh ON inh.inhrelid = c.oid
            JOIN pg_class parent ON parent.oid = inh.inhparent
            WHERE c.relname IN ('jst_monthly_orders_2026','jst_aftersale_returns_2026')
            ORDER BY 4, 1
        """)
        for r in cur.fetchall():
            p(f"  {r['parent_tbl']:<25} {r['idx']:<60} primary={r['indisprimary']} unique={r['indisunique']}")
    p()

    p("## PARTITIONED TABLES MISSING A FUTURE/RELEVANT PARTITION")
    for parent in ("jst_monthly_orders", "jst_aftersale_returns", "dewu_orders",
                   "product_goods_detail_snapshots", "product_goods_historical_sales",
                   "product_goods_historical_orders", "vip_daily_sales", "jst_daily_sales"):
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute("""
                SELECT c.relname, pg_get_expr(c.relpartbound, c.oid) AS bound, c.reltuples::bigint AS reltuples
                FROM pg_inherits inh
                JOIN pg_class c ON c.oid = inh.inhrelid
                JOIN pg_class p ON p.oid = inh.inhparent
                WHERE p.relname = %s ORDER BY c.relname
            """, (parent,))
            rows = cur.fetchall()
        if rows:
            p(f"  {parent}: {[ (r['relname'], r['bound'][:40]) for r in rows ]}")
    p()

    p("## AUTOVACUUM / VACUUM HISTORY OF LARGE TABLES (>1GB)")
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute("""
            SELECT c.relname,
                   pg_size_pretty(pg_total_relation_size(c.oid)) AS size,
                   COALESCE(s.n_live_tup,0) AS live, COALESCE(s.n_dead_tup,0) AS dead,
                   COALESCE(s.n_mod_since_analyze,0) AS mod_since_analyze,
                   s.last_vacuum, s.last_autovacuum, s.last_analyze, s.last_autoanalyze,
                   COALESCE(s.vacuum_count,0) AS vac, COALESCE(s.autovacuum_count,0) AS avac,
                   COALESCE(s.autoanalyze_count,0) AS aana, COALESCE(s.analyze_count,0) AS ana,
                   c.reloptions
            FROM pg_class c
            JOIN pg_namespace n ON n.oid=c.relnamespace
            LEFT JOIN pg_stat_user_tables s ON s.relid=c.oid
            WHERE c.relkind='r' AND n.nspname='public'
              AND pg_total_relation_size(c.oid) > 1073741824
            ORDER BY pg_total_relation_size(c.oid) DESC
        """)
        for r in cur.fetchall():
            p(f"  {r['relname']:<45} {r['size']:>9} live={r['live']:>10} dead={r['dead']:>8} "
              f"mod={r['mod_since_analyze']:>9} vac={r['vac']} avac={r['avac']} aana={r['aana']} "
              f"last_autoanalyze={r['last_autoanalyze']} opts={r['reloptions']}")
    p()

    # ---- refined duplicate index detection (method + full definition aware) ----
    p("## TRUE DUPLICATE INDEXES (same method, keys, expressions and predicate)")
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute("""
            SELECT i.indexrelid::regclass::text AS index_name,
                   i.indrelid::regclass::text AS table_name,
                   pg_get_indexdef(i.indexrelid) AS def,
                   pg_relation_size(i.indexrelid) AS bytes,
                   i.indisprimary, i.indisunique, i.indisexclusion,
                   pg_get_expr(i.indpred, i.indrelid) AS pred,
                   am.amname AS method
            FROM pg_index i
            JOIN pg_class ic ON ic.oid=i.indexrelid
            JOIN pg_am am ON am.oid=ic.relam
            JOIN pg_class c ON c.oid=i.indrelid
            JOIN pg_namespace n ON n.oid=c.relnamespace
            WHERE n.nspname='public' AND i.indisvalid
        """)
        rows = cur.fetchall()

    def norm(r):
        d = r["def"]
        d = re.sub(r"^CREATE (UNIQUE )?INDEX \S+ ON ", "ON ", d)
        d = re.sub(r"\s+TABLESPACE \S+", "", d)
        return d

    groups = defaultdict(list)
    for r in rows:
        groups[(r["table_name"], norm(r))].append(r)
    total_dup = 0
    for (tbl, d), grp in sorted(groups.items()):
        if len(grp) > 1:
            p(f"  {tbl}: {d}")
            for g in grp:
                p(f"      {g['index_name']:<65} {mb(g['bytes'])} primary={g['indisprimary']}")
                if not g["indisprimary"]:
                    total_dup += int(g["bytes"])
    p(f"  -> reclaimable (excl. primaries): {mb(total_dup)}")
    p()

    # ---- exact duplicate-key detection: identical leading key columns, one unique, one not
    p("## UNIQUE INDEX SHADOWED BY A NON-UNIQUE INDEX WITH IDENTICAL KEYS")
    shadow = 0
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute("""
            SELECT i.indrelid::regclass::text AS tbl, i.indexrelid::regclass::text AS idx,
                   i.indisunique, i.indisprimary, i.indkey::text AS key,
                   pg_relation_size(i.indexrelid) AS bytes, am.amname AS method
            FROM pg_index i
            JOIN pg_class ic ON ic.oid=i.indexrelid
            JOIN pg_am am ON am.oid=ic.relam
            JOIN pg_class c ON c.oid=i.indrelid JOIN pg_namespace n ON n.oid=c.relnamespace
            WHERE n.nspname='public' AND i.indisvalid
        """)
        rows = cur.fetchall()
    g2 = defaultdict(list)
    for r in rows:
        g2[(r["tbl"], r["key"], r["method"])].append(r)
    for (tbl, key, method), grp in sorted(g2.items()):
        if len(grp) > 1 and any(g["indisunique"] for g in grp):
            for g in grp:
                if not g["indisunique"] and not g["indisprimary"]:
                    p(f"  {tbl:<45} {g['idx']:<60} {mb(g['bytes'])} (duplicate of a unique index)")
                    shadow += int(g["bytes"])
    p(f"  -> reclaimable: {mb(shadow)}")
    p()

    # ---- bloat estimate for tables whose stats say 0 live rows ----
    p("## TABLES HOLDING SPACE WITH NO LIVE ROWS (exact count vs relpages)")
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute("""
            SELECT c.relname, c.relpages, c.reltuples::bigint AS reltuples,
                   pg_relation_size(c.oid) AS heap, pg_indexes_size(c.oid) AS idx,
                   pg_total_relation_size(c.oid) AS total,
                   COALESCE(s.n_tup_del,0) AS n_tup_del, s.last_vacuum, s.last_autovacuum
            FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
            LEFT JOIN pg_stat_user_tables s ON s.relid=c.oid
            WHERE c.relkind='r' AND n.nspname='public'
              AND c.relpages > 2000 AND COALESCE(s.n_live_tup,0) = 0
            ORDER BY pg_total_relation_size(c.oid) DESC
        """)
        cand = cur.fetchall()
    for r in cand:
        with conn.cursor() as cur:
            cur.execute(f'SELECT count(*) FROM public."{r["relname"]}"')
            n = cur.fetchone()[0]
        p(f"  {r['relname']:<45} exact={n:>10} relpages={r['relpages']:>9} heap={mb(r['heap'])} "
          f"idx={mb(r['idx'])} deletions={r['n_tup_del']} last_autoanalyze_vac={r['last_autovacuum']}")
    p()

    p("## INDEXES ON THE BIGGEST TABLES AND THEIR SCAN COUNTS")
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute("""
            SELECT s.relname AS tbl, s.indexrelname AS idx, s.idx_scan,
                   pg_size_pretty(pg_relation_size(s.indexrelid)) AS size,
                   pg_get_indexdef(s.indexrelid) AS def
            FROM pg_stat_user_indexes s
            WHERE s.relname IN ('fine_table_snapshot_payloads','fine_table_snapshot_metrics',
                                'fine_table_snapshot_refs_2026','vip_daily_sales_2026',
                                'product_goods_detail_snapshots_2026','jst_daily_stock',
                                'gj_merged_product_info','jst_product_price','jst_size_stock_snapshots')
            ORDER BY s.relname, pg_relation_size(s.indexrelid) DESC
        """)
        for r in cur.fetchall():
            p(f"  {r['tbl']:<40} {r['idx']:<60} scans={r['idx_scan']:>10} {r['size']}")
    p()

    p("## TABLES WITH SEQUENTIAL SCANS RETURNING HUGE ROW COUNTS")
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute("""
            SELECT relname, seq_scan, seq_tup_read, idx_scan, n_live_tup,
                   CASE WHEN seq_scan>0 THEN seq_tup_read/seq_scan ELSE 0 END AS avg_rows_per_seqscan,
                   pg_size_pretty(pg_total_relation_size(relid)) AS size
            FROM pg_stat_user_tables
            WHERE seq_scan > 0 AND n_live_tup > 10000
            ORDER BY seq_tup_read DESC LIMIT 25
        """)
        for r in cur.fetchall():
            p(f"  {r['relname']:<45} seq={r['seq_scan']:>8} seq_rows={r['seq_tup_read']:>14} "
              f"avg={r['avg_rows_per_seqscan'] or 0:>10} live={r['n_live_tup'] or 0:>10} "
              f"idx={r['idx_scan'] or 0:>10} {r['size']}")
    p()

    p("## INDEXES THAT EXIST ON COLUMNS WITH pg_trgm BUT ARE UNUSED OR MISSING")
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute("""
            SELECT s.relname AS tbl, s.indexrelname AS idx, s.idx_scan,
                   pg_relation_size(s.indexrelid) AS bytes, pg_get_indexdef(s.indexrelid) AS def
            FROM pg_stat_user_indexes s
            WHERE pg_get_indexdef(s.indexrelid) ILIKE '%gin_trgm_ops%'
            ORDER BY pg_relation_size(s.indexrelid) DESC
        """)
        for r in cur.fetchall():
            p(f"  {r['tbl']:<40} {r['idx']:<60} scans={r['idx_scan']:>9} {mb(r['bytes'])}")
    p()

    p("## CACHE HIT RATIO / TEMP SPILL DETAIL")
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute("""
            SELECT datname,
                   round(100.0*blks_hit/NULLIF(blks_hit+blks_read,0),2) AS cache_hit_pct,
                   blks_read, blks_hit,
                   pg_size_pretty(temp_bytes) AS temp_size, temp_files,
                   round(tup_returned::numeric/NULLIF(tup_fetched,1),2) AS returned_per_fetched,
                   round(100.0*xact_rollback/NULLIF(xact_commit+xact_rollback,0),2) AS rollback_pct
            FROM pg_stat_database WHERE datname=current_database()
        """)
        for r in cur.fetchall():
            p(f"  cache_hit={r['cache_hit_pct']}% blks_read={r['blks_read']:,} blks_hit={r['blks_hit']:,}")
            p(f"  temp={r['temp_size']} files={r['temp_files']:,} returned/fetched={r['returned_per_fetched']}")
            p(f"  rollback={r['rollback_pct']}%")
    p()

    p("## MEMORY / OS")
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute("SELECT pg_size_pretty(current_setting('shared_buffers')::bigint * 8192) AS shared_buffers,"
                    " pg_size_pretty(current_setting('work_mem')::bigint * 1024) AS work_mem,"
                    " pg_size_pretty(current_setting('maintenance_work_mem')::bigint * 1024) AS maintenance_work_mem,"
                    " pg_size_pretty(current_setting('effective_cache_size')::bigint * 8192) AS effective_cache_size")
        p("  " + json.dumps(cur.fetchone(), ensure_ascii=False))
    with conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM pg_stat_activity")
        p(f"  connections active+idle: {cur.fetchone()[0]} (max_connections=100)")
    p()

    p("## LARGEST RELATIONS ON THE COLD TABLESPACE")
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute("""
            SELECT n.nspname||'.'||c.relname AS rel, pg_size_pretty(pg_total_relation_size(c.oid)) AS size,
                   ts.spcname
            FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
            JOIN pg_tablespace ts ON ts.oid=c.reltablespace
            WHERE ts.spcname='hede_cold_archive' AND c.relkind IN ('r','p')
            ORDER BY pg_total_relation_size(c.oid) DESC LIMIT 25
        """)
        for r in cur.fetchall():
            p(f"  {r['rel']:<55} {r['size']}")
    p()

    p("## TOAST COLUMN CANDIDATES (wide text/json on the biggest toast tables)")
    for tbl in ("jst_aftersale_returns_2024", "jst_aftersale_returns_2025", "jst_aftersale_returns_2026",
                "vip_product_detail_daily"):
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute("""
                SELECT a.attname, format_type(a.atttypid,a.atttypmod) AS type,
                       s.avg_width, s.null_frac
                FROM pg_attribute a
                LEFT JOIN pg_stats s ON s.schemaname='public' AND s.tablename=%s AND s.attname=a.attname
                WHERE a.attrelid = ('public.'||%s)::regclass AND a.attnum>0 AND NOT a.attisdropped
                ORDER BY COALESCE(s.avg_width,0) DESC LIMIT 8
            """, (tbl, tbl))
            p(f"  {tbl}:")
            for r in cur.fetchall():
                p(f"      {r['attname']:<35} {r['type']:<20} avg_width={r['avg_width']} null_frac={r['null_frac']}")
    p()

(HERE / "findings2.txt").write_text("\n".join(OUT), encoding="utf-8")
print(f"[written] {HERE / 'findings2.txt'} sections={len(OUT)}")