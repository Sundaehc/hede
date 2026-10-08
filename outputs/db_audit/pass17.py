"""Pass 17: root-cause detail for the identity-link gap, and gap-by-weekday analysis."""
from __future__ import annotations

import sys
from pathlib import Path

import psycopg
from psycopg.rows import dict_row

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from audit import database_url  # noqa: E402

OUT = HERE / "completeness6.txt"
OUT.write_text("", encoding="utf-8")


def p(s: str = "") -> None:
    with open(OUT, "a", encoding="utf-8") as fh:
        fh.write(s + "\n")


def q(conn, sql, fetch="all"):
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(sql)
        return cur.fetchone() if fetch == "one" else cur.fetchall()


ARCH = ("cbanner_mens_products", "cbanner_womens_products", "yandou_products",
        "eblan_products", "smiley_products", "ni_products", "manual_product_archive_31")
UNION = " UNION ".join(f"SELECT sku AS s FROM public.{t} WHERE sku IS NOT NULL "
                       f"UNION ALL SELECT original_sku FROM public.{t} WHERE original_sku IS NOT NULL"
                       for t in ARCH)

with psycopg.connect(database_url(), autocommit=True) as conn:
    with conn.cursor() as cur:
        cur.execute("SET statement_timeout = '600s'")

    p("=" * 78)
    p("A. 1,390 条未关联身份的明细: 到底能不能匹配上")
    p("=" * 78)
    r = q(conn, f"""
        SELECT count(*) AS total,
               count(*) FILTER (WHERE d.product_code IS NULL) AS no_code,
               count(*) FILTER (WHERE d.product_code IS NOT NULL AND EXISTS (
                   SELECT 1 FROM ({UNION}) a WHERE a.s = d.product_code)) AS code_in_archive
        FROM public.inventory_details d WHERE d.product_identity_id IS NULL
    """, fetch="one")
    p(f"  总数={r['total']:,}  无编码={r['no_code']:,}  编码在档案中(本应能匹配)={r['code_in_archive']:,}")
    p()

    p("=" * 78)
    p("B. 商品身份表: 同一 product_code 是否有多个身份(会导致触发器无法确定)")
    p("=" * 78)
    r = q(conn, """
        SELECT count(*) AS identities, count(DISTINCT sku) AS distinct_sku
        FROM public.product_archive_identities
    """, fetch="one")
    p(f"  身份数={r['identities']:,}  不同 sku={r['distinct_sku']:,}  "
      f"一码多身份={r['identities'] - r['distinct_sku']:,}")
    r = q(conn, """
        SELECT sku, count(*) AS n FROM public.product_archive_identities
        GROUP BY 1 HAVING count(*) > 1 ORDER BY 2 DESC LIMIT 10
    """)
    p("  一码多身份示例:")
    for x in r:
        p(f"      {x['sku']:<26} {x['n']} 个身份")
    cols = [x["column_name"] for x in q(conn, """
        SELECT column_name FROM information_schema.columns
        WHERE table_name = 'product_archive_identities' ORDER BY ordinal_position
    """)]
    p(f"  身份表列: {cols}")
    if "brand" in cols:
        r = q(conn, """
            SELECT COALESCE(brand,'(空)') AS brand, count(*) AS n
            FROM public.product_archive_identities GROUP BY 1 ORDER BY 2 DESC
        """)
        p("  按品牌: " + ", ".join(f"{x['brand']}={x['n']:,}" for x in r))
    p()

    p("=" * 78)
    p("C. jst_daily_stock 缺失的 49 天是否集中在周末(判断是'按工作日采集'还是真断档)")
    p("=" * 78)
    r = q(conn, """
        WITH gaps AS (
          SELECT d::date AS gap FROM generate_series(
            (SELECT min(stock_date_value) FROM public.jst_daily_stock),
            (SELECT max(stock_date_value) FROM public.jst_daily_stock),
            interval '1 day') d
          WHERE d::date NOT IN (SELECT DISTINCT stock_date_value FROM public.jst_daily_stock)
        )
        SELECT to_char(gap,'Dy') AS dow, count(*) AS n FROM gaps GROUP BY 1 ORDER BY 2 DESC
    """)
    p("  缺失日按星期: " + ", ".join(f"{x['dow']}={x['n']}" for x in r))
    r = q(conn, """
        WITH have AS (SELECT DISTINCT stock_date_value AS d FROM public.jst_daily_stock)
        SELECT to_char(d,'Dy') AS dow, count(*) AS n FROM have GROUP BY 1 ORDER BY 2 DESC
    """)
    p("  有数据日按星期: " + ", ".join(f"{x['dow']}={x['n']}" for x in r))
    r = q(conn, """
        SELECT stock_date_value, count(*) AS rows FROM public.jst_daily_stock
        GROUP BY 1 ORDER BY 1 DESC LIMIT 3
    """)
    p("  最新三天: " + ", ".join(f"{x['stock_date_value']}({x['rows']:,})" for x in r))
    r = q(conn, """
        SELECT stock_date_value, count(*) AS rows FROM public.jst_daily_stock
        GROUP BY 1 ORDER BY 1 LIMIT 3
    """)
    p("  最旧三天: " + ", ".join(f"{x['stock_date_value']}({x['rows']:,})" for x in r))
    p()

    p("=" * 78)
    p("D. 快照表的缺失日是否集中在春节/假期")
    p("=" * 78)
    for t in ("product_goods_detail_snapshots_2025", "product_goods_detail_snapshots_2026",
              "fine_table_snapshot_refs_2026", "product_goods_detail_snapshots_2024"):
        r = q(conn, f"""
            WITH gaps AS (
              SELECT d::date AS gap FROM generate_series(
                (SELECT min(snapshot_date) FROM public.{t}),
                (SELECT max(snapshot_date) FROM public.{t}),
                interval '1 day') d
              WHERE d::date NOT IN (SELECT DISTINCT snapshot_date FROM public.{t})
            )
            SELECT count(*) AS n FROM gaps
        """, fetch="one")
        p(f"  {t:<42} 缺 {r['n']:>3} 天")
        if r["n"]:
            rows = q(conn, f"""
                WITH gaps AS (
                  SELECT d::date AS gap FROM generate_series(
                    (SELECT min(snapshot_date) FROM public.{t}),
                    (SELECT max(snapshot_date) FROM public.{t}),
                    interval '1 day') d
                  WHERE d::date NOT IN (SELECT DISTINCT snapshot_date FROM public.{t})
                )
                SELECT string_agg(gap::text, ', ' ORDER BY gap) AS list FROM gaps
            """, fetch="one")
            p(f"      {rows['list']}")
    p()

print("[done]")