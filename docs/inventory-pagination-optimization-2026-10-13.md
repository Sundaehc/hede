# 经营历程分页查询优化（2026-10-13）

## 范围与瓶颈

本次针对经营历程列表的分页查询（`GET /inventory` / `InventoryRepository.list_records`），不涉及进货入库明细页面。

默认查询筛选“已完成”、排除进货订单，每页 20 条。当前数据库约有 1.7 万条单据、41.2 万条明细；默认筛选匹配 14,640 条记录。

原实现分别查询记录数、分页记录和全量汇总，重复执行完成状态判断；缺失单价/金额的筛选扫描大量明细，内销客户判断则逐单据执行关联子查询。

## 优化内容

- 将记录数和全量数量、金额汇总合并为一次聚合查询，分页列表查询从三次减少为两次（不含原有过期软删除清理）。
- 内销客户名称与其单位名称组成非关联集合，用集合成员判断代替逐单据关联匹配；保持空客户名称、重复名称和原有完成状态规则的行为。
- 为明细表新增两个部分索引，只覆盖金额或单价为空、为零的记录，避免完成状态筛选全表扫描：
  - `idx_inventory_details_missing_amount_document`：`document_id WHERE amount IS NULL OR amount = 0`。
  - `idx_inventory_details_missing_price_document`：`document_id WHERE unit_price IS NULL OR unit_price = 0`。

两个索引已通过 `CREATE INDEX CONCURRENTLY` 创建，随后更新明细表统计信息；复查确认索引有效且定义匹配。未删除业务数据、未移除既有索引、未调整 Alembic 版本。

## 实测结果

| 查询条件 | 优化前 | 优化后 | 匹配记录数 |
| --- | ---: | ---: | ---: |
| 已完成，第 1 页 | 903.628 ms | 27.912 ms | 14,640 |
| 已完成，第 2 页 | 909.898 ms | 23.049 ms | 14,640 |
| 未完成，第 1 页 | 994.159 ms | 40.209 ms | 2 |
| 不筛选完成状态，第 1 页 | 9.442 ms | 6.585 ms | 14,642 |

以上是数据库仓储方法单次测量，不是完整 HTTP 请求耗时；只读测量跳过原有的过期软删除清理，结果受缓存和并发影响，不能作为固定响应时间保证。用原始 SQL 在当前数据库回放，核对记录数、分页 ID 与顺序、全量数量和金额汇总，四组结果均一致。

新执行计划中，内销客户集合只计算一次，缺失金额和单价筛选使用部分索引的 Index Only Scan。

## 验证与生效

相关分页、单号搜索、品牌筛选、内销客户、导出及进货订单搜索回归测试：40 passed，2 skipped。两项依赖独立测试 PostgreSQL 的测试因未设置 `TEST_DATABASE_URL` 跳过；不要将生产数据库用作这些测试的数据库。

数据库索引已生效。后端代码需要用户手动重启后生效；本次没有启动或重启后端。

## 复查及回退资料

在 `backend` 目录运行下列命令，仅预览或复查索引，不执行建索引操作：

`uv run --no-sync python -m scripts.optimize_inventory_pagination --output ../outputs/inventory-pagination-index-preview.json`

如在其他环境实施，确认预览后添加 `--execute`。脚本设置 5 秒锁等待超时、5 分钟语句超时；拒绝继续使用无效或定义不匹配的同名索引，并将逐项进度写入报告。

- 索引实施记录及对应回退 SQL：`outputs/inventory-pagination-index-applied-20261013.json`。
- 索引复查：`outputs/inventory-pagination-index-recheck-20261013.json`。
- 优化前后查询及耗时：`outputs/inventory-pagination-before-20261013.json`、`outputs/inventory-pagination-after-20261013.json`。
- 优化前后执行计划：`outputs/inventory-pagination-before-plan-20261013.txt`、`outputs/inventory-pagination-after-plan-20261013.txt`。

回退 SQL 仅用于撤销本次新增索引，需经人工确认后执行。若完全回退，还需同步撤销查询及 schema 中的索引声明，避免后续建表流程再次创建索引。
