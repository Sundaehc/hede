# 数据库规范文档

更新时间：2026-06-24

本文档根据当前 PostgreSQL 数据库表结构、SQLAlchemy 表定义和 Alembic 迁移整理，用于后续开发、维护和新增表时统一口径。文档不包含数据库连接串、账号密码和网络路径等敏感配置。

## 1. 总体原则

### 1.1 数据库定位

当前数据库是商品、精细表、供应商、进销存、库存、唯品会和聚水潭数据的业务数据底座。

主要用途：

- 商品基础资料管理
- 商品精细表查询与快照
- 唯品会销售/运营数据沉淀
- 聚水潭库存、价格、订单数据沉淀
- 进销存单据和单据明细管理
- 供应商/工厂管理与评级
- 仓库、一般客户、店铺等基础资料管理

### 1.2 命名规范

- 表名统一使用小写下划线命名：`inventory_records`、`gj_merged_product_info`。
- 字段名统一使用小写下划线命名：`goods_code`、`original_goods_code`、`factory_grade`。
- 主键字段统一为 `id`。
- 时间字段统一使用：
  - `created_at`
  - `updated_at`
- 原始导入数据表应保留：
  - `source_workbook`
  - `source_sheet`
  - `source_row_number`
  - `raw_payload`
  - `extra_fields`
- 可搜索编码字段建议建立普通索引；需要模糊搜索的编码字段可建立 trigram GIN 索引。

### 1.3 字段类型规范

- 文本类字段使用 `TEXT`。
- 金额、价格、数量金额类字段使用 `NUMERIC(10, 2)`。
- 数量类字段可使用 `INTEGER`；如果来源存在小数，使用 `NUMERIC(10, 2)`。
- 日期字段：
  - 原始文本日期保留为 `TEXT`，例如 `date`、`stock_date`。
  - 规范化日期另存为 `DATE`，例如 `date_value`、`stock_date_value`。
- 原始行内容使用 `JSON`。

### 1.4 迁移规范

- 所有结构变更必须新增 Alembic migration。
- migration 文件命名建议：`YYYYMMDD_序号_简短说明.py`。
- 新增字段应同时更新：
  - `backend/domain/fields.py`
  - 对应 schema 文件
  - Alembic migration
  - 必要时更新 repository 的运行时兜底 `ALTER TABLE IF EXISTS`
- 常用查询字段必须评估是否需要索引。

## 2. 当前业务模块与表

### 2.1 商品基础资料

品牌商品资料表：

- `cbanner_mens_products`
- `cbanner_womens_products`
- `yandou_products`
- `eblan_products`

用途：

- 保存各品牌商品档案。
- 以 `sku` 作为品牌内唯一货号。
- 支撑商品管理、图片匹配和精细表基础信息补充。

核心字段：

- `sku`：货号，唯一。
- `original_sku`：原始货号。
- `image_path`：图片路径。
- `group_name`：组别。
- `product_level`：商品等级。
- `cost`：成本。
- `factory_sku`：工厂货号。
- `supplier_name`：供应商名。
- `year`：年份。
- `season_category`：季节分类。

主要约束和索引：

- `UNIQUE(sku)`
- `idx_*_original_sku`
- `idx_*_sku_trgm`
- `idx_*_original_sku_trgm`
- `idx_*_year`

规范：

- 商品货号字段必须保留文本，不允许转为数字。
- Excel 导入时应保留原始 payload，便于追溯。
- `sku` 是品牌商品资料表的唯一键，不同品牌之间不共享唯一约束。

### 2.2 管家婆合并商品信息

表：`gj_merged_product_info`

用途：

- 保存管家婆导出的合并商品资料。
- 是精细表识别品牌、供应商/工厂、商品全名、原始货号的重要来源。

核心字段：

- `source_date`：来源日期文本。
- `source_date_value`：规范化来源日期。
- `fine_table_brand`：精细表品牌。
- `goods_code`：货号。
- `original_goods_code`：原始货号。
- `goods_full_name`：商品全名。
- `factory_code`：工厂货号。
- `product_name`：品名。
- `brand`：品牌。
- `primary_supplier`：主供应商。

