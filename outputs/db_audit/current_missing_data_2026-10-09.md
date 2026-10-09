# 数据库缺失数据周报

> 本报告为 2026-10-09 人工触发的当前数据库只读复核，不是计划任务自动运行。对比基线为 2026-10-08 14:11:12；下文“上周”均指该基线。数据库会话强制 `default_transaction_read_only=on`，未改动业务数据或定时巡检状态文件。

## 当前重点结论（含追加复核）

- 精细表快照缺少 2026-08-16 至 2026-08-23 共 8 天；千百度男鞋、千百度女鞋、伊伴、烟斗四个品牌均无这些日期的批次。2026-10-08 最新批次的明细行数与批次声明行数一致。
- 2026-07 至 2026-10 聚水潭订单共有 811,910 行未写入 `record_key`，占这些月份当前记录的 100%。近三个月按订单号、货号、下单时间筛出的疑似重复多余行共 83 行，需核对后再去重。
- 进销存共 1,392 条明细未关联商品身份，其中未删除单据下有 1,331 条、软删除单据下有 61 条。全部未关联明细中，917 条货号能在商品档案中查到；是否属于自动匹配逻辑问题仍需进一步排查。
- 笑脸商品档案 442 条中有 56 条缺少成本，缺失率 12.67%；2026-10-08 基线为 53 条。
- 追加全年日期复核发现：聚水潭订单在 2026-01-01 至 2026-10-08 期间，仅 2026-05-31 完全无订单记录。是否确有订单漏导，必须与源文件或上游系统对账，不能仅凭日期缺口确定。
- 2026-10-09 得物导入已失败两次，最近一次为数据库时间 09:50（UTC+8）；错误为千百度得物订单源文件缺少大量预期表头。数据库现有订单最新日期仍为 2026-10-08，今日源文件是否有未导入订单尚未核实。
- 库存历史断档已经补齐：2026-05-14 至 2026-10-08 共 148 天连续有数据，2026-10-09 也已有库存快照。不能继续引用旧报告的“库存缺49天”结论。
- 最近 90 天，聚水潭销售日报、唯品会销售日报、商品明细快照及得物订单均无整日日期断档，最新日期为 2026-10-08；这不代表已经逐条与源系统对账。唯品会商品日快照最新日期为 2026-10-07，但该序列不按必须每日生成处理。
- 163 项既有检查全部成功完成。追加全年订单日期检查首次使用逐日查询超时，改为一次聚合后成功完成。大表行数仍采用目录估算，不能据此断言完全没有数据丢失。

优先核查今日得物导入故障，其次修复订单去重键写入并评估历史回填，再补商品身份关联、精细表历史快照及商品成本。

- **生成时间**：2026-10-09 09:55:10
- **数据库**：`commodity_department`
- **日期断档检查区间**：最近 90 天
- **耗时**：102.6 秒 ｜ **检查项**：163 项
- **性质**：只读检查，未修改任何数据

## 一、结论

本次共检查 **163** 项：🔴 需要处理 **8** 项、🟡 需要关注 **8** 项、⚪ 已知长期为空/仅记录 **67** 项、✅ 正常 **80** 项。

**有 8 项需要处理**（见第二节）。

> 图例：🔴 需要处理 ｜ 🟡 需要关注 ｜ ⚪ 已知长期为空（只关注是否恶化） ｜ ✅ 正常

## 二、🔴 需要处理

**日期断档**

| 检查项 | 结果 | 说明 |
|---|---|---|
| 精细表快照明细 | 缺 8/90 天 | 缺失：2026-08-16, 2026-08-17, 2026-08-18, 2026-08-19, 2026-08-20, 2026-08-21, 2026-08-22, 2026-08-23 |

**去重键覆盖**

| 检查项 | 结果 | 说明 |
|---|---|---|
| jst_monthly_orders 2026-07 的 record_key | 缺失 210,432/210,432（100.0%） | 去重键未写入 → 唯一约束失效 |
| jst_monthly_orders 2026-08 的 record_key | 缺失 248,996/248,996（100.0%） | 去重键未写入 → 唯一约束失效 |
| jst_monthly_orders 2026-09 的 record_key | 缺失 277,636/277,636（100.0%） | 去重键未写入 → 唯一约束失效 |
| jst_monthly_orders 2026-10 的 record_key | 缺失 74,846/74,846（100.0%） | 去重键未写入 → 唯一约束失效 |
| 疑似重复订单行（近 3 个月，按订单号+货号+下单时间） | 83 行 | 需要去重 |

