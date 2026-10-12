from __future__ import annotations


STALE_LARGE_TABLES_SQL = """
    SELECT namespace.nspname AS schema_name, relation.relname AS table_name,
           pg_relation_size(relation.oid) AS size_bytes,
           GREATEST(statistics.last_analyze, statistics.last_autoanalyze) AS last_statistics_update
    FROM pg_class AS relation
    JOIN pg_namespace AS namespace ON namespace.oid = relation.relnamespace
    LEFT JOIN pg_stat_user_tables AS statistics ON statistics.relid = relation.oid
    WHERE namespace.nspname = 'public' AND relation.relkind = 'r'
      AND pg_relation_size(relation.oid) > 100 * 1024 * 1024
      AND (
          GREATEST(statistics.last_analyze, statistics.last_autoanalyze) IS NULL
          OR GREATEST(statistics.last_analyze, statistics.last_autoanalyze) < now() - interval '7 days'
      )
"""
