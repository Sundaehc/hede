-- Product goods / fine table pagination indexes, 2026-10-14.
-- Target: PostgreSQL public schema with direct annual aftersale partitions.
-- Run with psql, NOT inside a transaction (CREATE INDEX CONCURRENTLY).
-- Review target database first; use the Python helper to verify existing definitions.
SET lock_timeout = '5s';
SET statement_timeout = '5min';

CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_gj_merged_product_info_source_brand_code ON public.gj_merged_product_info USING btree (source_date_value, fine_table_brand, goods_code) INCLUDE (id);

CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_product_goods_sales_period_brand_product_pattern ON public.product_goods_sales_periods USING btree (brand, product_code text_pattern_ops);

CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_jst_aftersale_returns_2024_original_code_pattern ON public.jst_aftersale_returns_2024 USING btree (original_goods_code text_pattern_ops);

CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_jst_aftersale_returns_2025_original_code_pattern ON public.jst_aftersale_returns_2025 USING btree (original_goods_code text_pattern_ops);

CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_jst_aftersale_returns_2026_original_code_pattern ON public.jst_aftersale_returns_2026 USING btree (original_goods_code text_pattern_ops);

CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_jst_aftersale_returns_2027_original_code_pattern ON public.jst_aftersale_returns_2027 USING btree (original_goods_code text_pattern_ops);

CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_jst_aftersale_returns_default_original_code_pattern ON public.jst_aftersale_returns_default USING btree (original_goods_code text_pattern_ops);

CREATE INDEX IF NOT EXISTS idx_jst_aftersale_returns_original_code_pattern ON ONLY public.jst_aftersale_returns USING btree (original_goods_code text_pattern_ops);

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_inherits WHERE inhparent = 'public.idx_jst_aftersale_returns_original_code_pattern'::regclass AND inhrelid = 'public.idx_jst_aftersale_returns_2024_original_code_pattern'::regclass) THEN
        ALTER INDEX public.idx_jst_aftersale_returns_original_code_pattern ATTACH PARTITION public.idx_jst_aftersale_returns_2024_original_code_pattern;
    END IF;
END;
$$;

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_inherits WHERE inhparent = 'public.idx_jst_aftersale_returns_original_code_pattern'::regclass AND inhrelid = 'public.idx_jst_aftersale_returns_2025_original_code_pattern'::regclass) THEN
        ALTER INDEX public.idx_jst_aftersale_returns_original_code_pattern ATTACH PARTITION public.idx_jst_aftersale_returns_2025_original_code_pattern;
    END IF;
END;
$$;

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_inherits WHERE inhparent = 'public.idx_jst_aftersale_returns_original_code_pattern'::regclass AND inhrelid = 'public.idx_jst_aftersale_returns_2026_original_code_pattern'::regclass) THEN
        ALTER INDEX public.idx_jst_aftersale_returns_original_code_pattern ATTACH PARTITION public.idx_jst_aftersale_returns_2026_original_code_pattern;
    END IF;
END;
$$;

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_inherits WHERE inhparent = 'public.idx_jst_aftersale_returns_original_code_pattern'::regclass AND inhrelid = 'public.idx_jst_aftersale_returns_2027_original_code_pattern'::regclass) THEN
        ALTER INDEX public.idx_jst_aftersale_returns_original_code_pattern ATTACH PARTITION public.idx_jst_aftersale_returns_2027_original_code_pattern;
    END IF;
END;
$$;

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_inherits WHERE inhparent = 'public.idx_jst_aftersale_returns_original_code_pattern'::regclass AND inhrelid = 'public.idx_jst_aftersale_returns_default_original_code_pattern'::regclass) THEN
        ALTER INDEX public.idx_jst_aftersale_returns_original_code_pattern ATTACH PARTITION public.idx_jst_aftersale_returns_default_original_code_pattern;
    END IF;
END;
$$;

-- Rollback requires review; drop the partitioned parent first (not concurrently).
-- Dropping that parent removes its attached child indexes.
-- DROP INDEX IF EXISTS public.idx_jst_aftersale_returns_original_code_pattern;
-- DROP INDEX CONCURRENTLY IF EXISTS public.idx_product_goods_sales_period_brand_product_pattern;
-- DROP INDEX CONCURRENTLY IF EXISTS public.idx_gj_merged_product_info_source_brand_code;