**进销存勾稽**

| 检查项 | 结果 | 说明 |
|---|---|---|
| 未关联商品身份的明细 | 1,392 | 需要处理 |
| ↳ 其中货号在档案中（本应能匹配） | 917 | 触发器未解析出身份 |

## 三、🟡 需要关注

**进销存**

| 检查项 | 结果 | 说明 |
|---|---|---|
| inventory_details.product_identity_id | 空值 1.15%（1,392/120,959） | 超过阈值 1.0% |

**商品档案**

| 检查项 | 结果 | 说明 |
|---|---|---|
| smiley_products.cost | 空值 12.67%（56/442） | 超过阈值 5.0% |
| 跨品牌重复货号 | 1 | 同一货号出现在多个品牌档案 |

**进销存勾稽**

| 检查项 | 结果 | 说明 |
|---|---|---|
| total_count 与明细合计不符（明细数量完整） | 903 | 需要处理 |
| amount 与明细合计不符 | 903 | 需要处理 |
| 明细 amount ≠ 数量 × 单价 | 1,359 | 需要处理 |
| 挂在已软删除单据下的明细行 | 3,958 |  |

**运维信号**

| 检查项 | 结果 | 说明 |
|---|---|---|
| 超过 7 天未 ANALYZE 的大表 | 24 张 | 统计信息陈旧会拖慢查询计划 |

## 四、⚪ 已知长期为空 / 仅作记录

**进销存**

| 检查项 | 结果 | 说明 |
|---|---|---|
| inventory_records.total_count | 空值 5.41%（361/6,676） | 上周 5.48% → ↓0.07pp |
| inventory_records.supplier | 空值 3.34%（223/6,676） | 上周 2.81% → ↑0.53pp |
| inventory_details.product_code | 空值 0.30%（361/120,959） | 与上周持平 |
| inventory_details.color_spec | 空值 0.30%（363/120,959） | 与上周持平 |

**商品档案**

