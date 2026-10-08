"""Pass 14: follow-ups on the completeness findings."""
from __future__ import annotations

import sys
from pathlib import Path

import psycopg
from psycopg.rows import dict_row

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from audit import database_url  # noqa: E402

OUT = HERE / "completeness3.txt"
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
        if fetch == "one":
            return cur.fetchone()
        return cur.fetchall()


with psycopg.connect(database_url(), autocommit=True) as conn:
    with conn.cursor() as cur:
        cur.execute("SET statement_timeout = '600s'")

    p("=" * 78)
    p("A. jst_daily_stock 的日期列类型与断档")
    p("=" * 78)
    r = q(conn, """
        SELECT column_name, data_type FROM information_schema.columns
        WHERE table_name = 'jst_daily_stock' AND column_name LIKE '%date%'
        ORDER BY column_name
    """)
    for x in r:
        p(f"  {x['column_name']:<24} {x['data_type']}")
    r = q(conn, """
        SELECT count(*) AS rows,
               count(*) FILTER (WHERE stock_date !~ '^[0-9]{4}-[0-9]{2}-[0-9]{2}$') AS bad_format,
               min(stock_date) AS lo, max(stock_date) AS hi,
               count(DISTINCT stock_date) AS days
        FROM public.jst_daily_stock
    """, fetch="one")
    p(f"  行数={r['rows']:,} 非日期格式={r['bad_format']:,} 范围={r['lo']} ~ {r['hi']} "
      f"不同天数={r['days']:,}")
    if r["bad_format"] == 0:
        r2 = q(conn, """
            SELECT count(*) AS missing FROM (
              SELECT d::date FROM generate_series(
                (SELECT min(stock_date)::date FROM public.jst_daily_stock),
                (SELECT max(stock_date)::date FROM public.jst_daily_stock),
                interval '1 day') d
              WHERE d::date NOT IN (SELECT DISTINCT stock_date::date FROM public.jst_daily_stock)
            ) x
        """, fetch="one")
        p(f"  区间内缺失天数 = {r2['missing']}")
    r = q(conn, """
        SELECT stock_date, count(*) AS rows FROM public.jst_daily_stock
        GROUP BY 1 ORDER BY 1 DESC LIMIT 8
    """)
    p("  最近 8 个日期: " + ", ".join(f"{x['stock_date']}({x['rows']:,})" for x in r))
    p()

    p("=" * 78)
    p("B. vip_product_daily_snapshots 采集规律 (跨度 487 天只有 144 天有数据)")
    p("=" * 78)
    r = q(conn, """
        SELECT to_char(snapshot_date, 'Dy') AS dow, count(*) AS days, sum(rows) AS rows
        FROM (SELECT snapshot_date, count(*) AS rows FROM public.vip_product_daily_snapshots
              GROUP BY 1) t
        GROUP BY 1 ORDER BY 2 DESC
    """)
    p("  按星期分布: " + ", ".join(f"{x['dow']}={x['days']}天" for x in r))
    r = q(conn, """
        SELECT date_trunc('month', snapshot_date)::date AS mon, count(DISTINCT snapshot_date) AS days,
               count(*) AS rows
        FROM public.vip_product_daily_snapshots GROUP BY 1 ORDER BY 1 DESC LIMIT 14
    """)
    p("  按月: ")
    for x in r:
        p(f"      {x['mon']}  有数据 {x['days']:>3} 天   {x['rows']:>10,} 行")
    r = q(conn, """
        SELECT max(snapshot_date) AS last FROM public.vip_product_daily_snapshots
    """, fetch="one")
    p(f"  最后一天 = {r['last']}")
    p()

    p("=" * 78)
    p("C. jst_monthly_orders record_key 为 NULL 的 81 万行会破坏去重")
    p("=" * 78)
    r = q(conn, """
        SELECT count(*) AS dup_groups, COALESCE(sum(n - 1), 0) AS extra_rows FROM (
          SELECT order_time_at, record_key, count(*) AS n
          FROM public.jst_monthly_orders_2026
          WHERE record_key IS NOT NULL
          GROUP BY 1,2 HAVING count(*) > 1
        ) x
    """, fetch="one")
    p(f"  非 NULL record_key 的重复组={r['dup_groups']:,} 多余行={r['extra_rows']:,}")
    r = q(conn, """
        SELECT count(*) AS rows, count(DISTINCT order_time_at) AS distinct_time,
               count(*) - count(DISTINCT order_time_at) AS same_time
        FROM public.jst_monthly_orders_2026 WHERE record_key IS NULL
    """, fetch="one")
    p(f"  NULL record_key: 行数={r['rows']:,} 不同下单时间={r['distinct_time']:,} "
      f"同一时间多行={r['same_time']:,}")
    r = q(conn, """
        SELECT count(*) AS n FROM (
          SELECT internal_order_id, product_code, order_time_at, count(*) AS c
          FROM public.jst_monthly_orders_2026
          WHERE record_key IS NULL
          GROUP BY 1,2,3 HAVING count(*) > 1
        ) x
    """, fetch="one")
    p(f"  NULL record_key 中 按(内部订单号,商品编码,下单时间)重复的组 = {r['n']:,}")
    r = q(conn, """
        SELECT date_trunc('month', order_time_at)::date AS mon, count(*) AS rows,
               count(*) FILTER (WHERE record_key IS NULL) AS null_key
        FROM public.jst_monthly_orders_2026 GROUP BY 1 ORDER BY 1
    """)
    p("  按月 record_key 缺失: ")
    for x in r:
        p(f"      {x['mon']}  行数={x['rows']:>9,}  NULL={x['null_key']:>9,}")
    p()

    p("=" * 78)
    p("D. 关键列是否近期才开始缺失 (判断是回归还是一直如此)")
    p("=" * 78)
    r = q(conn, """
        SELECT date_trunc('month', snapshot_date)::date AS mon, count(*) AS rows,
               count(*) FILTER (WHERE goods_tag IS NULL OR btrim(goods_tag) = '') AS tag_missing
        FROM public.vip_product_ops_snapshots GROUP BY 1 ORDER BY 1
    """)
    p("  vip_product_ops_snapshots.goods_tag (小灯塔标签) 按月:")
    for x in r:
        pct = x["tag_missing"] / max(x["rows"], 1) * 100
        p(f"      {x['mon']}  行数={x['rows']:>9,}  缺失={x['tag_missing']:>9,} ({pct:5.1f}%)")
    r = q(conn, """
        SELECT date_trunc('month', sales_date)::date AS mon, count(*) AS rows,
               count(*) FILTER (WHERE product_type IS NULL) AS pt_null
        FROM public.vip_daily_sales_2026 GROUP BY 1 ORDER BY 1 LIMIT 6
    """)
    p("  vip_daily_sales_2026.product_type 按月 (前 6 个月):")
    for x in r:
        p(f"      {x['mon']}  行数={x['rows']:>9,}  NULL={x['pt_null']:>9,}")
    p()

    p("=" * 78)
    p("E. jst_product_price 价格字段的填充情况")
    p("=" * 78)
    r = q(conn, """
        SELECT count(*) AS rows,
               count(retail_price) AS retail, count(cost_unit_price) AS cost_unit,
               count(latest_purchase_price) AS latest_purchase, count(member_price) AS member
        FROM public.jst_product_price
    """, fetch="one")
    p(f"  总行数={r['rows']:,}  零售价={r['retail']:,}  成本单价={r['cost_unit']:,} "
      f"最近进价={r['latest_purchase']:,}  会员价={r['member']:,}")
    cols = [x["column_name"] for x in q(conn, """
        SELECT column_name FROM information_schema.columns
        WHERE table_name='jst_product_price' AND column_name LIKE '%date%' ORDER BY 1
    """)]
    p(f"  日期类列: {cols}")
    if cols:
        c = cols[0]
        r = q(conn, f"""
            SELECT date_trunc('month', "{c}"::timestamp)::date AS mon, count(*) AS rows,
                   count(retail_price) AS retail, count(cost_unit_price) AS cost_unit,
                   count(latest_purchase_price) AS latest
            FROM public.jst_product_price GROUP BY 1 ORDER BY 1 DESC LIMIT 12
        """)
        p(f"  按月 (依据 {c}):")
        for x in r:
            p(f"      {x['mon']}  行数={x['rows']:>9,}  零售价={x['retail']:>9,}  "
              f"成本单价={x['cost_unit']:>9,}  最近进价={x['latest']:>9,}")
    p()

    p("=" * 78)
    p("F. jst_aftersale_returns 分区键三列是否可能全空 (会导致落进 DEFAULT 分区)")
    p("=" * 78)
    for t in ("jst_aftersale_returns_2024", "jst_aftersale_returns_2025",
              "jst_aftersale_returns_2026", "jst_aftersale_returns_default"):
        r = q(conn, f"""
            SELECT count(*) AS rows,
                   count(*) FILTER (WHERE application_date_value IS NULL) AS app_null,
                   count(*) FILTER (WHERE order_date_value IS NULL) AS order_null,
                   count(*) FILTER (WHERE order_time_value IS NULL) AS time_null,
                   count(*) FILTER (WHERE application_date_value IS NULL
                                      AND order_date_value IS NULL
                                      AND order_time_value IS NULL) AS all_null
            FROM public.{t}
        """, fetch="one")
        p(f"  {t:<34} 行数={r['rows']:>8,} 申请日空={r['app_null']:>8,} "
          f"下单日空={r['order_null']:>8,} 下单时间空={r['time_null']:>8,} 三列全空={r['all_null']:>6,}")
    p()

    p("=" * 78)
    p("G. 进销存 1,202 条 total_count 不符的单据分布")
    p("=" * 78)
    r = q(conn, """
        SELECT COALESCE(document_type,'(空)') AS dtype, count(*) AS docs,
               count(*) FILTER (WHERE total_count IS NULL) AS total_null
        FROM public.inventory_records WHERE deleted_at IS NULL
        GROUP BY 1 ORDER BY 2 DESC LIMIT 12
    """)
    p("  未删除单据按凭证类型: " + ", ".join(f"{x['dtype']}={x['docs']}" for x in r))
    r = q(conn, """
        SELECT count(*) AS n FROM (
          SELECT r.id FROM public.inventory_records r
          LEFT JOIN public.inventory_details d ON d.document_id = r.id
          WHERE r.deleted_at IS NULL
          GROUP BY r.id, r.total_count
          HAVING r.total_count IS DISTINCT FROM COALESCE(SUM(d.quantity),0)
        ) x
    """, fetch="one")
    p(f"  未删除且 total_count 不符 = {r['n']:,}")
    r = q(conn, """
        SELECT count(*) AS n FROM public.inventory_records r
        WHERE r.deleted_at IS NULL AND r.total_count IS NULL
          AND EXISTS (SELECT 1 FROM public.inventory_details d
                      WHERE d.document_id = r.id AND d.quantity IS NOT NULL)
    """, fetch="one")
    p(f"  其中 total_count 为空但明细有数量的单据 = {r['n']:,}")
    r = q(conn, """
        SELECT count(*) AS n FROM public.inventory_records
        WHERE deleted_at IS NULL AND (date IS NULL OR total_count IS NULL)
    """, fetch="one")
    p(f"  未删除单据中 date 或 total_count 为空的 = {r['n']:,}")
    p()

    p("=" * 78)
    p("H. ni_products 到底是什么 (之前按陈旧统计误判为空表)")
    p("=" * 78)
    r = q(conn, "SELECT count(*) AS rows FROM public.ni_products", fetch="one")
    p(f"  实际行数 = {r['rows']:,}")
    r = q(conn, """
        SELECT source_workbook, source_sheet, count(*) AS rows
        FROM public.ni_products GROUP BY 1,2 ORDER BY 3 DESC LIMIT 10
    """)
    p("  来源: ")
    for x in r:
        p(f"      {(x['source_workbook'] or '')[:52]:<52} {(x['source_sheet'] or '')[:20]:<20} {x['rows']:>6,}")
    r = q(conn, "SELECT sku, product_name, cost FROM public.ni_products ORDER BY id LIMIT 5")
    p("  样例: " + "; ".join(f"{x['sku']}/{x['product_name']}" for x in r))
    p()

    p("=" * 78)
    p("I. 商品档案跨表重复 sku (例: 同一货号出现在两个品牌表)")
    p("=" * 78)
    r = q(conn, """
        WITH allskus AS (
          SELECT 'cbanner_mens' AS brand, sku FROM public.cbanner_mens_products WHERE sku IS NOT NULL
          UNION ALL SELECT 'cbanner_womens', sku FROM public.cbanner_womens_products WHERE sku IS NOT NULL
          UNION ALL SELECT 'yandou', sku FROM public.yandou_products WHERE sku IS NOT NULL
          UNION ALL SELECT 'eblan', sku FROM public.eblan_products WHERE sku IS NOT NULL
          UNION ALL SELECT 'smiley', sku FROM public.smiley_products WHERE sku IS NOT NULL
          UNION ALL SELECT 'ni', sku FROM public.ni_products WHERE sku IS NOT NULL
          UNION ALL SELECT 'manual31', sku FROM public.manual_product_archive_31 WHERE sku IS NOT NULL
        )
        SELECT count(*) AS total, count(DISTINCT sku) AS distinct_sku FROM allskus
    """, fetch="one")
    p(f"  档案 sku 总条目={r['total']:,} 去重后={r['distinct_sku']:,} "
      f"跨表重复={r['total'] - r['distinct_sku']:,}")
    r = q(conn, """
        WITH allskus AS (
          SELECT 'cbanner_mens' AS brand, sku FROM public.cbanner_mens_products WHERE sku IS NOT NULL
          UNION ALL SELECT 'cbanner_womens', sku FROM public.cbanner_womens_products WHERE sku IS NOT NULL
          UNION ALL SELECT 'yandou', sku FROM public.yandou_products WHERE sku IS NOT NULL
          UNION ALL SELECT 'eblan', sku FROM public.eblan_products WHERE sku IS NOT NULL
          UNION ALL SELECT 'smiley', sku FROM public.smiley_products WHERE sku IS NOT NULL
          UNION ALL SELECT 'ni', sku FROM public.ni_products WHERE sku IS NOT NULL
          UNION ALL SELECT 'manual31', sku FROM public.manual_product_archive_31 WHERE sku IS NOT NULL
        )
        SELECT sku, string_agg(DISTINCT brand, '+') AS brands, count(*) AS n
        FROM allskus GROUP BY 1 HAVING count(*) > 1 ORDER BY 3 DESC LIMIT 15
    """)
    p(f"  重复 sku 示例 ({len(r)} 条):")
    for x in r:
        p(f"      {x['sku']:<24} 出现在 {x['brands']}")
    p()

    p("=" * 78)
    p("J. 档案中 last_imported_at 缺失 (决定哪些档案从未被增量更新过)")
    p("=" * 78)
    for t in ("cbanner_mens_products", "cbanner_womens_products", "yandou_products",
              "eblan_products", "smiley_products", "ni_products"):
        r = q(conn, f"""
            SELECT count(*) AS rows,
                   count(*) FILTER (WHERE last_imported_at IS NULL) AS no_ts,
                   max(last_imported_at) AS last
            FROM public.{t}
        """, fetch="one")
        p(f"  {t:<28} 行数={r['rows']:>7,}  无时间戳={r['no_ts']:>7,}  最近={r['last']}")
    p()

print("[done]")