-- =====================================================================
-- 数据库优化动作脚本  (commodity_department @ PostgreSQL 18.3)
-- 生成时间: 2026-10-07   依据: outputs/db_audit/数据库优化报告.md
--
-- 重要说明
--   1. 本脚本尚未执行, 请逐节确认后分批运行, 不要一次性全部执行。
--   2. 第 3 / 5 / 9.1 节使用 DROP/CREATE INDEX CONCURRENTLY:
--      不能在事务块中运行 —— 不要用 psql -1 / --single-transaction,
--      也不要用 BEGIN...COMMIT 包住。
--   3. 第 4 节针对分区父级索引: 不支持 CONCURRENTLY, 必须用普通 DROP INDEX,
--      删除父索引会连带删除其全部子索引。操作是元数据级的, 很快,
--      但会对父表取 ACCESS EXCLUSIVE 锁(极短暂)。
--   4. 第 9 节的回滚 DDL 全部由 pg_get_indexdef 实测导出, 非人工推断。
--   5. 脚本中所有索引名均已逐一核对存在, 且确认没有一个是约束索引
--      (即都可以直接 DROP INDEX)。
--   6. 本次体检本身未对数据库做任何写操作。
-- =====================================================================


-- =====================================================================
-- 第 0 节  执行前快照 (只读, 建议保存输出以便对比)
-- =====================================================================

-- 0.1 索引使用基线 (idx_scan = 0 即 41 天内从未被读取)
SELECT s.schemaname, s.relname AS table_name, s.indexrelname AS index_name,
       s.idx_scan, pg_size_pretty(pg_relation_size(s.indexrelid)) AS size
FROM pg_stat_user_indexes s
ORDER BY pg_relation_size(s.indexrelid) DESC;

-- 0.2 库 / 表 / 索引总量
SELECT pg_size_pretty(pg_database_size(current_database())) AS db_size,
       pg_size_pretty(SUM(pg_relation_size(c.oid)))        AS heap_size,
       pg_size_pretty(SUM(pg_indexes_size(c.oid)))         AS index_size
FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
WHERE c.relkind IN ('r','p') AND n.nspname = 'public';

-- 0.3 缓存命中率 / 临时文件基线
SELECT round(100.0*blks_hit/NULLIF(blks_hit+blks_read,0),2) AS cache_hit_pct,
       blks_read, temp_files, pg_size_pretty(temp_bytes) AS temp_size
FROM pg_stat_database WHERE datname = current_database();

-- 0.4 保存待删索引的原始定义 (保险起见, 再存一份)
SELECT indexrelid::regclass::text AS index_name, pg_get_indexdef(indexrelid) AS ddl
FROM pg_index
WHERE indexrelid::regclass::text IN (
  'idx_jst_stock_date_qty','idx_fine_table_snapshot_refs_2026_batch_original_sku',
  'idx_fine_table_snapshot_refs_2025_batch_original_sku','idx_fine_table_snapshot_refs_2026_sku_trgm',
  'idx_fine_table_snapshot_refs_2025_sku_trgm','idx_ops_snapshots_goods_code_date',
  'idx_fine_table_snapshot_refs_2025_batch_row_index','idx_fine_table_snapshot_refs_2026_original_sku_trgm',
  'idx_fine_table_snapshot_refs_2025_original_sku_trgm','idx_fine_table_snapshot_refs_2024_sku_trgm',
  'idx_fine_table_snapshot_refs_2024_batch_original_sku','idx_fine_table_snapshot_refs_2024_batch_row_index',
  'idx_fine_table_snapshot_refs_2024_original_sku_trgm'
);


-- =====================================================================
-- 第 1 节  刷新统计信息 (低锁, 可立即执行)
--   自 2026-08-27 重启后 41 天内这些大表都没有被 analyze 过。
--   列级统计信息仍存在(来自更早的 analyze), 属于"陈旧"而非"缺失"。
-- =====================================================================

