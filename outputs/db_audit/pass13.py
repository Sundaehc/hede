"""Pass 13: exact data-completeness measurements.

A. per-column missing data for the app's core tables (NULL and empty string, separately)
B. inventory reconciliation: header totals vs detail sums, orphan documents, soft-deleted leaks
C. targeted missing-value counts for the large analytics tables (suspicious 100% NULL columns)
D. date-series coverage gaps (missing days) for daily snapshot tables
E. cross-references between archives and inventory / size groups / tags
"""
from __future__ import annotations

import sys
from pathlib import Path

import psycopg
from psycopg.rows import dict_row

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from audit import database_url  # noqa: E402

OUT = HERE / "completeness2.txt"
OUT.write_text("", encoding="utf-8")


def p(s: str = "") -> None:
    with open(OUT, "a", encoding="utf-8") as fh:
        fh.write(s + "\n")


# ---- load column metadata dumped by pass12 ----
COLS: dict[str, list[tuple[str, str, bool]]] = {}
for line in (HERE / "columns.txt").read_text(encoding="utf-8").splitlines():
    tbl, _num, col, typ, nullflag, _est = line.split("\t")
    COLS.setdefault(tbl, []).append((col, typ, nullflag == "NOT NULL"))

TEXT_TYPES = ("text", "character varying", "character")

ARCHIVES = [
    "cbanner_mens_products", "cbanner_womens_products", "yandou_products",
    "eblan_products", "smiley_products", "ni_products", "manual_product_archive_31",
]
CORE = ["inventory_records", "inventory_details", "suppliers", "warehouses"]

# columns worth checking on the big analytics tables
BIG = {
    "jst_product_price": ["member_price", "preset_commission", "preset_discount",
                          "preset_commission_name", "retail_price", "cost_unit_price",
                          "latest_purchase_price", "extra_fields", "product_code"],
    "jst_monthly_orders_2026": ["cost_price", "category", "registered_qty", "actual_return_qty",
                                "address", "shop_style_code", "record_key", "ship_date_value",
                                "online_sub_order_id", "product_code", "style_code", "order_time_at"],
    "vip_daily_sales_2026": ["product_type", "goods_code", "sales_quantity", "sales_date"],
    "vip_product_ops_snapshots": ["extra_fields", "goods_tag", "goods_code", "snapshot_date"],
    "jst_daily_sales_2026": ["supplier_style_code", "net_sales_amount", "cost_amount",
                             "gross_profit", "return_quantity", "product_code", "sales_date"],
    "gj_merged_product_info": ["disabled_flag", "shoe_box_spec", "row_no", "insole_material",
                               "goods_code", "source_date_value"],
    "jst_daily_stock": ["product_code", "stock_date", "available_qty"],
    "dewu_orders_2026": ["full_payment_amount", "intent_deposit_amount", "buyer_remark",
                         "delivery_party", "order_number", "goods_code"],
    "jst_full_stock": ["safety_stock_max_qty", "safety_stock_min_qty", "main_warehouse_location",
                       "product_code"],
    "vip_product_detail_daily": ["shop_code", "shop_name", "member_benefit_cost", "goods_code"],
    "product_tag_assignments": ["style_id", "valid_from", "valid_to", "created_by", "tag_id"],
    "jst_aftersale_returns_2026": ["platform_site", "order_time", "order_time_value",
                                   "extra_fields", "original_goods_code", "order_date_value"],
    "product_goods_historical_sales_2025": ["color", "style_code", "sales_quantity"],
    "jst_product_profiles": ["extra_fields", "product_code"],
    "fine_table_snapshot_refs_2026": ["sku", "original_sku", "snapshot_date", "batch_id"],
    "product_goods_detail_snapshots_2026": ["style_code", "goods_code", "snapshot_date"],
}


def col_type(tbl: str, col: str) -> str | None:
    for c, t, _ in COLS.get(tbl, []):
        if c == col:
            return t
    return None