主要约束和索引：

- `UNIQUE(source_date, goods_code)`
- `idx_gj_merged_product_info_goods_code`
- `idx_gj_merged_product_info_original_code`
- `idx_gj_merged_product_info_source_date`
- `idx_gj_merged_product_info_source_brand_id_desc`
- `idx_gj_merged_product_info_goods_code_trgm`
- `idx_gj_merged_product_info_original_goods_code_trgm`

规范：

- 业务查询默认应优先取最新 `source_date_value`。
- 供应商/工厂归属优先使用 `primary_supplier`。
- 品牌区分优先使用 `fine_table_brand`。
- 不要用货号前缀硬编码品牌，除非没有供应商或品牌字段可用。

### 2.3 精细表快照

批次表：`fine_table_snapshot_batches`

按年分表：

- `fine_table_snapshot_rows_2024`
- `fine_table_snapshot_rows_2025`
- `fine_table_snapshot_rows_2026`

用途：

- 保存精细表每日/定期快照。
- 用于历史追溯、按日期查看精细表。

批次表核心字段：

- `brand`
- `snapshot_date`
- `total_rows`
- `latest_order_date`

行表核心字段：

- `batch_id`
- `sku`
- `original_sku`
- `row_index`
- `payload`

主要约束和索引：

- 批次表：`UNIQUE(brand, snapshot_date)`
- 行表：`UNIQUE(batch_id, row_index)`
- 行表按 `batch_id + sku`、`batch_id + original_sku` 建索引
- `sku`、`original_sku` 建 trigram 索引用于模糊搜索

规范：

- 新年份快照行表按 `fine_table_snapshot_rows_YYYY` 命名。
- 快照行内容应以 `payload` 保存完整结果，避免历史展示受后续字段变更影响。

### 2.4 笑脸精细表

表：`smiley_fine_table`

用途：

- 保存 smiley/笑脸品牌的精细表快照数据。

核心字段：

- `snapshot_date`
- `sku`
- `original_sku`
- `factory_code`
- `factory_sku`
- `market_price`
- `cost`
- `stock_qty`
- `inbound_qty`
- `daily_sales_total`
- `total_3d_sales`
- `total_7d_sales`
- `total_15d_sales`
- `total_30d_sales`
- `shop_sales`
- `size_stock`
- `return_rates`

主要约束和索引：

- `UNIQUE(snapshot_date, sku)`
- `idx_smiley_fine_table_snapshot_date`
- `idx_smiley_fine_table_sku`
- `idx_smiley_fine_table_original_sku`

规范：

- 笑脸作为独立品牌处理，品牌 key 使用 `smiley`。
- 销售、库存、退货结构化字段优先使用 JSON 保存明细。

## 3. 唯品会与聚水潭数据

### 3.1 唯品会商品日报

表：`vip_product_daily`

用途：

- 保存唯品会不同周期的商品销售、UV、拒退数据。

核心字段：

- `goods_id`
- `goods_code`
- `style_code`
- `sales_amount`
- `sales_volume`
- `detail_uv`
- `reject_count`
- `reject_rate`
- `report_type`
- `period`
- `report_start_date`
- `report_end_date`

主要约束和索引：

- `UNIQUE(report_type, period, goods_id)`
- `idx_vip_daily_goods_code_report_updated`
- `idx_vip_daily_report_dates`

规范：

- 取 30 天销量时使用 `period = '30d'`。
- 拒退率来源字段为 `reject_rate`，解析时需要兼容百分数字符串。

### 3.2 唯品会商品日报快照

表：`vip_product_daily_snapshots`

用途：

- 保存唯品会日报历史快照。
- 用于按快照日期回看日销售和 UV。

主要约束和索引：

- `UNIQUE(snapshot_date, goods_id)`
- `idx_daily_snapshots_code_type_period_date`
- `idx_daily_snapshots_snapshot_date`

规范：