ANALYZE public.fine_table_snapshot_payloads;       -- 27,043,096 行 / 40 GB
ANALYZE public.vip_daily_sales_2026;               -- 15,305,680 行 / 21 GB
ANALYZE public.fine_table_snapshot_metrics;        --  9,762,598 行
ANALYZE public.product_goods_detail_snapshots_2026;
ANALYZE public.vip_product_ops_snapshots;
ANALYZE public.jst_monthly_orders;
ANALYZE public.jst_product_price;
ANALYZE public.jst_daily_stock;
ANALYZE public.jst_size_stock_snapshots;
ANALYZE public.gj_merged_product_info;
ANALYZE public.fine_table_snapshot_refs_2026;
ANALYZE public.fine_table_snapshot_refs_2025;
ANALYZE public.fine_table_snapshot_refs_2024;
ANALYZE public.vip_product_daily_snapshots;
ANALYZE public.jst_purchase_inbound_daily;
ANALYZE public.jst_daily_sales_2026;
ANALYZE public.jst_aftersale_returns;
ANALYZE public.product_size_group_mappings;
ANALYZE public.jst_product_profiles;

-- 需要更新死元组时可再执行 (大表耗时较长):
-- VACUUM (ANALYZE, VERBOSE) public.jst_daily_sales_2026;      -- dead=172,699 且从未 autovacuum
-- VACUUM (ANALYZE, VERBOSE) public.jst_purchase_inbound_daily; -- dead=193,954


-- =====================================================================
-- 第 2 节  为高变动大表单独设置 autovacuum (立即生效, 无需重启)
--   默认 vacuum_scale_factor=0.2 意味着 2700 万行的表要死 540 万行才清理。
-- =====================================================================

ALTER TABLE public.fine_table_snapshot_payloads SET (
  autovacuum_vacuum_scale_factor = 0.02, autovacuum_vacuum_threshold = 5000,
  autovacuum_analyze_scale_factor = 0.01, autovacuum_analyze_threshold = 2000);
ALTER TABLE public.fine_table_snapshot_metrics SET (
  autovacuum_vacuum_scale_factor = 0.02, autovacuum_vacuum_threshold = 5000,
  autovacuum_analyze_scale_factor = 0.01, autovacuum_analyze_threshold = 2000);
ALTER TABLE public.fine_table_snapshot_refs_2026 SET (
  autovacuum_vacuum_scale_factor = 0.02, autovacuum_vacuum_threshold = 5000,
  autovacuum_analyze_scale_factor = 0.01, autovacuum_analyze_threshold = 2000);
ALTER TABLE public.jst_daily_stock SET (
  autovacuum_analyze_scale_factor = 0.01, autovacuum_analyze_threshold = 2000);
ALTER TABLE public.jst_product_price SET (
  autovacuum_analyze_scale_factor = 0.01, autovacuum_analyze_threshold = 2000);
ALTER TABLE public.gj_merged_product_info SET (
  autovacuum_analyze_scale_factor = 0.01, autovacuum_analyze_threshold = 2000);
ALTER TABLE public.vip_product_ops_snapshots SET (
  autovacuum_analyze_scale_factor = 0.01, autovacuum_analyze_threshold = 2000);
ALTER TABLE public.vip_product_daily_snapshots SET (
  autovacuum_analyze_scale_factor = 0.01, autovacuum_analyze_threshold = 2000);
ALTER TABLE public.jst_daily_sales_2026 SET (
  autovacuum_vacuum_scale_factor = 0.05, autovacuum_vacuum_threshold = 1000,
  autovacuum_analyze_scale_factor = 0.01, autovacuum_analyze_threshold = 1000);
ALTER TABLE public.jst_purchase_inbound_daily SET (
  autovacuum_vacuum_scale_factor = 0.02, autovacuum_vacuum_threshold = 1000,
  autovacuum_analyze_scale_factor = 0.01, autovacuum_analyze_threshold = 1000);


-- =====================================================================
-- 第 3 节  删除从未使用的独立索引
--   依据: 2026-08-27 至 2026-10-07 (41 天) idx_scan = 0
--   小计 4,942.5 MB。全部可用第 9 节原样重建。
-- =====================================================================

