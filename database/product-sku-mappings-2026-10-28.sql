CREATE TABLE IF NOT EXISTS public.product_sku_mappings (
    sku TEXT PRIMARY KEY,
    original_sku TEXT NOT NULL,
    CONSTRAINT product_sku_mappings_sku_not_blank CHECK (length(trim(sku)) > 0),
    CONSTRAINT product_sku_mappings_original_not_blank CHECK (length(trim(original_sku)) > 0)
);

CREATE INDEX IF NOT EXISTS idx_product_sku_mappings_original_sku
    ON public.product_sku_mappings (original_sku);