| 检查项 | 结果 | 说明 |
|---|---|---|
| cbanner_mens_products.image_path | 空值 1.32%（260/19,675） | 与上周持平 |
| cbanner_mens_products.product_level | 空值 21.05%（4,142/19,675） | 上周 21.12% → ↓0.07pp |
| cbanner_mens_products.group_name | 空值 14.77%（2,906/19,675） | 与上周持平 |
| cbanner_mens_products.category | 空值 6.95%（1,367/19,675） | 与上周持平 |
| cbanner_mens_products.last_imported_at | 空值 97.80%（19,243/19,675） | 与上周持平 |
| cbanner_womens_products.image_path | 空值 18.75%（2,992/15,958） | 与上周持平 |
| cbanner_womens_products.product_level | 空值 73.45%（11,721/15,958） | 与上周持平 |
| cbanner_womens_products.group_name | 空值 0.00%（0/15,958） | 与上周持平 |
| cbanner_womens_products.category | 空值 6.35%（1,014/15,958） | 上周 6.24% → ↑0.12pp |
| cbanner_womens_products.last_imported_at | 空值 99.89%（15,940/15,958） | 上周 99.82% → ↑0.06pp |
| yandou_products.image_path | 空值 81.17%（14,011/17,261） | 与上周持平 |
| yandou_products.product_level | 空值 100.00%（17,261/17,261） | 与上周持平 |
| yandou_products.group_name | 空值 100.00%（17,261/17,261） | 与上周持平 |
| yandou_products.category | 空值 9.12%（1,574/17,261） | 与上周持平 |
| yandou_products.last_imported_at | 空值 100.00%（17,261/17,261） | 与上周持平 |
| eblan_products.image_path | 空值 1.77%（182/10,259） | 与上周持平 |
| eblan_products.product_level | 空值 30.30%（3,108/10,259） | 与上周持平 |
| eblan_products.group_name | 空值 99.91%（10,250/10,259） | 与上周持平 |
| eblan_products.category | 空值 2.65%（272/10,259） | 与上周持平 |
| eblan_products.last_imported_at | 空值 99.96%（10,255/10,259） | 与上周持平 |
| smiley_products.image_path | 空值 0.00%（0/442） | 与上周持平 |
| smiley_products.product_level | 空值 100.00%（442/442） | 与上周持平 |
| smiley_products.group_name | 空值 100.00%（442/442） | 与上周持平 |
| smiley_products.category | 空值 13.57%（60/442） | 上周 12.98% → ↑0.59pp |
| smiley_products.last_imported_at | 空值 41.86%（185/442） | 上周 41.46% → ↑0.40pp |
| ni_products.image_path | 空值 0.00%（0/87） | 与上周持平 |
| ni_products.product_level | 空值 100.00%（87/87） | 与上周持平 |
| ni_products.group_name | 空值 0.00%（0/87） | 与上周持平 |
| ni_products.category | 空值 100.00%（87/87） | 与上周持平 |
| ni_products.last_imported_at | 空值 100.00%（87/87） | 与上周持平 |
| manual_product_archive_31.image_path | 空值 100.00%（37/37） | 与上周持平 |
| manual_product_archive_31.product_level | 空值 100.00%（37/37） | 与上周持平 |
| manual_product_archive_31.group_name | 空值 0.00%（0/37） | 与上周持平 |
| manual_product_archive_31.category | 空值 24.32%（9/37） | 与上周持平 |
| manual_product_archive_31.last_imported_at | 空值 0.00%（0/37） | 与上周持平 |
| cbanner_mens_products 图片路径缺失 | 260/19,675（1.3%） | 与上周持平｜19,243 行无导入时间戳｜最近导入：2026-09-15 18:09:40.781897+08:00 |
| cbanner_womens_products 图片路径缺失 | 2,992/15,958（18.7%） | 与上周持平｜15,940 行无导入时间戳｜最近导入：2026-10-06 14:01:18.048977+08:00 |
| yandou_products 图片路径缺失 | 14,011/17,261（81.2%） | 与上周持平｜17,261 行无导入时间戳｜最近导入：从未 |
| eblan_products 图片路径缺失 | 182/10,259（1.8%） | 与上周持平｜10,255 行无导入时间戳｜最近导入：2026-09-11 17:11:05.309138+08:00 |
| smiley_products 图片路径缺失 | 0/442（0.0%） | 与上周持平｜最近导入：2026-08-10 10:56:18.464891+08:00 |
| ni_products 图片路径缺失 | 0/87（0.0%） | 与上周持平｜87 行无导入时间戳｜最近导入：从未 |
| manual_product_archive_31 图片路径缺失 | 37/37（100.0%） | 与上周持平｜最近导入：2026-09-15 16:02:02.497052+08:00 |

**聚水潭订单**

| 检查项 | 结果 | 说明 |
|---|---|---|
| jst_monthly_orders_2026.cost_price | 空值 100.00%（3,348,465/3,348,465） | 与上周持平 |
| jst_monthly_orders_2026.category | 空值 100.00%（3,348,465/3,348,465） | 与上周持平 |
| jst_monthly_orders_2026.registered_qty | 空值 100.00%（3,348,465/3,348,465） | 与上周持平 |
| jst_monthly_orders_2026.actual_return_qty | 空值 100.00%（3,348,465/3,348,465） | 与上周持平 |
| jst_monthly_orders_2026.address | 空值 100.00%（3,348,465/3,348,465） | 与上周持平 |
| jst_monthly_orders_2026.shop_style_code | 空值 100.00%（3,348,465/3,348,465） | 与上周持平 |

**聚水潭价格**

| 检查项 | 结果 | 说明 |
|---|---|---|
| jst_product_price.latest_purchase_price | 空值 25.53%（2,338,169/9,159,147）（近 120 天） | 与上周持平 |
| jst_product_price.cost_unit_price | 空值 72.79%（6,667,350/9,159,147）（近 120 天） | 与上周持平 |
| jst_product_price.retail_price | 空值 89.50%（8,197,768/9,159,147）（近 120 天） | 与上周持平 |
| jst_product_price.member_price | 空值 100.00%（9,159,147/9,159,147）（近 120 天） | 与上周持平 |