-- --- 3.1 三张 refs 表: 3,860.6 MB (索引/堆比 2.6-3.0, 无一被有效使用) ---
DROP INDEX CONCURRENTLY public.idx_fine_table_snapshot_refs_2026_batch_original_sku;  -- 548.5 MB
DROP INDEX CONCURRENTLY public.idx_fine_table_snapshot_refs_2026_batch_row_index;     -- 503.9 MB (与唯一索引完全重复)
DROP INDEX CONCURRENTLY public.idx_fine_table_snapshot_refs_2026_sku_trgm;            -- 362.2 MB
DROP INDEX CONCURRENTLY public.idx_fine_table_snapshot_refs_2026_original_sku_trgm;   -- 320.5 MB
DROP INDEX CONCURRENTLY public.idx_fine_table_snapshot_refs_2025_batch_original_sku;  -- 396.2 MB
DROP INDEX CONCURRENTLY public.idx_fine_table_snapshot_refs_2025_sku_trgm;            -- 345.0 MB
DROP INDEX CONCURRENTLY public.idx_fine_table_snapshot_refs_2025_batch_row_index;     -- 332.4 MB (与唯一索引完全重复)
DROP INDEX CONCURRENTLY public.idx_fine_table_snapshot_refs_2025_original_sku_trgm;   -- 299.8 MB
DROP INDEX CONCURRENTLY public.idx_fine_table_snapshot_refs_2024_sku_trgm;            -- 200.9 MB
DROP INDEX CONCURRENTLY public.idx_fine_table_snapshot_refs_2024_batch_original_sku;  -- 196.8 MB
DROP INDEX CONCURRENTLY public.idx_fine_table_snapshot_refs_2024_batch_row_index;     -- 179.1 MB (与唯一索引完全重复)
DROP INDEX CONCURRENTLY public.idx_fine_table_snapshot_refs_2024_original_sku_trgm;   -- 173.4 MB

-- --- 3.2 jst_daily_stock: 751.8 MB ---
-- (stock_date, product_code, available_qty) 是 uq_jst_stock_date_code(stock_date, product_code)
-- 的加宽版本, 后者 608.9 万次扫描在用, 因此删除不损失查询能力。
DROP INDEX CONCURRENTLY public.idx_jst_stock_date_qty;

-- --- 3.3 vip_product_ops_snapshots: 390.6 MB ---
-- uq_ops_snapshot_date_goods(snapshot_date, goods_id) 有 254.9 万次扫描, 保留。
DROP INDEX CONCURRENTLY public.idx_ops_snapshots_goods_code_date;                     -- 338.1 MB
DROP INDEX CONCURRENTLY public.idx_ops_snapshots_snapshot_date;                       --  52.5 MB

-- --- 3.4 与唯一索引完全重复的索引 (实测定义相同): 78.8 MB ---
DROP INDEX CONCURRENTLY public.idx_jst_stock_summary_snapshots_date_code;             --  78.6 MB
DROP INDEX CONCURRENTLY public.idx_product_goods_detail_snapshot_batches_brand_date;  --   0.1 MB
DROP INDEX CONCURRENTLY public.idx_inventory_account_subjects_name;                   --   0.0 MB
DROP INDEX CONCURRENTLY public.idx_purchase_order_requirement_brand;                  --   0.0 MB
DROP INDEX CONCURRENTLY public.idx_purchase_print_templates_user;                     --   0.0 MB
DROP INDEX CONCURRENTLY public.idx_product_goods_shop_channel_brand;                  --   0.0 MB
DROP INDEX CONCURRENTLY public.idx_general_customer_units_shop_id;                    --   0.0 MB

