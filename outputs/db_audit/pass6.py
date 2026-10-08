"""Sixth pass: inventory_details index coverage, duplicate-key checks, totals."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import psycopg
from psycopg.rows import dict_row

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from audit import database_url  # noqa: E402

OUT: list[str] = []
RAW = json.loads((HERE / "raw.json").read_text(encoding="utf-8"))


def p(s: str = "") -> None:
    OUT.append(s)


with psycopg.connect(database_url(), autocommit=True) as conn:
    p("## INVENTORY_DETAILS: COLUMNS AND INDEX COVERAGE")
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute("""
            SELECT a.attname, format_type(a.atttypid,a.atttypmod) AS type,
                   COALESCE(s.avg_width,0) AS avg_width, COALESCE(s.n_distinct,0) AS n_distinct
            FROM pg_attribute a
            LEFT JOIN pg_stats s ON s.schemaname='public' AND s.tablename='inventory_details' AND s.attname=a.attname
            WHERE a.attrelid='public.inventory_details'::regclass AND a.attnum>0 AND NOT a.attisdropped
            ORDER BY a.attnum
        """)
        for r in cur.fetchall():
            p(f"  {r['attname']:<22} {r['type']:<22} avg_width={r['avg_width']:>6} n_distinct={r['n_distinct']}")
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute("""
            SELECT s.indexrelname AS idx, s.idx_scan, pg_relation_size(s.indexrelid) AS bytes,
                   pg_get_indexdef(s.indexrelid) AS def
            FROM pg_stat_user_indexes s
            WHERE s.relname='inventory_details'
            ORDER BY pg_relation_size(s.indexrelid) DESC
        """)
        for r in cur.fetchall():
            p(f"  INDEX {r['idx']:<45} scans={r['idx_scan']:>10} {r['bytes']/1048576:>8.2f}MB")
            p(f"        {r['def']}")
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute("""
            SELECT s.relname, s.seq_scan, s.seq_tup_read, s.idx_scan, s.n_live_tup
            FROM pg_stat_user_tables s WHERE s.relname IN ('inventory_details','inventory_records')
        """)
        for r in cur.fetchall():
            p(f"  stats {r['relname']}: seq_scan={r['seq_scan']:,} seq_rows={r['seq_tup_read']:,} "
              f"idx_scan={r['idx_scan']:,} live={r['n_live_tup']:,}")
    p()

    p("## DUPLICATE-KEY CHECK ON TABLES WITHOUT A UNIQUE CONSTRAINT")
    checks = [
        ("jst_aftersale_returns_2026", "source_workbook, source_sheet, source_row_number"),
        ("jst_aftersale_returns_2025", "source_workbook, source_sheet, source_row_number"),
        ("dewu_orders_2026", "order_number"),
    ]
    for table, key in checks:
        try:
            with conn.cursor(row_factory=dict_row) as cur:
                cur.execute(f"""
                    SELECT count(*) AS total,
                           count(DISTINCT ({key})) AS distinct_keys
                    FROM public.{table}
                """)
                r = cur.fetchone()
            dup = (r["total"] or 0) - (r["distinct_keys"] or 0)
            p(f"  {table:<32} key=({key}) rows={r['total']:,} distinct={r['distinct_keys']:,} duplicates={dup:,}")
        except Exception as exc:  # noqa: BLE001
            conn.rollback()
            p(f"  {table}: check failed -> {exc}")
    p()

    p("## GLOBAL INDEX FOOTPRINT")
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute("""
            SELECT count(*) AS n_indexes,
                   pg_size_pretty(SUM(pg_relation_size(i.indexrelid))) AS index_size
            FROM pg_index i
            JOIN pg_class c ON c.oid=i.indrelid JOIN pg_namespace n ON n.oid=c.relnamespace
            WHERE n.nspname='public'
        """)
        p(f"  {json.dumps(cur.fetchone(), ensure_ascii=False)}")
        cur.execute("""
            SELECT pg_size_pretty(SUM(pg_relation_size(c.oid))) AS heap_size,
                   pg_size_pretty(SUM(pg_indexes_size(c.oid))) AS index_size,
                   pg_size_pretty(SUM(pg_total_relation_size(c.oid))) AS total_size
            FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
            WHERE c.relkind IN ('r','p') AND n.nspname='public'
        """)
        p(f"  {json.dumps(cur.fetchone(), ensure_ascii=False)}")
        cur.execute("""
            SELECT count(*) FROM pg_index i
            JOIN pg_class c ON c.oid=i.indrelid JOIN pg_namespace n ON n.oid=c.relnamespace
            WHERE n.nspname='public' AND i.indisvalid AND NOT i.indisprimary AND NOT i.indisunique
        """)
        p(f"  non-unique, non-primary indexes: {cur.fetchone()['count']}")
    p()

    p("## TOP 20 PARTITIONS BY SIZE (row identity check)")
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute("""
            SELECT c.relname, c.reltuples::bigint AS reltuples,
                   pg_size_pretty(pg_total_relation_size(c.oid)) AS size,
                   (SELECT count(*) FROM pg_index i WHERE i.indrelid=c.oid AND i.indisunique) AS uq,
                   (SELECT count(*) FROM pg_index i WHERE i.indrelid=c.oid AND i.indisprimary) AS pk
            FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
            WHERE c.relispartition AND n.nspname='public'
            ORDER BY pg_total_relation_size(c.oid) DESC LIMIT 20
        """)
        for r in cur.fetchall():
            p(f"  {r['relname']:<40} rows={r['reltuples']:>10} unique_idx={r['uq']} pk={r['pk']} {r['size']}")
    p()

    p("## REDUNDANT INDEX CANDIDATES - CONSOLIDATED (safe drops)")
    idx_bytes = {r["index_name"]: int(r["index_bytes"]) for r in RAW["index_keys"]}
    safe = [
        ("idx_fine_table_snapshot_refs_2026_batch_row_index", "identical to uq_..._batch_row_index", 503.9),
        ("idx_fine_table_snapshot_refs_2025_batch_row_index", "identical to uq_..._batch_row_index", 332.4),
        ("idx_fine_table_snapshot_refs_2024_batch_row_index", "identical to uq_..._batch_row_index", 179.1),
        ("idx_jst_stock_date_qty", "leading cols covered by uq_jst_stock_date_code; 0 scans", 751.8),
        ("idx_jst_stock_summary_snapshots_date_code", "identical to uq_jst_stock_summary_snapshot", 78.6),
        ("idx_fine_table_snapshot_refs_2026_batch_original_sku", "0 scans", 548.5),
        ("idx_fine_table_snapshot_refs_2026_sku_trgm", "0 scans", 362.2),
        ("idx_fine_table_snapshot_refs_2026_original_sku_trgm", "0 scans", 320.5),
        ("idx_fine_table_snapshot_refs_2025_batch_original_sku", "0 scans (table not appended to)", 396.2),
        ("idx_fine_table_snapshot_refs_2025_sku_trgm", "0 scans", 345.0),
        ("idx_fine_table_snapshot_refs_2025_original_sku_trgm", "0 scans", 299.8),
        ("idx_ops_snapshots_goods_code_date", "0 scans", 338.1),
        ("jst_monthly_orders_2024_style_code_order_time_at_idx", "prefix covered by wider index/0 scans", 332.0),
        ("jst_monthly_orders_2025_style_code_order_time_at_idx", "prefix covered by wider index/0 scans", 288.1),
        ("idx_fine_table_snapshot_refs_2024_sku_trgm", "0 scans", 200.9),
        ("idx_fine_table_snapshot_refs_2024_batch_original_sku", "0 scans", 196.8),
        ("idx_fine_table_snapshot_refs_2024_original_sku_trgm", "0 scans", 173.4),
        ("jst_monthly_orders_2024_product_code_idx", "0 scans", 54.4),
        ("jst_monthly_orders_2025_product_code_idx", "0 scans", 49.6),
        ("jst_monthly_orders_2026_product_code_idx", "0 scans", 43.8),
        ("idx_inventory_records_document_number", "identical to uq_inventory_records_active_document_number", 0.4),
        ("idx_product_goods_detail_snapshot_batches_brand_date", "identical to uq_..._batch", 0.1),
        ("idx_purchase_order_requirement_brand", "identical to uq_..._brand", 0.0),
        ("idx_inventory_account_subjects_name", "identical to uq_..._name", 0.0),
        ("idx_purchase_print_templates_user", "identical key to uq_..._user_default", 0.0),
        ("idx_vip_daily_sales_2026_sales_date", "prefix of uq_vip_daily_sales_2026_business_key", 105.7),
        ("idx_jst_daily_sales_2026_sales_date", "prefix of uq_jst_daily_sales_2026_business_key", 10.9),
        ("idx_jst_size_stock_snapshots_date_code", "prefix of uq_jst_size_stock_snapshot", 167.7),
        ("idx_factory_channel_sales_daily_summary_brand_date", "prefix of uq_..._key", 11.8),
        ("idx_gj_merged_product_info_source_date", "prefix of idx_..._source_date_id_desc", 49.0),
    ]
    p(f"  {'index':<58} {'size':>10}  reason")
    total = 0.0
    for name, reason, size in safe:
        total += size
        p(f"  {name:<58} {size:>9.1f}MB  {reason}")
    p(f"  -> candidate reclaim: {total:,.1f}MB")
    p()

(HERE / "findings6.txt").write_text("\n".join(OUT), encoding="utf-8")
print(f"[written] {HERE / 'findings6.txt'} sections={len(OUT)}")