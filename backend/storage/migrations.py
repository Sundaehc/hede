from __future__ import annotations

from sqlalchemy import Engine, text

from domain.sources import TABLE_NAMES


def apply_core_database_optimizations(engine: Engine) -> None:
    """Apply idempotent schema/index optimizations for existing databases."""

    with engine.begin() as conn:
        conn.execute(text("CREATE EXTENSION IF NOT EXISTS pg_trgm"))

        conn.execute(text("ALTER TABLE inventory_records ADD COLUMN IF NOT EXISTS date_value DATE"))
        conn.execute(text("ALTER TABLE jst_daily_stock ADD COLUMN IF NOT EXISTS stock_date_value DATE"))
        conn.execute(text("ALTER TABLE vip_product_daily ADD COLUMN IF NOT EXISTS report_start_date DATE"))
        conn.execute(text("ALTER TABLE vip_product_daily ADD COLUMN IF NOT EXISTS report_end_date DATE"))
        conn.execute(text("ALTER TABLE jst_product_price ADD COLUMN IF NOT EXISTS source_date TEXT"))
        conn.execute(text("ALTER TABLE jst_product_price ADD COLUMN IF NOT EXISTS source_date_value DATE"))
        conn.execute(text("ALTER TABLE jst_monthly_orders ADD COLUMN IF NOT EXISTS order_time_at TIMESTAMP"))
        conn.execute(text("ALTER TABLE jst_monthly_orders ADD COLUMN IF NOT EXISTS ship_date_value DATE"))
        conn.execute(
            text(
                """
                update inventory_records
                set document_type = case document_type
                    when '工厂进货单' then '进货单'
                    when '工厂退货单' then '进货退货单'
                    else document_type
                end
                where document_type in ('工厂进货单', '工厂退货单')
                """
            )
        )
        conn.execute(text("ALTER TABLE gj_merged_product_info ADD COLUMN IF NOT EXISTS fine_table_brand TEXT"))
        for table in TABLE_NAMES.values():
            conn.execute(text(f"ALTER TABLE {table} ADD COLUMN IF NOT EXISTS product_level TEXT"))
        conn.execute(
            text(
                """
                update gj_merged_product_info
                set fine_table_brand = case
                    when upper(coalesce(brand, '')) like '%TRUMPPIPE%'
                      or coalesce(brand, '') like '%烟斗%' then 'yandou'
                    when upper(coalesce(brand, '')) like '%EBLAN%'
                      or coalesce(brand, '') like '%伊伴%' then 'eblan'
                    when coalesce(primary_supplier, '') like '%千百度品牌方%' then null
                    when coalesce(primary_supplier, '') like '%千百度女鞋%' then 'cbanner_womens'
                    when coalesce(primary_supplier, '') like '%千百度%' then 'cbanner_mens'
                    else null
                end
                where fine_table_brand is null
                """
            )
        )
        conn.execute(
            text(
                """
                update jst_product_price
                set
                    source_date = coalesce(source_date, to_char(current_date, 'YYYY-MM-DD')),
                    source_date_value = coalesce(source_date_value, current_date)
                where source_date is null
                   or source_date = ''
                   or source_date_value is null
                """
            )
        )
        conn.execute(text("ALTER TABLE jst_product_price ALTER COLUMN source_date SET NOT NULL"))
        conn.execute(
            text(
                """
                do $$
                begin
                    if exists (
                        select 1
                        from pg_constraint
                        where conname = 'uq_jst_price_code_name'
                    ) then
                        alter table jst_product_price drop constraint uq_jst_price_code_name;
                    end if;
                end $$;
                """
            )
        )

        conn.execute(
            text(
                """
                update inventory_records
                set date_value = date::date
                where date_value is null
                  and date ~ '^\\d{4}-\\d{2}-\\d{2}$'
                """
            )
        )
        conn.execute(
            text(
                """
                update jst_daily_stock
                set stock_date_value = make_date(
                    extract(year from current_date)::int,
                    split_part(stock_date, '.', 1)::int,
                    split_part(stock_date, '.', 2)::int
                )
                where stock_date_value is null
                  and stock_date ~ '^\\d{1,2}\\.\\d{1,2}$'
                """
            )
        )
        conn.execute(
            text(
                """
                update vip_product_daily
                set
                    report_start_date = split_part(date, '~', 1)::date,
                    report_end_date = case
                        when date like '%~%' then split_part(date, '~', 2)::date
                        else date::date
                    end
                where (report_start_date is null or report_end_date is null)
                  and date ~ '^\\d{4}-\\d{2}-\\d{2}(~\\d{4}-\\d{2}-\\d{2})?$'
                """
            )
        )
        conn.execute(
            text(
                """
                update jst_monthly_orders
                set order_time_at = order_time::timestamp
                where order_time_at is null
                  and order_time ~ '^\\d{4}-\\d{2}-\\d{2}[ T]\\d{2}:\\d{2}:\\d{2}'
                """
            )
        )
        conn.execute(
            text(
                """
                update jst_monthly_orders
                set ship_date_value = left(ship_date, 10)::date
                where ship_date_value is null
                  and ship_date ~ '^\\d{4}-\\d{2}-\\d{2}'
                """
            )
        )

    with engine.connect().execution_options(isolation_level="AUTOCOMMIT") as conn:
        product_index_statements = []
        for table in TABLE_NAMES.values():
            product_index_statements.extend(
                [
                    f"CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_{table}_year ON {table} (year)",
                    f"CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_{table}_sku_trgm ON {table} USING GIN (sku gin_trgm_ops)",
                    f"CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_{table}_original_sku_trgm ON {table} USING GIN (original_sku gin_trgm_ops)",
                    f"CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_{table}_factory_sku_trgm ON {table} USING GIN (factory_sku gin_trgm_ops)",
                ]
            )

        statements = [
            *product_index_statements,
            "CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_inventory_records_date_value ON inventory_records (date_value)",
            "CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_jst_stock_date_value_code ON jst_daily_stock (stock_date_value, product_code)",
            "CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_jst_monthly_orders_order_time_at ON jst_monthly_orders (order_time_at)",
            "CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_jst_monthly_orders_product_code ON jst_monthly_orders (product_code)",
            "CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_jst_monthly_orders_style_code ON jst_monthly_orders (style_code)",
            "CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_jst_monthly_orders_ship_date_value ON jst_monthly_orders (ship_date_value)",
            "CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_jst_monthly_orders_time_product ON jst_monthly_orders (order_time_at, product_code)",
            "CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_vip_daily_report_dates ON vip_product_daily (report_start_date, report_end_date)",
            "CREATE UNIQUE INDEX CONCURRENTLY IF NOT EXISTS uq_jst_price_date_code_name ON jst_product_price (source_date, goods_code, goods_full_name)",
            "CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_jst_price_source_date_value ON jst_product_price (source_date_value)",
            "CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_gj_merged_product_info_source_brand_id_desc ON gj_merged_product_info (source_date_value, fine_table_brand, id DESC)",
            "DROP INDEX CONCURRENTLY IF EXISTS idx_jst_stock_summary_date_code",
        ]
        for statement in statements:
            conn.execute(text(statement))
