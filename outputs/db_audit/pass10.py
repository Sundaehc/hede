"""Dump exact DDL for every index proposed for removal (verification + reversal)."""
from __future__ import annotations

import sys
from pathlib import Path

import psycopg
from psycopg.rows import dict_row

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from audit import database_url  # noqa: E402

OUT: list[str] = []
(HERE / "findings10.txt").write_text("", encoding="utf-8")


def p(s: str = "") -> None:
    OUT.append(s)
    with open(HERE / "findings10.txt", "a", encoding="utf-8") as fh:
        fh.write(s + "\n")


STANDALONE = [
    "idx_jst_stock_date_qty",
    "idx_fine_table_snapshot_refs_2026_batch_original_sku",
    "idx_fine_table_snapshot_refs_2025_batch_original_sku",
    "idx_fine_table_snapshot_refs_2026_sku_trgm",
    "idx_fine_table_snapshot_refs_2025_sku_trgm",
    "idx_ops_snapshots_goods_code_date",
    "idx_fine_table_snapshot_refs_2025_batch_row_index",
    "idx_fine_table_snapshot_refs_2026_original_sku_trgm",
    "idx_fine_table_snapshot_refs_2025_original_sku_trgm",
    "idx_fine_table_snapshot_refs_2024_sku_trgm",
    "idx_fine_table_snapshot_refs_2024_batch_original_sku",
    "idx_fine_table_snapshot_refs_2024_batch_row_index",
    "idx_fine_table_snapshot_refs_2024_original_sku_trgm",
    "idx_ops_snapshots_snapshot_date",
    "idx_vip_product_detail_daily_goods_code_date",
    "idx_vip_product_detail_daily_brand_date",
    "idx_vip_product_detail_daily_shop_date",
    "idx_product_archive_identities_brand_sku",
    "idx_jst_stock_summary_date_value_code",
    "zhiyi_hot_item_range_item_id_idx",
    "ix_jst_purchase_inbound_style_color",
    "ix_jst_purchase_inbound_style_color_normalized",
    "ix_jst_purchase_inbound_womens_date",
    "idx_yandou_products_last_imported_at",
    "idx_operation_logs_user",
    "idx_product_auxiliary_attributes_name",
    "idx_suppliers_factory_grade",
    "idx_inventory_details_product_code_trgm",
    "idx_jst_daily_stock_product_code",
    "idx_vip_daily_sales_2026_sales_date",
    "idx_jst_daily_sales_2026_sales_date",
    "idx_jst_size_stock_snapshots_date_code",
    "idx_factory_channel_sales_daily_summary_brand_date",
    "idx_gj_merged_product_info_source_date",
    "idx_jst_stock_summary_snapshots_date_code",
    "idx_inventory_records_document_number",
]

PARENTS = [
    "idx_jst_monthly_orders_product_code",
    "idx_jst_monthly_orders_style_code",
    "idx_jst_monthly_orders_ship_date_value",
    "idx_jst_monthly_orders_order_time_at",
    "idx_jst_aftersale_returns_id",
    "idx_jst_aftersale_returns_application_date",
    "idx_jst_aftersale_returns_order_time",
    "idx_jst_aftersale_returns_business_date",
]

MEASURE = [
    "idx_jst_stock_date_qty", "idx_jst_stock_date_value_code", "uq_jst_stock_date_code",
    "idx_fine_table_snapshot_refs_2026_batch_sku", "idx_fine_table_snapshot_refs_2026_payload_id",
    "idx_ops_snapshots_goods_code_date", "uq_ops_snapshot_date_goods",
    "idx_jst_monthly_orders_time_product", "uq_jst_monthly_orders_order_time_record_key",
]

with psycopg.connect(database_url(), autocommit=True) as conn:
    p("## EXACT DDL OF INDEXES PROPOSED FOR REMOVAL (standalone)")
    for name in STANDALONE:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute("""
                SELECT i.indexrelid::regclass::text AS idx, i.indrelid::regclass::text AS tbl,
                       pg_get_indexdef(i.indexrelid) AS def,
                       pg_relation_size(i.indexrelid) AS bytes, s.idx_scan,
                       i.indisvalid, i.indisunique
                FROM pg_index i
                LEFT JOIN pg_stat_user_indexes s ON s.indexrelid = i.indexrelid
                WHERE i.indexrelid = to_regclass('public.'||%s)
            """, (name,))
            r = cur.fetchone()
        if not r:
            p(f"  !! NOT FOUND: {name}")
            continue
        p(f"  [{r['bytes']/1048576:>7.1f}MB scans={r['idx_scan']}] {r['tbl']}")
        p(f"      {r['def']};")
    p()

    p("## EXACT DDL OF PARTITIONED-PARENT INDEXES PROPOSED FOR REMOVAL")
    for name in PARENTS:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute("""
                SELECT i.indexrelid::regclass::text AS idx, i.indrelid::regclass::text AS tbl,
                       pg_get_indexdef(i.indexrelid) AS def,
                       (SELECT count(*) FROM pg_inherits ih WHERE ih.inhparent=i.indexrelid) AS kids,
                       (SELECT COALESCE(SUM(pg_relation_size(ci.inhrelid)),0) FROM pg_inherits ci
                         WHERE ci.inhparent=i.indexrelid) AS bytes,
                       (SELECT COALESCE(SUM(si.idx_scan),0) FROM pg_inherits ci
                          JOIN pg_stat_user_indexes si ON si.indexrelid=ci.inhrelid
                         WHERE ci.inhparent=i.indexrelid) AS scans
                FROM pg_index i
                WHERE i.indexrelid = to_regclass('public.'||%s)
            """, (name,))
            r = cur.fetchone()
        if not r:
            p(f"  !! NOT FOUND: {name}")
            continue
        p(f"  [{r['bytes']/1048576:>7.1f}MB across {r['kids']} children, scans={r['scans']}] {r['tbl']}")
        p(f"      {r['def']};")
    p()

    p("## KEPT-INDEX VERIFICATION (the indexes that will serve the traffic instead)")
    for name in MEASURE:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute("""
                SELECT i.indexrelid::regclass::text AS idx, i.indrelid::regclass::text AS tbl,
                       pg_get_indexdef(i.indexrelid) AS def,
                       pg_relation_size(i.indexrelid) AS bytes, s.idx_scan
                FROM pg_index i LEFT JOIN pg_stat_user_indexes s ON s.indexrelid=i.indexrelid
                WHERE i.indexrelid = to_regclass('public.'||%s)
            """, (name,))
            r = cur.fetchone()
        if not r:
            p(f"  !! NOT FOUND: {name}")
            continue
        p(f"  [{r['bytes']/1048576:>7.1f}MB scans={r['idx_scan']}] {r['def']};")
    p()

    p("## FK THAT NEEDS AN INDEX")
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute("""
            SELECT con.conname, con.conrelid::regclass::text AS child,
                   pg_get_constraintdef(con.oid) AS def
            FROM pg_constraint con
            WHERE con.contype='f' AND con.conname='product_tag_assignments_style_id_fkey'
        """)
        for r in cur.fetchall():
            p(f"  {r['child']} {r['conname']}: {r['def']}")
    p()

print(f"[written] {HERE / 'findings10.txt'} sections={len(OUT)}")