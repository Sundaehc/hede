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

### 商品档案管理
- **品牌 Tab 切换** — 千百度男鞋 / 千百度女鞋 / 烟斗 / 伊伴 / 总览
- **商品列表** — 卡片式展示，含图片、全部字段、分页（10/50/100 条可选）
- **批量搜索** — 支持按货号或原始货号搜索，逗号或换行分隔多个关键词
- **新增 / 编辑** — 表单弹窗，季节分类下拉选择、日期选择器、图片自动匹配
- **删除 / 批量删除** — 二次确认对话框
- **Excel 导出** — 导出当前品牌全部数据，中文文件名
- **Excel 导入** — 上传 Excel 按货号匹配更新，仅覆盖有值字段，自动查找图片

### 进销存管理
- **单据列表** — 表格展示，含入库单号、日期、单据类型、供应商、总数、金额、仓库、摘要
- **单据 + 明细两层结构** — 主单据存汇总信息，明细行存每条商品编码详情
- **明细面板** — 点击明细按钮展开右侧滑出面板（shadcn Sheet），显示商品图片、编码、名称、颜色规格、数量、单价、金额
- **明细图片自动匹配** — 根据商品编码去掉后五位，跨四个品牌图片目录匹配商品图片
- **新增 / 编辑 / 删除明细** — 明细行 CRUD，支持自动计算金额（数量 × 单价）
- **总数和金额自动汇总** — 后端根据明细行自动重算主单据的总数和金额
- **筛选搜索** — 按日期范围、单据类型、供应商、仓库筛选
- **Excel 导入** — 支持主单据与明细在同一张表中，通过备注（摘要）字段关联
- **Excel 导出** — 导出全部进销存数据

### 通用功能
- **深色 / 浅色主题** — 右上角切换
- **供应商 / 仓库管理** — Excel 导入时自动同步新供应商和仓库名称

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