**唯品会**

| 检查项 | 结果 | 说明 |
|---|---|---|
| vip_product_ops_snapshots.goods_tag | 空值 61.93%（2,048,550/3,307,933）（近 120 天） | 上周 61.84% → ↑0.09pp |
| vip_product_detail_daily.shop_code | 空值 100.00%（252,923/252,923） | 与上周持平 |

**其它分析表**

| 检查项 | 结果 | 说明 |
|---|---|---|
| gj_merged_product_info.disabled_flag | 空值 94.31%（3,593,173/3,809,923）（近 120 天） | 与上周持平 |
| jst_full_stock.safety_stock_min_qty | 空值 100.00%（248,528/248,528） | 与上周持平 |
| suppliers.contact | 空值 95.53%（1,004/1,051） | 与上周持平 |

**日期断档**

| 检查项 | 结果 | 说明 |
|---|---|---|
| 唯品会商品日快照 | 缺 12/89 天 | 缺失：2026-07-13, 2026-08-02, 2026-08-04, 2026-08-07, 2026-08-23, 2026-08-25, 2026-08-28, 2026-08-31, 2026-09-01, 2026-09-11, 2026-09-29, 2026-09-30｜该表为不定期采集，仅作记录 |

**进销存勾稽**

| 检查项 | 结果 | 说明 |
|---|---|---|
| 单据总数 | 6,676 |  |
| 已软删除单据 | 478 |  |
| ↳ 上述明细的金额合计 | 20,115,457.13 | 统计若未过滤 deleted_at 会虚增此金额 |

**运维信号**

| 检查项 | 结果 | 说明 |
|---|---|---|
| 数据库大小 | 185 GB |  |
| 精确为空的表 | 9 张 | data_quality_issues、dewu_orders_2027、dewu_orders_default、jst_aftersale_returns_2027、jst_aftersale_returns_default、jst_monthly_orders_2023、jst_monthly_orders_2027、jst_monthly_orders_default、product_style_entities |

## 五、✅ 检查通过

**数据丢失监测**

