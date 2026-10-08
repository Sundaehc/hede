"""Read-only PostgreSQL health/optimization audit.

Collects sizes, bloat, index usage, constraint coverage, sequence headroom,
partitioning, tablespaces and key GUCs. Writes raw JSON + a readable summary.
Never writes to the database.
"""
from __future__ import annotations

import json
import os
import re
from pathlib import Path

import psycopg
from psycopg.rows import dict_row

HERE = Path(__file__).resolve().parent


def database_url() -> str:
    env_file = Path(r"E:\hede\backend\.env")
    url = os.environ.get("DATABASE_URL")
    if not url and env_file.exists():
        for line in env_file.read_text(encoding="utf-8").splitlines():
            m = re.match(r"\s*DATABASE_URL\s*=\s*(.+)\s*$", line)
            if m:
                url = m.group(1).strip().strip("'\"")
                break
    if not url:
        raise SystemExit("DATABASE_URL not found")
    return url.replace("postgresql+psycopg://", "postgresql://")


RAW: dict[str, object] = {}


def grab(conn, key: str, sql: str, params=None):
    try:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(sql, params)
            RAW[key] = cur.fetchall()
    except Exception as exc:  # noqa: BLE001
        conn.rollback()
        RAW[key] = {"error": f"{type(exc).__name__}: {exc}"}


def scalar(conn, key: str, sql: str):
    try:
        with conn.cursor() as cur:
            cur.execute(sql)
            row = cur.fetchone()
            RAW[key] = row[0] if row else None
    except Exception as exc:  # noqa: BLE001
        conn.rollback()
        RAW[key] = f"error: {exc}"


