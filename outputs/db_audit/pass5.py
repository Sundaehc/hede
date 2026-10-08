"""Fifth pass: uniqueness integrity, biggest-table shape, index-to-heap ranking."""
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
RAW = json.loads((HERE / "raw.json").read_text(encoding="utf-8"))


def p(s: str = "") -> None:
    OUT.append(s)


with psycopg.connect(database_url(), autocommit=True) as conn:
    with conn.cursor() as cur:
        cur.execute("SELECT current_date, now(), version()")
        d, n, v = cur.fetchone()
        p(f"## CLOCK: db date={d} now={n}")
        p(f"## SERVER: {v}")
    p()

    p("## TABLES WITH NO UNIQUE/PRIMARY INDEX AT ALL AND > 50k ROWS")
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute("""
            SELECT n.nspname||'.'||c.relname AS rel,
                   COALESCE(s.n_live_tup,0) AS live,
                   pg_size_pretty(pg_total_relation_size(c.oid)) AS size,
                   (SELECT count(*) FROM pg_index i WHERE i.indrelid=c.oid) AS n_indexes,
                   c.relispartition
            FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
            LEFT JOIN pg_stat_user_tables s ON s.relid=c.oid
            WHERE c.relkind IN ('r','p') AND n.nspname='public'
              AND NOT EXISTS (SELECT 1 FROM pg_index i WHERE i.indrelid=c.oid AND i.indisunique)
              AND COALESCE(s.n_live_tup,0) > 50000
            ORDER BY pg_total_relation_size(c.oid) DESC
        """)
        for r in cur.fetchall():
            p(f"  {r['rel']:<50} live={r['live']:>10} {r['size']:>10} indexes={r['n_indexes']} "
              f"partition={r['relispartition']}")
    p()

    p("## SHAPE OF THE THREE BIGGEST TABLES")
    for tbl in ("fine_table_snapshot_payloads", "fine_table_snapshot_metrics", "fine_table_snapshot_refs_2026"):
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute("""
                SELECT a.attname, format_type(a.atttypid, a.atttypmod) AS type, a.attnotnull,
                       COALESCE(s.avg_width,0) AS avg_width
                FROM pg_attribute a
                LEFT JOIN pg_stats s ON s.schemaname='public' AND s.tablename=%s AND s.attname=a.attname
                WHERE a.attrelid=('public.'||%s)::regclass AND a.attnum>0 AND NOT a.attisdropped
                ORDER BY a.attnum
            """, (tbl, tbl))
            cols = cur.fetchall()
        p(f"  {tbl}: {len(cols)} columns")
        for c in cols:
            p(f"      {c['attname']:<25} {c['type']:<22} notnull={c['attnotnull']} avg_width={c['avg_width']}")
    p()

    p("## INDEX vs HEAP RATIO RANKING (>200MB total)")
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute("""
            SELECT n.nspname||'.'||c.relname AS rel,
                   pg_relation_size(c.oid) AS heap, pg_indexes_size(c.oid) AS idx,
                   (SELECT count(*) FROM pg_index i WHERE i.indrelid=c.oid) AS n_idx,
                   (SELECT COALESCE(SUM(s.idx_scan),0) FROM pg_stat_user_indexes s
                     WHERE s.relid=c.oid) AS total_scans
            FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
            WHERE c.relkind='r' AND n.nspname='public'
              AND pg_total_relation_size(c.oid) > 200000000 AND pg_relation_size(c.oid) > 0
            ORDER BY (pg_indexes_size(c.oid)::numeric / pg_relation_size(c.oid)) DESC
        """)
        for r in cur.fetchall():
            ratio = r["idx"] / r["heap"]
            p(f"  {r['rel']:<45} heap={r['heap']/1048576:>9,.0f}MB idx={r['idx']/1048576:>9,.0f}MB "
              f"ratio={ratio:5.2f} indexes={r['n_idx']} scans={r['total_scans']:,}")
    p()

    p("## TOTAL RECLAIMABLE INDEX SPACE SUMMARY")
    unused = RAW["user_indexes_unused"]
    idx_bytes = {r["index_name"]: int(r["index_bytes"]) for r in RAW["index_keys"]}
    unused_total = sum(idx_bytes.get(u["index_name"], 0) for u in unused)
    p(f"  unused non-unique indexes: {len(unused)} = {unused_total/1048576:,.1f}MB")
    trgm = [u for u in unused if "trgm" in u["index_name"]]
    p(f"  of which pg_trgm indexes: {len(trgm)} = "
      f"{sum(idx_bytes.get(u['index_name'],0) for u in trgm)/1048576:,.1f}MB")
    p()

    p("## DUPLICATE CHECK: jst_aftersale_returns_2026 NATURAL KEY")
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute("""
            SELECT string_agg(attname, ',' ORDER BY attnum) AS cols
            FROM pg_attribute
            WHERE attrelid='public.jst_aftersale_returns_2026'::regclass AND attnum>0 AND NOT attisdropped
        """)
        p(f"  columns: {cur.fetchone()['cols']}")
    with conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM public.jst_aftersale_returns_2026")
        total = cur.fetchone()[0]
        p(f"  rows: {total:,}")
    p()

    p("## DUPLICATE CHECK: fine_table_snapshot_payloads BRAND+HASH")
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute("""
            SELECT count(*) AS total, count(DISTINCT (brand, content_hash)) AS distinct_keys
            FROM public.fine_table_snapshot_payloads
        """)
        r = cur.fetchone()
        p(f"  rows={r['total']:,} distinct(brand,content_hash)={r['distinct_keys']:,} "
          f"duplicates={r['total']-r['distinct_keys']:,}")
    p()

    p("## API-FACING HOT TABLES: size, indexes, scans")
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute("""
            SELECT s.relname, s.n_live_tup, s.n_dead_tup, s.seq_scan, s.idx_scan,
                   pg_size_pretty(pg_total_relation_size(s.relid)) AS size,
                   (SELECT count(*) FROM pg_index i WHERE i.indrelid=s.relid) AS n_idx
            FROM pg_stat_user_tables s
            WHERE s.relname IN ('inventory_records','inventory_details','suppliers','warehouses',
                                'cbanner_mens_products','cbanner_womens_products','yandou_products',
                                'eblan_products','smiley_products','ni_products','product_tag_assignments',
                                'product_goods_overrides','scheduled_task_runs','operation_logs','auth_sessions')
            ORDER BY pg_total_relation_size(s.relid) DESC
        """)
        for r in cur.fetchall():
            p(f"  {r['relname']:<30} live={r['n_live_tup']:>8} dead={r['n_dead_tup']:>7} "
              f"seq={r['seq_scan']:>7} idx={r['idx_scan']:>9} idx#={r['n_idx']:>3} {r['size']}")
    p()

(HERE / "findings5.txt").write_text("\n".join(OUT), encoding="utf-8")
print(f"[written] {HERE / 'findings5.txt'} sections={len(OUT)}")