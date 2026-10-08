"""Eighth pass: corrected partitioned-parent index aggregation (no duplication)."""
from __future__ import annotations

import sys
from pathlib import Path

import psycopg
from psycopg.rows import dict_row

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from audit import database_url  # noqa: E402

OUT: list[str] = []
(HERE / "findings8.txt").write_text("", encoding="utf-8")


def p(s: str = "") -> None:
    OUT.append(s)
    with open(HERE / "findings8.txt", "a", encoding="utf-8") as fh:
        fh.write(s + "\n")


with psycopg.connect(database_url(), autocommit=True) as conn:
    p("## PARTITIONED PARENT INDEXES: usage and size (children counted once)")
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute("""
            SELECT parent.relname AS parent_table,
                   pi.indexrelid::regclass::text AS parent_index,
                   pi.indisunique,
                   pg_get_indexdef(pi.indexrelid) AS def,
                   SUM(pg_relation_size(ci.indexrelid)) AS bytes,
                   COALESCE(SUM(si.idx_scan), 0) AS child_scans,
                   count(*) AS n_children
            FROM pg_class parent
            JOIN pg_namespace n ON n.oid = parent.relnamespace
            JOIN pg_index pi ON pi.indrelid = parent.oid
            JOIN pg_inherits ci_inh ON ci_inh.inhparent = pi.indexrelid
            JOIN pg_index ci ON ci.indexrelid = ci_inh.inhrelid
            LEFT JOIN pg_stat_user_indexes si ON si.indexrelid = ci.indexrelid
            WHERE parent.relkind = 'p' AND n.nspname = 'public'
            GROUP BY 1, 2, 3, 4
            ORDER BY 1, SUM(pg_relation_size(ci.indexrelid)) DESC
        """)
        total = 0
        for r in cur.fetchall():
            total += int(r["bytes"])
            flag = "   <-- ZERO/BARELY USED" if r["child_scans"] < 500 else ""
            p(f"  {r['parent_table']:<32} {r['parent_index']:<52} kids={r['n_children']:>2} "
              f"{r['bytes']/1048576:>9,.1f}MB scans={r['child_scans']:>12,} uq={r['indisunique']}{flag}")
            p(f"        {r['def']}")
        p(f"  -> partitioned index bytes on children: {total/1048576:,.1f}MB")
    p()

    p("## PARENT-LEVEL INDEX DEFINITIONS: properties that matter for dropping")
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute("""
            SELECT parent.relname AS parent_table, pi.indexrelid::regclass::text AS parent_index,
                   pi.indisvalid, pi.indisready, pi.indisclustered, pi.indisexclusion,
                   pg_get_expr(pi.indpred, pi.indrelid) AS pred,
                   (SELECT count(*) FROM pg_inherits inh WHERE inh.inhparent = pi.indexrelid) AS attached_children
            FROM pg_class parent
            JOIN pg_namespace n ON n.oid = parent.relnamespace
            JOIN pg_index pi ON pi.indrelid = parent.oid
            WHERE parent.relkind = 'p' AND n.nspname = 'public'
            ORDER BY 1, 2
        """)
        for r in cur.fetchall():
            p(f"  {r['parent_table']:<32} {r['parent_index']:<52} valid={r['indisvalid']} "
              f"ready={r['indisready']} children={r['attached_children']} pred={r['pred']}")
    p()

    p("## CONSOLIDATED SAFE-DROP LIST (real, verified names)")
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute("""
            WITH child_scans AS (
                SELECT pi.indexrelid AS parent_idx, COALESCE(SUM(si.idx_scan),0) AS scans
                FROM pg_index pi
                JOIN pg_inherits ci ON ci.inhparent = pi.indexrelid
                LEFT JOIN pg_stat_user_indexes si ON si.indexrelid = ci.inhrelid
                GROUP BY 1
            )
            SELECT n.nspname||'.'||c.relname AS tbl,
                   i.indexrelid::regclass::text AS idx,
                   pg_relation_size(i.indexrelid) AS bytes,
                   s.idx_scan,
                   i.indisunique, i.indisprimary,
                   COALESCE(cs.scans, 0) AS child_scans,
                   (SELECT count(*) FROM pg_inherits ih WHERE ih.inhparent = i.indexrelid) AS children
            FROM pg_index i
            JOIN pg_class c ON c.oid = i.indrelid
            JOIN pg_namespace n ON n.oid = c.relnamespace
            LEFT JOIN pg_stat_user_indexes s ON s.indexrelid = i.indexrelid
            LEFT JOIN child_scans cs ON cs.parent_idx = i.indexrelid
            WHERE n.nspname='public' AND i.indisvalid
              AND NOT i.indisprimary AND NOT i.indisunique
              AND COALESCE(s.idx_scan,0) = 0
              AND c.relkind IN ('r','p')
              AND (i.indrelid NOT IN (SELECT inhrelid FROM pg_inherits)
                   OR (SELECT count(*) FROM pg_inherits ih2 WHERE ih2.inhparent = i.indexrelid) > 0)
            ORDER BY pg_relation_size(i.indexrelid) DESC
        """)
        rows = cur.fetchall()
        grand = 0
        for r in rows:
            grand += int(r["bytes"])
            kind = "partitioned-parent" if r["children"] else "standalone"
            p(f"  {r['tbl']:<40} {r['idx']:<56} {r['bytes']/1048576:>9,.1f}MB scans={r['idx_scan']} "
              f"({kind})")
        p(f"  -> total zero-scan, non-unique index bytes at top level: {grand/1048576:,.1f}MB")
        p(f"  -> count: {len(rows)}")
    p()

print(f"[written] {HERE / 'findings8.txt'} sections={len(OUT)}")