def missing_matrix(conn, tables: list[str], only_suspicious: bool,
                   cols_override: dict[str, list[str]] | None = None) -> None:
    for tbl in tables:
        if cols_override and tbl in cols_override:
            wanted = set(cols_override[tbl])
            cols = [c for c, _t, _n in COLS.get(tbl, []) if c in wanted]
            unknown = wanted - {c for c, _t, _n in COLS.get(tbl, [])}
            if unknown:
                p(f"  !! {tbl}: 这些列不存在, 已忽略: {sorted(unknown)}")
        else:
            cols = [c for c, _t, _n in COLS.get(tbl, [])]
        if not cols:
            p(f"  !! no metadata for {tbl}")
            continue
        exprs = ["count(*) AS total"]
        for c in cols:
            exprs.append(f'count(*) FILTER (WHERE "{c}" IS NULL) AS "n_{c}"')
        sql = f'SELECT {", ".join(exprs)} FROM public."{tbl}"'
        try:
            with conn.cursor(row_factory=dict_row) as cur:
                cur.execute(sql)
                row = cur.fetchone()
        except Exception as exc:  # noqa: BLE001
            conn.rollback()
            p(f"  !! {tbl}: {type(exc).__name__}: {exc}")
            continue
        total = row["total"]
        # empty-string check only for text columns
        empties: dict[str, int] = {}
        text_cols = [c for c in cols if col_type(tbl, c) in TEXT_TYPES]
        if text_cols:
            eexprs = [f'count(*) FILTER (WHERE btrim("{c}") = \'\') AS "e_{c}"' for c in text_cols]
            try:
                with conn.cursor(row_factory=dict_row) as cur:
                    cur.execute(f'SELECT {", ".join(eexprs)} FROM public."{tbl}"')
                    erow = cur.fetchone()
                empties = {c: erow[f"e_{c}"] for c in text_cols}
            except Exception:  # noqa: BLE001
                conn.rollback()
        p(f"  {tbl}  (总行数 {total:,})")
        findings = []
        for c in cols:
            n = row[f"n_{c}"]
            e = empties.get(c, 0)
            missing = n + e
            if missing == 0:
                continue
            if only_suspicious and missing / max(total, 1) < 0.01:
                continue
            detail = f"NULL={n:,}" + (f" 空串={e:,}" if e else "")
            findings.append((missing / max(total, 1), c, detail))
        if not findings:
            p("      无缺失")
        for ratio, c, detail in sorted(findings, reverse=True):
            p(f"      {ratio*100:6.2f}%  {c:<30} {detail}")
        p()


