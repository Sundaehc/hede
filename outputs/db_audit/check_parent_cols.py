import sys
sys.path.insert(0, r"E:\hede\backend")
from config import load_settings
from sqlalchemy import create_engine
s = load_settings(require_database=True)
e = create_engine(s.database_url)
targets = ["jst_daily_sales","vip_daily_sales","dewu_orders","fine_table_snapshot_refs",
           "product_goods_detail_snapshots","product_goods_historical_orders",
           "jst_monthly_orders","product_goods_historical_sales","jst_aftersale_returns",
           "jst_daily_stock","jst_purchase_inbound_daily","jst_product_price",
           "vip_product_ops_snapshots","jst_size_stock_snapshots","vip_product_daily_snapshots"]
with e.connect() as c:
    c = c.execution_options(isolation_level="AUTOCOMMIT")
    for t in targets:
        rows = c.exec_driver_sql(f"""
            SELECT a.attname, format_type(a.atttypid,a.atttypmod)
            FROM pg_attribute a JOIN pg_class cl ON cl.oid=a.attrelid
            JOIN pg_namespace n ON n.oid=cl.relnamespace
            WHERE n.nspname='public' AND cl.relname='{t}' AND a.attnum>0 AND NOT a.attisdropped
              AND (a.attname LIKE '%%date%%' OR a.attname IN ('record_key','order_time_at','sku'))
            ORDER BY a.attnum""").fetchall()
        kind = c.exec_driver_sql(f"SELECT relkind FROM pg_class WHERE relname='{t}' AND relnamespace='public'::regnamespace").fetchone()
        print(f"{t:<34} relkind={kind[0] if kind else '?'}  " + ", ".join(f"{r[0]}:{r[1]}" for r in rows))