| 检查项 | 结果 | 说明 |
|---|---|---|
| inventory_records | 6,676 行 / 5.8 MB | 较上周 +87 |
| inventory_details | 120,959 行 / 121.5 MB | 较上周 +736 |
| suppliers | 1,051 行 / 2.0 MB | 较上周 +2 |
| warehouses | 37 行 / 0.1 MB | 较上周 +4 |
| cbanner_mens_products | 19,675 行 / 67.6 MB | 较上周 +0 |
| cbanner_womens_products | 15,958 行 / 51.0 MB | 较上周 +20 |
| yandou_products | 17,261 行 / 57.7 MB | 较上周 +0 |
| eblan_products | 10,259 行 / 37.6 MB | 较上周 +0 |
| smiley_products | 442 行 / 1.6 MB | 较上周 +3 |
| ni_products | 87 行 / 0.3 MB | 较上周 +0 |
| manual_product_archive_31 | 37 行 / 0.2 MB | 较上周 +0 |
| product_archive_identities | 63,742 行 / 33.7 MB | 较上周 +23 |
| product_size_group_mappings | 61,616 行 / 23.6 MB | 较上周 +0 |
| product_goods_overrides | 21,793 行 / 5.4 MB | 较上周 +42 |
| jst_monthly_orders（估算） | 14,488,242 行 / 26.00 GB | 估算值较上周 +937；行数为目录估算值 |
| jst_product_price（估算） | 9,303,194 行 / 6.85 GB | 估算值较上周 +62,626；行数为目录估算值 |
| jst_daily_stock（估算） | 22,264,560 行 / 6.53 GB | 估算值较上周 +315,510；行数为目录估算值 |
| jst_size_stock_snapshots（估算） | 11,473,462 行 / 2.17 GB | 估算值较上周 +0；行数为目录估算值 |
| jst_daily_sales（估算） | 1,252,136 行 / 2.57 GB | 估算值较上周 +1,305；行数为目录估算值 |
| jst_purchase_inbound_daily（估算） | 3,665,807 行 / 2.32 GB | 估算值较上周 +0；行数为目录估算值 |
| jst_full_stock | 248,528 行 / 259.7 MB | 较上周 +196 |
| jst_stock_summary | 31,277 行 / 23.2 MB | 较上周 +0 |
| jst_stock_summary_snapshots（估算） | 2,362,613 行 / 477.8 MB | 估算值较上周 +0；行数为目录估算值 |
| jst_size_stock | 159,574 行 / 61.4 MB | 较上周 +0 |
| jst_product_profiles（估算） | 418,201 行 / 687.2 MB | 估算值较上周 +0；行数为目录估算值 |
| jst_aftersale_returns（估算） | 1,518,213 行 / 3.76 GB | 估算值较上周 +484；行数为目录估算值 |
| vip_daily_sales（估算） | 15,397,656 行 / 21.78 GB | 估算值较上周 +47,612；行数为目录估算值 |
| vip_product_ops_snapshots（估算） | 7,992,301 行 / 11.17 GB | 估算值较上周 +72,190；行数为目录估算值 |
| vip_product_daily_snapshots（估算） | 1,178,991 行 / 1.71 GB | 估算值较上周 +10,136；行数为目录估算值 |
| vip_product_detail_daily（估算） | 252,923 行 / 660.0 MB | 估算值较上周 +0；行数为目录估算值 |
| vip_product_ops | 70,049 行 / 208.4 MB | 较上周 +0 |
| gj_merged_product_info（估算） | 7,439,053 行 / 9.36 GB | 估算值较上周 +66,538；行数为目录估算值 |
| dewu_orders | 116,733 行 / 102.5 MB | 较上周 +0 |
| fine_table_snapshot_refs_2026（估算） | 12,690,483 行 / 5.14 GB | 估算值较上周 +0；行数为目录估算值 |
| fine_table_snapshot_batches | 3,505 行 / 0.6 MB | 较上周 +4 |
| product_goods_detail_snapshots（估算） | 12,688,951 行 / 19.17 GB | 估算值较上周 +44,084；行数为目录估算值 |
| product_goods_historical_orders | 67,732 行 / 23.0 MB | 较上周 +0 |
| product_goods_historical_sales（估算） | 1,840,831 行 / 683.3 MB | 估算值较上周 +0；行数为目录估算值 |
| product_tag_assignments | 563,681 行 / 230.6 MB | 较上周 +323 |
| operation_logs | 10,524 行 / 16.6 MB | 较上周 +40 |

**进销存**

| 检查项 | 结果 | 说明 |
|---|---|---|
| inventory_records.date_value | 空值 0.00%（0/6,676） | 正常 |
| inventory_details.unit_price | 空值 0.56%（678/120,959） | 正常 |
| inventory_details.amount | 空值 0.26%（318/120,959） | 正常 |

**商品档案**

| 检查项 | 结果 | 说明 |
|---|---|---|
| cbanner_mens_products.sku | 空值 0.00%（0/19,675） | 正常 |
| cbanner_mens_products.product_name | 空值 0.03%（5/19,675） | 正常 |
| cbanner_mens_products.cost | 空值 0.77%（151/19,675） | 正常 |
| cbanner_womens_products.sku | 空值 0.00%（0/15,958） | 正常 |
| cbanner_womens_products.product_name | 空值 0.16%（26/15,958） | 正常 |
| cbanner_womens_products.cost | 空值 0.16%（25/15,958） | 正常 |
| yandou_products.sku | 空值 0.00%（0/17,261） | 正常 |
| yandou_products.product_name | 空值 0.01%（2/17,261） | 正常 |
| yandou_products.cost | 空值 0.11%（19/17,261） | 正常 |
| eblan_products.sku | 空值 0.00%（0/10,259） | 正常 |
| eblan_products.product_name | 空值 0.07%（7/10,259） | 正常 |
| eblan_products.cost | 空值 0.03%（3/10,259） | 正常 |
| smiley_products.sku | 空值 0.00%（0/442） | 正常 |
| smiley_products.product_name | 空值 0.00%（0/442） | 正常 |
| ni_products.sku | 空值 0.00%（0/87） | 正常 |
| ni_products.product_name | 空值 0.00%（0/87） | 正常 |
| ni_products.cost | 空值 1.15%（1/87） | 正常 |
| manual_product_archive_31.sku | 空值 0.00%（0/37） | 正常 |
| manual_product_archive_31.product_name | 空值 0.00%（0/37） | 正常 |
| manual_product_archive_31.cost | 空值 0.00%（0/37） | 正常 |
| 档案货号未登记到身份表 | 0 | 正常 |

