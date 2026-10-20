# 商品信息档案管理系统

商品信息档案管理系统，用于管理千百度男鞋、千百度女鞋、烟斗、伊伴四个品牌的商品数据，以及进销存记录，支持 Excel 导入导出、图片管理、批量搜索等功能。

## 项目结构

```
hede/
├── backend/           # FastAPI 后端
│   ├── api/           # API 路由（商品 CRUD、图片服务、导入导出、进销存）
│   │   └── routes/    # products.py, images.py, import_export.py, inventory.py
│   ├── domain/        # 数据模型与字段定义（商品 + 进销存）
│   ├── fileio/        # Excel 读取、图片匹配
│   ├── pipeline/      # 商品数据导入管线
│   ├── storage/       # 数据库访问层（商品 + 进销存 repository）
│   ├── transform/     # 数据转换与规范化
│   ├── scripts/       # 一次性脚本（聚水杉数据补全、数据库迁移等）
│   ├── cli.py         # 命令行入口（数据导入）
│   └── api_main.py    # API 服务入口
├── frontend/          # Next.js 前端
│   ├── app/           # 页面路由
│   ├── components/    # UI 组件（shadcn/ui + 商品管理 + 进销存管理）
│   └── lib/           # API 客户端、类型定义、工具函数
└── docs/              # 项目文档
```

## 功能

### 页面查询会话
- 页面查询条件、已提交筛选、品牌、日期、页码、每页条数与排序按页面独立保存到当前标签页的 `sessionStorage`；跳转返回或刷新时恢复，数据结果仍重新请求。
- 清空／重置查询同步覆盖保存状态；采购单与经营历程分别保存，不缓存编辑弹窗、未保存业务单据或商品勾选。
- 查询状态按登录账号隔离，退出登录时清理；不使用长期 `localStorage` 保存查询。关闭标签页后结束会话，浏览器“恢复上次会话”行为由浏览器决定。

### 用户管理
- **姓名模糊筛选** — 输入部分姓名后点击“查询”或按回车，在全部用户中匹配；“清空”恢复全部账号。分页与账号状态统计同步使用筛选条件。

### 商品档案管理
- **品牌 Tab 切换** — 千百度男鞋 / 千百度女鞋 / 烟斗 / 伊伴 / 总览
- **商品列表** — 卡片式展示，含图片、全部字段、分页（10/50/100 条可选）
- **商品标签管理** — 在独立管理页面查看并按商品档案重建风格、功能、运营和数据质量标签；每日档案同步后自动增量同步，仅开发部和超级管理员可访问
- **批量搜索** — 支持按货号或原始货号搜索，逗号或换行分隔多个关键词
- **新增 / 编辑** — 表单弹窗，季节分类下拉选择、日期选择器、图片自动匹配
- **删除 / 批量删除** — 二次确认对话框
- **Excel 导出** — 导出当前品牌全部数据，中文文件名
- **Excel 导入** — 上传 Excel 按货号匹配更新，仅覆盖有值字段，自动查找图片
- **女鞋款式字段** — 千百度女鞋与千百度赫锦共用款式信息字段：跟底款式、流行元素、鞋帮高度、开口深度、靴筒、闭合方式、鞋网面类型、鞋头款式、后跟高；新增/编辑、卡片、详情、普通和带尺码导出均支持，Excel 导入分别保留跟高与后跟高。赫锦使用女鞋辅助属性选项，不改变其独立商品档案和成本数据，也不会自动补造未维护的字段值。

#### 新增品牌的导出规则

- 在品牌管理新增品牌后，商品档案按品牌配置自动发现独立档案表；普通、勾选、搜索、物价、带尺码、按时间与总览导出均直接读取配置，不需要增加品牌名称字典或再次重启服务。品牌改名后，下次导出的名称同步更新；伊伴档案仍显示“伊伴”。
- 文件名、工作表名及导出品牌列使用品牌名称。工作表名自动替换 Excel 不支持的字符并限制为 31 个字符。
- 导出仅包含未删除且不在排除清单中的商品；总览与带尺码的资料补齐也使用相同过滤规则，不包含回收站商品。
- 手工新增品牌仅使用本品牌的商品资料、成本、颜色代码及尺码组，不按同名货号借用其他品牌的聚水潭或管家婆资料。成本空值与零值保持原样；未维护尺码组或可解析尺码段时保留商品行，不虚构尺码。
- 回归测试覆盖不同品牌编码、运行中新增多个随机品牌、相同货号隔离、品牌改名、回收站排除及所有导出模式。在 `backend` 目录执行 `python -m pytest tests/test_product_archive_export.py tests/test_product_price_export.py tests/test_product_size_export.py -q`，这些测试使用临时内存数据库，无需连接业务数据库。