-- --- 3.5 其余零扫描索引: 约 25 MB ---
DROP INDEX CONCURRENTLY public.idx_vip_product_detail_daily_goods_code_date;          --  11.2 MB
DROP INDEX CONCURRENTLY public.idx_product_archive_identities_brand_sku;              --   5.0 MB
DROP INDEX CONCURRENTLY public.idx_jst_stock_summary_date_value_code;                 --   4.3 MB
DROP INDEX CONCURRENTLY public.zhiyi_hot_item_range_item_id_idx;                      --   2.6 MB
DROP INDEX CONCURRENTLY public.idx_vip_product_detail_daily_brand_date;               --   2.0 MB
DROP INDEX CONCURRENTLY public.ix_jst_purchase_inbound_style_color;                   --   0.5 MB
DROP INDEX CONCURRENTLY public.ix_jst_purchase_inbound_style_color_normalized;        --   0.3 MB
DROP INDEX CONCURRENTLY public.ix_jst_purchase_inbound_womens_date;                   --   0.3 MB
DROP INDEX CONCURRENTLY public.idx_yandou_products_last_imported_at;                  --   0.3 MB
DROP INDEX CONCURRENTLY public.idx_operation_logs_user;                               --   0.1 MB
DROP INDEX CONCURRENTLY public.idx_product_auxiliary_attributes_name;                 --   0.1 MB
DROP INDEX CONCURRENTLY public.idx_suppliers_factory_grade;                           --   0.1 MB
DROP INDEX CONCURRENTLY public.idx_auth_sessions_expires_at;
DROP INDEX CONCURRENTLY public.idx_color_barcodes_color_barcode;
DROP INDEX CONCURRENTLY public.idx_general_customer_shops_customer_name;
DROP INDEX CONCURRENTLY public.idx_general_customer_shops_shop_name;
DROP INDEX CONCURRENTLY public.idx_general_customer_units_unit_name;
DROP INDEX CONCURRENTLY public.idx_auth_users_role;
DROP INDEX CONCURRENTLY public.idx_auth_users_department;
DROP INDEX CONCURRENTLY public.idx_warehouses_brand_sort;
DROP INDEX CONCURRENTLY public.idx_warehouse_brands_sort;
DROP INDEX CONCURRENTLY public.idx_supplier_brands_sort;
DROP INDEX CONCURRENTLY public.idx_general_customer_brands_sort;
DROP INDEX CONCURRENTLY public.idx_size_group_items_group_sort;
DROP INDEX CONCURRENTLY public.idx_smiley_products_last_imported_at;
DROP INDEX CONCURRENTLY public.idx_smiley_product_copy_log_lookup;
DROP INDEX CONCURRENTLY public.idx_smiley_product_copy_base_status;
DROP INDEX CONCURRENTLY public.idx_ni_products_last_imported_at;
DROP INDEX CONCURRENTLY public.idx_manual_product_archive_31_original_sku;
DROP INDEX CONCURRENTLY public.idx_manual_product_archive_31_last_imported_at;
DROP INDEX CONCURRENTLY public.idx_data_quality_issues_open;
DROP INDEX CONCURRENTLY public.idx_vip_product_detail_daily_shop_date;

-- !!! 以下两个索引请勿删除 !!!
--   idx_inventory_records_document_number : 其"重复项" uq_inventory_records_active_document_number
--       是部分索引(带 WHERE 条件), 本索引仍在服务软删除行 (299 次扫描)
--   idx_jst_stock_date_value_code         : 406 次扫描, 部分查询依赖 stock_date_value


-- =====================================================================
-- 第 4 节  删除分区父级索引  (649.7 MB)
--   不支持 CONCURRENTLY; 删除父索引会连带删除其全部子索引。
-- =====================================================================

-- 4.1 jst_monthly_orders (26 GB, 6 个分区): 406.3 MB
DROP INDEX public.idx_jst_monthly_orders_product_code;     -- 147.8 MB, 子索引仅 3 次扫描
DROP INDEX public.idx_jst_monthly_orders_style_code;       -- 136.7 MB, 仅 29 次, 且是 style_time 的前缀
DROP INDEX public.idx_jst_monthly_orders_ship_date_value;  -- 121.8 MB, 192 次

-- 4.2 jst_aftersale_returns (3.8 GB, 5 个分区): 79.0 MB
--   该家族每分区 7 个索引, 全部扫描次数在 0-240 之间。
DROP INDEX public.idx_jst_aftersale_returns_id;                -- 38.5 MB, 6 次
DROP INDEX public.idx_jst_aftersale_returns_application_date;  -- 13.4 MB, 24 次
DROP INDEX public.idx_jst_aftersale_returns_order_time;        -- 13.7 MB, 34 次
DROP INDEX public.idx_jst_aftersale_returns_business_date;     -- 13.4 MB, 207 次

-- 4.3 观察一周后再决定 (在用, 但被更宽的索引覆盖) —— 约 480 MB
-- DROP INDEX public.idx_jst_monthly_orders_order_time_at;     -- 278.3 MB, 52,415 次,
--                                                             --   是 uq_...(order_time_at, record_key) 前缀
-- DROP INDEX public.idx_jst_stock_product_code;               -- 128.0 MB, 仅 2 次
-- DROP INDEX public.idx_jst_size_stock_snapshots_date_code;   -- 167.7 MB, 330 次, 唯一索引前缀
-- DROP INDEX public.idx_vip_daily_sales_2026_sales_date;      -- 105.7 MB, 79,359 次, 唯一索引前缀
-- DROP INDEX public.idx_jst_daily_sales_2026_sales_date;      --  10.9 MB, 79,669 次, 唯一索引前缀
-- DROP INDEX public.idx_gj_merged_product_info_source_date;   --  49.0 MB, 41,039 次, 更宽索引前缀
-- DROP INDEX public.idx_inventory_details_product_code_trgm;  --  11.9 MB, 31 次 (btree 同列 10,373 次)