- 查询日销售趋势时按 `goods_code + report_type + period + snapshot_date` 过滤。

### 3.3 唯品会实时数据

表：`vip_product_realtime`

用途：

- 保存商品实时销售和库存表现。

核心字段：

- `goods_id`
- `goods_code`
- `style_code`
- `sales_amount`
- `sales_volume`
- `stock_on_sale`

主要约束：

- `UNIQUE(goods_id)`

### 3.4 唯品会运营数据

表：`vip_product_ops`

快照表：`vip_product_ops_snapshots`

用途：

- 保存商品运营侧价格、状态、标签等信息。

核心字段：

- `goods_code`
- `style_code`
- `goods_id`
- `p_spu`
- `category_l3`
- `goods_status`
- `market_price`
- `vip_price`
- `final_price`
- `sales_tag`
- `goods_tag`

主要约束和索引：

- `vip_product_ops`：`UNIQUE(goods_id)`
- `vip_product_ops_snapshots`：`UNIQUE(snapshot_date, goods_id)`
- `idx_vip_ops_goods_code_updated`
- `idx_ops_snapshots_goods_code_date`

### 3.5 聚水潭价格

表：`jst_product_price`

用途：

- 保存聚水潭商品价格、库存数量、成本价等数据。

核心字段：

- `source_date`
- `source_date_value`
- `goods_code`
- `goods_full_name`
- `stock_qty`
- `latest_purchase_price`
- `cost_unit_price`
- `retail_price`
- `preset_price`

主要约束和索引：

- `UNIQUE(source_date, goods_code, goods_full_name)`
- `idx_jst_price_code_date_updated`
- `idx_jst_price_source_date_value`

规范：

- 成本价取值优先级应在业务代码中统一，例如最近进价、预设价格、成本单价等。

### 3.6 聚水潭订单

表：`jst_monthly_orders`

用途：

- 保存聚水潭订单明细。
- 用于其他渠道销售统计、近 30 天销量、退货数量等。

核心字段：

- `order_time`
- `order_time_at`
- `ship_date`
- `ship_date_value`
- `shop_name`
- `style_code`
- `product_code`
- `quantity`
- `actual_return_qty`
- `cost_price`
- `buyer_paid`
- `seller_received`

主要索引：

- `idx_jst_monthly_orders_style_time`
- `idx_jst_monthly_orders_order_time_at`
- `idx_jst_monthly_orders_product_code`
- `idx_jst_monthly_orders_style_code`
- `idx_jst_monthly_orders_time_product`

规范：

- 时间范围查询应使用 `order_time_at`。
- 商品匹配可按 `style_code` 或 `product_code`，需要在业务逻辑中明确口径。

### 3.7 聚水潭库存

表：`jst_daily_stock`

用途：

- 保存每日聚水潭可用库存。

核心字段：

- `stock_date`
- `stock_date_value`
- `product_code`
- `available_qty`

主要约束和索引：

- `UNIQUE(stock_date, product_code)`
- `idx_jst_stock_product_code`
- `idx_jst_stock_product_code_trgm`
- `idx_jst_stock_date_value_code`
- `idx_jst_stock_date_qty`

表：`jst_size_stock`

用途：

- 保存尺码库存。

核心字段：

- `product_code`
- `size`
- `stock_qty`

主要索引：

- `idx_jst_size_stock_product_size`

表：`jst_stock_summary`

用途：

- 保存次品库存、采购在途、下架仓、订单占有等汇总库存。

核心字段：

- `stock_date`
- `stock_date_value`
- `product_code`
- `defect_stock_qty`
- `purchase_in_transit_qty`
- `off_shelf_qty`
- `order_occupy_qty`

主要约束和索引：

- `UNIQUE(stock_date, product_code)`
- `idx_jst_stock_summary_product_code`
- `idx_jst_stock_summary_date_value_code`

表：`jst_purchase_defects`

用途：

- 保存采购差异/次品在途相关数据。

核心字段：

- `product_code`
- `difference_count`

主要索引：

- `idx_jst_purchase_defects_product_code`

