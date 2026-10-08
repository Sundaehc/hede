"""Generate exact DROP + recreate statements for the whole proposed index list."""
from __future__ import annotations

import sys
from pathlib import Path

import psycopg
from psycopg.rows import dict_row

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from audit import database_url  # noqa: E402

STANDALONE = [
    # 3.1 refs tables
    "idx_fine_table_snapshot_refs_2026_batch_original_sku",
    "idx_fine_table_snapshot_refs_2026_batch_row_index",
    "idx_fine_table_snapshot_refs_2026_sku_trgm",
    "idx_fine_table_snapshot_refs_2026_original_sku_trgm",
    "idx_fine_table_snapshot_refs_2025_batch_original_sku",
    "idx_fine_table_snapshot_refs_2025_sku_trgm",
    "idx_fine_table_snapshot_refs_2025_batch_row_index",
    "idx_fine_table_snapshot_refs_2025_original_sku_trgm",
    "idx_fine_table_snapshot_refs_2024_sku_trgm",
    "idx_fine_table_snapshot_refs_2024_batch_original_sku",
    "idx_fine_table_snapshot_refs_2024_batch_row_index",
    "idx_fine_table_snapshot_refs_2024_original_sku_trgm",
    # 3.2
    "idx_jst_stock_date_qty",
    # 3.3
    "idx_ops_snapshots_goods_code_date",
    "idx_ops_snapshots_snapshot_date",
    # 3.4 duplicates of unique constraints
    "idx_jst_stock_summary_snapshots_date_code",
    "idx_product_goods_detail_snapshot_batches_brand_date",
    "idx_inventory_account_subjects_name",
    "idx_purchase_order_requirement_brand",
    "idx_purchase_print_templates_user",
    "idx_product_goods_shop_channel_brand",
    "idx_general_customer_units_shop_id",
    # 3.5 the rest
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
    "idx_auth_sessions_expires_at",
    "idx_color_barcodes_color_barcode",
    "idx_general_customer_shops_customer_name",
    "idx_general_customer_shops_shop_name",
    "idx_general_customer_units_unit_name",
    "idx_auth_users_role",
    "idx_auth_users_department",
    "idx_warehouses_brand_sort",
    "idx_warehouse_brands_sort",
    "idx_supplier_brands_sort",
    "idx_general_customer_brands_sort",
    "idx_size_group_items_group_sort",
    "idx_smiley_products_last_imported_at",
    "idx_smiley_product_copy_log_lookup",
    "idx_smiley_product_copy_base_status",
    "idx_ni_products_last_imported_at",
    "idx_manual_product_archive_31_original_sku",
    "idx_manual_product_archive_31_last_imported_at",
    "idx_data_quality_issues_open",
]

PARENTS = [
    "idx_jst_monthly_orders_product_code",
    "idx_jst_monthly_orders_style_code",
    "idx_jst_monthly_orders_ship_date_value",
    "idx_jst_aftersale_returns_id",
    "idx_jst_aftersale_returns_application_date",
    "idx_jst_aftersale_returns_order_time",
    "idx_jst_aftersale_returns_business_date",
]

lines: list[str] = []
missing: list[str] = []
total = 0

with psycopg.connect(database_url(), autocommit=True) as conn:
    def fetch(name: str):
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute("""
                SELECT i.indexrelid::regclass::text AS idx,
                       i.indrelid::regclass::text AS tbl,
                       pg_get_indexdef(i.indexrelid) AS def,
                       pg_relation_size(i.indexrelid) AS bytes,
                       i.indisunique, i.indisprimary,
                       (SELECT count(*) FROM pg_inherits ih WHERE ih.inhparent = i.indexrelid) AS kids,
                       (SELECT COALESCE(SUM(pg_relation_size(ci.inhrelid)),0) FROM pg_inherits ci
                         WHERE ci.inhparent = i.indexrelid) AS child_bytes,
                       (SELECT COALESCE(SUM(si.idx_scan),0) FROM pg_inherits ci
                          JOIN pg_stat_user_indexes si ON si.indexrelid = ci.inhrelid
                         WHERE ci.inhparent = i.indexrelid) AS child_scans
                FROM pg_index i WHERE i.indexrelid = to_regclass('public.' || %s)
            """, (name,))
            return cur.fetchone()

    lines.append("-- ==== AUTO-GENERATED: DROP statements (standalone, CONCURRENTLY) ====")
    for name in STANDALONE:
        r = fetch(name)
        if not r:
            missing.append(name)
            lines.append(f"-- !! NOT FOUND, SKIPPED: {name}")
            continue
        assert not r["indisunique"] and not r["indisprimary"], f"{name} backs a constraint!"
        total += int(r["bytes"])
        lines.append(f"DROP INDEX CONCURRENTLY public.{name};"
                     f"  -- {r['bytes']/1048576:.1f} MB, scans=0, {r['tbl']}")
    lines.append("")
    lines.append("-- ==== AUTO-GENERATED: DROP statements (partitioned parents) ====")
    for name in PARENTS:
        r = fetch(name)
        if not r:
            missing.append(name)
            lines.append(f"-- !! NOT FOUND, SKIPPED: {name}")
            continue
        total += int(r["child_bytes"])
        lines.append(f"DROP INDEX public.{name};"
                     f"  -- {r['child_bytes']/1048576:.1f} MB across {r['kids']} children, "
                     f"scans={r['child_scans']}, {r['tbl']}")
    lines.append("")
    lines.append("-- ==== AUTO-GENERATED: RECREATE statements (rollback) ====")
    for name in STANDALONE + PARENTS:
        r = fetch(name)
        if not r:
            continue
        ddl = r["def"].rstrip(";")
        ddl = ddl.replace("CREATE INDEX ", "CREATE INDEX CONCURRENTLY ", 1) \
            if "ON ONLY" not in ddl else ddl
        lines.append(f"{ddl};  -- {r['idx']}")
    lines.append("")
    lines.append(f"-- standalone+parent bytes accounted: {total/1048576:,.1f} MB")
    lines.append(f"-- missing names: {missing}")

out = HERE / "drops_and_recreates.sql"
out.write_text("\n".join(lines), encoding="utf-8")
print("\n".join(lines))
print(f"\n[written] {out}")