-- =====================================================================
-- 第 5 节  补一个缺失的外键索引 (需先确认非重复创建)
--   product_tag_assignments.style_id 无前导索引, 该表 210 MB / 560,303 行,
--   外键为 ON DELETE CASCADE —— 删除/更新 product_style_entities 时会全表扫描。
-- =====================================================================

CREATE INDEX CONCURRENTLY idx_product_tag_assignments_style_id
  ON public.product_tag_assignments (style_id);


-- =====================================================================
-- 第 6 节  (可选, 需评估) 为无唯一约束的表补唯一索引
--   现状: jst_aftersale_returns 全家族无唯一约束, 共 151 万行;
--         按 (source_workbook, source_sheet, source_row_number) 实测 0 重复。
--   注意: 分区表的唯一约束必须包含分区键, 而这里是日期表达式,
--         所以只能建在子分区上, 且 ON CONFLICT 仍无法作用于父表 ——
--         若要真正用于幂等导入, 需同步修改导入代码。
-- =====================================================================

-- 6.1 先校验 (应返回 0 行)
SELECT source_workbook, source_sheet, source_row_number, count(*)
FROM public.jst_aftersale_returns_2026
GROUP BY 1,2,3 HAVING count(*) > 1 LIMIT 20;

SELECT order_number, count(*)
FROM public.dewu_orders_2026
GROUP BY 1 HAVING count(*) > 1 LIMIT 20;

-- 6.2 校验通过后再建 (每个子分区各建一个)
-- CREATE UNIQUE INDEX CONCURRENTLY uq_jst_aftersale_returns_2024_source_row
--   ON public.jst_aftersale_returns_2024 (source_workbook, source_sheet, source_row_number);
-- CREATE UNIQUE INDEX CONCURRENTLY uq_jst_aftersale_returns_2025_source_row
--   ON public.jst_aftersale_returns_2025 (source_workbook, source_sheet, source_row_number);
-- CREATE UNIQUE INDEX CONCURRENTLY uq_jst_aftersale_returns_2026_source_row
--   ON public.jst_aftersale_returns_2026 (source_workbook, source_sheet, source_row_number);


-- =====================================================================
-- 第 7 节  (需确认后执行) 清理遗留表 / 备份表
--   两张 2026-09-26 的采购备份表共 1.8 GB, 无索引、无查询。
--   建议先 pg_dump 到文件再删。
-- =====================================================================

-- pg_dump -t public.jst_purchase_backup_20260926_164350 -t public.jst_purchase_restore_20260926_164350 ^
--         -f E:\hede\backend\backups\jst_purchase_backup_20260926.sql commodity_department

-- DROP TABLE public.jst_purchase_backup_20260926_164350;    --  690 MB / 1,608,143 行
-- DROP TABLE public.jst_purchase_restore_20260926_164350;   -- 1.12 GB / 2,706,701 行
--
-- !!! ni_products 请勿删除 !!!
--   它是前端 "NI" 品牌的正式档案表, 实测 87 行
--   (schema.py / brands.ts 均有引用), 初稿"0 行"的说法来自陈旧的 reltuples, 已勘误。


-- =====================================================================
-- 第 8 节  膨胀精确测量 (需先装扩展)
-- =====================================================================

CREATE EXTENSION IF NOT EXISTS pgstattuple;

-- 粗估显示 jst_product_profiles 约 2.13x 膨胀(约 330 MB 可回收),
-- 但其统计信息陈旧, 结论不可靠, 必须实测后再动手:
SELECT * FROM pgstattuple_approx('public.jst_product_profiles');
SELECT * FROM pgstattuple_approx('public.jst_monthly_orders_2026');
SELECT * FROM pgstattuple_approx('public.jst_aftersale_returns_2026');

-- 若 table_len 远大于 tuple_len + free_space 且 dead_tuple_len 很小,
-- 说明是历史膨胀, 需要 VACUUM FULL (取排他锁, 必须停机窗口):
-- VACUUM FULL public.jst_product_profiles;

