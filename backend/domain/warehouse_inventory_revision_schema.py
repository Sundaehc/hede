"""Transaction-aware invalidation for compact warehouse query results."""
from sqlalchemy import text


INSTALL_SQL = """
CREATE TABLE IF NOT EXISTS public.warehouse_inventory_revisions (
    transaction_id BIGINT PRIMARY KEY,
    created_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp()
);
CREATE OR REPLACE FUNCTION public.mark_warehouse_inventory_changed()
RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE
    current_transaction BIGINT := pg_current_xact_id()::text::bigint;
BEGIN
    INSERT INTO public.warehouse_inventory_revisions (transaction_id)
    VALUES (current_transaction) ON CONFLICT DO NOTHING;
    -- Rows are immutable and unique per transaction, avoiding a shared counter
    -- lock across unrelated imports. Old rows only cause extra invalidations.
    IF FOUND AND current_transaction % 64 = 0 THEN
        DELETE FROM public.warehouse_inventory_revisions
        WHERE created_at < clock_timestamp() - interval '1 day'
          AND transaction_id <> current_transaction;
    END IF;
    RETURN NULL;
END;
$$;
"""
SOURCE_TABLES = ("inventory_records", "inventory_details", "general_customer_shops", "general_customer_units", "warehouses")


def install_revision_tracking(connection) -> None:
    connection.execute(text(INSTALL_SQL))
    for table in SOURCE_TABLES:
        trigger = f"trg_{table}_warehouse_inventory_revision"
        connection.execute(text(f"DROP TRIGGER IF EXISTS {trigger} ON public.{table}"))
        connection.execute(text(
            f"CREATE TRIGGER {trigger} AFTER INSERT OR UPDATE OR DELETE OR TRUNCATE ON public.{table} "
            "FOR EACH STATEMENT EXECUTE FUNCTION public.mark_warehouse_inventory_changed()"
        ))


VERSION_SQL = text(
    "SELECT md5(coalesce(string_agg(transaction_id::text, ',' ORDER BY transaction_id), '')) "
    "FROM public.warehouse_inventory_revisions"
)

CAPABILITIES_SQL = text("""
    SELECT to_regclass('public.warehouse_inventory_revisions') IS NOT NULL
           AND to_regprocedure('public.mark_warehouse_inventory_changed()') IS NOT NULL
           AND (SELECT count(*) FROM pg_trigger
                WHERE tgfoid = to_regprocedure('public.mark_warehouse_inventory_changed()')
                  AND NOT tgisinternal AND tgenabled = 'O'
                  AND tgrelid IN (
                      to_regclass('public.inventory_records'), to_regclass('public.inventory_details'),
                      to_regclass('public.general_customer_shops'), to_regclass('public.general_customer_units'),
                      to_regclass('public.warehouses')
                  )) = 5 AS revisions_ready,
           EXISTS (SELECT 1 FROM pg_index
                   WHERE indexrelid = to_regclass('public.idx_inventory_details_warehouse_stock')
                     AND indisvalid) AS stock_index_ready
""")
