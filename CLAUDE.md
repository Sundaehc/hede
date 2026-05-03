# CLAUDE.md

This file provides guidance to Claude Code when working with code in this repository.

## Project Overview

商品信息档案管理系统 — Product Information Archive Management System for managing 4 shoe brands' product data with Excel import/export, image management, and batch search.

- **Brands**: 千百度男鞋 (qbd_mens) / 千百度女鞋 (qbd_womens) / 烟斗 (yandou) / 伊伴 (yiban)
- **Git Remote**: https://github.com/Sundaehc/hede.git

## Quick Start

### Requirements
- Python 3.13+
- Node.js 20+ with pnpm
- PostgreSQL

### Backend
```bash
cd backend
pip install -e ".[dev]"
# Create backend/.env (see Configuration below)
python -m cli import              # Import data from Excel
python -m scripts.enrich_from_jst # Enrich 5 fields from 聚水潭
uvicorn api_main:app --host 0.0.0.0 --port 8137
```

### Frontend
```bash
cd frontend
pnpm install
pnpm run dev    # http://127.0.0.1:3000
```

Frontend proxies `/api/*` to backend via Next.js rewrites. Override with `BACKEND_URL=http://host:port pnpm run dev`.

## Configuration

Create `backend/.env`:
```env
DATABASE_URL=postgresql+psycopg://postgres:password@127.0.0.1:5432/dbname
FRONTEND_ORIGIN=http://127.0.0.1:3000
EXCEL_ROOT=\\network\商品资料档案汇总
QBD_IMAGE_ROOT=\\network\千百度45度图男女鞋
YANDOU_IMAGE_ROOT=\\network\烟斗45图准确版
YIBAN_IMAGE_ROOT=\\network\伊伴男女鞋45度图
```

## Backend Structure

```
backend/
├── api/              # FastAPI routes: products CRUD, images, import/export
│   ├── routes/       #   products.py, images.py, import_export.py
│   ├── app.py        #   FastAPI app factory
│   └── schemas.py    #   Pydantic request/response models
├── domain/           # Data models & field definitions
│   ├── sources.py    #   COLUMN_ALIASES, CANONICAL_COLUMNS, IMAGE_BRAND_KEYS, WorkbookSpecs
│   └── schema.py     #   SQLAlchemy table definitions (PRODUCT_TABLES)
├── fileio/           # Excel reading (openpyxl/xlrd), ImageMatcher
├── pipeline/         # Data import pipeline (Excel → DB)
├── storage/          # Database access layer
│   ├── db.py         #   Engine creation, table init, bulk replace
│   └── product_repository.py  # CRUD operations, batch search, UNION ALL for 总览
├── transform/        # Data normalization, header mapping, record building
├── scripts/          # One-off scripts (enrich_from_jst)
├── tests/            # pytest tests
├── api_main.py       # API entry point
├── cli.py            # CLI entry point (data import)
└── config.py         # Settings dataclass, .env loading
```

### Key Backend Patterns

- **Brand routing**: All API endpoints accept `brand` as a string key. `"all"` triggers `list_all_products()` which uses SQL UNION ALL across brand tables.
- **Column aliases**: `domain/sources.py` maps Chinese column headers (e.g. "货号"→"sku", "尺码段"→"size_range") via `COLUMN_ALIASES`. Add new field mappings there.
- **Import merge logic**: `import_export.py` matches by sku first, then original_sku. Only overwrites fields that have values in the imported Excel. Unrecognized columns go to `extra_fields` JSON.
- **Image matching**: `ImageMatcher` finds images by SKU in brand-specific shared directories. `image_url_for()` generates `/images/serve/{brand}/{relative_path}` URLs.
- **JSON serialization**: `orjson` is used as SQLAlchemy's `json_serializer` to store Chinese characters directly (not `\uXXXX` escapes).
- **SKU uniqueness**: All tables have `UniqueConstraint("sku")`. Import pipeline deduplicates by keeping the last occurrence.

## Frontend Structure

```
frontend/
├── app/                          # Next.js page routes
├── components/
│   ├── product-admin/            # Business components
│   │   ├── product-admin-page.tsx  # Main page: brand tabs, search, list, CRUD
│   │   ├── product-table.tsx       # Card/table view, pagination, page size selector
│   │   ├── product-toolbar.tsx     # Search (textarea), import/export buttons
│   │   ├── product-form-dialog.tsx # Create/edit dialog (left: image, right: fields)
│   │   ├── product-tabs.tsx        # Brand tab triggers
│   │   └── image-lookup-status.tsx # Image lookup result feedback
│   ├── ui/                       # shadcn/ui components (button, dialog, table, etc.)
│   └── confirm-dialog.tsx        # Confirm/Message dialogs
├── lib/
│   ├── api.ts                    # API client functions
│   ├── brands.ts                 # Brand definitions (BRANDS array)
│   ├── fields.ts                 # FIELD_LABELS, FIELD_GROUPS, SEASON_OPTIONS, CARD_DISPLAY_FIELDS
│   ├── types.ts                  # TypeScript type definitions
│   └── utils.ts                  # cn() utility
├── next.config.mjs               # Rewrites: /api/* → backend
├── vitest.config.ts              # Vitest with jsdom
└── package.json
```

### Key Frontend Patterns

- **Brand tabs**: `BRANDS` array includes `{ key: "all", label: "总览" }`. 总览 tab hides create/edit/delete buttons.
- **Field definitions**: `FIELD_GROUPS` in `fields.ts` defines grouped display for both list cards and edit form. `FIELD_LABELS` maps field keys to Chinese labels. Add new fields to both.
- **Search**: Textarea supports batch input (comma or newline separated). Backend splits and builds ILIKE conditions.
- **Product form**: Left-right layout — left column has brand selector + image preview + image lookup, right column has SKU row + grouped fields.
- **Image proxy**: Product images served via `/api/images/serve/{brand}/{path}`.

## Common Commands

```bash
# Backend
cd backend
pytest                                              # Run all tests
pytest tests/test_api_products.py -k test_create    # Run specific test

# Frontend
cd frontend
pnpm run typecheck    # TypeScript check
pnpm run format       # Prettier auto-format
pnpm run lint         # ESLint
pnpm run test         # Vitest run
pnpm run test:watch   # Vitest watch mode
```

## Database

- **Engine**: PostgreSQL via SQLAlchemy 2.0
- **Tables**: `qbd_mens_products`, `qbd_womens_products`, `yandou_products`, `yiban_products`
- **Common columns**: id, source_workbook, source_sheet, source_row_number, raw_payload (JSON), extra_fields (JSON), sku (UNIQUE), original_sku, + ~30 canonical fields
- **Schema**: Defined in `domain/schema.py` via `PRODUCT_TABLES` dict. Add new columns to all 4 tables.

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Frontend | Next.js 16, React 19, TypeScript, Tailwind CSS 4, shadcn/ui |
| Backend | Python 3.13, FastAPI, SQLAlchemy 2.0, PostgreSQL, openpyxl, xlrd, orjson |
| Testing | Frontend: Vitest + jsdom; Backend: pytest + httpx |