**聚水潭订单**

| 检查项 | 结果 | 说明 |
|---|---|---|
| jst_monthly_orders_2026.order_time_at | 空值 0.00%（0/3,348,465） | 正常 |
| jst_monthly_orders_2026.product_code | 空值 0.00%（0/3,348,465） | 正常 |

**唯品会**

| 检查项 | 结果 | 说明 |
|---|---|---|
| vip_product_ops_snapshots.goods_code | 空值 0.00%（0/3,307,933）（近 120 天） | 正常 |

**其它分析表**

| 检查项 | 结果 | 说明 |
|---|---|---|
| gj_merged_product_info.goods_code | 空值 0.00%（0/3,809,923）（近 120 天） | 正常 |
| jst_product_profiles.product_code | 空值 0.00%（0/421,427） | 正常 |
| suppliers.name | 空值 0.00%（0/1,051） | 正常 |

**日期断档**

| 检查项 | 结果 | 说明 |
|---|---|---|
| 聚水潭库存快照 | 完整（90 天） | 无断档｜jst_daily_stock.stock_date_value |
| 聚水潭销售日报 | 完整（90 天） | 无断档｜jst_daily_sales.sales_date |
| 唯品会销售日报 | 完整（90 天） | 无断档｜vip_daily_sales.sales_date |
| 商品明细快照 | 完整（90 天） | 无断档｜product_goods_detail_snapshots.snapshot_date |
| 得物订单 | 完整（90 天） | 无断档｜dewu_orders.order_date |
| 聚水潭采购入库日报 | 完整（90 天） | 无断档｜jst_purchase_inbound_daily.inbound_date |

**去重键覆盖**

| 检查项 | 结果 | 说明 |
|---|---|---|
| jst_monthly_orders 2026-05 的 record_key | 缺失 7/526,578（0.0%） | 正常 |
| jst_monthly_orders 2026-06 的 record_key | 缺失 6/412,075（0.0%） | 正常 |

**引用完整性**

| 检查项 | 结果 | 说明 |
|---|---|---|
| 外键孤儿行（已检查 20/20 个外键） | 0 行 | 全部外键均无孤儿行 |

**进销存勾稽**

| 检查项 | 结果 | 说明 |
|---|---|---|
| 无明细行的空单据 | 0 | 正常 |

## 六、与上周对比（有变化的指标）