### 3.8 聚水潭售后退货退款

表：`jst_aftersale_returns`

用途：

- 保存共享目录“售后（退货退款）”Excel 中的售后退货明细。
- 用于按原始货号统计供应商退货率，并参与供应商等级评估。

核心字段：

- `original_goods_code`
- `returned_qty`
- `order_date`
- `order_time`
- `platform_site`
- `shop_name`
- `online_order_id`
- `order_date_value`
- `order_time_value`
- `raw_payload`

主要索引：

- `idx_jst_aftersale_returns_original_code`
- `idx_jst_aftersale_returns_order_date`
- `idx_jst_aftersale_returns_order_time`

规范：

- 导入时按整张表刷新，避免旧售后记录残留。
- 供应商退货率按 `original_goods_code` 关联 `gj_merged_product_info.original_goods_code`，优先按售后/订单日期匹配当时的 `primary_supplier`，避免货号换供应商后全部归到最新供应商。
- 售后统计窗口默认取最新售后日期往前 30 天；如果源表有 `order_time`，销量窗口按原始下单日期收窄，否则向前扩展一个 30 天窗口降低售后日期偏差。
- 销量匹配字段为 `jst_monthly_orders.style_code`，并排除状态为 `取消`、`异常`、`被拆分`、`已付款待审核` 的订单。
- 售后表有 `shop_name` 或 `platform_site` 时，销量优先按相同店铺/平台匹配；没有这些字段时按货号总销量匹配。
- 有售后退货但匹配不到销量时，不计算退货率，也不回退使用唯品会拒退率，避免误导供应商等级。

## 4. 进销存模块

### 4.1 单据主表

表：`inventory_records`

用途：

- 保存进销存单据头信息。

核心字段：

- `document_number`：单据编号。
- `date`：原始日期文本。
- `date_value`：规范化日期。
- `supplier`：供应商/客户/出货仓库等，根据单据类型有不同含义。
- `warehouse`：仓库/入货仓库等，根据单据类型有不同含义。
- `document_type`：单据类型。
- `handler`：经手人。
- `summary`：摘要。
- `total_count`：总数量。
- `amount`：总金额。

当前单据类型：

- `进货单`
- `进货退货单`
- `报溢单`
- `报损单`
- `批发销售单`
- `批发销售退货单`
- `同价调拨单`

主要索引：

- `idx_inventory_records_date`
- `idx_inventory_records_date_value`
- `idx_inventory_records_document_number`
- `idx_inventory_records_document_type`
- `idx_inventory_records_supplier`
- `idx_inventory_records_warehouse`

规范：

- `document_number` 格式：`单据类型拼音缩写-YYYY-MM-DD-当日序号`，例如 `JHD-2026-06-17-0001`。
- `total_count` 和 `amount` 应由单据明细自动汇总，不建议手工填写。
- 新增单据默认日期应使用当天日期。

### 4.2 单据明细表

表：`inventory_details`

用途：

- 保存单据商品明细。

核心字段：

- `document_id`：关联 `inventory_records.id`。
- `product_code`：商品编码/货号。
- `product_name`：商品名称。
- `color_spec`：颜色及规格。
- `color_barcode`：颜色条码。
- `color_name`：颜色名称。
- `quantity`：数量。
- `unit_price`：单价。
- `amount`：金额。
- `size_quantities`：尺码数量 JSON。

主要索引：

- `idx_inventory_details_document_id`
- `idx_inventory_details_product_code`
- `idx_inventory_details_product_code_trgm`

规范：

- 明细删除应依赖 `document_id` 关联主表。
- 导入 Excel 时，应按商品编码解析货号、颜色条码和尺码。
- 手动新增明细时，尺码数量由用户填写，`quantity` 由尺码数量自动汇总。
- 金额应由 `quantity * unit_price` 自动计算。

## 5. 基础资料模块

### 5.1 供应商/工厂

表：`suppliers`

用途：

- 保存供应商/工厂基础资料。
- 支撑供应商选择、品牌归属、工厂评级、系统建议。