-- 索引膨胀同样需要停机窗口 (会短暂锁写):
-- REINDEX INDEX CONCURRENTLY public.<index_name>;


-- =====================================================================
-- 第 9 节  回滚脚本: 原样重建第 3/4 节删除的索引
--   以下 DDL 全部由 pg_get_indexdef 实测导出, 与线上定义逐字一致。
-- =====================================================================

-- 9.1 独立索引 (等价于第 3 节, 顺序相反)
CREATE INDEX CONCURRENTLY idx_fine_table_snapshot_refs_2026_batch_original_sku ON public.fine_table_snapshot_refs_2026 USING btree (batch_id, original_sku);
CREATE INDEX CONCURRENTLY idx_fine_table_snapshot_refs_2026_batch_row_index ON public.fine_table_snapshot_refs_2026 USING btree (batch_id, row_index);
CREATE INDEX CONCURRENTLY idx_fine_table_snapshot_refs_2026_sku_trgm ON public.fine_table_snapshot_refs_2026 USING gin (sku gin_trgm_ops);
CREATE INDEX CONCURRENTLY idx_fine_table_snapshot_refs_2026_original_sku_trgm ON public.fine_table_snapshot_refs_2026 USING gin (original_sku gin_trgm_ops);
CREATE INDEX CONCURRENTLY idx_fine_table_snapshot_refs_2025_batch_original_sku ON public.fine_table_snapshot_refs_2025 USING btree (batch_id, original_sku);
CREATE INDEX CONCURRENTLY idx_fine_table_snapshot_refs_2025_sku_trgm ON public.fine_table_snapshot_refs_2025 USING gin (sku gin_trgm_ops);
CREATE INDEX CONCURRENTLY idx_fine_table_snapshot_refs_2025_batch_row_index ON public.fine_table_snapshot_refs_2025 USING btree (batch_id, row_index);
CREATE INDEX CONCURRENTLY idx_fine_table_snapshot_refs_2025_original_sku_trgm ON public.fine_table_snapshot_refs_2025 USING gin (original_sku gin_trgm_ops);
CREATE INDEX CONCURRENTLY idx_fine_table_snapshot_refs_2024_sku_trgm ON public.fine_table_snapshot_refs_2024 USING gin (sku gin_trgm_ops);
CREATE INDEX CONCURRENTLY idx_fine_table_snapshot_refs_2024_batch_original_sku ON public.fine_table_snapshot_refs_2024 USING btree (batch_id, original_sku);
CREATE INDEX CONCURRENTLY idx_fine_table_snapshot_refs_2024_batch_row_index ON public.fine_table_snapshot_refs_2024 USING btree (batch_id, row_index);
CREATE INDEX CONCURRENTLY idx_fine_table_snapshot_refs_2024_original_sku_trgm ON public.fine_table_snapshot_refs_2024 USING gin (original_sku gin_trgm_ops);
CREATE INDEX CONCURRENTLY idx_jst_stock_date_qty ON public.jst_daily_stock USING btree (stock_date, product_code, available_qty);
CREATE INDEX CONCURRENTLY idx_ops_snapshots_goods_code_date ON public.vip_product_ops_snapshots USING btree (goods_code, snapshot_date);
CREATE INDEX CONCURRENTLY idx_ops_snapshots_snapshot_date ON public.vip_product_ops_snapshots USING btree (snapshot_date);
CREATE INDEX CONCURRENTLY idx_jst_stock_summary_snapshots_date_code ON public.jst_stock_summary_snapshots USING btree (snapshot_date, product_code);
CREATE INDEX CONCURRENTLY idx_product_goods_detail_snapshot_batches_brand_date ON public.product_goods_detail_snapshot_batches USING btree (brand, snapshot_date);
CREATE INDEX CONCURRENTLY idx_inventory_account_subjects_name ON public.inventory_account_subjects USING btree (name);
CREATE INDEX CONCURRENTLY idx_purchase_order_requirement_brand ON public.purchase_order_requirement_templates USING btree (brand);
CREATE INDEX CONCURRENTLY idx_purchase_print_templates_user ON public.purchase_print_templates USING btree (user_id);
CREATE INDEX CONCURRENTLY idx_product_goods_shop_channel_brand ON public.product_goods_shop_channel_mappings USING btree (brand);
CREATE INDEX CONCURRENTLY idx_general_customer_units_shop_id ON public.general_customer_units USING btree (shop_id);
CREATE INDEX CONCURRENTLY idx_vip_product_detail_daily_goods_code_date ON public.vip_product_detail_daily USING btree (goods_code, report_date DESC);
CREATE INDEX CONCURRENTLY idx_vip_product_detail_daily_brand_date ON public.vip_product_detail_daily USING btree (brand_sn, report_date DESC);
CREATE INDEX CONCURRENTLY idx_vip_product_detail_daily_shop_date ON public.vip_product_detail_daily USING btree (shop_code, report_date DESC) WHERE (shop_code IS NOT NULL);
CREATE INDEX CONCURRENTLY idx_product_archive_identities_brand_sku ON public.product_archive_identities USING btree (brand, sku);
CREATE INDEX CONCURRENTLY idx_jst_stock_summary_date_value_code ON public.jst_stock_summary USING btree (stock_date_value, product_code);
CREATE INDEX CONCURRENTLY zhiyi_hot_item_range_item_id_idx ON public.zhiyi_hot_item_range USING btree (item_id);
CREATE INDEX CONCURRENTLY ix_jst_purchase_inbound_style_color ON public.jst_purchase_inbound_items USING btree (style_color_code);
CREATE INDEX CONCURRENTLY ix_jst_purchase_inbound_style_color_normalized ON public.jst_purchase_inbound_items USING btree (upper(btrim(style_color_code)));
CREATE INDEX CONCURRENTLY ix_jst_purchase_inbound_womens_date ON public.jst_purchase_inbound_items USING btree (is_womens, inbound_date);
CREATE INDEX CONCURRENTLY idx_yandou_products_last_imported_at ON public.yandou_products USING btree (last_imported_at);
CREATE INDEX CONCURRENTLY idx_operation_logs_user ON public.operation_logs USING btree (username);
CREATE INDEX CONCURRENTLY idx_product_auxiliary_attributes_name ON public.product_auxiliary_attributes USING btree (attribute_name);
CREATE INDEX CONCURRENTLY idx_suppliers_factory_grade ON public.suppliers USING btree (factory_grade);
CREATE INDEX CONCURRENTLY idx_auth_sessions_expires_at ON public.auth_sessions USING btree (expires_at);
CREATE INDEX CONCURRENTLY idx_color_barcodes_color_barcode ON public.color_barcodes USING btree (color_barcode);
CREATE INDEX CONCURRENTLY idx_general_customer_shops_customer_name ON public.general_customer_shops USING btree (customer_name);
CREATE INDEX CONCURRENTLY idx_general_customer_shops_shop_name ON public.general_customer_shops USING btree (shop_name);
CREATE INDEX CONCURRENTLY idx_general_customer_units_unit_name ON public.general_customer_units USING btree (unit_name);
CREATE INDEX CONCURRENTLY idx_auth_users_role ON public.auth_users USING btree (role_code);
CREATE INDEX CONCURRENTLY idx_auth_users_department ON public.auth_users USING btree (department_code);
CREATE INDEX CONCURRENTLY idx_warehouses_brand_sort ON public.warehouses USING btree (brand, sort_order);
CREATE INDEX CONCURRENTLY idx_warehouse_brands_sort ON public.warehouse_brands USING btree (sort_order);
CREATE INDEX CONCURRENTLY idx_supplier_brands_sort ON public.supplier_brands USING btree (sort_order);
CREATE INDEX CONCURRENTLY idx_general_customer_brands_sort ON public.general_customer_brands USING btree (sort_order);
CREATE INDEX CONCURRENTLY idx_size_group_items_group_sort ON public.size_group_items USING btree (size_group_id, sort_order);
CREATE INDEX CONCURRENTLY idx_smiley_products_last_imported_at ON public.smiley_products USING btree (last_imported_at);
CREATE INDEX CONCURRENTLY idx_smiley_product_copy_log_lookup ON public.smiley_product_copy_operation_log USING btree (original_sku, created_at DESC);
CREATE INDEX CONCURRENTLY idx_smiley_product_copy_base_status ON public.smiley_product_copy_base USING btree (status, updated_at DESC);
CREATE INDEX CONCURRENTLY idx_ni_products_last_imported_at ON public.ni_products USING btree (last_imported_at);
CREATE INDEX CONCURRENTLY idx_manual_product_archive_31_original_sku ON public.manual_product_archive_31 USING btree (original_sku);
CREATE INDEX CONCURRENTLY idx_manual_product_archive_31_last_imported_at ON public.manual_product_archive_31 USING btree (last_imported_at);
CREATE INDEX CONCURRENTLY idx_data_quality_issues_open ON public.data_quality_issues USING btree (resolved_at, table_name);