| 指标 | 上周 | 本周 |
|---|---|---|
| `rows.inventory_records` | 6589 | 6676 |
| `bytes.inventory_records` | 6094848 | 6103040 |
| `rows.inventory_details` | 120223 | 120959 |
| `bytes.inventory_details` | 127385600 | 127434752 |
| `rows.suppliers` | 1049 | 1051 |
| `bytes.suppliers` | 2023424 | 2048000 |
| `rows.warehouses` | 33 | 37 |
| `rows.cbanner_womens_products` | 15938 | 15958 |
| `rows.smiley_products` | 439 | 442 |
| `rows.product_archive_identities` | 63719 | 63742 |
| `bytes.product_archive_identities` | 35299328 | 35315712 |
| `rows.product_goods_overrides` | 21751 | 21793 |
| `bytes.product_goods_overrides` | 5668864 | 5677056 |
| `rows.jst_monthly_orders` | 14487305 | 14488242 |
| `bytes.jst_monthly_orders` | 27303370752 | 27914797056 |
| `rows.jst_product_price` | 9240568 | 9303194 |
| `bytes.jst_product_price` | 7295860736 | 7352672256 |
| `rows.jst_daily_stock` | 21949050 | 22264560 |
| `bytes.jst_daily_stock` | 6971203584 | 7011024896 |
| `rows.jst_daily_sales` | 1250831 | 1252136 |
| `bytes.jst_daily_sales` | 2749833216 | 2759368704 |
| `bytes.jst_purchase_inbound_daily` | 2489196544 | 2489286656 |
| `rows.jst_full_stock` | 248332 | 248528 |
| `bytes.jst_full_stock` | 272089088 | 272277504 |
| `rows.jst_aftersale_returns` | 1517729 | 1518213 |
| `bytes.jst_aftersale_returns` | 4040572928 | 4040597504 |
| `rows.vip_daily_sales` | 15350044 | 15397656 |
| `bytes.vip_daily_sales` | 23311450112 | 23385243648 |
| `rows.vip_product_ops_snapshots` | 7920111 | 7992301 |
| `rows.vip_product_daily_snapshots` | 1168855 | 1178991 |
| `rows.gj_merged_product_info` | 7372515 | 7439053 |
| `bytes.gj_merged_product_info` | 9968361472 | 10053402624 |
| `bytes.fine_table_snapshot_refs_2026` | 5479636992 | 5521694720 |
| `rows.fine_table_snapshot_batches` | 3501 | 3505 |
| `rows.product_goods_detail_snapshots` | 12644867 | 12688951 |
| `bytes.product_goods_detail_snapshots` | 20471595008 | 20584955904 |
| `rows.product_tag_assignments` | 563358 | 563681 |
| `bytes.product_tag_assignments` | 241467392 | 241827840 |
| `rows.operation_logs` | 10484 | 10524 |
| `bytes.operation_logs` | 17326080 | 17383424 |
| `null.inventory_records.total_count` | 5.4788 | 5.4074 |
| `null.inventory_records.supplier` | 2.8077 | 3.3403 |
| `null.inventory_details.unit_price` | 0.5448 | 0.5605 |
| `null.inventory_details.amount` | 0.2454 | 0.2629 |
| `null.inventory_details.product_identity_id` | 1.1578 | 1.1508 |
| `null.inventory_details.product_code` | 0.3003 | 0.2984 |
| `null.inventory_details.color_spec` | 0.3019 | 0.3001 |
| `null.cbanner_mens_products.product_level` | 21.1233 | 21.0521 |
| `null.cbanner_mens_products.group_name` | 14.7344 | 14.77 |
| `null.cbanner_womens_products.product_name` | 0.1631 | 0.1629 |
| `null.cbanner_womens_products.cost` | 0.1569 | 0.1567 |
| `null.cbanner_womens_products.image_path` | 18.7727 | 18.7492 |
| `null.cbanner_womens_products.product_level` | 73.4157 | 73.4491 |
| `null.cbanner_womens_products.category` | 6.2367 | 6.3542 |
| `null.cbanner_womens_products.last_imported_at` | 99.8243 | 99.8872 |
| `null.smiley_products.cost` | 12.0729 | 12.6697 |
| `null.smiley_products.category` | 12.9841 | 13.5747 |
| `null.smiley_products.last_imported_at` | 41.4579 | 41.8552 |
| `null.jst_product_price.latest_purchase_price~window` | 25.518 | 25.5282 |
| `null.jst_product_price.cost_unit_price~window` | 72.7715 | 72.7944 |

---

*既有检查使用 `backend/scripts/review_missing_data.py`；本次为人工触发只读复核。*
*运行日志：`backend/logs/missing_data_review.log`；历史报告：`backend/logs/missing_data_reports/`。*
## 附加检查：近期数据最新日期

| 数据 | 最新日期 | 距昨日滞后天数 |
|---|---|---|
| 聚水潭库存快照 | 2026-10-09 | 0 |
| 聚水潭销售日报 | 2026-10-08 | 0 |
| 唯品会销售日报 | 2026-10-08 | 0 |
| 商品明细快照 | 2026-10-08 | 0 |
| 得物订单 | 2026-10-08 | 0 |
| 精细表快照明细 | 2026-10-08 | 0 |
| 聚水潭采购入库日报 | 2026-10-08 | 0 |
| 唯品会商品日快照 | 2026-10-07 | 1 |