with psycopg.connect(database_url(), autocommit=True) as conn:
    with conn.cursor() as cur:
        cur.execute("SET statement_timeout = '600s'")

    p("=" * 78)
    p("A. 核心业务表: 逐列缺失 (NULL 与空字符串分开统计)")
    p("   商品档案表 —— 应用真正读取的字段")
    p("=" * 78)
    p()
    missing_matrix(conn, ARCHIVES, only_suspicious=False)

    p("=" * 78)
    p("A2. 进销存表 (inventory_records / inventory_details / suppliers / warehouses)")
    p("=" * 78)
    p()
    missing_matrix(conn, CORE, only_suspicious=False)

    p("=" * 78)
    p("B. 进销存勾稽与一致性")
    p("=" * 78)
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute("""
            SELECT count(*) AS documents,
                   count(*) FILTER (WHERE deleted_at IS NOT NULL) AS soft_deleted
            FROM public.inventory_records
        """)
        r = cur.fetchone()
        p(f"  单据总数={r['documents']:,}  已软删除={r['soft_deleted']:,}")

        cur.execute("""
            SELECT count(*) AS no_details
            FROM public.inventory_records r
            WHERE NOT EXISTS (SELECT 1 FROM public.inventory_details d WHERE d.document_id = r.id)
        """)
        p(f"  没有任何明细行的单据数量 = {cur.fetchone()['no_details']:,}")

        cur.execute("""
            SELECT count(*) AS n
            FROM public.inventory_records r
            WHERE r.deleted_at IS NULL
              AND NOT EXISTS (SELECT 1 FROM public.inventory_details d WHERE d.document_id = r.id)
        """)
        p(f"    其中未软删除的 '空单据' = {cur.fetchone()['n']:,}")

        cur.execute("""
            SELECT count(*) AS n
            FROM public.inventory_details d
            JOIN public.inventory_records r ON r.id = d.document_id
            WHERE r.deleted_at IS NOT NULL
        """)
        p(f"  挂在已软删除单据下的明细行 = {cur.fetchone()['n']:,}")

        cur.execute("""
            SELECT count(*) AS mismatched_qty FROM (
              SELECT r.id, r.total_count, COALESCE(SUM(d.quantity),0) AS detail_qty
              FROM public.inventory_records r
              LEFT JOIN public.inventory_details d ON d.document_id = r.id
              WHERE r.deleted_at IS NULL
              GROUP BY r.id, r.total_count
              HAVING r.total_count IS DISTINCT FROM COALESCE(SUM(d.quantity),0)
            ) x
        """)
        p(f"  total_count 与明细合计不符的单据 = {cur.fetchone()['mismatched_qty']:,}")

        cur.execute("""
            SELECT count(*) AS mismatched_amt FROM (
              SELECT r.id, r.amount, COALESCE(SUM(d.amount),0) AS detail_amount
              FROM public.inventory_records r
              LEFT JOIN public.inventory_details d ON d.document_id = r.id
              WHERE r.deleted_at IS NULL
              GROUP BY r.id, r.amount
              HAVING r.amount IS DISTINCT FROM COALESCE(SUM(d.amount),0)
            ) x
        """)
        p(f"  amount 与明细合计不符的单据 = {cur.fetchone()['mismatched_amt']:,}")

        cur.execute("""
            SELECT count(*) AS qty_null_or_zero FROM public.inventory_details WHERE quantity IS NULL
        """)
        p(f"  明细 quantity 为 NULL = {cur.fetchone()['qty_null_or_zero']:,}")

        cur.execute("""
            SELECT count(*) AS n FROM public.inventory_details
            WHERE quantity IS NOT NULL AND quantity = 0
        """)
        p(f"  明细 quantity 为 0 = {cur.fetchone()['n']:,}")

        cur.execute("""
            SELECT count(*) AS n FROM public.inventory_details
            WHERE amount IS NULL OR unit_price IS NULL
        """)
        p(f"  明细 unit_price 或 amount 为 NULL = {cur.fetchone()['n']:,}")

        cur.execute("""
            SELECT count(*) AS n FROM public.inventory_details
            WHERE (quantity IS NOT NULL AND unit_price IS NOT NULL AND amount IS NOT NULL)
              AND round(quantity * unit_price, 2) <> round(amount, 2)
        """)
        p(f"  明细 amount ≠ quantity × unit_price = {cur.fetchone()['n']:,}")

        cur.execute("""
            SELECT count(*) AS n FROM public.inventory_details
            WHERE product_code IS NULL OR btrim(product_code) = ''
        """)
        p(f"  明细缺少商品编码 product_code = {cur.fetchone()['n']:,}")

        cur.execute("""
            SELECT count(*) AS n FROM public.inventory_details
            WHERE color_spec IS NULL OR btrim(color_spec) = ''
        """)
        p(f"  明细缺少颜色规格 color_spec = {cur.fetchone()['n']:,}")

        cur.execute("""
            SELECT count(*) AS n FROM public.inventory_details
            WHERE size_quantities IS NULL
        """)
        p(f"  明细缺少尺码数量 size_quantities = {cur.fetchone()['n']:,}")
    p()

    p("=" * 78)
    p("C. 大表可疑列实测 (只看缺失率 >= 1% 的列)")
    p("=" * 78)
    p()
    missing_matrix(conn, list(BIG.keys()), only_suspicious=True, cols_override=BIG)

    p("=" * 78)
    p("D. 日粒度序列的日期断档")
    p("=" * 78)
    DAILY = [
        ("jst_daily_stock", "stock_date"),
        ("jst_daily_sales_2026", "sales_date"),
        ("vip_daily_sales_2026", "sales_date"),
        ("fine_table_snapshot_refs_2026", "snapshot_date"),
        ("product_goods_detail_snapshots_2026", "snapshot_date"),
        ("vip_product_daily_snapshots", "snapshot_date"),
        ("product_goods_historical_orders_2026", "order_date"),
        ("dewu_orders_2026", "order_date"),
    ]
    for tbl, col in DAILY:
        if col_type(tbl, col) is None:
            p(f"  {tbl}.{col}: 列不存在, 跳过")
            continue
        try:
            with conn.cursor(row_factory=dict_row) as cur:
                cur.execute(f'SELECT min("{col}") AS lo, max("{col}") AS hi, '
                            f'count(DISTINCT "{col}") AS days, count(*) AS rows '
                            f'FROM public."{tbl}"')
                r = cur.fetchone()
            if r["lo"] is None:
                p(f"  {tbl}.{col}: 无数据")
                continue
            span = (r["hi"] - r["lo"]).days + 1
            p(f"  {tbl}.{col}: {r['lo']} ~ {r['hi']} 跨度={span}天 有数据天数={r['days']} "
              f"缺={span - r['days']} 行数={r['rows']:,}")
            with conn.cursor() as cur:
                cur.execute(f"""
                    SELECT d::date FROM generate_series(%s::date, %s::date, interval '1 day') d
                    WHERE d::date NOT IN (SELECT DISTINCT "{col}" FROM public."{tbl}"
                                          WHERE "{col}" IS NOT NULL)
                    ORDER BY 1 LIMIT 40
                """, (r["lo"], r["hi"]))
                gaps = [x[0] for x in cur.fetchall()]
            if gaps:
                p(f"      缺失日期: {', '.join(str(g) for g in gaps)}")
        except Exception as exc:  # noqa: BLE001
            conn.rollback()
            p(f"  {tbl}.{col}: 检查失败 {type(exc).__name__}: {exc}")
    p()

    p("=" * 78)
    p("E. 交叉引用缺失")
    p("=" * 78)
    archive_union = " UNION ".join(
        f'SELECT sku, original_sku FROM public.{t} WHERE sku IS NOT NULL' for t in ARCHIVES)

    with conn.cursor() as cur:
        cur.execute(f"""
            SELECT count(*) FROM public.inventory_details d
            WHERE d.product_code IS NOT NULL AND btrim(d.product_code) <> ''
              AND NOT EXISTS (
                SELECT 1 FROM ({archive_union}) a
                WHERE a.sku = d.product_code OR a.original_sku = d.product_code)
        """)
        p(f"  明细商品编码不在任何商品档案(sku/original_sku)中的行数 = {cur.fetchone()[0]:,}")

    with conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM public.product_size_group_mappings")
        p(f"  product_size_group_mappings 行数 = {cur.fetchone()[0]:,}")
        cur.execute(f"""
            SELECT count(*) FROM public.product_size_group_mappings m
            WHERE m.product_code IS NOT NULL
              AND NOT EXISTS (SELECT 1 FROM ({archive_union}) a
                              WHERE a.sku = m.product_code OR a.original_sku = m.product_code)
        """)
        p(f"    其中 product_code 不在商品档案中 = {cur.fetchone()[0]:,}")
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute("SELECT count(*) AS n FROM public.product_goods_overrides")
        p(f"  product_goods_overrides 行数 = {cur.fetchone()['n']:,}")
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute("""
            SELECT (SELECT count(*) FROM public.product_tag_definitions) AS definitions,
                   (SELECT count(*) FROM public.product_tag_assignments) AS assignments,
                   (SELECT count(*) FROM public.product_style_entities) AS style_entities,
                   (SELECT count(DISTINCT tag_id) FROM public.product_tag_assignments) AS distinct_tags,
                   (SELECT count(DISTINCT style_id) FROM public.product_tag_assignments) AS distinct_styles
        """)
        r = cur.fetchone()
        p(f"  标签体系: definitions={r['definitions']:,} assignments={r['assignments']:,} "
          f"style_entities={r['style_entities']:,} distinct_tags={r['distinct_tags']:,} "
          f"distinct_styles={r['distinct_styles']:,}")
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute("""
            SELECT (SELECT count(*) FROM public.product_archive_identities) AS identities,
                   (SELECT count(*) FROM public.inventory_details WHERE product_identity_id IS NULL) AS details_without_identity,
                   (SELECT count(*) FROM public.inventory_details) AS details
        """)
        r = cur.fetchone()
        p(f"  商品身份表 product_archive_identities={r['identities']:,} ; "
          f"未关联身份的明细={r['details_without_identity']:,}/{r['details']:,}")
    p()

print("[done]")