### 进销存管理
- **单据列表** — 表格展示，含入库单号、日期、单据类型、供应商、总数、金额、仓库、摘要
- **单据 + 明细两层结构** — 主单据存汇总信息，明细行存每条商品编码详情
- **明细面板** — 点击明细按钮展开右侧滑出面板（shadcn Sheet），显示商品图片、编码、名称、颜色规格、数量、单价、金额
- **明细图片自动匹配** — 根据商品编码去掉后五位，跨四个品牌图片目录匹配商品图片
- **新增 / 编辑 / 删除明细** — 明细行 CRUD，支持自动计算金额（数量 × 单价）
- **总数和金额自动汇总** — 后端根据明细行自动重算主单据的总数和金额
- **筛选搜索** — 按日期范围、单据类型、供应商、仓库筛选
- **商品进货明细品牌筛选** — 支持搜索、多选品牌，与经营历程使用相同品牌列表和匹配规则；查询、合计、分页与 Excel 导出统一使用已提交的筛选条件。
- **Excel 导入** — 支持主单据与明细在同一张表中，通过备注（摘要）字段关联
- **Excel 导出** — 导出全部进销存数据

### 通用功能
- **深色 / 浅色主题** — 右上角切换
- **供应商 / 仓库管理** — Excel 导入时自动同步新供应商和仓库名称
- **跨页批量删除** — 勾选跨页、切换每页条数时保留；“全选筛选结果”通过只读 `POST /inventory/selection-ids` 获取已提交查询条件下的单据 ID 快照，不受当前页限制。重新查询、清空或切换完成状态会清除选择。删除确认显示跨页单据数，只将快照内单据移入回收站，之后新增的单据不包含在内。采购单使用同一交互，但范围限定为进货订单。大批次按 1,000 条分段更新，所有分段处于同一事务，失败整体回滚，10 天内可恢复。

## 技术栈

| 层 | 技术 |
|---|------|
| 前端 | Next.js 16 + React 19 + TypeScript + Tailwind CSS 4 + shadcn/ui |
| 后端 | Python + FastAPI + SQLAlchemy + PostgreSQL |
| 数据源 | openpyxl / xlrd 读取 Excel，共享目录图片匹配 |

## 快速开始

### 1. 环境准备

- Python 3.13+
- Node.js 20+ (推荐使用 pnpm)
- PostgreSQL

### 2. 后端

```bash
cd backend
pip install -e ".[dev]"
```

创建 `backend/.env` 文件：

```env
DATABASE_URL=postgresql+psycopg://postgres:密码@127.0.0.1:5432/数据库名
FRONTEND_ORIGIN=http://127.0.0.1:3001
EXCEL_ROOT=\\共享路径\商品资料档案汇总
QBD_IMAGE_ROOT=\\共享路径\千百度45度图男女鞋
YANDOU_IMAGE_ROOT=\\共享路径\烟斗45图准确版
YIBAN_IMAGE_ROOT=\\共享路径\伊伴男女鞋45度图
```

导入数据并启动服务：

```bash
# 从 Excel 导入商品数据到数据库
python -m cli import

# 从聚水潭表补全供应商名、尺码段等5个字段
python -m scripts.enrich_from_jst

# 启动 API 服务
uv run python -m uvicorn api_main:app --host 0.0.0.0 --port 8137
```

### 3. 前端

```bash
cd frontend
pnpm install
pnpm run dev
```

访问 http://127.0.0.1:3001

前端通过 Next.js rewrites 代理 API 请求到后端，无需配置后端地址。