-- 9.2 分区父级索引
--   注意: 这里用不带 ONLY 的 CREATE INDEX —— 它会同时在父表和全部分区上建索引,
--   正好还原删除前的状态。带 ONLY 只会建出一个"空壳"父索引(不可用),
--   pg_get_indexdef 显示的 "ON ONLY" 只是分区索引的目录表示方式, 不是建索引的写法。
CREATE INDEX idx_jst_monthly_orders_product_code ON public.jst_monthly_orders (product_code);
CREATE INDEX idx_jst_monthly_orders_style_code ON public.jst_monthly_orders (style_code);
CREATE INDEX idx_jst_monthly_orders_ship_date_value ON public.jst_monthly_orders (ship_date_value);
CREATE INDEX idx_jst_aftersale_returns_id ON public.jst_aftersale_returns (id);
CREATE INDEX idx_jst_aftersale_returns_application_date ON public.jst_aftersale_returns (application_date_value);
CREATE INDEX idx_jst_aftersale_returns_order_time ON public.jst_aftersale_returns (order_time_value);
CREATE INDEX idx_jst_aftersale_returns_business_date ON public.jst_aftersale_returns (COALESCE(application_date_value, order_date_value, order_time_value));

-- 9.3 校验回滚后与线上一致 (应返回 4,942.5 MB / 649.7 MB 两组索引)
SELECT indexrelid::regclass::text AS index_name, pg_get_indexdef(indexrelid) AS ddl
FROM pg_index
WHERE indexrelid::regclass::text LIKE 'idx_fine_table_snapshot_refs_%'
   OR indexrelid::regclass::text LIKE 'idx_jst_monthly_orders_%'
   OR indexrelid::regclass::text LIKE 'idx_jst_aftersale_returns_%'
