# CLAUDE.md

此文件为 Claude Code 在本仓库中工作时提供指导。

## 项目概览

商品信息档案管理系统，管理四个鞋品牌的商品数据及进销存记录，支持 Excel 导入导出、图片管理、批量搜索。

- **品牌**: 千百度男鞋 (qbd_mens) / 千百度女鞋 (qbd_womens) / 烟斗 (yandou) / 伊伴 (yiban)
- **模块**: 商品档案 / 进销存管理
- **Git Remote**: https://github.com/Sundaehc/hede.git

## 快速开始

### 环境要求
- Python 3.13+
- Node.js 20+，使用 pnpm
- PostgreSQL

### 后端
```bash
cd backend
pip install -e ".[dev]"
# 创建 backend/.env（见下方配置说明）
python -m cli import              # 从 Excel 导入商品数据
python -m scripts.enrich_from_jst # 从聚水潭补全 5 个字段
uvicorn api_main:app --host 0.0.0.0 --port 8137
```

### 前端
```bash
cd frontend
pnpm install
pnpm run dev    # http://127.0.0.1:3000
```

前端通过 Next.js rewrites 将 `/api/*` 代理到后端。可通过 `BACKEND_URL=http://host:port pnpm run dev` 覆盖。

## 配置

创建 `backend/.env`：
```env
DATABASE_URL=postgresql+psycopg://postgres:password@127.0.0.1:5432/dbname
FRONTEND_ORIGIN=http://127.0.0.1:3000
EXCEL_ROOT=\\network\商品资料档案汇总
QBD_IMAGE_ROOT=\\network\千百度45度图男女鞋
YANDOU_IMAGE_ROOT=\\network\烟斗45图准确版
YIBAN_IMAGE_ROOT=\\network\伊伴男女鞋45度图
```

## 后端结构

```
backend/
├── api/              # FastAPI 路由
│   ├── routes/       #   products.py, images.py, import_export.py, inventory.py
│   ├── app.py        #   FastAPI 应用工厂
│   └── schemas.py    #   Pydantic 请求/响应模型
├── domain/           # 数据模型与字段定义
│   ├── sources.py    #   商品：字段别名(COLUMN_ALIASES)、规范字段(CANONICAL_COLUMNS)、工作簿规格
│   ├── schema.py     #   商品：SQLAlchemy 表定义 (PRODUCT_TABLES)
│   ├── inventory_sources.py  # 进销存：字段别名、规范字段、明细字段
│   └── inventory_schema.py   # 进销存：表定义（主表 + 明细 + 供应商 + 仓库）
├── fileio/           # Excel 读取 (openpyxl/xlrd)、图片匹配 (ImageMatcher)
├── pipeline/         # 商品数据导入管线 (Excel → DB)
├── storage/          # 数据库访问层
│   ├── db.py         #   引擎创建、表初始化、METADATA 注册
│   ├── product_repository.py  # 商品 CRUD、批量搜索、UNION ALL 总览
│   └── inventory_repository.py # 进销存 CRUD、明细 CRUD、汇总重算、供应商、仓库
├── transform/        # 数据规范化、表头映射、记录构建
├── scripts/          # 一次性脚本
│   ├── enrich_from_jst.py
│   ├── migrate_inventory_to_docs.py  # 迁移：单行模式 → 单据+明细
│   ├── add_product_name.py           # 迁移：inventory_details 添加 product_name 列
│   └── add_color_spec.py             # 迁移：inventory_details 添加 color_spec 列
├── tests/            # pytest 测试
├── api_main.py       # API 入口
├── cli.py            # CLI 入口（数据导入）
└── config.py         # 配置 dataclass，.env 加载
```

### 后端关键模式

- **品牌路由**: 所有商品接口接受 `brand` 字符串参数。`"all"` 触发 `list_all_products()`，使用 SQL UNION ALL 跨品牌表查询。
- **字段别名**: `domain/sources.py` 通过 `COLUMN_ALIASES` 映射中文表头（如 "货号"→"sku"）。`domain/inventory_sources.py` 同理映射进销存字段。新增字段映射在此添加。
- **导入合并逻辑**: `import_export.py` 先按 sku 匹配，再按 original_sku 匹配。仅覆盖 Excel 中有值的字段。未识别列存入 `extra_fields` JSON。
- **进销存导入**: 按 `summary`（摘要）将 Excel 行分组。每个唯一摘要创建一个主单据；含 `product_code` 的行成为该单据的明细行。明细创建后自动重算主单据的 `total_count` 和 `amount`。
- **图片匹配**: `ImageMatcher` 在品牌专用共享目录中按 SKU 查找图片。`image_url_for()` 生成 `/images/serve/{brand}/{relative_path}` URL。进销存明细图片通过 `POST /api/images/match-sku` 将商品编码去掉后 5 位后跨所有品牌目录搜索匹配。
- **JSON 序列化**: 使用 `orjson` 作为 SQLAlchemy 的 `json_serializer`，必须以 `.decode("utf-8")` 将 bytes 转为 str，否则会写入 `\uXXXX` 转义导致中文乱码。
- **SKU 唯一性**: 所有商品表有 `UniqueConstraint("sku")`。导入管线通过保留最后一次出现来去重。
- **主从表汇总**: `inventory_repository.recalculate_totals()` 从 `inventory_details` 汇总 `quantity` 和 `amount`，更新父表 `inventory_records` 的 `total_count` 和 `amount`。每次明细增删改后调用。
- **空字符串处理**: `_prepare_record` 和 `_coerce_empty` 在数据库操作前将空字符串转为 `None`，因为 PostgreSQL numeric 列不接受空字符串。

