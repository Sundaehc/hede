"""Pass 18: two loose ends — size-group mapping key semantics, and the blank detail rows."""
from __future__ import annotations

import sys
from pathlib import Path

import psycopg
from psycopg.rows import dict_row

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from audit import database_url  # noqa: E402

OUT = HERE / "completeness7.txt"
OUT.write_text("", encoding="utf-8")


def p(s: str = "") -> None:
    with open(OUT, "a", encoding="utf-8") as fh:
        fh.write(s + "\n")


ARCH = ("cbanner_mens_products", "cbanner_womens_products", "yandou_products",
        "eblan_products", "smiley_products", "ni_products", "manual_product_archive_31")
UNION = " UNION ".join(f"SELECT sku AS s FROM public.{t} WHERE sku IS NOT NULL "
                       f"UNION ALL SELECT original_sku FROM public.{t} WHERE original_sku IS NOT NULL"
                       for t in ARCH)

with psycopg.connect(database_url(), autocommit=True) as conn:
    with conn.cursor() as cur:
        cur.execute("SET statement_timeout = '300s'")

    p("=" * 78)
    p("A. product_size_group_mappings 未匹配上的 3,690 个编码长什么样")
    p("=" * 78)
    rows = []
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(f"""
            SELECT m.product_code, m.size_group_name
            FROM public.product_size_group_mappings m
            WHERE m.product_code IS NOT NULL
              AND NOT EXISTS (SELECT 1 FROM ({UNION}) a WHERE a.s = m.product_code)
            LIMIT 12
        """)
        rows = cur.fetchall()
    for x in rows:
        p(f"      {x['product_code']:<26} 尺码组={x['size_group_name']}")
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute("""
            SELECT count(*) AS n FROM public.product_size_group_mappings m
            WHERE m.product_code IS NOT NULL
              AND NOT EXISTS (SELECT 1 FROM public.product_archive_identities i WHERE i.sku = m.product_code)
        """)
        p(f"  其中也不在 product_archive_identities 里的 = {cur.fetchone()['n']:,}")
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute("""
            SELECT length(product_code) AS len, count(*) AS n
            FROM public.product_size_group_mappings GROUP BY 1 ORDER BY 2 DESC LIMIT 6
        """)
        p("  编码长度分布: " + ", ".join(f"{x['len']}位={x['n']:,}" for x in cur.fetchall()))
    p()

    p("=" * 78)
    p("B. 359 行空白明细的归属单据")
    p("=" * 78)
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute("""
            SELECT count(DISTINCT d.document_id) AS docs, count(*) AS details
            FROM public.inventory_details d
            WHERE d.product_code IS NULL AND d.quantity IS NULL
        """)
        r = cur.fetchone()
        p(f"  product_code 与 quantity 同时为空的明细 = {r['details']:,} 行, 分布在 {r['docs']:,} 张单据")
        cur.execute("""
            SELECT COALESCE(r.document_type,'(空)') AS dtype, count(*) AS n
            FROM public.inventory_details d JOIN public.inventory_records r ON r.id = d.document_id
            WHERE d.product_code IS NULL AND d.quantity IS NULL
            GROUP BY 1 ORDER BY 2 DESC LIMIT 8
        """)
        p("  按凭证类型: " + ", ".join(f"{x['dtype']}={x['n']}" for x in cur.fetchall()))
        cur.execute("""
            SELECT count(*) AS n FROM public.inventory_details d
            WHERE d.product_code IS NULL AND d.quantity IS NULL AND d.amount IS NULL
              AND d.unit_price IS NULL AND d.color_spec IS NULL
        """)
        p(f"  其中连颜色/单价/金额也全空的 = {cur.fetchone()['n']:,}")
    p()

    p("=" * 78)
    p("C. 3,960 条挂在已软删除单据下的明细")
    p("=" * 78)
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute("""
            SELECT count(*) AS details, count(DISTINCT r.id) AS docs,
                   COALESCE(SUM(d.amount),0) AS amount
            FROM public.inventory_details d
            JOIN public.inventory_records r ON r.id = d.document_id
            WHERE r.deleted_at IS NOT NULL
        """)
        r = cur.fetchone()
        p(f"  明细={r['details']:,} 行 / 单据={r['docs']:,} 张 / 金额合计={r['amount']:,}")
        cur.execute("""
            SELECT min(r.deleted_at) AS first_del, max(r.deleted_at) AS last_del
            FROM public.inventory_records r WHERE r.deleted_at IS NOT NULL
        """)
        r = cur.fetchone()
        p(f"  软删除时间范围: {r['first_del']} ~ {r['last_del']}")
    p()

print("[done]")