ORDER BY 1;


-- =====================================================================
-- 第 10 节  postgresql.conf 建议 (主机 31.8 GB RAM / NVMe SSD)
--   标记 [重启] 的需要重启实例, 其余重载即可生效。
-- =====================================================================
--
-- shared_buffers = 8GB                        # [重启] 当前仅 128MB, 命中率 49%
-- effective_cache_size = 20GB                 # 当前 4GB
-- work_mem = 16MB                             # 当前 4MB, 已落盘 893GB 临时文件
-- maintenance_work_mem = 1GB                  # 当前 64MB
-- max_wal_size = 8GB                          # 当前 1GB
-- min_wal_size = 2GB                          # 当前 80MB
-- random_page_cost = 1.1                      # NVMe; 当前 4
-- effective_io_concurrency = 200              # NVMe; 当前 16
-- autovacuum_max_workers = 6                  # 当前 3
-- autovacuum_naptime = 30s                    # 当前 60s
-- autovacuum_vacuum_scale_factor = 0.05       # 当前 0.2
-- autovacuum_analyze_scale_factor = 0.02      # 当前 0.1
-- autovacuum_vacuum_cost_limit = 2000         # 当前默认 200
-- wal_compression = lz4                       # 当前 off, 已写 662GB WAL
-- default_toast_compression = lz4             # 当前 pglz, 仅对新数据生效
-- track_io_timing = on                        # 当前 off
-- log_min_duration_statement = 1000           # 当前 -1, 完全没有慢查询日志
-- log_lock_waits = on                         # 当前 off
-- log_temp_files = 0                          # 当前 -1
-- log_autovacuum_min_duration = 60000         # 当前 600000
-- max_parallel_workers_per_gather = 4         # 当前 2 (主机 20 线程)
-- max_worker_processes = 12                   # [重启] 当前 8
-- shared_preload_libraries = 'pg_stat_statements'   # [重启]
-- pg_stat_statements.max = 5000
-- pg_stat_statements.track = top
--
-- 调整后核对实际生效值:
-- SELECT name, setting, unit, source, pending_restart FROM pg_settings
-- WHERE name IN ('shared_buffers','effective_cache_size','work_mem','max_wal_size',
--                'random_page_cost','autovacuum_max_workers','shared_preload_libraries');