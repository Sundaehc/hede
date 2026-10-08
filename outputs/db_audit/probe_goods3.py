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
    print("=== 该 code 的来源/品牌分布 ===")
    for r in c.exec_driver_sql(f"""
        SELECT source_workbook, brand, count(*), min(snapshot_date), max(snapshot_date),
               count(DISTINCT goods_code), count(DISTINCT style_code)
        FROM public.product_goods_detail_snapshots
        WHERE style_code='{CODE}' OR goods_code='{CODE}'
        GROUP BY 1,2 ORDER BY 3 DESC""").fetchall():
        print("   ", r)
    print("\n=== 最近 6 个快照日的 metrics ===")
    for r in c.exec_driver_sql(f"""
        SELECT snapshot_date, brand, goods_code, style_code,
               data->'metrics'->>'total_sales'   AS total_sales,
               data->'metrics'->>'return_qty'    AS return_qty,
               data->'metrics'->>'total_order_count' AS orders,
               data->'metrics'->>'year_sales'    AS year_sales,
               data->'metrics'->>'sales_2025'    AS sales_2025,
               data->'metrics'->>'month_sales'   AS month_sales
        FROM public.product_goods_detail_snapshots
        WHERE style_code='{CODE}' AND snapshot_date >= '2026-10-01'
        ORDER BY snapshot_date DESC, goods_code LIMIT 12""").fetchall():
        print("   ", r)
    print("\n=== 该款各 goods_code（SKU）在最新快照日 ===")
    d = c.exec_driver_sql(f"SELECT max(snapshot_date) FROM public.product_goods_detail_snapshots WHERE style_code='{CODE}'").fetchone()[0]
    print("最新快照日:", d)
    for r in c.exec_driver_sql(f"""
        SELECT goods_code, style_code, brand,
               data->'metrics'->>'total_sales', data->'metrics'->>'return_qty',
               data->'metrics'->>'year_sales', data->'metrics'->>'sales_2025'
        FROM public.product_goods_detail_snapshots
        WHERE (style_code='{CODE}' OR goods_code='{CODE}') AND snapshot_date='{d}'
        ORDER BY goods_code""").fetchall():
        print("   ", r)
    print("\n=== metrics 里的全部键（该款）===")
    ks = c.exec_driver_sql(f"""
        SELECT k, count(*) FROM (
          SELECT json_object_keys(data->'metrics') AS k
          FROM public.product_goods_detail_snapshots
          WHERE snapshot_date='{d}' AND (style_code='{CODE}' OR goods_code='{CODE}')
        ) x GROUP BY k ORDER BY k""").fetchall()
    print([k for k,_ in ks])
