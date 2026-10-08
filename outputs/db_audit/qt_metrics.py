# -*- coding: utf-8 -*-
import sys, json
sys.path.insert(0, r"E:\hede\backend")
from config import load_settings
from sqlalchemy import create_engine
CODE = "QT653891S30"
OUT = r"E:\hede\outputs\db_audit\qt_metrics_cmp.txt"
buf = []
def p(*a): buf.append(" ".join(str(x) for x in a))

e = create_engine(load_settings(require_database=True).database_url)
with e.connect() as c:
    c = c.execution_options(isolation_level="AUTOCOMMIT")
    c.exec_driver_sql("SET statement_timeout = '300s'")

    def fetch(where):
        return c.exec_driver_sql(f"""
            SELECT snapshot_date, source_workbook, data, source_sheet, source_row_number
            FROM public.product_goods_detail_snapshots
            WHERE (style_code='{CODE}' OR goods_code='{CODE}') AND {where}
            ORDER BY snapshot_date DESC LIMIT 1""").fetchone()

    excel = fetch("starts_with(source_workbook, '赫德货品表')")
    db    = fetch("starts_with(source_workbook, 'database_calculated')")
    parsed = {}
    for label, row in (("货品表 Excel 文件", excel), ("数据库计算", db)):
        p("="*100)
        p(f"### {label}")
        p(f"快照日={row[0]}   来源文件={row[1]}   sheet={row[3]}   行号={row[4]}")
        p("="*100)
        d = row[2] if isinstance(row[2], dict) else json.loads(row[2])
        parsed[label] = d
        p("顶层字段:", sorted(d.keys()))
        m = d.get("metrics") or {}
        p(f"\nmetrics 共 {len(m)} 项：")
        for k in sorted(m):
            p(f"    {k:<40} = {m[k]}")
        for extra in ("annual_sales", "monthly_sales", "snapshot_format", "sales_by_size"):
            if extra in d:
                p(f"\n[{extra}] " + json.dumps(d[extra], ensure_ascii=False)[:1200])
        if "daily_sales_by_date" in d:
            v = d["daily_sales_by_date"]
            if isinstance(v, dict):
                items = sorted(v.items())[-8:]
                p(f"\n[daily_sales_by_date] 共 {len(v)} 天，最后 8 天: {json.dumps(dict(items), ensure_ascii=False)}")
        p("")

    p("="*100); p("### 并排对比"); p("="*100)
    me = (parsed["货品表 Excel 文件"].get("metrics") or {})
    md = (parsed["数据库计算"].get("metrics") or {})
    p(f"{'字段':<40}{'Excel货品表':>16}{'数据库计算':>16}{'一致':>6}")
    for k in sorted(set(me) | set(md)):
        a, b = me.get(k), md.get(k)
        p(f"{k:<40}{str(a):>16}{str(b):>16}{'是' if str(a)==str(b) else '否':>6}")

    p("\n" + "="*100); p("### product_goods_historical_sales_2025"); p("="*100)
    cols = [x[0] for x in c.exec_driver_sql("""
        SELECT a.attname FROM pg_attribute a JOIN pg_class cl ON cl.oid=a.attrelid
        JOIN pg_namespace n ON n.oid=cl.relnamespace
        WHERE n.nspname='public' AND cl.relname='product_goods_historical_sales_2025'
          AND a.attnum>0 AND NOT a.attisdropped ORDER BY a.attnum""").fetchall()]
    p("列:", cols)
    r = c.exec_driver_sql(f"""
        SELECT count(*), min(sales_date), max(sales_date), sum(sales_quantity), count(DISTINCT channel)
        FROM public.product_goods_historical_sales_2025
        WHERE starts_with(product_code, '{CODE}') OR original_sku='{CODE}'""").fetchone()
    p(f"该货号: 行数={r[0]}  日期={r[1]}~{r[2]}  sum(sales_quantity)={r[3]}  渠道数={r[4]}")
    p("\n渠道分布:")
    p(f"{'渠道':<28}{'行数':>7}{'销量':>12}")
    for r in c.exec_driver_sql(f"""
        SELECT channel, count(*), sum(sales_quantity)
        FROM public.product_goods_historical_sales_2025
        WHERE starts_with(product_code, '{CODE}') OR original_sku='{CODE}'
        GROUP BY channel ORDER BY 3 DESC NULLS LAST""").fetchall():
        p(f"{str(r[0])[:26]:<28}{r[1]:>7}{r[2] or 0:>12}")
    p("\n样本 6 行:")
    for r in c.exec_driver_sql(f"""
        SELECT * FROM public.product_goods_historical_sales_2025
        WHERE starts_with(product_code, '{CODE}') OR original_sku='{CODE}'
        ORDER BY sales_date DESC LIMIT 6""").mappings().fetchall():
        p("   ", json.dumps(dict(r), ensure_ascii=False, default=str))

    p("\n" + "="*100); p("### jst_daily_sales 列定义"); p("="*100)
    for r in c.exec_driver_sql("""
        SELECT a.attname, format_type(a.atttypid,a.atttypmod)
        FROM pg_attribute a JOIN pg_class cl ON cl.oid=a.attrelid
        JOIN pg_namespace n ON n.oid=cl.relnamespace
        WHERE n.nspname='public' AND cl.relname='jst_daily_sales'
          AND a.attnum>0 AND NOT a.attisdropped ORDER BY a.attnum""").fetchall():
        p(f"    {r[0]:<30} {r[1]}")

open(OUT, "w", encoding="utf-8").write("\n".join(buf))
print("written", OUT, len(buf), "lines")