核心字段：

- `brand`：品牌归属。
- `name`：供应商名称。
- `factory_code`：工厂代码。
- `contact`：联系人。
- `wechat`：微信号。
- `cooperation_status`：合作状态。
- `factory_grade`：工厂等级，A/B/C/D。
- `factory_suggestion`：系统建议。
- `address`：地址。
- `notes`：备注。

主要约束和索引：

- `UNIQUE(brand, name)`
- `idx_suppliers_brand`
- `idx_suppliers_factory_code`
- `idx_suppliers_factory_grade`

品牌 key：

- `cbanner_mens`：千百度男鞋
- `cbanner_womens`：千百度女鞋
- `yandou`：烟斗
- `eblan`：伊伴
- `smiley`：笑脸

规范：

- 供应商品牌归属优先按供应商名称中的品牌关键字判断。
- `factory_grade` 和 `factory_suggestion` 可由系统计算写回。
- 编辑供应商基础资料时，不应误清空已有评级字段。
- 供应商等级采用统一 100 分制，合作状态为 `淘汰` 或 `暂停` 时直接为 D；其他供应商按近 30 天销量、动销率、退货率、款式资料、库存压力统一加减分：
  - 近 30 天销量最高 30 分：`>=800` 得 30，`>=500` 得 26，`>=300` 得 22，`>=100` 得 15，`>=30` 得 8，`>0` 得 3。
  - 动销率最高 25 分：`>=45%` 得 25，`>=35%` 得 22，`>=25%` 得 18，`>=15%` 得 12，`>=8%` 得 6，有销量但低于 8% 得 2。
  - 退货率最高 20 分：无退货率数据得 10，`<5%` 得 20，`<8%` 得 17，`<12%` 得 13，`<15%` 得 8，`<18%` 得 3，`18%-25%` 扣 8，`>=25%` 扣 18。
  - 款式资料最高 10 分：`>=20` 款得 10，`>=10` 款得 8，`>0` 款得 5。
  - 库存压力最高 15 分：库存 `<=100` 得 15，`<=300` 得 10，`<=600` 得 5；库存 `>=1000` 且动销率 `<10%` 扣 25；库存 `>=300` 且近 30 天无销量扣 30。
  - 最终分数限制在 `0-100`；`>=80` 为 A，`>=60` 为 B，`>=25` 为 C，`<25` 为 D。

### 5.2 仓库

表：`warehouses`

用途：

- 保存仓库基础资料。

核心字段：

- `name`
- `address`
- `notes`

主要约束：

- `UNIQUE(name)`

### 5.3 一般客户与店铺

品牌/客户表：`general_customer_brands`

用途：

- 保存一般客户品牌，例如烟斗一般客户。

核心字段：

- `name`

主要约束：

- `UNIQUE(name)`

店铺表：`general_customer_shops`

用途：

- 保存一般客户下属店铺。

核心字段：

- `customer_name`
- `shop_name`

主要约束和索引：

- `UNIQUE(customer_name, shop_name)`
- `idx_general_customer_shops_customer_name`
- `idx_general_customer_shops_shop_name`

规范：

- 店铺归属于一般客户品牌。
- 删除品牌时可以连带删除旗下店铺。

### 5.4 颜色条码

表：`color_barcodes`

用途：

- 保存颜色条码与颜色名称映射。
- 进销存导入明细时根据货号后缀匹配颜色名称。

核心字段：

- `brand`
- `color_barcode`
- `color_name`
- `source_workbook`
- `source_sheet`
- `source_row_number`
- `raw_payload`

主要约束和索引：

- `UNIQUE(brand, color_barcode)`
- `idx_color_barcodes_brand`
- `idx_color_barcodes_color_barcode`
- `idx_color_barcodes_color_name`

## 6. 定时任务状态

表：`scheduled_task_statuses`

用途：

- 保存定时任务运行状态。

核心字段：

- `task_name`
- `business_date`
- `status`
- `source_path`
- `message`
- `result`
- `attempts`
- `first_started_at`
- `last_started_at`
- `finished_at`

