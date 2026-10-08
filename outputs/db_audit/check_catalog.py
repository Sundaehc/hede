import sys
sys.path.insert(0, r"E:\hede\backend")
from config import load_settings
from sqlalchemy import create_engine
s = load_settings(require_database=True)
e = create_engine(s.database_url)
SQL = """
WITH parts AS (
  SELECT i.inhparent AS parent, c.reltuples AS rt, pg_total_relation_size(c.oid) AS bytes
  FROM pg_inherits i JOIN pg_class c ON c.oid = i.inhrelid
)
SELECT c.relname, c.relkind::text,
       c.reltuples::bigint AS own_rt,
       pg_total_relation_size(c.oid) AS own_bytes,
       COALESCE((SELECT sum(p.rt) FROM parts p WHERE p.parent = c.oid),0)::bigint AS child_rt,
       COALESCE((SELECT sum(p.bytes) FROM parts p WHERE p.parent = c.oid),0) AS child_bytes
FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
WHERE n.nspname='public' AND c.relkind IN ('r','p')
  AND c.relname IN ('jst_monthly_orders','vip_daily_sales','dewu_orders',
                    'product_goods_detail_snapshots','jst_daily_stock','inventory_details',
                    'fine_table_snapshot_refs_2026','product_goods_historical_orders')
ORDER BY c.relname
"""
with e.connect() as c:
    c = c.execution_options(isolation_level="AUTOCOMMIT")
    print(f"{'table':<34}{'kind':<5}{'own_rt':>14}{'own_MB':>10}{'child_rt':>14}{'child_MB':>10}")
    for r in c.exec_driver_sql(SQL).fetchall():
        print(f"{r[0]:<34}{r[1]:<5}{r[2]:>14,}{r[3]/1048576:>10.1f}{r[4]:>14,}{r[5]/1048576:>10.1f}")
    # 分区父表的 pg_total_relation_size 是否已含子表?
    q = c.exec_driver_sql("SELECT pg_total_relation_size('public.jst_monthly_orders')").fetchone()[0]
    print("\npg_total_relation_size(jst_monthly_orders 父表) =", q, "字节")
