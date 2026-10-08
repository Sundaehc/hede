"""Fourth pass: checkpointer, storage layout, bloat heuristic, remaining gaps."""
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


def mb(n) -> str:
    try:
        return f"{float(n) / 1048576:,.1f}MB"
    except Exception:
        return str(n)


with psycopg.connect(database_url(), autocommit=True) as conn:
    p("## STORAGE LAYOUT")
    with conn.cursor() as cur:
        for name in ("data_directory", "config_file", "hba_file"):
            cur.execute(f"SHOW {name}")
            p(f"  {name:<15} = {cur.fetchone()[0]}")
        cur.execute("SHOW block_size")
        p(f"  block_size      = {cur.fetchone()[0]}")
        cur.execute("SELECT pg_size_pretty(SUM(size)) FROM pg_ls_waldir()")
        p(f"  WAL directory   = {cur.fetchone()[0]}")
    p()

    p("## CHECKPOINTER PRESSURE (pg_stat_checkpointer)")
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute("""
            SELECT num_timed, num_requested, num_done, restartpoints_timed, restartpoints_req,
                   write_time, sync_time, buffers_written, stats_reset
            FROM pg_stat_checkpointer
        """)
        for r in cur.fetchall():
            total = (r["num_timed"] or 0) + (r["num_requested"] or 0)
            p(f"  timed={r['num_timed']:,} requested={r['num_requested']:,} "
              f"(requested share={100.0*(r['num_requested'] or 0)/max(total,1):.1f}%)")
            p(f"  write_time={r['write_time']:,}ms sync_time={r['sync_time']:,}ms "
              f"buffers_written={r['buffers_written']:,}")
            p(f"  stats_reset={r['stats_reset']}")
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute("SELECT buffers_clean, maxwritten_clean, buffers_alloc, stats_reset FROM pg_stat_bgwriter")
        for r in cur.fetchall():
            p(f"  bgwriter: buffers_clean={r['buffers_clean']:,} maxwritten_clean={r['maxwritten_clean']:,} "
              f"buffers_alloc={r['buffers_alloc']:,}")
    p()

    p("## REPLICATION / ARCHIVE")
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute("SELECT client_addr, state, sync_state, replay_lag FROM pg_stat_replication")
        rows = cur.fetchall()
        p(f"  replicas: {len(rows)}" + (f" {rows}" if rows else ""))
        cur.execute("SELECT archived_count, failed_count, last_archived_wal, last_failed_wal FROM pg_stat_archiver")
        p(f"  archiver: {json.dumps(cur.fetchone(), default=str, ensure_ascii=False)}")
    p()

    p("## TABLE BLOAT HEURISTIC (relpages vs width-derived expectation, tables > 300MB heap)")
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute("""
            WITH w AS (
                SELECT c.oid, c.relname, c.relpages, c.reltuples,
                       (SELECT sum(s.avg_width) FROM pg_stats s
                         WHERE s.schemaname='public' AND s.tablename=c.relname) AS row_width,
                       (SELECT count(*) FROM pg_attribute a
                         WHERE a.attrelid=c.oid AND a.attnum>0 AND NOT a.attisdropped) AS ncols
                FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
                WHERE c.relkind='r' AND n.nspname='public'
                  AND pg_relation_size(c.oid) > 300000000
            )
            SELECT relname, relpages, reltuples::bigint AS reltuples, row_width, ncols,
                   CASE WHEN COALESCE(row_width,0) > 0 AND reltuples > 0
                        THEN ceil(reltuples * (row_width + 4 + 24 + (ncols+7)/8) / 8168)::bigint
                        ELSE NULL END AS expected_pages
            FROM w ORDER BY relpages DESC
        """)
        for r in cur.fetchall():
            exp = r["expected_pages"]
            if exp and exp > 0:
                ratio = r["relpages"] / exp
                flag = "  <-- possible bloat" if ratio > 1.5 else ""
                p(f"  {r['relname']:<45} pages={r['relpages']:>9} expected~{exp:>9} ratio={ratio:5.2f}{flag}")
            else:
                p(f"  {r['relname']:<45} pages={r['relpages']:>9} expected=unknown (no stats)")
    p()

    p("## TABLES WHERE n_mod_since_analyze IS HIGH (stale planner statistics)")
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute("""
            SELECT relname, n_live_tup, n_mod_since_analyze,
                   round(100.0*n_mod_since_analyze/NULLIF(n_live_tup,0),1) AS pct_changed,
                   last_autoanalyze, last_analyze
            FROM pg_stat_user_tables
            WHERE n_live_tup > 100000 AND n_mod_since_analyze > 50000
            ORDER BY n_mod_since_analyze DESC LIMIT 25
        """)
        for r in cur.fetchall():
            p(f"  {r['relname']:<45} live={r['n_live_tup']:>10} modified={r['n_mod_since_analyze']:>10} "
              f"({r['pct_changed']}%) last_autoanalyze={r['last_autoanalyze']}")
    p()

    p("## SESSIONS / LOCKS SNAPSHOT")
    p(f"  long running queries: {json.dumps(RAW.get('long_running'), default=str, ensure_ascii=False)[:800]}")
    p(f"  locks: {json.dumps(RAW.get('locks'), default=str, ensure_ascii=False)[:600]}")
    p()

    p("## EXTENSION CAPABILITY STATUS")
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute("""
            SELECT name, installed_version, default_version
            FROM pg_available_extensions
            WHERE name IN ('pg_stat_statements','pgstattuple','pg_repack','pg_trgm','btree_gin')
            ORDER BY name
        """)
        for r in cur.fetchall():
            p(f"  {r['name']:<20} installed={r['installed_version']} available={r['default_version']}")
    p()

    p("## QUERY-LEVEL VISIBILITY")
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute("""
            SELECT name, setting FROM pg_settings
            WHERE name IN ('log_min_duration_statement','log_statement','log_lock_waits',
                           'log_autovacuum_min_duration','log_temp_files','log_checkpoints',
                           'auto_explain.log_min_duration','shared_preload_libraries')
              AND name <> 'auto_explain.log_min_duration'
            UNION ALL
            SELECT 'pg_stat_statements installed', count(*)::text FROM pg_extension WHERE extname='pg_stat_statements'
        """)
        for r in cur.fetchall():
            p(f"  {r['name']:<35} = {r['setting']}")
    p()

    p("## SMALL-TABLE FK COVERAGE DETAIL")
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute("""
            SELECT c.relname AS child_table, con.conname,
                   (SELECT string_agg(a.attname, ',') FROM unnest(con.conkey) k(attnum)
                      JOIN pg_attribute a ON a.attrelid=con.conrelid AND a.attnum=k.attnum) AS cols,
                   pg_size_pretty(pg_total_relation_size(c.oid)) AS size,
                   COALESCE(s.n_live_tup,0) AS live
            FROM pg_constraint con
            JOIN pg_class c ON c.oid=con.conrelid
            JOIN pg_namespace n ON n.oid=c.relnamespace
            LEFT JOIN pg_stat_user_tables s ON s.relid=c.oid
            WHERE con.contype='f' AND n.nspname='public'
              AND NOT EXISTS (
                SELECT 1 FROM pg_index i
                WHERE i.indrelid=con.conrelid
                  AND (SELECT array_agg(a2.attname) FROM unnest(i.indkey) k2(attnum)
                         JOIN pg_attribute a2 ON a2.attrelid=i.indrelid AND a2.attnum=k2.attnum)
                      [1:array_length(con.conkey,1)] = (SELECT array_agg(a3.attname) FROM unnest(con.conkey) k3(attnum)
                         JOIN pg_attribute a3 ON a3.attrelid=con.conrelid AND a3.attnum=k3.attnum)
              )
            ORDER BY pg_total_relation_size(c.oid) DESC
        """)
        for r in cur.fetchall():
            p(f"  {r['child_table']:<40} {r['conname']:<45} cols={r['cols']} {r['size']} live={r['live']}")
    p()

(HERE / "findings4.txt").write_text("\n".join(OUT), encoding="utf-8")
print(f"[written] {HERE / 'findings4.txt'} sections={len(OUT)}")