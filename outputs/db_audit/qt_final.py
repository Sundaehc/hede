# -*- coding: utf-8 -*-
import sys, json
sys.path.insert(0, r"E:\hede\backend")
from config import load_settings
from sqlalchemy import create_engine
CODE = "QT653891S30"
OUT = r"E:\hede\outputs\db_audit\qt_final.txt"
buf = []
def p(*a): buf.append(" ".join(str(x) for x in a))
e = create_engine(load_settings(require_database=True).database_url)
with e.connect() as c:
    c = c.execution_options(isolation_level="AUTOCOMMIT")
    c.exec_driver_sql("SET statement_timeout = '300s'")

    p("="*100); p("1) jst_aftersale_returns 全部分区（父表）"); p("="*100)
    p(f"{'分区':<34}{'行数':>9}{'returned_qty合计':>18}")
    for r in c.exec_driver_sql("""
        SELECT c.relname, (SELECT count(*) FROM pg_stat_user_tables s WHERE s.relid=c.oid)
        FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
        WHERE n.nspname='public' AND c.relname ~ '^jst_aftersale_returns'
        ORDER BY c.relname""").fetchall():
        t = r[0]
        try:
            n, tot = c.exec_driver_sql(f"SELECT count(*), sum(returned_qty) FROM public.{t}").fetchone()
        except Exception as ex:
            n, tot = "ERR", str(ex)[:40]
        p(f"{t:<34}{str(n):>9}{str(tot):>18}")

    p("\n-- 该款式在父表上的各种口径 --")
    variants = [
        ("精确等值 original_goods_code = 货号", f"original_goods_code = '{CODE}'"),
        ("前缀 starts_with(original_goods_code)", f"starts_with(original_goods_code, '{CODE}')"),
    ]
    for label, cond in variants:
        r = c.exec_driver_sql(f"SELECT count(*), sum(returned_qty) FROM public.jst_aftersale_returns WHERE {cond}").fetchone()
        p(f"{label:<44} 行数={r[0]:>8,}  sum(returned_qty)={r[1] or 0:>10,}")
        r2 = c.exec_driver_sql(f"""
            SELECT count(*), sum(returned_qty) FROM public.jst_aftersale_returns
            WHERE {cond} AND coalesce(application_date_value, order_date_value, order_time_value) <= DATE '2026-10-06'""").fetchone()
        p(f"{'  加 as_of_date<=2026-10-06':<44} 行数={r2[0]:>8,}  sum(returned_qty)={r2[1] or 0:>10,}")

    p("\n-- 按年份分布（prefix 匹配）--")
    p(f"{'年':<8}{'行数':>9}{'returned_qty':>14}")
    for r in c.exec_driver_sql(f"""
        SELECT extract(year FROM coalesce(application_date_value, order_date_value, order_time_value))::int AS y,
               count(*), sum(returned_qty)
        FROM public.jst_aftersale_returns
        WHERE starts_with(original_goods_code, '{CODE}')
        GROUP BY 1 ORDER BY 1""").fetchall():
        p(f"{str(r[0]):<8}{r[1]:>9}{r[2] or 0:>14}")

    p("\n-- original_goods_code 明细（前 15 个，观察前缀匹配是否过宽）--")
    for r in c.exec_driver_sql(f"""
        SELECT original_goods_code, count(*), sum(returned_qty)
        FROM public.jst_aftersale_returns
        WHERE starts_with(original_goods_code, '{CODE}')
        GROUP BY 1 ORDER BY 3 DESC NULLS LAST LIMIT 15""").fetchall():
        p(f"   {r[0]:<30} 行数={r[1]:>7,}  退货量={r[2] or 0:>8,}")

    p("\n" + "="*100); p("2) 该款式的 SKU 列表（product_codes）"); p("="*100)
    for r in c.exec_driver_sql(f"""
        SELECT DISTINCT product_code, style_code FROM public.jst_daily_sales
        WHERE starts_with(product_code, '{CODE}') OR style_code='{CODE}' ORDER BY 1""").fetchall():
        p("   jst_daily_sales:", r)
    for r in c.exec_driver_sql(f"""
        SELECT DISTINCT goods_code, style_code FROM public.vip_daily_sales
        WHERE starts_with(goods_code, '{CODE}') OR style_code='{CODE}' ORDER BY 1""").fetchall():
        p("   vip_daily_sales:", r)

    p("\n" + "="*100); p("3) 2026 年逐月：数据库 vs 货品表 Excel"); p("="*100)
    p("(Excel 的 monthly_sales: 26-2:2 26-3:85 26-4:5845 26-5:26884 26-6:17667 26-7:4834 26-8:203 26-9:30 26-10:1 = 55551)")
    p(f"\n{'月份':<10}{'jst净销量':>12}{'jst退货':>12}{'jst订单':>10}{'vip销量':>10}")
    jst = {str(r[0]): r for r in c.exec_driver_sql(f"""
        SELECT to_char(sales_date,'YYYY-MM') AS m, sum(net_sales_quantity), sum(return_quantity), sum(sales_order_count)
        FROM public.jst_daily_sales WHERE starts_with(product_code,'{CODE}') OR style_code='{CODE}'
        GROUP BY 1 ORDER BY 1""").fetchall()}
    vip = {str(r[0]): r for r in c.exec_driver_sql(f"""
        SELECT to_char(sales_date,'YYYY-MM') AS m, sum(sales_quantity)
        FROM public.vip_daily_sales WHERE starts_with(goods_code,'{CODE}') OR style_code='{CODE}'
        GROUP BY 1 ORDER BY 1""").fetchall()}
    for m in sorted(set(jst) | set(vip)):
        a = jst.get(m); b = vip.get(m)
        p(f"{m:<10}{(a[1] if a else 0) or 0:>12,}{(a[2] if a else 0) or 0:>12,}{(a[3] if a else 0) or 0:>10,}{(b[1] if b else 0) or 0:>10,}")

    p("\n-- product_goods_historical_sales_2025 逐月（数据库用来补 2025 的）--")
    for r in c.exec_driver_sql(f"""
        SELECT to_char(sales_date,'YYYY-MM') AS m, sum(sales_quantity)
        FROM public.product_goods_historical_sales_2025
        WHERE starts_with(product_code,'{CODE}') OR original_sku='{CODE}'
        GROUP BY 1 ORDER BY 1""").fetchall():
        p(f"   {r[0]}: {r[1]:,}")

    p("\n-- 是否存在 product_goods_historical_sales_2026 --")
    p("   ", c.exec_driver_sql("SELECT to_regclass('public.product_goods_historical_sales_2026')").fetchone()[0])

    p("\n" + "="*100); p("4) jst_daily_sales 全表口径校验（判断 return 列是否全局异常）"); p("="*100)
    r = c.exec_driver_sql("""
        SELECT count(*), sum(sales_quantity), sum(shipped_quantity), sum(return_quantity),
               sum(net_sales_quantity), sum(return_order_count), sum(sales_order_count)
        FROM public.jst_daily_sales""").fetchone()
    p(f"全表行数={r[0]:,}")
    p(f"  sum(sales_quantity)      = {r[1]:,}")
    p(f"  sum(shipped_quantity)    = {r[2]:,}")
    p(f"  sum(return_quantity)     = {r[3]:,}")
    p(f"  sum(net_sales_quantity)  = {r[4]:,}")
    p(f"  sum(return_order_count)  = {r[5]:,}")
    p(f"  sum(sales_order_count)   = {r[6]:,}")
    p(f"  校验 net == sales - return ? {r[4]} == {r[1]} - {r[3]} = {(r[1] or 0)-(r[3] or 0)}")
    r = c.exec_driver_sql("""
        SELECT count(*) FILTER (WHERE return_quantity > sales_quantity),
               count(*) FILTER (WHERE return_quantity IS NOT NULL AND net_sales_quantity IS NOT NULL
                                AND net_sales_quantity <> sales_quantity - return_quantity)
        FROM public.jst_daily_sales""").fetchone()
    p(f"  全表 return>sales 行数 = {r[0]:,} ; net <> sales-return 行数 = {r[1]:,}")

open(OUT,"w",encoding="utf-8").write("\n".join(buf))
print("written", OUT, len(buf), "lines")
