# 商品货品表、商品精细表分页优化（2026-10-14）

## 范围

优化当前货品表 GET /product-goods 和精细表 GET /fine-table 的分页链路，不修改前端、业务筛选规则、销量口径或业务数据。相关库存、售后、销量和快照指标仍保持原有结果。精细表历史快照及其他使用排除款号条件的接口也共享排除条件优化，但历史快照不在本次性能测量范围中。

## 瓶颈与改动

- 货品表售后退货量按原始货号前缀匹配，原执行计划全扫描年度分区约 150 万行；补充 text_pattern_ops 索引，保留最长货号匹配和业务日期口径。
- 年月销量查询原先扫描整个品牌的期间记录；新增品牌、货号前缀复合索引。
- 管家婆最新日期、品牌筛选原先读取大量堆表；新增日期、品牌、货号覆盖索引并包含 ID。
- 货品表先按轻量的 ID、年份、货号排序分页，之后仅加载当前页完整字段，避免携带 JSON 等大字段排序；排序规则不变。
- 货品表总数缓存按品牌、视图、搜索、平台、年份、筛选和快照日期隔离，换页复用；沿用现有 300 秒 TTL、写入后的清理逻辑，强制刷新绕过缓存。
- 精细表快照日期先按当前页货号分组计算最大值再合并，避免 MAX 选择全局日期索引倒序扫描大量不相关图片/商品日快照记录。
- 排除款号集合通过单个参数绑定的 PostgreSQL 文本数组，使用非关联集合查询；缓存数组编码，避免每次请求重复序列化大量款号。保留空值、空字符串和仅按 SKU 排除的原有行为。
- 货品表销量期间查询和销量矩阵表存在性检查复用当前连接，避免不必要的连接池借用。

## 已创建索引

1. idx_gj_merged_product_info_source_brand_code：source_date_value、fine_table_brand、goods_code，INCLUDE (id)。
2. idx_product_goods_sales_period_brand_product_pattern：brand、product_code text_pattern_ops。
3. idx_jst_aftersale_returns_original_code_pattern：original_goods_code text_pattern_ops 分区父索引。

售后父索引下挂接 2024、2025、2026、2027 和 default 五个子索引。实际新增 7 个物理索引及 1 个分区父索引；原索引未删除，业务表数据未修改。

物理索引采用 CREATE INDEX CONCURRENTLY；分区父索引采用 ON ONLY 创建后挂接，避免对整张分区表直接创建阻塞式索引。设置 5 秒锁等待、5 分钟语句超时；新增索引后更新统计信息。已经核对索引有效性和定义，并通过脚本重复执行验证。

## 性能及一致性

每页 50 条，基于同一数据库，只读调用完整 Python 路由函数，关闭响应缓存后测量：

| 案例 | 优化前 | 优化后 | 匹配数 |
| --- | ---: | ---: | ---: |
| 女鞋货品表，第 1 页 | 1332.447 ms | 503.027 ms | 16019 |
| 女鞋货品表，第 2 页 | 1192.640 ms | 234.010 ms | 16019 |
| 男鞋货品表，第 1 页 | 966.278 ms | 250.823 ms | 19665 |
| 男鞋精细表，第 1 页 | 2516.173 ms | 108.366 ms | 19665 |
| 男鞋精细表，第 2 页 | 323.233 ms | 86.163 ms | 19665 |
| 女鞋精细表，第 1 页 | 264.692 ms | 77.770 ms | 16019 |

以上为单次代表性采样，受数据库缓存、连接初始化、并发和分析工具开销影响，不是固定 HTTP 响应耗时保证。尤其精细表第一组优化前存在明显冷缓存成本，不能直接视为稳定的倍数提升。未包含前端网络传输和渲染。

六组响应逐字段对比一致，包括总数、ID、顺序、库存、退货量、销量等。另只读回放原实现，核对货品搜索、款号汇总、年份筛选、精细表搜索、前缀、计算字段筛选及 include_all 导出，结果均一致；空值及特殊字符款号的排除行为也一致。

连续换页额外核对：货品表第 2 页查询数由 37 减为 33（含已有快照日期缓存），精细表第 2 页少查一次总数。92 项相关回归测试通过。扩大检查时还发现 test_product_goods_sales_mapping.py 有两项既有失败：跨码尺寸映射、库存健康标签预期与当前业务实现不一致；此次没有修改这两处业务逻辑。

## 部署与复查

代码需用户手动重启后端生效；本次没有启动或重启后端。

在 backend 目录预览目标环境索引：

    uv run --no-sync python -m scripts.optimize_product_pagination --output ../outputs/product-pagination-index-preview.json

确认后加 --execute。脚本会验证同名索引定义；已有合法索引和已挂接的分区自动跳过，无效物理索引拒绝继续。脚本默认预览，不清理旧索引或数据，不调整 Alembic 版本。

database/product-pagination-indexes-2026-10-14.sql 提供本次增量索引 SQL，仅适用于 public schema 且售后分区为当前列出的年度和 default 分区的环境。必须用 psql 非事务方式执行，不能包在 BEGIN 或 --single-transaction 中。目标分区布局可能不同时，优先用 Python 脚本动态识别并校验。回退语句在 SQL 文件末尾，执行前需人工确认；先删除分区父索引会一并移除挂接的子索引，不要逐个对挂接子索引执行 DROP INDEX CONCURRENTLY。

database/schema.sql 仍保留为 2026-10-13 的已验证完整结构快照，不直接修改它或使其 manifest 校验失效。用该快照初始化新库后，需要再应用本次增量索引。

## 报告

- outputs/product-pagination-index-applied-20261014.json：索引实际创建和挂接记录。
- outputs/product-pagination-index-recheck-20261014.json：索引定义复查。
- outputs/product-pagination-index-idempotent-20261014.json：重复执行记录。
- outputs/product-pagination-comparison-20261014.json：六组性能和响应一致性对比。
- outputs/product-pagination-results-verified-20261014.json：搜索、筛选、汇总和导出对照。
- outputs/product-pagination-before-plans-20261014.txt、outputs/product-pagination-after-plans-20261014.txt：执行计划。