def main() -> None:
    with psycopg.connect(database_url(), autocommit=True) as conn:
        scalar(conn, "server_version", "SHOW server_version")
        scalar(conn, "database", "SELECT current_database()")
        scalar(conn, "db_size_bytes", "SELECT pg_database_size(current_database())")
        scalar(conn, "db_size_pretty", "SELECT pg_size_pretty(pg_database_size(current_database()))")

        grab(conn, "schemas", """
            SELECT nspname AS schema, pg_size_pretty(SUM(pg_total_relation_size(c.oid))) AS size,
                   SUM(pg_total_relation_size(c.oid)) AS bytes, count(*) FILTER (WHERE c.relkind='r') AS tables
            FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
            WHERE c.relkind IN ('r','p','m') AND n.nspname NOT IN ('pg_catalog','information_schema')
            GROUP BY 1 ORDER BY bytes DESC NULLS LAST
        """)

        grab(conn, "tables", """
            SELECT n.nspname AS schema, c.relname AS table_name, c.relkind,
                   c.reltuples::bigint AS est_rows,
                   pg_total_relation_size(c.oid) AS total_bytes,
                   pg_relation_size(c.oid) AS heap_bytes,
                   pg_indexes_size(c.oid) AS index_bytes,
                   pg_total_relation_size(c.oid) - pg_relation_size(c.oid)
                     - pg_indexes_size(c.oid) AS toast_bytes,
                   COALESCE(s.n_live_tup,0) AS n_live_tup,
                   COALESCE(s.n_dead_tup,0) AS n_dead_tup,
                   COALESCE(s.n_tup_ins,0) AS n_tup_ins,
                   COALESCE(s.n_tup_upd,0) AS n_tup_upd,
                   COALESCE(s.n_tup_del,0) AS n_tup_del,
                   COALESCE(s.n_tup_hot_upd,0) AS n_tup_hot_upd,
                   COALESCE(s.seq_scan,0) AS seq_scan,
                   COALESCE(s.seq_tup_read,0) AS seq_tup_read,
                   COALESCE(s.idx_scan,0) AS idx_scan,
                   s.last_vacuum, s.last_autovacuum, s.last_analyze, s.last_autoanalyze,
                   COALESCE(s.vacuum_count,0) AS vacuum_count,
                   COALESCE(s.autovacuum_count,0) AS autovacuum_count,
                   c.reloptions, c.relpersistence, ts.spcname AS tablespace,
                   (SELECT count(*) FROM pg_attribute a
                     WHERE a.attrelid=c.oid AND a.attnum>0 AND NOT a.attisdropped) AS n_columns,
                   (SELECT count(*) FROM pg_index i WHERE i.indrelid=c.oid) AS n_indexes,
                   (SELECT count(*) FROM pg_constraint k WHERE k.conrelid=c.oid) AS n_constraints,
                   (SELECT count(*) FROM pg_constraint k WHERE k.conrelid=c.oid AND k.contype='f') AS n_fks
            FROM pg_class c
            JOIN pg_namespace n ON n.oid = c.relnamespace
            LEFT JOIN pg_stat_user_tables s ON s.relid = c.oid
            LEFT JOIN pg_tablespace ts ON ts.oid = c.reltablespace
            WHERE c.relkind IN ('r','p','m') AND n.nspname NOT IN ('pg_catalog','information_schema')
            ORDER BY total_bytes DESC
        """)

        grab(conn, "indexes", """
            SELECT s.schemaname AS schema, s.relname AS table_name, s.indexrelname AS index_name,
                   s.idx_scan, s.idx_tup_read, s.idx_tup_fetch,
                   pg_relation_size(s.indexrelid) AS index_bytes,
                   i.indisunique, i.indisprimary, i.indisvalid, i.indisready,
                   i.indnkeyatts, i.indnatts,
                   pg_get_indexdef(s.indexrelid) AS indexdef,
                   am.amname AS method
            FROM pg_stat_user_indexes s
            JOIN pg_index i ON i.indexrelid = s.indexrelid
            JOIN pg_class ic ON ic.oid = s.indexrelid
            JOIN pg_am am ON am.oid = ic.relam
            ORDER BY pg_relation_size(s.indexrelid) DESC
        """)

        grab(conn, "index_keys", """
            SELECT i.indexrelid::regclass::text AS index_name,
                   i.indrelid::regclass::text AS table_name,
                   i.indkey::text AS indkey,
                   i.indnkeyatts, i.indisunique, i.indisprimary, i.indisvalid,
                   pg_get_indexdef(i.indexrelid) AS indexdef,
                   pg_relation_size(i.indexrelid) AS index_bytes
            FROM pg_index i
            JOIN pg_class c ON c.oid = i.indrelid
            JOIN pg_namespace n ON n.oid = c.relnamespace
            WHERE n.nspname NOT IN ('pg_catalog','information_schema')
        """)

        grab(conn, "index_columns", """
            SELECT i.indexrelid::regclass::text AS index_name,
                   i.indrelid::regclass::text AS table_name,
                   k.ordinality AS pos,
                   a.attname AS column_name,
                   pg_get_indexdef(i.indexrelid, k.ordinality::int, true) AS expr
            FROM pg_index i
            CROSS JOIN LATERAL unnest(i.indkey) WITH ORDINALITY AS k(attnum, ordinality)
            LEFT JOIN pg_attribute a ON a.attrelid = i.indrelid AND a.attnum = k.attnum
            JOIN pg_class c ON c.oid = i.indrelid
            JOIN pg_namespace n ON n.oid = c.relnamespace
            WHERE n.nspname NOT IN ('pg_catalog','information_schema')
            ORDER BY 1, 3
        """)

        grab(conn, "no_pk_tables", """
            SELECT n.nspname AS schema, c.relname AS table_name,
                   COALESCE(s.n_live_tup,0) AS n_live_tup
            FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
            LEFT JOIN pg_stat_user_tables s ON s.relid=c.oid
            WHERE c.relkind='r' AND n.nspname NOT IN ('pg_catalog','information_schema')
              AND NOT EXISTS (SELECT 1 FROM pg_index i WHERE i.indrelid=c.oid AND i.indisprimary)
            ORDER BY n_live_tup DESC
        """)

        grab(conn, "foreign_keys", """
            SELECT n.nspname AS schema, c.relname AS table_name, con.conname,
                   pg_get_constraintdef(con.oid) AS definition,
                   con.conrelid::regclass::text AS child,
                   con.confrelid::regclass::text AS parent,
                   (SELECT array_agg(a.attname ORDER BY k.ordinality)
                      FROM unnest(con.conkey) WITH ORDINALITY AS k(attnum, ordinality)
                      JOIN pg_attribute a ON a.attrelid=con.conrelid AND a.attnum=k.attnum) AS cols
            FROM pg_constraint con
            JOIN pg_class c ON c.oid = con.conrelid
            JOIN pg_namespace n ON n.oid = c.relnamespace
            WHERE con.contype='f' AND n.nspname NOT IN ('pg_catalog','information_schema')
        """)

        grab(conn, "sequences", """
            SELECT schemaname AS schema, sequencename AS sequence, data_type,
                   last_value, max_value, start_value, increment_by, cache_size, cycle,
                   (SELECT count(*) FROM pg_class c WHERE c.relkind='S'
                      AND c.oid = (quote_ident(schemaname)||'.'||quote_ident(sequencename))::regclass) AS attached_owner_exists
            FROM pg_sequences s
            WHERE schemaname NOT IN ('pg_catalog','information_schema')
            ORDER BY (last_value::numeric / NULLIF(max_value::numeric,0)) DESC NULLS LAST
        """)

        grab(conn, "column_types", """
            SELECT table_schema AS schema, table_name, column_name, data_type,
                   character_maximum_length, is_nullable, column_default
            FROM information_schema.columns
            WHERE table_schema NOT IN ('pg_catalog','information_schema')
              AND (data_type IN ('character varying','character','numeric','money','timestamp without time zone')
                   OR column_name ILIKE '%json%')
            ORDER BY table_name, ordinal_position
        """)

        grab(conn, "json_columns", """
            SELECT n.nspname AS schema, c.relname AS table_name, a.attname AS column_name,
                   format_type(a.atttypid, a.atttypmod) AS type,
                   a.attnotnull AS not_null,
                   COALESCE(s.null_frac,0) AS null_frac,
                   COALESCE(s.avg_width,0) AS avg_width,
                   COALESCE(s.n_distinct,0) AS n_distinct
            FROM pg_attribute a
            JOIN pg_class c ON c.oid=a.attrelid
            JOIN pg_namespace n ON n.oid=c.relnamespace
            LEFT JOIN pg_stats s ON s.schemaname=n.nspname AND s.tablename=c.relname AND s.attname=a.attname
            WHERE a.attnum>0 AND NOT a.attisdropped AND c.relkind IN ('r','p')
              AND n.nspname NOT IN ('pg_catalog','information_schema')
              AND format_type(a.atttypid, a.atttypmod) IN ('json','jsonb')
            ORDER BY COALESCE(s.avg_width,0) DESC
        """)

        grab(conn, "partitions", """
            SELECT parent.relname AS parent_table, parent.relkind,
                   count(*) AS partition_count,
                   pg_size_pretty(SUM(pg_total_relation_size(child.oid))) AS total_size,
                   min(pg_get_expr(child.relpartbound, child.oid)) AS first_bound,
                   max(pg_get_expr(child.relpartbound, child.oid)) AS last_bound
            FROM pg_inherits inh
            JOIN pg_class parent ON parent.oid = inh.inhparent
            JOIN pg_class child ON child.oid = inh.inhrelid
            JOIN pg_namespace n ON n.oid = parent.relnamespace
            WHERE n.nspname NOT IN ('pg_catalog','information_schema')
            GROUP BY 1,2 ORDER BY SUM(pg_total_relation_size(child.oid)) DESC
        """)

        grab(conn, "inherited_children", """
            SELECT parent.relname AS parent_table, count(*) AS children,
                   pg_size_pretty(SUM(pg_total_relation_size(child.oid))) AS total_size
            FROM pg_inherits inh
            JOIN pg_class parent ON parent.oid=inh.inhparent
            JOIN pg_class child ON child.oid=inh.inhrelid
            WHERE parent.relkind = 'r'
            GROUP BY 1 ORDER BY SUM(pg_total_relation_size(child.oid)) DESC
        """)

        grab(conn, "tablespaces", """
            SELECT spcname, pg_get_userbyid(spcowner) AS owner,
                   pg_tablespace_location(oid) AS location,
                   pg_size_pretty(pg_tablespace_size(oid)) AS size
            FROM pg_tablespace ORDER BY pg_tablespace_size(oid) DESC
        """)

        grab(conn, "extensions", """
            SELECT extname, extversion FROM pg_extension ORDER BY extname
        """)
        grab(conn, "available_extensions", """
            SELECT name, default_version, installed_version
            FROM pg_available_extensions
            WHERE name IN ('pgstattuple','pg_stat_statements','pg_trgm','btree_gin','btree_gist','pgcrypto','postgres_fdw','pg_repack')
            ORDER BY name
        """)

        grab(conn, "settings", """
            SELECT name, setting, unit, boot_val, source, pending_restart
            FROM pg_settings
            WHERE name IN ('shared_buffers','work_mem','maintenance_work_mem','effective_cache_size',
                           'max_connections','random_page_cost','effective_io_concurrency','max_wal_size',
                           'min_wal_size','checkpoint_completion_target','wal_level','archive_mode',
                           'autovacuum','autovacuum_max_workers','autovacuum_naptime',
                           'autovacuum_vacuum_scale_factor','autovacuum_vacuum_threshold',
                           'autovacuum_analyze_scale_factor','autovacuum_vacuum_cost_limit',
                           'autovacuum_vacuum_cost_delay','default_statistics_target','max_parallel_workers',
                           'max_parallel_workers_per_gather','track_io_timing','jit','huge_pages',
                           'synchronous_commit','wal_compression','max_worker_processes','shared_preload_libraries',
                           'log_min_duration_statement','statement_timeout','idle_in_transaction_session_timeout',
                           'temp_buffers','hash_mem_multiplier','enable_partition_pruning','constraint_exclusion',
                           'default_toast_compression','track_counts','track_activities')
            ORDER BY name
        """)

        grab(conn, "db_stats", """
            SELECT datname, numbackends, xact_commit, xact_rollback, blks_read, blks_hit,
                   tup_returned, tup_fetched, tup_inserted, tup_updated, tup_deleted,
                   conflicts, temp_files, temp_bytes, deadlocks, checksum_failures,
                   stats_reset
            FROM pg_stat_database WHERE datname = current_database()
        """)

        grab(conn, "wal_stats", """
            SELECT wal_records, wal_fpi, wal_bytes, stats_reset FROM pg_stat_wal
        """)

        grab(conn, "io_stats", """
            SELECT backend_type, object, context, reads, writes, writebacks, extends,
                   hits, evictions, reuses, fsyncs
            FROM pg_stat_io ORDER BY reads DESC LIMIT 30
        """)

        grab(conn, "user_indexes_unused", """
            SELECT s.schemaname AS schema, s.relname AS table_name, s.indexrelname AS index_name,
                   s.idx_scan, pg_size_pretty(pg_relation_size(s.indexrelid)) AS size,
                   pg_get_indexdef(s.indexrelid) AS indexdef
            FROM pg_stat_user_indexes s
            JOIN pg_index i ON i.indexrelid = s.indexrelid
            WHERE s.idx_scan = 0 AND NOT i.indisprimary AND NOT i.indisunique
              AND NOT i.indisreplident
            ORDER BY pg_relation_size(s.indexrelid) DESC
        """)

        grab(conn, "never_analyzed", """
            SELECT n.nspname AS schema, c.relname AS table_name, s.n_live_tup, s.n_dead_tup,
                   s.last_analyze, s.last_autoanalyze, s.last_vacuum, s.last_autovacuum
            FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
            LEFT JOIN pg_stat_user_tables s ON s.relid=c.oid
            WHERE c.relkind='r' AND n.nspname NOT IN ('pg_catalog','information_schema')
              AND s.last_analyze IS NULL AND s.last_autoanalyze IS NULL
            ORDER BY COALESCE(s.n_live_tup,0) DESC
        """)

        grab(conn, "long_running", """
            SELECT pid, now() - query_start AS duration, state, wait_event_type, wait_event,
                   left(query, 300) AS query
            FROM pg_stat_activity
            WHERE state <> 'idle' AND query_start IS NOT NULL
              AND now() - query_start > interval '5 seconds'
            ORDER BY duration DESC LIMIT 20
        """)

        grab(conn, "locks", """
            SELECT l.locktype, l.mode, l.granted, c.relname, count(*) AS n
            FROM pg_locks l LEFT JOIN pg_class c ON c.oid = l.relation
            WHERE NOT l.granted OR l.mode IN ('ExclusiveLock','AccessExclusiveLock')
            GROUP BY 1,2,3,4 ORDER BY n DESC LIMIT 20
        """)

        grab(conn, "invalid_indexes", """
            SELECT n.nspname AS schema, c.relname AS table_name, i.indexrelid::regclass::text AS index_name,
                   i.indisvalid, i.indisready, pg_get_indexdef(i.indexrelid) AS indexdef
            FROM pg_index i
            JOIN pg_class c ON c.oid = i.indrelid
            JOIN pg_namespace n ON n.oid = c.relnamespace
            WHERE NOT i.indisvalid OR NOT i.indisready
        """)

        grab(conn, "stats_target_zero", """
            SELECT n.nspname AS schema, c.relname AS table_name, a.attname, s.n_distinct, s.null_frac
            FROM pg_attribute a
            JOIN pg_class c ON c.oid=a.attrelid
            JOIN pg_namespace n ON n.oid=c.relnamespace
            JOIN pg_stats s ON s.schemaname=n.nspname AND s.tablename=c.relname AND s.attname=a.attname
            WHERE a.attnum>0 AND NOT a.attisdropped AND c.relkind='r'
              AND n.nspname NOT IN ('pg_catalog','information_schema')
              AND s.n_distinct = 0 AND pg_total_relation_size(c.oid) > 50000000
        """)

        grab(conn, "toast_heavy", """
            SELECT n.nspname AS schema, c.relname AS table_name,
                   pg_size_pretty(pg_total_relation_size(c.oid) - pg_relation_size(c.oid)
                                  - pg_indexes_size(c.oid)) AS toast_size,
                   pg_total_relation_size(c.oid) - pg_relation_size(c.oid)
                     - pg_indexes_size(c.oid) AS toast_bytes
            FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
            WHERE c.relkind='r' AND n.nspname NOT IN ('pg_catalog','information_schema')
              AND pg_total_relation_size(c.oid) - pg_relation_size(c.oid) - pg_indexes_size(c.oid) > 0
            ORDER BY toast_bytes DESC LIMIT 25
        """)

        # bloat approximation where pgstattuple is available
        grab(conn, "stattuple", """
            SELECT c.relname AS table_name, n.nspname AS schema,
                   pg_size_pretty(pg_relation_size(c.oid)) AS heap_size
            FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
            WHERE c.relkind='r' AND n.nspname NOT IN ('pg_catalog','information_schema')
              AND pg_relation_size(c.oid) > 20000000
            ORDER BY pg_relation_size(c.oid) DESC LIMIT 40
        """)

        grab(conn, "top_stat_statements", """
            SELECT calls, rows, total_exec_time, mean_exec_time, shared_blks_hit, shared_blks_read,
                   temp_blks_written, left(query, 400) AS query
            FROM pg_stat_statements
            WHERE query NOT ILIKE '%pg_stat%'
            ORDER BY total_exec_time DESC LIMIT 40
        """)

    out = HERE / "raw.json"
    out.write_text(json.dumps(RAW, default=str, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"wrote {out}")

    tables = RAW.get("tables")
    if isinstance(tables, list):
        print("\n=== TOP TABLES BY TOTAL SIZE ===")
        for t in tables[:30]:
            mb = t["total_bytes"] / 1048576
            print(f"{mb:10.1f}MB  heap={t['heap_bytes']/1048576:9.1f} idx={t['index_bytes']/1048576:9.1f} "
                  f"toast={t['toast_bytes']/1048576:9.1f} live={t['n_live_tup']:>10} dead={t['n_dead_tup']:>9} "
                  f"seq={t['seq_scan']:>8} idxscan={t['idx_scan']:>9} {t['schema']}.{t['table_name']}")
    print("\ncounts:", {k: (len(v) if isinstance(v, list) else v)
                        for k, v in RAW.items() if k in
                        ("tables", "indexes", "foreign_keys", "no_pk_tables", "user_indexes_unused",
                         "partitions", "sequences", "invalid_indexes", "available_extensions", "extensions")})


if __name__ == "__main__":
    main()