## 前端结构

```
frontend/
├── app/                          # Next.js 页面路由
├── components/
│   ├── product-admin/            # 商品档案组件
│   │   ├── product-admin-page.tsx  # 主页面：品牌 Tab、搜索、列表、CRUD
│   │   ├── product-table.tsx       # 卡片/表格视图、分页、每页条数选择
│   │   ├── product-toolbar.tsx     # 搜索（textarea）、导入导出按钮
│   │   ├── product-form-dialog.tsx # 新增/编辑弹窗（左图右字段）
│   │   ├── product-tabs.tsx        # 品牌 Tab 切换
│   │   └── image-lookup-status.tsx # 图片查找结果反馈
│   ├── inventory-admin/          # 进销存管理组件
│   │   ├── inventory-page.tsx      # 主页面：搜索、表格、CRUD、导入导出
│   │   └── inventory-detail-panel.tsx # 右侧滑出面板 (Sheet)：明细行含图片
│   ├── ui/                       # shadcn/ui 组件 (button, dialog, table, sheet 等)
│   └── confirm-dialog.tsx        # 确认/消息弹窗
├── lib/
│   ├── api.ts                    # API 客户端（商品 + 进销存）
│   ├── brands.ts                 # 品牌定义 (BRANDS 数组)
│   ├── fields.ts                 # FIELD_LABELS、FIELD_GROUPS、SEASON_OPTIONS、CARD_DISPLAY_FIELDS
│   ├── types.ts                  # TypeScript 类型定义
│   └── utils.ts                  # cn() 工具函数
├── next.config.mjs               # Rewrites: /api/* → 后端
├── vitest.config.ts              # Vitest + jsdom
└── package.json
```

### 前端关键模式

- **品牌 Tab**: `BRANDS` 数组包含 `{ key: "all", label: "总览" }`。总览 Tab 隐藏新增/编辑/删除按钮。
- **字段定义**: `fields.ts` 中的 `FIELD_GROUPS` 定义列表卡片和编辑表单的分组展示。`FIELD_LABELS` 映射字段键到中文标签。新增字段需同时添加。
- **搜索**: Textarea 支持批量输入（逗号或换行分隔）。后端拆分关键词构建 ILIKE 条件。
- **商品表单**: 左右布局 — 左列：品牌选择 + 图片预览 + 图片查找；右列：SKU 行 + 分组字段。
- **进销存明细面板**: 使用 shadcn `Sheet`（右侧滑入）+ `Table` 组件。通过商品编码去掉后 5 位跨所有品牌图片目录自动加载商品图片。
- **自动计算**: 明细表单在输入变化时自动计算 `amount = quantity × unit_price`。
- **图片代理**: 所有图片通过 `/api/images/serve/{brand}/{path}` 或 `/api` + match-sku 返回的 `image_url` 提供。

## 常用命令

```bash
# 后端
cd backend
pytest                                              # 运行所有测试
pytest tests/test_api_products.py -k test_create    # 运行指定测试
python -m scripts.migrate_inventory_to_docs         # 执行进销存迁移
python -m scripts.add_product_name                   # 执行 product_name 迁移
python -m scripts.add_color_spec                     # 执行 color_spec 迁移

# 前端
cd frontend
pnpm run typecheck    # TypeScript 类型检查
pnpm run format       # Prettier 自动格式化
pnpm run lint         # ESLint 检查
pnpm run test         # Vitest 测试
pnpm run test:watch   # Vitest 监视模式
```

## 数据库

- **引擎**: PostgreSQL，通过 SQLAlchemy 2.0
- **商品表**: `qbd_mens_products`、`qbd_womens_products`、`yandou_products`、`yiban_products`
  - 通用列：id, source_workbook, source_sheet, source_row_number, raw_payload (JSON), extra_fields (JSON), sku (UNIQUE), original_sku，以及 30+ 个规范字段
- **进销存表**:
  - `inventory_records` — 主单据（date, supplier, total_count, amount, warehouse, document_type, summary）
  - `inventory_details` — 明细行（document_id FK → inventory_records.id ON DELETE CASCADE, product_code, product_name, color_spec, quantity, unit_price, amount）
  - `suppliers` — 供应商（name, contact, address, notes）
  - `warehouses` — 仓库（name, address, notes）
- **Schema 定义**: 商品 schema 在 `domain/schema.py` 的 `PRODUCT_TABLES` 字典中。进销存 schema 在 `domain/inventory_schema.py`。所有表通过 `storage/db.py` 注册到共享 METADATA。

## 技术栈

| 层 | 技术 |
|-------|-----------|
| 前端 | Next.js 16, React 19, TypeScript, Tailwind CSS 4, shadcn/ui |
| 后端 | Python 3.13, FastAPI, SQLAlchemy 2.0, PostgreSQL, openpyxl, xlrd, orjson |
| 测试 | 前端: Vitest + jsdom；后端: pytest + httpx |
