# -*- coding: utf-8 -*-
import sys
sys.path.insert(0, r"E:\hede\backend")
from config import load_settings
from sqlalchemy import create_engine

CODE = "QT653891S30"
CANDIDATES = [
    "product_goods_detail_snapshots", "product_goods_historical_sales",
    "product_goods_historical_orders", "product_goods_overrides",
    "jst_monthly_orders", "jst_daily_sales", "jst_aftersale_returns",
    "jst_product_profiles", "jst_full_stock", "jst_product_price",
    "jst_daily_stock", "vip_daily_sales", "gj_merged_product_info",
    "inventory_details", "product_archive_identities", "product_size_group_mappings",
    "cbanner_mens_products", "cbanner_womens_products", "yandou_products",
    "eblan_products", "smiley_products", "ni_products", "manual_product_archive_31",
]
e = create_engine(load_settings(require_database=True).database_url)
with e.connect() as c:
    c = c.execution_options(isolation_level="AUTOCOMMIT")
    c.exec_driver_sql("SET statement_timeout = '120s'")
    for t in CANDIDATES:
        exists = c.exec_driver_sql(f"SELECT to_regclass('public.{t}') IS NOT NULL").fetchone()[0]
        if not exists:
            print(f"[缺表] {t}")
            continue
        cols = [r[0] for r in c.exec_driver_sql(f"""
            SELECT a.attname FROM pg_attribute a
            JOIN pg_class cl ON cl.oid=a.attrelid JOIN pg_namespace n ON n.oid=cl.relnamespace
            WHERE n.nspname='public' AND cl.relname='{t}' AND a.attnum>0 AND NOT a.attisdropped
              AND (a.attname LIKE '%%code%%' OR a.attname LIKE '%%sku%%')
            ORDER BY a.attnum""").fetchall()]
        hits = []
        for col in cols:
            try:
                n = c.exec_driver_sql(
                    f"SELECT count(*) FROM public.{t} WHERE {col}::text = '{CODE}'").fetchone()[0]
            except Exception as ex:
                hits.append(f"{col}=ERR"); continue
            if n:
                hits.append(f"{col}={n:,}")
        print(f"[{t}] 候选列 {cols} -> 命中: {hits if hits else '无'}")
