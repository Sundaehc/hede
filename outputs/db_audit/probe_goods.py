# -*- coding: utf-8 -*-
import sys
sys.path.insert(0, r"E:\hede\backend")
from config import load_settings
from sqlalchemy import create_engine
CODE = "QT653891S30"
e = create_engine(load_settings(require_database=True).database_url)
with e.connect() as c:
    c = c.execution_options(isolation_level="AUTOCOMMIT")
    c.exec_driver_sql("SET statement_timeout = '120s'")
    print("=== product_goods_detail_snapshots 结构 ===")
    for r in c.exec_driver_sql("""
        SELECT a.attname, format_type(a.atttypid,a.atttypmod)
        FROM pg_attribute a JOIN pg_class cl ON cl.oid=a.attrelid
        JOIN pg_namespace n ON n.oid=cl.relnamespace
        WHERE n.nspname='public' AND cl.relname='product_goods_detail_snapshots'
          AND a.attnum>0 AND NOT a.attisdropped ORDER BY a.attnum""").fetchall():
        print("   ", r[0], "|", r[1])
    print("\n=== 该款的快照记录（按日期）===")
    rows = c.exec_driver_sql(f"""
        SELECT snapshot_date, source_workbook, goods_code, style_code, product_name,
               total_sales, return_qty, total_order_count, yesterday_sales
        FROM public.product_goods_detail_snapshots
        WHERE style_code = '{CODE}'
        ORDER BY snapshot_date, goods_code""").fetchall()
    print("行数:", len(rows))
    for r in rows[:25]:
        print("   ", r)
    if len(rows) > 25:
        print(f"    ... 其余 {len(rows)-25} 行略")
