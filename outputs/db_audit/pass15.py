"""Pass 15: closing the remaining completeness loops."""
from __future__ import annotations

import sys
from pathlib import Path

import psycopg
from psycopg.rows import dict_row

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from audit import database_url  # noqa: E402

OUT = HERE / "completeness4.txt"
OUT.write_text("", encoding="utf-8")


def p(s: str = "") -> None:
    with open(OUT, "a", encoding="utf-8") as fh:
        fh.write(s + "\n")


def q(conn, sql, params=None, fetch="all"):
    with conn.cursor(row_factory=dict_row) as cur:
        if params:
            cur.execute(sql, params)
        else:
            cur.execute(sql)
        return cur.fetchone() if fetch == "one" else cur.fetchall()


with psycopg.connect(database_url(), autocommit=True) as conn:
    with conn.cursor() as cur:
        cur.execute("SET statement_timeout = '600s'")

    p("=" * 78)
    p("A. jst_daily_stock: stock_date 是 'MM.DD' 文本(无年份), 真实日期在 stock_date_value")
    p("=" * 78)
    r = q(conn, """
        SELECT count(DISTINCT stock_date) AS d_text, count(DISTINCT stock_date_value) AS d_date,
               min(stock_date_value) AS lo, max(stock_date_value) AS hi
        FROM public.jst_daily_stock
    """, fetch="one")
    p(f"  distinct(stock_date)={r['d_text']}  distinct(stock_date_value)={r['d_date']}  "
      f"真实范围={r['lo']} ~ {r['hi']}")
    p(f"  → 说明文本列把不同年份的同一天合并了" if r["d_date"] > r["d_text"] else "  → 未跨年")
    r = q(conn, """
        SELECT stock_date, count(DISTINCT stock_date_value) AS years FROM public.jst_daily_stock
        GROUP BY 1 HAVING count(DISTINCT stock_date_value) > 1 ORDER BY 2 DESC LIMIT 5
    """)
    for x in r:
        p(f"      stock_date='{x['stock_date']}' 对应 {x['years']} 个真实日期")
    r = q(conn, """
        SELECT count(*) AS missing FROM (
          SELECT d::date FROM generate_series(
            (SELECT min(stock_date_value) FROM public.jst_daily_stock),
            (SELECT max(stock_date_value) FROM public.jst_daily_stock),
            interval '1 day') d
          WHERE d::date NOT IN (SELECT DISTINCT stock_date_value FROM public.jst_daily_stock)
        ) x
    """, fetch="one")
    p(f"  真实范围内缺失天数 = {r['missing']}")
    r = q(conn, """
        SELECT d::date AS gap FROM generate_series(
          (SELECT min(stock_date_value) FROM public.jst_daily_stock),
          (SELECT max(stock_date_value) FROM public.jst_daily_stock),
          interval '1 day') d
        WHERE d::date NOT IN (SELECT DISTINCT stock_date_value FROM public.jst_daily_stock)
        ORDER BY 1 LIMIT 30
    """)
    if r:
        p("  缺失日期: " + ", ".join(str(x["gap"]) for x in r))
    p()

    p("=" * 78)
    p("B. jst_monthly_orders_2026: record_key 自 2026-07 起完全不再写入 (数据回归)")
    p("=" * 78)
    r = q(conn, """
        SELECT count(*) AS groups, COALESCE(sum(c - 1), 0) AS extra_rows FROM (
          SELECT internal_order_id, product_code, order_time_at, count(*) AS c
          FROM public.jst_monthly_orders_2026
          WHERE record_key IS NULL
          GROUP BY 1,2,3 HAVING count(*) > 1
        ) x
    """, fetch="one")
    p(f"  NULL record_key 中按(内部订单号,商品编码,下单时间)重复: 组={r['groups']} "
      f"多余行={r['extra_rows']}")
    p("  这些疑似重复行的样例:")
    r = q(conn, """
        SELECT internal_order_id, product_code, order_time_at, quantity, payable_amount, count(*) AS c
        FROM public.jst_monthly_orders_2026
        WHERE record_key IS NULL
        GROUP BY 1,2,3,4,5 HAVING count(*) > 1
        ORDER BY 1 LIMIT 8
    """)
    for x in r:
        p(f"      {x['internal_order_id']} {x['product_code']} {x['order_time_at']} "
          f"数量={x['quantity']} × {x['c']}")
    p()

    p("=" * 78)
    p("C. 进销存 total_count 不符: 剔除 quantity 为 NULL 造成的假不符")
    p("=" * 78)
    r = q(conn, """
        SELECT count(*) AS strict_mismatch FROM (
          SELECT r.id, r.total_count, COALESCE(SUM(d.quantity),0) AS s
          FROM public.inventory_records r
          JOIN public.inventory_details d ON d.document_id = r.id
          WHERE r.deleted_at IS NULL
          GROUP BY r.id, r.total_count
          HAVING count(*) FILTER (WHERE d.quantity IS NULL) = 0
             AND r.total_count IS DISTINCT FROM COALESCE(SUM(d.quantity),0)
        ) x
    """, fetch="one")
    p(f"  全部明细都有数量、且合计仍不符的单据 = {r['strict_mismatch']:,}")
    r = q(conn, """
        SELECT count(*) AS n FROM public.inventory_records
        WHERE deleted_at IS NULL AND date IS NULL
    """, fetch="one")
    p(f"  未删除单据中 date 为空 = {r['n']:,}")
    r = q(conn, """
        SELECT count(*) AS n FROM public.inventory_records
        WHERE deleted_at IS NULL AND (document_number IS NULL OR btrim(document_number) = '')
    """, fetch="one")
    p(f"  未删除单据中单据编号为空 = {r['n']:,}")
    r = q(conn, """
        SELECT count(*) AS n FROM public.inventory_records
        WHERE deleted_at IS NULL AND (supplier IS NULL OR btrim(supplier) = '')
    """, fetch="one")
    p(f"  未删除单据中供应商为空 = {r['n']:,}")
    p()

    p("=" * 78)
    p("D. vip_product_daily_snapshots 的整月空洞")
    p("=" * 78)
    r = q(conn, """
        SELECT to_char(d, 'YYYY-MM') AS mon,
               (SELECT count(DISTINCT snapshot_date) FROM public.vip_product_daily_snapshots v
                 WHERE date_trunc('month', v.snapshot_date) = d) AS days
        FROM generate_series('2025-06-01'::date, '2026-10-01'::date, interval '1 month') d
        ORDER BY 1
    """)
    for x in r:
        mark = "   <-- 整整一个月没有数据" if x["days"] == 0 else ""
        p(f"      {x['mon']}  有数据 {x['days']:>2} 天{mark}")
    p()

    p("=" * 78)
    p("E. 各年度快照表的日期覆盖")
    p("=" * 78)
    for t in ("fine_table_snapshot_refs_2024", "fine_table_snapshot_refs_2025",
              "fine_table_snapshot_refs_2026",
              "product_goods_detail_snapshots_2024", "product_goods_detail_snapshots_2025",
              "product_goods_detail_snapshots_2026"):
        r = q(conn, f"""
            SELECT min(snapshot_date) AS lo, max(snapshot_date) AS hi,
                   count(DISTINCT snapshot_date) AS days, count(*) AS rows
            FROM public.{t}
        """, fetch="one")
        if r["lo"] is None:
            p(f"  {t:<42} 无数据")
            continue
        span = (r["hi"] - r["lo"]).days + 1
        p(f"  {t:<42} {r['lo']} ~ {r['hi']} 跨度={span:>4}天 有数据={r['days']:>4}天 "
          f"缺={span - r['days']:>4} 行数={r['rows']:,}")
    p()

    p("=" * 78)
    p("F. 商品身份表覆盖率")
    p("=" * 78)
    archives = ("cbanner_mens_products", "cbanner_womens_products", "yandou_products",
                "eblan_products", "smiley_products", "ni_products",
                "manual_product_archive_31")
    union = " UNION ".join(f"SELECT sku FROM public.{t} WHERE sku IS NOT NULL" for t in archives)
    r = q(conn, f"""
        SELECT count(*) AS n FROM ({union}) a
        WHERE NOT EXISTS (SELECT 1 FROM public.product_archive_identities i WHERE i.sku = a.sku)
    """, fetch="one")
    p(f"  档案 sku 未登记到 product_archive_identities 的 = {r['n']:,}")
    r = q(conn, """
        SELECT count(*) AS n FROM public.product_archive_identities i
        WHERE NOT EXISTS (
          SELECT 1 FROM public.cbanner_mens_products t WHERE t.sku = i.sku
          UNION ALL SELECT 1 FROM public.cbanner_womens_products t WHERE t.sku = i.sku
          UNION ALL SELECT 1 FROM public.yandou_products t WHERE t.sku = i.sku
          UNION ALL SELECT 1 FROM public.eblan_products t WHERE t.sku = i.sku
          UNION ALL SELECT 1 FROM public.smiley_products t WHERE t.sku = i.sku
          UNION ALL SELECT 1 FROM public.ni_products t WHERE t.sku = i.sku
          UNION ALL SELECT 1 FROM public.manual_product_archive_31 t WHERE t.sku = i.sku
        )
    """, fetch="one")
    p(f"  身份表中已无对应档案行的 '孤儿身份' = {r['n']:,}")
    p()

    p("=" * 78)
    p("G. 1,390 条未关联身份的明细: 集中在什么时间")
    p("=" * 78)
    r = q(conn, """
        SELECT to_char(date_trunc('month', COALESCE(r.date_value, r.created_at::date)), 'YYYY-MM') AS mon,
               count(*) AS rows
        FROM public.inventory_details d
        JOIN public.inventory_records r ON r.id = d.document_id
        WHERE d.product_identity_id IS NULL
        GROUP BY 1 ORDER BY 1 DESC LIMIT 12
    """)
    for x in r:
        p(f"      {x['mon']}  {x['rows']:>6,} 行")
    r = q(conn, """
        SELECT d.product_code, count(*) AS n
        FROM public.inventory_details d
        WHERE d.product_identity_id IS NULL AND d.product_code IS NOT NULL
        GROUP BY 1 ORDER BY 2 DESC LIMIT 8
    """)
    p("  高频商品编码: " + ", ".join(f"{x['product_code']}({x['n']})" for x in r))
    p()

    p("=" * 78)
    p("H. suppliers 联系信息缺失")
    p("=" * 78)
    r = q(conn, """
        SELECT count(*) AS total,
               count(*) FILTER (WHERE contact IS NULL OR btrim(contact)='') AS no_contact,
               count(*) FILTER (WHERE factory_code IS NULL OR btrim(factory_code)='') AS no_code,
               count(*) FILTER (WHERE factory_grade IS NULL OR btrim(factory_grade)='') AS no_grade
        FROM public.suppliers
    """, fetch="one")
    p(f"  供应商={r['total']:,} 无联系人={r['no_contact']:,} 无工厂编码={r['no_code']:,} "
      f"无工厂等级={r['no_grade']:,}")
    p("  (wechat / address / notes / cooperation_status 四列 100% 为空)")
    p()

print("[done]")