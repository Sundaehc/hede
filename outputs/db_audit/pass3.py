"""Third pass: remaining metrics (memory, cold storage, json/toast shape)."""
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


RAW = json.loads((HERE / "raw.json").read_text(encoding="utf-8"))

with psycopg.connect(database_url(), autocommit=True) as conn:
    p("## MEMORY / CONNECTION SETTINGS (resolved)")
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute("""
            SELECT name, setting, unit,
                   CASE name
                     WHEN 'shared_buffers' THEN pg_size_pretty(setting::bigint*8192)
                     WHEN 'work_mem' THEN pg_size_pretty(setting::bigint*1024)
                     WHEN 'maintenance_work_mem' THEN pg_size_pretty(setting::bigint*1024)
                     WHEN 'effective_cache_size' THEN pg_size_pretty(setting::bigint*8192)
                     WHEN 'max_wal_size' THEN pg_size_pretty(setting::bigint*1048576)
                     ELSE NULL END AS human
            FROM pg_settings
            WHERE name IN ('shared_buffers','work_mem','maintenance_work_mem','effective_cache_size','max_wal_size')
        """)
        for r in cur.fetchall():
            p(f"  {r['name']:<25} {r['setting']:>10} {str(r['unit']):<5} = {r['human']}")

    with conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM pg_stat_activity")
        p(f"  current connections = {cur.fetchone()[0]} / max_connections=100")
        cur.execute("SELECT count(*) FROM pg_stat_activity WHERE state='idle in transaction'")
        p(f"  'idle in transaction' = {cur.fetchone()[0]}")
        cur.execute("""
            SELECT pg_size_pretty(SUM(pg_total_relation_size(c.oid)))
            FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
            WHERE n.nspname='public' AND c.relkind IN ('r','p')
        """)
        p(f"  total size of public relations = {cur.fetchone()[0]}")
    p()

    p("## COLD TABLESPACE CONTENTS")
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute("""
            SELECT n.nspname||'.'||c.relname AS rel,
                   pg_size_pretty(pg_total_relation_size(c.oid)) AS size, c.relkind
            FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
            JOIN pg_tablespace ts ON ts.oid=c.reltablespace
            WHERE ts.spcname='hede_cold_archive' AND c.relkind IN ('r','p','i','I')
            ORDER BY pg_total_relation_size(c.oid) DESC LIMIT 30
        """)
        rows = cur.fetchall()
        p(f"  objects on cold tablespace: {len(rows)}")
        for r in rows:
            p(f"  {r['rel']:<55} {r['size']} kind={r['relkind']}")
    p()

    p("## JSON / JSONB COLUMNS BY AVERAGE WIDTH")
    for r in RAW["json_columns"][:40]:
        p(f"  {r['schema']}.{r['table_name']:<40} {r['column_name']:<20} {r['type']:<7} "
          f"avg_width={r['avg_width']:>8} null_frac={r['null_frac']}")
    p()

    p("## WIDE TABLE SHAPES (columns with the largest average width, top tables)")
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute("""
            SELECT s.schemaname||'.'||s.tablename AS tbl, s.attname, format_type(a.atttypid,a.atttypmod) AS type,
                   s.avg_width, s.null_frac
            FROM pg_stats s
            JOIN pg_class c ON c.relname=s.tablename
            JOIN pg_namespace n ON n.oid=c.relnamespace AND n.nspname=s.schemaname
            JOIN pg_attribute a ON a.attrelid=c.oid AND a.attname=s.attname
            WHERE s.schemaname='public' AND s.avg_width > 60 AND c.relkind='r'
              AND pg_total_relation_size(c.oid) > 300000000
            ORDER BY s.avg_width DESC LIMIT 25
        """)
        for r in cur.fetchall():
            p(f"  {r['tbl']:<50} {r['attname']:<25} {r['type']:<15} avg={r['avg_width']} null={r['null_frac']}")
    p()

    p("## UNLOGGED / TEMP-LIKE RELATIONS")
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute("""
            SELECT n.nspname||'.'||c.relname AS rel, c.relpersistence,
                   pg_size_pretty(pg_total_relation_size(c.oid)) AS size
            FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
            WHERE c.relkind='r' AND c.relpersistence <> 'p'
              AND n.nspname NOT IN ('pg_catalog','information_schema')
        """)
        for r in cur.fetchall():
            p(f"  {r['rel']:<55} persistence={r['relpersistence']} {r['size']}")
    p()

    p("## MATERIALIZED VIEWS")
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute("""
            SELECT n.nspname||'.'||c.relname AS rel, pg_size_pretty(pg_total_relation_size(c.oid)) AS size,
                   (SELECT count(*) FROM pg_index i WHERE i.indrelid=c.oid) AS indexes
            FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
            WHERE c.relkind='m' AND n.nspname NOT IN ('pg_catalog','information_schema')
            ORDER BY pg_total_relation_size(c.oid) DESC
        """)
        for r in cur.fetchall():
            p(f"  {r['rel']:<55} {r['size']} indexes={r['indexes']}")
    p()

    p("## TABLE STATS TARGET OVERRIDES (only where set)")
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute("""
            SELECT n.nspname||'.'||c.relname AS rel, a.attname, a.attstattarget
            FROM pg_attribute a
            JOIN pg_class c ON c.oid=a.attrelid
            JOIN pg_namespace n ON n.oid=c.relnamespace
            WHERE a.attstattarget >= 0 AND a.attnum>0 AND NOT a.attisdropped
              AND n.nspname NOT IN ('pg_catalog','information_schema')
        """)
        rows = cur.fetchall()
        p(f"  columns with a custom statistics target: {len(rows)}")
        for r in rows[:20]:
            p(f"  {r['rel']:<50} {r['attname']:<25} target={r['attstattarget']}")
    p()

    p("## CHECK: partitions whose parent lacks a matching PK/unique (row identity)")
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute("""
            SELECT parent.relname AS parent_tbl,
                   (SELECT count(*) FROM pg_index i WHERE i.indrelid=parent.oid AND i.indisprimary) AS pk,
                   (SELECT count(*) FROM pg_index i WHERE i.indrelid=parent.oid AND i.indisunique) AS uq,
                   pg_size_pretty(SUM(pg_total_relation_size(child.oid))) AS size
            FROM pg_inherits inh
            JOIN pg_class parent ON parent.oid=inh.inhparent
            JOIN pg_class child ON child.oid=inh.inhrelid
            JOIN pg_namespace n ON n.oid=parent.relnamespace
            WHERE n.nspname='public'
            GROUP BY 1,2,3 ORDER BY SUM(pg_total_relation_size(child.oid)) DESC
        """)
        for r in cur.fetchall():
            flag = "  <-- NO ROW IDENTITY" if (r["pk"] == 0 and r["uq"] == 0) else ""
            p(f"  {r['parent_tbl']:<40} pk={r['pk']} unique={r['uq']} {r['size']}{flag}")
    p()

    p("## WAL / CHECKPOINT PRESSURE")
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute("""
            SELECT checkpoints_timed, checkpoints_req, checkpoint_write_time, checkpoint_sync_time,
                   buffers_checkpoint, buffers_clean, maxwritten_clean, buffers_backend, buffers_backend_fsync,
                   buffers_alloc, stats_reset
            FROM pg_stat_bgwriter
        """)
        for r in cur.fetchall():
            total = (r["checkpoints_timed"] or 0) + (r["checkpoints_req"] or 0)
            p(f"  checkpoints timed={r['checkpoints_timed']} requested={r['checkpoints_req']} "
              f"(requested share={100.0*(r['checkpoints_req'] or 0)/max(total,1):.1f}%)")
            p(f"  checkpoint_write_time={r['checkpoint_write_time']}ms sync_time={r['checkpoint_sync_time']}ms")
            p(f"  buffers_alloc={r['buffers_alloc']:,} backend={r['buffers_backend']:,} "
              f"backend_fsync={r['buffers_backend_fsync']:,} maxwritten_clean={r['maxwritten_clean']}")
    p()

    p("## REPLICATION / ARCHIVE STATE")
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute("SELECT client_addr, state, sync_state, replay_lag FROM pg_stat_replication")
        rows = cur.fetchall()
        p(f"  replicas: {len(rows)}" + ("" if not rows else f" {rows}"))
        cur.execute("SELECT count(*) FROM pg_stat_archiver")
        cur.execute("SELECT * FROM pg_stat_archiver")
        for r in cur.fetchall():
            p(f"  archiver: {json.dumps(r, default=str, ensure_ascii=False)}")
    p()

    p("## EXTENSION-LEVEL CAPABILITY GAPS")
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

(HERE / "findings3.txt").write_text("\n".join(OUT), encoding="utf-8")
print(f"[written] {HERE / 'findings3.txt'} sections={len(OUT)}")