主要约束和索引：

- `UNIQUE(task_name, business_date)`
- `idx_scheduled_task_statuses_task_status_date`

规范：

- 每个任务每天应只有一条状态记录。
- `result` 保存结构化结果。
- `message` 保存面向用户或运维的简短错误/结果说明。

## 7. 通用导入表字段规范

凡是由 Excel、共享盘、第三方平台导入的数据表，建议保留以下字段：

- `source_workbook`：来源工作簿。
- `source_sheet`：来源 sheet。
- `source_row_number`：来源行号。
- `raw_payload`：原始行数据。
- `extra_fields`：未映射字段。
- `created_at`：创建时间。
- `updated_at`：更新时间。

作用：

- 支持追溯原始数据。
- 支持字段映射变更后的回查。
- 支持排查导入异常。

## 8. 索引设计规范

### 8.1 必须建索引的字段

- 主查询条件字段：
  - `goods_code`
  - `original_goods_code`
  - `sku`
  - `product_code`
  - `source_date_value`
  - `snapshot_date`
  - `stock_date_value`
  - `order_time_at`
  - `brand`
  - `document_type`
  - `document_number`
- 外键或逻辑关联字段：
  - `document_id`
  - `batch_id`
  - `customer_name`

### 8.2 模糊搜索字段

需要 `LIKE '%xxx%'` 或 `ILIKE '%xxx%'` 的字段，应考虑 trigram GIN 索引：

- 商品货号：`sku`
- 原始货号：`original_sku`
- 管家婆货号：`goods_code`
- 管家婆原始货号：`original_goods_code`
- 进销存商品编码：`inventory_details.product_code`
- 聚水潭库存商品编码：`jst_daily_stock.product_code`

### 8.3 排序字段

如果字段用于列表排序，并且数据量较大，应建立索引：

- `suppliers.factory_grade`
- `inventory_records.date_value`
- `jst_monthly_orders.order_time_at`
- `fine_table_snapshot_batches.snapshot_date`

## 9. 关联关系说明

### 9.1 商品与供应商/工厂

主要关联：

- `gj_merged_product_info.primary_supplier` -> `suppliers.name`
- `gj_merged_product_info.fine_table_brand` -> `suppliers.brand`

说明：

- 当前没有强外键约束，属于业务逻辑关联。
- 供应商名称需要保持稳定，避免同一工厂出现多个不同写法。

### 9.2 商品与库存/销售

常用关联：

- 商品货号：`goods_code` / `sku` / `product_code`
- 原始货号：`original_goods_code` / `original_sku`

说明：

- 不同来源系统字段命名不同，代码中必须明确匹配口径。
- 精细表中通常以货号和原始货号混合聚合库存、销量。

### 9.3 进销存主从关系

物理外键：

- `inventory_details.document_id` -> `inventory_records.id`

删除规则：

- 删除单据主表时，明细应级联删除。

## 10. 新增表规范

新增业务表时建议包含：

- `id BIGINT IDENTITY PRIMARY KEY`
- 必要业务唯一约束
- `created_at`
- `updated_at`

如为导入表，必须额外包含：

- `source_workbook`
- `source_sheet`
- `source_row_number`
- `raw_payload`
- `extra_fields`

新增表必须补充：

- Alembic migration
- domain schema
- repository 读写方法
- 必要 API schema/type
- 前端类型定义
- 本文档对应章节

## 11. 当前注意事项

- `suppliers.factory_grade` 和 `suppliers.factory_suggestion` 已落表，但仍由系统计算写回；不要手动随意覆盖，除非后续明确支持人工调整等级。
- 进销存实际历史数据目前较少，涉及采购、退货、调拨分析时应先确认数据量。
- 商品 ID、货号、条码等字段必须按文本处理，导出 Excel 时也要避免被 Excel 自动转成科学计数法。
- 部分表没有物理外键，是为了兼容多来源导入和历史数据，业务代码需要做好空值、重复值、名称不一致的处理。
