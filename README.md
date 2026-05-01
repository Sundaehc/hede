# 商品信息档案管理系统

商品信息档案管理系统，用于管理千百度男鞋、千百度女鞋、烟斗、伊伴四个品牌的商品数据，支持 Excel 导入导出、图片管理、批量搜索等功能。

## 项目结构

```
hede/
├── backend/           # FastAPI 后端
│   ├── api/           # API 路由（商品 CRUD、图片服务、导入导出）
│   ├── domain/        # 数据模型与字段定义
│   ├── fileio/        # Excel 读取、图片匹配
│   ├── pipeline/      # 数据导入管线
│   ├── storage/       # 数据库访问层（SQLAlchemy）
│   ├── transform/     # 数据转换与规范化
│   ├── scripts/       # 一次性脚本（聚水潭数据补全等）
│   ├── cli.py         # 命令行入口（数据导入）
│   └── api_main.py    # API 服务入口
├── frontend/          # Next.js 前端
│   ├── app/           # 页面路由
│   ├── components/    # UI 组件（shadcn/ui + 业务组件）
│   └── lib/           # API 客户端、类型定义、工具函数
└── docs/              # 项目文档
```

## 功能

- **品牌 Tab 切换** — 千百度男鞋 / 千百度女鞋 / 烟斗 / 伊伴 / 总览
- **商品列表** — 卡片式展示，含图片、全部字段、分页（10/50/100 条可选）
- **批量搜索** — 支持按货号或原始货号搜索，逗号或换行分隔多个关键词
- **新增 / 编辑** — 表单弹窗，季节分类下拉选择、日期选择器、图片自动匹配
- **删除** — 二次确认对话框
- **Excel 导出** — 导出当前品牌全部数据，中文文件名
- **Excel 导入** — 上传 Excel 按货号匹配更新，仅覆盖有值字段，自动查找图片
- **深色 / 浅色主题** — 右上角切换
- **SKU 唯一约束** — 数据库层面保证货号不重复

## 技术栈

| 层 | 技术 |
|---|------|
| 前端 | Next.js 16 + React 19 + TypeScript + Tailwind CSS 4 + shadcn/ui |
| 后端 | Python + FastAPI + SQLAlchemy + PostgreSQL |
| 数据源 | openpyxl / xlrd 读取 Excel，共享目录图片匹配 |

## 快速开始

### 1. 环境准备

- Python 3.13+
- Node.js 20+
- PostgreSQL

### 2. 后端

```bash
cd backend
pip install -e .
```

创建 `backend/.env` 文件：

```env
DATABASE_URL=postgresql+psycopg://postgres:密码@127.0.0.1:5432/数据库名
FRONTEND_ORIGIN=http://127.0.0.1:3000
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
uvicorn api_main:app --host 0.0.0.0 --port 8137
```

### 3. 前端

```bash
cd frontend
npm install
npm run dev
```

访问 http://127.0.0.1:3000

前端通过 Next.js rewrites 代理 API 请求到后端，无需配置后端地址。

## 数据库表结构

每个品牌一张表（`qbd_mens_products` / `qbd_womens_products` / `yandou_products` / `yiban_products`），包含：

- `id` — 主键
- `source_workbook` / `source_sheet` / `source_row_number` — 数据来源追踪
- `raw_payload` — 原始行数据完整快照（JSON）
- `extra_fields` — 未映射到规范字段的额外数据（JSON）
- `sku` — 货号（唯一约束）
- `original_sku` — 原始货号
- 以及尺码段、产品型号、供应商名、颜色代码、上市时间等 30+ 个规范字段