经营历程和采购单的 Excel 导入、预检查及明细重新导入支持单文件不超过 100MiB（页面提示为 100MB）。Next.js 的 `experimental.proxyClientMaxBodySize` 设置为 101MiB，额外空间用于 multipart 表单字段与边界；超限文件在上传前提示拆分，带超限 `Content-Length` 的请求返回 413。限制由 `frontend/lib/upload-limits.mjs` 统一维护。配置变更需手动重启前端，生产模式还需重新构建；无需因此重启后端或修改数据库。外网经过 Nginx 时，还需在对应站点或上传路径设置 `client_max_body_size 110m;` 并检查、重载配置，否则仍可能由 Nginx 拒绝大文件。上传大小限制和执行超时相互独立；导入超时后先检查是否已入库，勿立即重复提交。

经营历程的“按模板导入”确认后使用后台批次：

- `POST /inventory/import-template/tasks/{task_id}` 提交，`GET` 同一路径查询 queued/running/succeeded/failed；同一批次 ID 和文件参数重复提交只返回已有结果，不再次执行。新 ID 仍需重新预检查重复单据。
- 批次结果保存在 `inventory_import_tasks`，成功结果与单据、明细在同一事务中提交。操作日志异常不会把已提交的导入误报为失败。
- 页面每 3 秒核验结果，成功或明确失败后刷新列表；同一浏览器标签页刷新或返回页面时会恢复未完成批次。连接中断只表示结果暂未确认，请勿直接重传或覆盖；浏览器存储不可用、清除存储或关闭标签页后不保证自动恢复。
- 导入状态卡区分文件提交、等待处理、导入中、恢复核验、连接中断及批次待确认；关闭弹窗后页面仍显示任务提醒。“立即核验”和网络恢复后的查询仅核对已有批次，不会重复导入；不支持文件断点续传或后端重启后续跑，明确失败后需重新预检查。
- 后端每 15 秒主动巡检，心跳中断超过 2 分钟的批次会判为失败，不依赖页面打开；查询批次也会检查心跳。被判失败的旧任务无法再提交业务事务。接口暂不可达或未查到批次时保留“核验中”，需先恢复连接或由管理员核对批次，不能据此断言导入失败。
- 校验错误、后台线程异常、未确认提交就退出和提交取消都会记录失败；失败状态写入最多立即尝试 3 次，仍失败则记录严重日志并每 15 秒重试（当前进程内）。失败响应附带批次编号，任务表和后端日志保留失败原因，另尝试写入经营历程操作日志；操作日志不可用不影响任务失败状态。数据库不可用期间无法保证页面立即收到结果，恢复后继续核验。不会自动重新导入业务数据，已提交成功的结果不会被失败覆盖。
- 后台模板导入的 PostgreSQL 写入事务设置 30 秒锁等待和单条语句 10 分钟执行上限，超时或死锁会提示原因；这不是整批导入时长限制，不影响正常的大文件解析。所有单据、明细与成功状态仍整批提交或回滚。
- 部署需更新并手动重启后端、重新构建并启动前端。后端初始化会补建批次表，也保留了 Alembic 迁移及 `database/inventory-import-tasks-2026-10-16.sql`。现有同步接口继续保留，但页面模板导入不再使用它。

页面筛选条件、分页和滚动位置按当前用户保存在浏览器会话中。切换其他页面再返回时恢复上次位置，异步列表加载后继续恢复；同时支持表格内部的横向/纵向滚动。浏览器刷新页面时清除已保存的筛选、分页和滚动位置，重新使用默认条件并从顶部开始；普通页面跳转和浏览器前进/后退不清除。首次访问页面从顶部开始，手动滚动会中止待完成的自动恢复，退出登录清除位置记录。

### 管家婆商品信息任务并发与错误展示

`import_gj_merged_product_info_daily` 在检查成功状态和写入业务状态之前取得 PostgreSQL 会话互斥锁，独立定时任务与商品档案串行工作流同时触发时只执行一份；另一份正常跳过且不覆盖正在执行的业务状态。底层导入对同一数据日期再加事务锁，手动导入也不会并发删除/插入同一快照；异常仍整批回滚，连接和锁会释放，不修改已有历史执行记录。

