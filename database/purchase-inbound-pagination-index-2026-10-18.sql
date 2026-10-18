-- Run outside a transaction; existing databases should use the Python helper
-- to verify any existing index definition before applying this migration.
SET lock_timeout = '5s';
SET statement_timeout = '5min';

CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_inventory_details_document_page ON public.inventory_details USING btree (document_id, id) INCLUDE (quantity, amount);

ANALYZE public.inventory_details;

-- Rollback after review:
-- DROP INDEX CONCURRENTLY IF EXISTS public.idx_inventory_details_document_page;
