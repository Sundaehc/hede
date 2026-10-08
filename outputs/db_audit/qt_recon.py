# -*- coding: utf-8 -*-
import sys
sys.path.insert(0, r"E:\hede\backend")
from config import load_settings
from sqlalchemy import create_engine
CODE = "QT653891S30"
OUT = r"E:\hede\outputs\db_audit\qt_check.txt"
buf = []
def p(*a): buf.append(" ".join(str(x) for x in a))
JST_MATCH = f"(starts_with(product_code, '{CODE}') OR style_code = '{CODE}')"
VIP_MATCH = f"(starts_with(goods_code, '{CODE}') OR style_code = '{CODE}')"

e = create_engine(load_settings(require_database=True).database_url)
with e.connect() as c:
    c = c.execution_options(isolation_level="AUTOCOMMIT")
    c.exec_driver_sql("SET statement_timeout = '300s'")

    p("="*100)
    p("A. 货品表 Excel 文件自己写的数值（source_workbook = 具体 xlsx）")
    p("="*100)
    p(f"{'快照日':<12}{'来源文件':<46}{'总销量':>9}{'退货数量':>9}{'总订单量':>9}{'年销量':>8}{'2025':>7}{'2024':>7}")
    rows = c.exec_driver_sql(f"""
        SELECT snapshot_date, source_workbook,
               data->'metrics'->>'total_sales', data->'metrics'->>'return_qty',
               data->'metrics'->>'total_order_count', data->'metrics'->>'year_sales',
               data->'metrics'->>'sales_2025', data->'metrics'->>'sales_2024'
        FROM public.product_goods_detail_snapshots
        WHERE (style_code='{CODE}' OR goods_code='{CODE}')
          AND NOT starts_with(source_workbook, 'database_calculated')
        ORDER BY snapshot_date DESC LIMIT 12""").fetchall()
    for r in rows:
        p(f"{str(r[0]):<12}{str(r[1])[:44]:<46}{str(r[2]):>9}{str(r[3]):>9}{str(r[4]):>9}{str(r[5]):>8}{str(r[6]):>7}{str(r[7]):>7}")
    n = c.exec_driver_sql(f"""SELECT count(*) FROM public.product_goods_detail_snapshots
        WHERE (style_code='{CODE}' OR goods_code='{CODE}')
          AND NOT starts_with(source_workbook, 'database_calculated')""").fetchone()[0]
    p(f"\n(Excel 来源快照共 {n} 行)")

    p("\n" + "="*100)
    p("B. 数据库自己算出来的货品表数值（source_workbook = database_calculated_product_goods）")
    p("="*100)
    p(f"{'快照日':<12}{'总销量':>9}{'退货数量':>9}{'总订单量':>9}{'年销量':>8}{'2025':>7}{'2024':>7}")
    for r in c.exec_driver_sql(f"""
        SELECT snapshot_date,
               data->'metrics'->>'total_sales', data->'metrics'->>'return_qty',
               data->'metrics'->>'total_order_count', data->'metrics'->>'year_sales',
               data->'metrics'->>'sales_2025', data->'metrics'->>'sales_2024'
        FROM public.product_goods_detail_snapshots
        WHERE (style_code='{CODE}' OR goods_code='{CODE}')
          AND starts_with(source_workbook, 'database_calculated')
        ORDER BY snapshot_date DESC LIMIT 6""").fetchall():
        p(f"{str(r[0]):<12}{str(r[1]):>9}{str(r[2]):>9}{str(r[3]):>9}{str(r[4]):>8}{str(r[5]):>7}{str(r[6]):>7}")

    p("\n" + "="*100)
    p("C. 原始表重算（数据库的底层事实）")
    p("="*100)
    p("\n-- jst_daily_sales 汇总 --")
    r = c.exec_driver_sql(f"""
        SELECT count(*), min(sales_date), max(sales_date),
               sum(net_sales_quantity), sum(return_quantity), sum(sales_order_count)
        FROM public.jst_daily_sales WHERE {JST_MATCH}""").fetchone()
    p(f"行数={r[0]:,}  日期={r[1]}~{r[2]}")
    p(f"sum(net_sales_quantity) 净销量 = {r[3]:,}")
    p(f"sum(return_quantity)    退货  = {r[4]:,}")
    p(f"sum(sales_order_count)  订单  = {r[5]:,}")

    p("\n-- 按渠道 --")
    p(f"{'渠道':<26}{'行数':>7}{'净销量':>13}{'退货数量':>13}{'订单数':>11}")
    for r in c.exec_driver_sql(f"""
        SELECT channel, count(*), sum(net_sales_quantity), sum(return_quantity), sum(sales_order_count)
        FROM public.jst_daily_sales WHERE {JST_MATCH}
        GROUP BY channel ORDER BY 3 DESC NULLS LAST""").fetchall():
        p(f"{str(r[0])[:24]:<26}{r[1]:>7,}{r[2] or 0:>13,}{r[3] or 0:>13,}{r[4] or 0:>11,}")

    p("\n-- 关键疑点：return_quantity 是否几乎等于 net_sales_quantity --")
    r = c.exec_driver_sql(f"""
        SELECT count(*) AS rows,
               count(*) FILTER (WHERE return_quantity IS NULL) AS rq_null,
               count(*) FILTER (WHERE net_sales_quantity IS NULL) AS sq_null,
               count(*) FILTER (WHERE return_quantity = net_sales_quantity) AS equal_rows,
               count(*) FILTER (WHERE return_quantity <> net_sales_quantity) AS diff_rows,
               count(*) FILTER (WHERE return_quantity > net_sales_quantity) AS rq_gt
        FROM public.jst_daily_sales WHERE {JST_MATCH}""").fetchone()
    p(f"总行数={r[0]:,}")
    p(f"return_quantity 为 NULL 的行 = {r[1]:,} ；net_sales_quantity 为 NULL = {r[2]:,}")
    p(f"两列【相等】的行 = {r[3]:,}")
    p(f"两列【不等】的行 = {r[4]:,}")
    p(f"退货 > 销量 的行 = {r[5]:,}")

    p("\n-- 抽样 12 行（return_quantity > 0）--")
    p(f"{'sales_date':<12}{'channel':<16}{'color_spec':<18}{'净销量':>8}{'退货数量':>9}{'订单数':>7}")
    for r in c.exec_driver_sql(f"""
        SELECT sales_date, channel, color_spec, net_sales_quantity, return_quantity, sales_order_count
        FROM public.jst_daily_sales
        WHERE {JST_MATCH} AND return_quantity > 0
        ORDER BY sales_date DESC LIMIT 12""").fetchall():
        p(f"{str(r[0]):<12}{str(r[1])[:14]:<16}{str(r[2])[:16]:<18}{str(r[3]):>8}{str(r[4]):>9}{str(r[5]):>7}")

    p("\n-- vip_daily_sales --")
    r = c.exec_driver_sql(f"""
        SELECT count(*), min(sales_date), max(sales_date), sum(sales_quantity), sum(customer_count)
        FROM public.vip_daily_sales WHERE {VIP_MATCH}""").fetchone()
    p(f"行数={r[0]:,}  日期={r[1]}~{r[2]}  sum(sales_quantity)={r[3]:,}  sum(customer_count)={r[4]:,}")

    p("\n-- product_goods_historical_sales_* --")
    for y in (2024, 2025, 2026):
        t = f"product_goods_historical_sales_{y}"
        if not c.exec_driver_sql(f"SELECT to_regclass('public.{t}') IS NOT NULL").fetchone()[0]:
            p(f"{t}: 表不存在"); continue
        r = c.exec_driver_sql(f"""
            SELECT count(*), sum(sales_quantity) FROM public.{t}
            WHERE starts_with(product_code, '{CODE}') OR original_sku='{CODE}'""").fetchone()
        p(f"{t}: 行数={r[0]:,}  sum(sales_quantity)={r[1] or 0:,}")

    p("\n-- jst_aftersale_returns（售后退货）--")
    for y in (2025, 2026):
        t = f"jst_aftersale_returns_{y}"
        if not c.exec_driver_sql(f"SELECT to_regclass('public.{t}') IS NOT NULL").fetchone()[0]:
            p(f"{t}: 表不存在"); continue
        cols = [x[0] for x in c.exec_driver_sql(f"""
            SELECT a.attname FROM pg_attribute a JOIN pg_class cl ON cl.oid=a.attrelid
            JOIN pg_namespace n ON n.oid=cl.relnamespace
            WHERE n.nspname='public' AND cl.relname='{t}' AND a.attnum>0 AND NOT a.attisdropped
              AND a.attname ~ 'qty|quantity|count'""").fetchall()]
        p(f"{t} 数量相关列: {cols}")
        for col in cols:
            r = c.exec_driver_sql(f"SELECT count(*), sum({col}) FROM public.{t} WHERE original_goods_code='{CODE}'").fetchone()
            p(f"   {col}: 行数={r[0]:,} sum={r[1] or 0:,}")

open(OUT, "w", encoding="utf-8").write("\n".join(buf))
print("written", OUT, len(buf), "lines")
