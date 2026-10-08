"""Pass 12: data-completeness reconnaissance.

A. global NULL map from pg_stats (candidates for missing data)
B. foreign-key orphan counts (child rows with no matching parent)
C. column metadata for every public table, dumped for later targeted checks
D. tables that are completely empty
"""
from __future__ import annotations

import sys
from pathlib import Path

import psycopg
from psycopg.rows import dict_row

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from audit import database_url  # noqa: E402

(HERE / "completeness.txt").write_text("", encoding="utf-8")


def p(s: str = "") -> None:
    with open(HERE / "completeness.txt", "a", encoding="utf-8") as fh:
        fh.write(s + "\n")


with psycopg.connect(database_url(), autocommit=True) as conn:
    with conn.cursor() as cur:
        cur.execute("SET statement_timeout = '90s'")

    p("=" * 78)
    p("A. NULL MAP (pg_stats, tables > 5,000 rows, null_frac > 0.5%)")
    p("   注意: 统计信息来自上一次 ANALYZE(最迟 2026-08-27), 仅作线索, 后续逐项实测")
    p("=" * 78)
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute("""
            SELECT s.tablename, s.attname, s.null_frac, s.avg_width, s.n_distinct,
                   c.reltuples::bigint AS est_rows,
                   (c.reltuples * s.null_frac)::bigint AS est_nulls
            FROM pg_stats s
            JOIN pg_class c ON c.relname = s.tablename
            JOIN pg_namespace n ON n.oid = c.relnamespace AND n.nspname = s.schemaname
            WHERE s.schemaname = 'public' AND c.relkind = 'r'
              AND c.reltuples > 5000 AND s.null_frac > 0.005
            ORDER BY c.reltuples * s.null_frac DESC
            LIMIT 120
        """)
        rows = cur.fetchall()
        p(f"  候选列数: {len(rows)}")
        p(f"  {'table':<44} {'column':<26} {'est_rows':>11} {'null_frac':>9} {'est_nulls':>11}")
        for r in rows:
            p(f"  {r['tablename']:<44} {r['attname']:<26} {r['est_rows']:>11,} "
              f"{r['null_frac']:>9.4f} {r['est_nulls']:>11,}")
    p()

    p("=" * 78)
    p("B. FOREIGN KEY ORPHANS (child rows whose parent is missing)")
    p("=" * 78)
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute("""
            SELECT con.conname,
                   con.conrelid::regclass::text AS child,
                   con.confrelid::regclass::text AS parent,
                   (SELECT array_agg(a.attname ORDER BY k.ordinality)
                      FROM unnest(con.conkey) WITH ORDINALITY k(attnum, ordinality)
                      JOIN pg_attribute a ON a.attrelid = con.conrelid AND a.attnum = k.attnum) AS ccols,
                   (SELECT array_agg(a.attname ORDER BY k.ordinality)
                      FROM unnest(con.confkey) WITH ORDINALITY k(attnum, ordinality)
                      JOIN pg_attribute a ON a.attrelid = con.confrelid AND a.attnum = k.attnum) AS pcols,
                   pg_get_constraintdef(con.oid) AS def,
                   (SELECT COALESCE(s.n_live_tup,0) FROM pg_stat_user_tables s
                     WHERE s.relid = con.conrelid) AS child_live
            FROM pg_constraint con
            JOIN pg_namespace n ON n.oid = con.connamespace
            WHERE con.contype = 'f' AND n.nspname = 'public'
            ORDER BY child_live DESC
        """)
        fks = cur.fetchall()

    for fk in fks:
        ccols, pcols = fk["ccols"], fk["pcols"]
        child = fk["child"]
        parent = fk["parent"]
        if not ccols or not pcols:
            continue
        null_guard = " AND ".join(f"c.{c} IS NOT NULL" for c in ccols)
        join_pred = " AND ".join(f"p.{pc} = c.{cc}" for cc, pc in zip(ccols, pcols))
        sql = (f"SELECT count(*) FROM {child} c "
               f"WHERE {null_guard} AND NOT EXISTS "
               f"(SELECT 1 FROM {parent} p WHERE {join_pred})")
        try:
            with conn.cursor() as cur:
                cur.execute(sql)
                orphans = cur.fetchone()[0]
            with conn.cursor() as cur:
                cur.execute(f"SELECT count(*) FROM {child} c WHERE NOT ({null_guard})")
                all_null = cur.fetchone()[0]
            flag = "  <-- ORPHANS" if orphans else ""
            p(f"  {fk['child']:<42} {fk['conname']:<42} orphans={orphans:>8} fk_all_null={all_null:>8}{flag}")
        except Exception as exc:  # noqa: BLE001
            conn.rollback()
            p(f"  {fk['child']:<42} {fk['conname']:<42} CHECK FAILED: {type(exc).__name__}: {exc}")
    p()

    p("=" * 78)
    p("C. COLUMN METADATA FOR ALL PUBLIC TABLES (written to columns.txt)")
    p("=" * 78)
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute("""
            SELECT c.relname AS table_name, c.reltuples::bigint AS est_rows,
                   a.attnum, a.attname, format_type(a.atttypid, a.atttypmod) AS type,
                   a.attnotnull
            FROM pg_class c
            JOIN pg_namespace n ON n.oid = c.relnamespace
            JOIN pg_attribute a ON a.attrelid = c.oid
            WHERE n.nspname = 'public' AND c.relkind = 'r'
              AND a.attnum > 0 AND NOT a.attisdropped
            ORDER BY c.relname, a.attnum
        """)
        cols = cur.fetchall()
    (HERE / "columns.txt").write_text(
        "\n".join(f"{r['table_name']}\t{r['attnum']}\t{r['attname']}\t{r['type']}\t"
                  f"{'NOT NULL' if r['attnotnull'] else 'nullable'}\test_rows={r['est_rows']}"
                  for r in cols), encoding="utf-8")
    p(f"  {len(cols)} columns across {len({r['table_name'] for r in cols})} tables -> columns.txt")
    p()

    p("=" * 78)
    p("D. COMPLETELY EMPTY TABLES (exact count = 0)")
    p("=" * 78)
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute("""
            SELECT c.relname FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
            WHERE c.relkind='r' AND n.nspname='public' AND c.reltuples < 1
            ORDER BY c.relname
        """)
        candidates = [r["relname"] for r in cur.fetchall()]
    empty = []
    for t in candidates:
        try:
            with conn.cursor() as cur:
                cur.execute(f'SELECT count(*) FROM public."{t}"')
                if cur.fetchone()[0] == 0:
                    empty.append(t)
        except Exception:  # noqa: BLE001
            conn.rollback()
    p(f"  空表 ({len(empty)}): {', '.join(empty) if empty else '无'}")
    p()

print("[done]")