错误摘要保留异常开头和数据库原因，不再截取 SQL 参数尾部；完整诊断继续写入任务日志。定时任务的执行记录、运行历史与业务日期状态默认只显示两行简要信息，长内容可展开，在限定高度内滚动。脚本修改在下一次任务启动时生效；页面需更新前端构建。

## 数据库表结构

### 商品表（每品牌一张）
`qbd_mens_products` / `qbd_womens_products` / `yandou_products` / `yiban_products`

- `id` — 主键
- `source_workbook` / `source_sheet` / `source_row_number` — 数据来源追踪
- `raw_payload` — 原始行数据完整快照（JSON）
- `extra_fields` — 未映射到规范字段的额外数据（JSON）
- `sku` — 货号（唯一约束）
- `original_sku` — 原始货号
- 以及尺码段、产品型号、供应商名、颜色代码、上市时间等 30+ 个规范字段

### 商品标签表

标签不写入商品档案字段，也不使用向量化；通过独立关系表维护：

- `product_tag_definitions` — 标签字典，包含编码、名称、分组、启用状态和人工覆盖标记
- `product_tag_assignments` — 商品与标签绑定，记录来源、置信度、状态和证据
- `product_style_entities` — 预留款级标签实体，当前重建按 SKU/商品档案记录绑定

当前标签由“从商品档案重建”按商品档案字段生成，使用 `source_type=rule`、`status=confirmed`；每日商品档案、图片和提示词任务完成后执行 `sync_product_tags_daily`，只处理当日新增、变更、删除以及新品标签到期的商品。开发部和超级管理员可以编辑标签名称、分组、排序和启用状态，人工修改会在后续重建时保留。数据库结构由 Alembic 迁移 `20260927_0073`、`20260927_0074` 创建，正式环境部署时执行：

```bash
cd backend
alembic upgrade head
```

### 进销存表

**inventory_records** — 主单据表
- `id` — 入库单号
- `date` — 日期
- `supplier` — 供应商
- `total_count` — 总数（由明细自动汇总）
- `amount` — 金额（由明细自动汇总）
- `warehouse` — 仓库
- `document_type` — 单据类型（工厂进货单 / 工厂退货单）
- `summary` — 摘要（导入时用于关联明细行）
- `extra_fields` — 未映射的额外字段（JSON）
- `source_workbook` / `source_sheet` / `source_row_number` — 数据来源追踪
- `raw_payload` — 原始行数据完整快照（JSON）

**inventory_details** — 明细表
- `id` — 主键
- `document_id` — 外键关联 inventory_records.id（级联删除）
- `product_code` — 商品编码
- `product_name` — 商品名称
- `color_spec` — 颜色及规格
- `quantity` — 数量
- `unit_price` — 单价
- `amount` — 金额

商品进货明细分页将总行数和数量/金额合计合并为一次查询，先对明细 ID 和排序键分页，再读取当前页商品、尺码及额外字段；保持日期、单据编号、明细 ID 顺序和退货负数合计，不缓存统计结果。空结果或超出末页时不再读取明细。新库包含覆盖索引 `idx_inventory_details_document_page (document_id, id) INCLUDE (quantity, amount)`；已有 PostgreSQL 库需独立执行以下命令并手动重启后端，不在应用启动时阻塞建索引：

```bash
cd backend
python -m scripts.optimize_purchase_inbound_pagination --output logs/purchase-inbound-index-plan.json
python -m scripts.optimize_purchase_inbound_pagination --execute --output logs/purchase-inbound-index-result.json
```

脚本核对同名索引定义，使用 `CREATE INDEX CONCURRENTLY` 在线构建，设置锁等待/执行超时并保存结果及回滚命令。也保留独立 SQL 文件 `database/purchase-inbound-pagination-index-2026-10-18.sql`，必须在事务外执行。

**suppliers** — 供应商表
- `id` / `name` / `contact` / `address` / `notes`

**warehouses** — 仓库表
- `id` / `name` / `address` / `notes`

## 常用命令

```bash
# 后端
cd backend
pytest                                    # 运行所有测试
python -m scripts.migrate_inventory_to_docs  # 进销存数据迁移

# 前端
cd frontend
pnpm run typecheck    # TypeScript 类型检查
pnpm run format       # Prettier 格式化
pnpm run lint         # ESLint 检查
pnpm run test         # Vitest 测试
```
