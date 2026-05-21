from __future__ import annotations

from sqlalchemy import Engine, text


def apply_core_database_optimizations(engine: Engine) -> None:
    """Apply idempotent schema/index optimizations for existing databases."""

    with engine.begin() as conn:
        conn.execute(text("CREATE EXTENSION IF NOT EXISTS pg_trgm"))

        conn.execute(text("ALTER TABLE inventory_records ADD COLUMN IF NOT EXISTS date_value DATE"))
        conn.execute(text("ALTER TABLE jst_daily_stock ADD COLUMN IF NOT EXISTS stock_date_value DATE"))
        conn.execute(text("ALTER TABLE vip_product_daily ADD COLUMN IF NOT EXISTS report_start_date DATE"))
        conn.execute(text("ALTER TABLE vip_product_daily ADD COLUMN IF NOT EXISTS report_end_date DATE"))
        conn.execute(text("ALTER TABLE jst_monthly_orders ADD COLUMN IF NOT EXISTS order_time_at TIMESTAMP"))
        conn.execute(text("ALTER TABLE jst_monthly_orders ADD COLUMN IF NOT EXISTS ship_date_value DATE"))

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
        statements = [
            "CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_inventory_records_date_value ON inventory_records (date_value)",
            "CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_jst_stock_date_value_code ON jst_daily_stock (stock_date_value, product_code)",
            "CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_jst_monthly_orders_order_time_at ON jst_monthly_orders (order_time_at)",
            "CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_jst_monthly_orders_product_code ON jst_monthly_orders (product_code)",
            "CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_jst_monthly_orders_style_code ON jst_monthly_orders (style_code)",
            "CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_jst_monthly_orders_shop_name ON jst_monthly_orders (shop_name)",
            "CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_jst_monthly_orders_status ON jst_monthly_orders (status)",
            "CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_jst_monthly_orders_ship_date_value ON jst_monthly_orders (ship_date_value)",
            "CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_jst_monthly_orders_time_product ON jst_monthly_orders (order_time_at, product_code)",
            "CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_vip_daily_report_dates ON vip_product_daily (report_start_date, report_end_date)",
        ]
        for statement in statements:
            conn.execute(text(statement))
