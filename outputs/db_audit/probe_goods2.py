# -*- coding: utf-8 -*-
import sys, json
sys.path.insert(0, r"E:\hede\backend")
from config import load_settings
from sqlalchemy import create_engine
CODE = "QT653891S30"
e = create_engine(load_settings(require_database=True).database_url)
with e.connect() as c:
    c = c.execution_options(isolation_level="AUTOCOMMIT")
    c.exec_driver_sql("SET statement_timeout = '180s'")
    print("=== 该 code 的 JSON 字段名 ===")
    keys = c.exec_driver_sql(f"""
        SELECT k, count(*) FROM (
          SELECT json_object_keys(data) AS k
          FROM public.product_goods_detail_snapshots
          WHERE style_code='{CODE}' OR goods_code='{CODE}'
        ) x GROUP BY k ORDER BY k""").fetchall()
    print("字段数:", len(keys))
    print([k for k,_ in keys])
    print("\n=== 快照日期范围（该 code）===")
    print(c.exec_driver_sql(f"""
        SELECT min(snapshot_date), max(snapshot_date), count(*), count(DISTINCT snapshot_date)
        FROM public.product_goods_detail_snapshots
        WHERE style_code='{CODE}' OR goods_code='{CODE}'""").fetchone())
    print("\n=== 全表快照日期范围 ===")
    print(c.exec_driver_sql("""
        SELECT min(snapshot_date), max(snapshot_date), count(DISTINCT snapshot_date)
        FROM public.product_goods_detail_snapshots""").fetchone())
    print("\n=== 该 style_code 的快照明细（最近 20 条）===")
    for r in c.exec_driver_sql(f"""
        SELECT snapshot_date, brand, goods_code, style_code, source_workbook,
               data->>'total_sales', data->>'return_qty', data->>'total_order_count'
        FROM public.product_goods_detail_snapshots
        WHERE style_code='{CODE}'
        ORDER BY snapshot_date DESC, goods_code LIMIT 20""").fetchall():
        print("   ", r)
