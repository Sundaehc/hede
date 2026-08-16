# AI 只读 SQL 查询配置

## 功能说明

智能查询在启用 AI SQL 后，会将自然语言发送给 OpenAI 兼容接口生成 PostgreSQL 查询。后端只允许执行单条 `SELECT` 或 `WITH` 查询，不允许自然语言执行新增、编辑、删除、导入、更新或数据库结构变更。

未启用 AI SQL 时，系统继续使用原有的商品档案、货品表、工厂渠道和定时任务规则查询。

## 环境变量

在 `backend/.env` 中配置：

```dotenv
AI_SQL_ENABLED=true
AI_API_KEY=填写实际密钥
AI_PROVIDER=openai
AI_BASE_URL=https://api.openai.com/v1
AI_MODEL=gpt-4.1-mini
AI_TIMEOUT_SECONDS=180
AI_SQL_MAX_ROWS=500
```

`AI_PROVIDER` 支持 `openai` 和 `custom`。`custom` 用于 OpenAI Chat Completions 兼容网关，不强制发送 `response_format`。`AI_BASE_URL` 可以填写 `/v1` 基础地址或完整 `/chat/completions` 地址。修改配置后需要重新启动后端。

## 权限

- 所有部门均可使用 AI 只读 SQL 查询。
- 每个账户只会把现有权限允许的表结构发送给 AI，生成的 SQL 还会再次校验引用表权限。
- 商品档案、精细表、采购单和进销存分别受 `product.view`、`fine_table.view`、`purchase.view`、`inventory.view` 控制。
- 只有采购权限但没有进销存权限时，采购单数据通过仅包含“进货订单”的虚拟只读表提供，不会暴露经营历程中的其他单据。
- 超级管理员仍具有全部已开放业务数据权限；账户安全表和操作日志不开放给 AI SQL。

## 安全限制

1. 自然语言命中新增、编辑、删除、导入或更新意图时直接拒绝。
2. SQL 使用 `sqlglot` 按 PostgreSQL 语法解析，只接受一个查询语句。
3. 禁止 DML、DDL、事务控制、多语句、注释、锁表和有副作用函数。
4. 禁止访问 `auth_*` 账户表、会话表、角色表及 `operation_logs`。
5. 只允许引用发送给 AI 的业务表结构，禁止系统表及未开放表。
6. 数据库事务强制设置为 `READ ONLY`，即使前置校验漏判也不能写库。
7. 当前模型请求和数据库查询超时为 60 秒，最多返回 500 行。
8. 查询问题、查询模式、实际 SQL 和返回行数写入智能查询操作日志。

## 规范化查询规则

AI 不直接在所有同名表中自行选择数据源。后端只向模型开放统一业务视图和当前仍在使用的业务表，并在执行前再次校验 SQL 的业务口径。

1. 商品档案按品牌查询，并固定过滤 `deleted_at IS NULL`。
2. 聚水潭逐日销量只使用 `v_jst_daily_sales.net_sales_quantity`；唯品逐日销量只使用 `v_vip_daily_sales.sales_quantity`。
3. 2024、2025 历史工作簿销量使用 `v_product_goods_historical_sales`；历史销量、当年逐日销量和 `product_goods_sales_periods` 不得重复叠加。
4. 聚水潭平台先通过 `product_goods_shop_channel_mappings` 按品牌和店铺映射。与唯品日销合并时，必须排除聚水潭中映射为唯品的记录。
5. 当前库存使用 `jst_full_stock` 的最新 `sync_date`；在仓、在途和整体库存按货品表现有组成字段计算，组成列先逐列 `COALESCE(字段, 0)`。指定日期库存使用库存快照，当前库存与历史快照不得混合求和。
6. 精细表历史使用 `v_fine_table_snapshot_rows`，必须同时限定品牌和快照日期；唯品周期指标使用 `v_vip_product_daily_normalized`，必须限定报表类型和周期。
7. 采购、经营历程只统计未删除单据，单据明细按 `document_id` 关联；采购专用账户只能查询“进货订单”。
8. 空值表示没有可靠数据，不能由 AI 自动改成 `0`。

年度原表、统一父表和底层快照载荷表不会进入 AI 的可见结构，避免同一业务数据被重复统计。规则实现位于 `backend/domain/ai_query_semantics.py`。

## 自动纠正

模型生成 SQL 后依次经过只读语法、表权限和业务语义校验。首次 SQL 未通过时，后端会把原 SQL 和具体校验原因反馈给模型自动改写一次；第二次仍不合规才向用户返回错误。自动纠正不会放宽权限、开放隐藏表或绕过只读事务。

## 示例

```text
统计2026年各品牌有成本商品的数量和平均成本
查询最近30天各渠道销量并按销量从高到低排列
查询库存大于0但近7天没有销量的商品
按供应商统计采购数量和采购金额
```
