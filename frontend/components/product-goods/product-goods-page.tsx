"use client"

import {
  useCallback,
  useDeferredValue,
  useEffect,
  memo,
  useMemo,
  useRef,
  useState,
  useTransition,
  type ReactNode,
} from "react"
import {
  ArrowRight,
  CalendarDays,
  Check,
  ChevronLeft,
  ChevronRight,
  ChevronsLeft,
  ChevronsRight,
  Download,
  Filter,
  History,
  ImageIcon,
  MoreHorizontal,
  Plus,
  RefreshCw,
  Search,
  SlidersHorizontal,
  Trash2,
  X,
} from "lucide-react"

import { useAuth } from "@/components/auth/auth-provider"
import { Button } from "@/components/ui/button"
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import { Input } from "@/components/ui/input"
import { Select } from "@/components/ui/select"
import { OperationLogDialog } from "@/components/operation-log-dialog"
import {
  ProductGoodsDetailDrawer,
  type ProductGoodsManualFields,
} from "@/components/product-goods/product-goods-detail-drawer"
import {
  listProductGoods,
  listProductGoodsFilterOptions,
  updateProductGoods,
  type ProductGoodsFilter,
  type ProductGoodsFilterOptionsResponse,
} from "@/lib/api"
import { BRANDS, type BrandKey } from "@/lib/brands"
import type { ProductGoodsItem, ProductGoodsResponse } from "@/lib/types"
import { cn } from "@/lib/utils"

const PAGE_SIZE = 50
const SUMMARY_PAGE_SIZE = 20
const PAGE_SIZE_OPTIONS = [20, 50, 100, 200]
const EXPORT_PAGE_SIZE = 200
const EXPORT_CONCURRENCY = 2
const PRODUCT_GOODS_PAGE_CACHE_LIMIT = 12
const PRODUCT_GOODS_CLIENT_CACHE_TTL_MS = 3 * 60 * 1000
const GOODS_BRANDS = BRANDS.filter((item) => item.key !== "all") as Array<{
  key: Exclude<BrandKey, "all">
  label: string
}>
const DEFAULT_BRAND: Exclude<BrandKey, "all"> = "cbanner_mens"
const DEFAULT_COLUMN_KEYS = [
  "year",
  "season",
  "platform",
  "category_l4",
  "first_order_date",
  "factory_sku",
  "factory_code",
  "factory_name",
  "color",
  "cost",
  "product_role",
  "product_type",
  "douyin_hot",
  "clearance",
  "remark",
  "total_order_count",
  "total_sales",
  "stock_plus_purchase",
  "in_transit_total",
  "return_qty",
  "post_replenishment_stock",
  "post_replenishment_turnover_days",
  "day_over_day",
  "yesterday_sales",
  "week_sales",
  "last_week_sales",
  "month_sales",
  "stock_total",
  "shortage_total",
  "stock_health",
  "broken_size_sku",
]
const PRODUCT_GOODS_FILTER_FIELDS: Array<{
  value: ProductGoodsFilter["field"]
  label: string
}> = [
  { value: "year", label: "年份" },
  { value: "season", label: "季节" },
  { value: "platform", label: "所属平台" },
  { value: "category_l4", label: "四级分类" },
  { value: "first_order_date", label: "首单日期" },
  { value: "factory_sku", label: "工厂货号" },
  { value: "factory_code", label: "工厂代码" },
  { value: "factory_name", label: "工厂名称" },
  { value: "style_code", label: "款号" },
  { value: "goods_code", label: "货号" },
  { value: "color", label: "颜色" },
  { value: "cost", label: "成本" },
  { value: "product_role", label: "商品角色" },
  { value: "product_type", label: "类型" },
  { value: "douyin_hot", label: "抖音爆款" },
  { value: "clearance", label: "清仓" },
  { value: "remark", label: "备注" },
]
const PRODUCT_GOODS_FILTER_OPERATORS: Array<{
  value: ProductGoodsFilter["operator"]
  label: string
}> = [
  { value: "contains", label: "包含" },
  { value: "equals", label: "等于" },
  { value: "empty", label: "为空" },
  { value: "not_empty", label: "不为空" },
]
type ColumnGroup =
  | "基础"
  | "经营"
  | "库存"
  | "销售"
  | "年度销量"
  | "月度销量"
  | "近14天每日销量"
  | "在仓库存"
  | "在途库存"
  | "库存合计"
  | "缺货库存"
  | "销售明细"
  | "补单明细"
  | "补单后尺码"
  | "日销量"
  | "周销量"
  | "月销量"
type TableColumn = {
  key: string
  label: string
  group: ColumnGroup
  width?: number
  filterField?: ProductGoodsFilter["field"]
  render: (row: ProductGoodsItem) => ReactNode
}
type ActiveColumnFilter = {
  field: ProductGoodsFilter["field"]
  label: string
  top: number
  left: number
}
type ProductGoodsView = "goods" | "style_summary"
type ProductGoodsPageContext = {
  brand: Exclude<BrandKey, "all">
  filters: ProductGoodsFilter[]
  pageSize: number
  query: string
  snapshotDate: string
  view: ProductGoodsView
}
type ProductGoodsPageCacheEntry = {
  data: ProductGoodsResponse
  cachedAt: number
}

const productGoodsPageCache = new Map<string, ProductGoodsPageCacheEntry>()
const productGoodsPagePrefetching = new Set<string>()
const productGoodsPageRequests = new Map<
  string,
  Promise<ProductGoodsResponse>
>()
const productGoodsColumnsCache = new Map<string, TableColumn[]>()

function value(value: unknown) {
  return value === null || value === undefined || value === ""
    ? ""
    : String(value)
}
function dateLabel(value: string) {
  const date = new Date(`${value}T00:00:00`)
  return `${String(date.getMonth() + 1).padStart(2, "0")}-${String(date.getDate()).padStart(2, "0")}`
}
function csvCell(value: unknown) {
  return `"${String(value ?? "").replaceAll('"', '""')}"`
}
function pageTokens(
  currentPage: number,
  totalPages: number
): Array<number | "ellipsis"> {
  if (totalPages <= 7)
    return Array.from({ length: totalPages }, (_, index) => index + 1)
  const tokens: Array<number | "ellipsis"> = [1]
  const start = Math.max(2, currentPage - 1)
  const end = Math.min(totalPages - 1, currentPage + 1)
  if (start > 2) tokens.push("ellipsis")
  for (let current = start; current <= end; current += 1) tokens.push(current)
  if (end < totalPages - 1) tokens.push("ellipsis")
  tokens.push(totalPages)
  return tokens
}

function metric(row: ProductGoodsItem, key: string) {
  return value(row.metrics?.[key])
}
function matrix(
  row: ProductGoodsItem,
  source: keyof Pick<
    ProductGoodsItem,
    | "stock_by_size"
    | "in_transit_by_size"
    | "inventory_by_size"
    | "shortage_by_size"
    | "sales_by_size"
    | "replenishment_by_size"
    | "post_replenishment_by_size"
  >,
  size: string
) {
  return value(row[source]?.[size])
}
function platformMatrix(
  row: ProductGoodsItem,
  source: keyof Pick<
    ProductGoodsItem,
    "daily_platform_sales" | "weekly_platform_sales" | "monthly_platform_sales"
  >,
  platform: string
) {
  return value(row[source]?.[platform])
}
function salesPeriodMatrix(
  row: ProductGoodsItem,
  source: keyof Pick<ProductGoodsItem, "annual_sales" | "monthly_sales">,
  period: string
) {
  return value(row[source]?.[period])
}
function manualTag(tag: unknown) {
  return tag === true ? "是" : tag === false ? "" : value(tag)
}

function normalizeProductGoodsResponse(
  response: ProductGoodsResponse
): ProductGoodsResponse {
  return {
    ...response,
    items: (response.items ?? []).map((item) => ({
      ...item,
      metrics: item.metrics ?? {},
      stock_by_size: item.stock_by_size ?? {},
      in_transit_by_size: item.in_transit_by_size ?? {},
      inventory_by_size: item.inventory_by_size ?? {},
      shortage_by_size: item.shortage_by_size ?? {},
      sales_by_size: item.sales_by_size ?? {},
      replenishment_by_size: item.replenishment_by_size ?? {},
      post_replenishment_by_size: item.post_replenishment_by_size ?? {},
      daily_sales_by_date: item.daily_sales_by_date ?? {},
      annual_sales: item.annual_sales ?? {},
      monthly_sales: item.monthly_sales ?? {},
      daily_platform_sales: item.daily_platform_sales ?? {},
      weekly_platform_sales: item.weekly_platform_sales ?? {},
      monthly_platform_sales: item.monthly_platform_sales ?? {},
    })),
    daily_dates: response.daily_dates ?? [],
    annual_sales_columns: response.annual_sales_columns ?? [],
    monthly_sales_columns: response.monthly_sales_columns ?? [],
    size_columns: response.size_columns ?? [],
    platform_columns: response.platform_columns ?? [],
    snapshot_date: response.snapshot_date ?? null,
    snapshot_dates: response.snapshot_dates ?? [],
  }
}

function productGoodsPageCacheKey(
  context: ProductGoodsPageContext,
  page: number
) {
  return JSON.stringify([
    context.brand,
    context.filters,
    context.pageSize,
    context.query,
    context.snapshotDate,
    context.view,
    page,
  ])
}

async function loadProductGoodsPage(
  context: ProductGoodsPageContext,
  page: number,
  cacheBust?: string
) {
  const requestKey = `${productGoodsPageCacheKey(context, page)}:${cacheBust ?? ""}`
  const existingRequest = productGoodsPageRequests.get(requestKey)
  if (existingRequest) return existingRequest

  const request = listProductGoods({
    brand: context.brand,
    query: context.query || undefined,
    filters: context.filters.length ? context.filters : undefined,
    view: context.view,
    snapshotDate: context.snapshotDate || undefined,
    page,
    pageSize: context.pageSize,
    cacheBust,
  }).then(normalizeProductGoodsResponse)
  productGoodsPageRequests.set(requestKey, request)
  void request.then(
    () => {
      if (productGoodsPageRequests.get(requestKey) === request)
        productGoodsPageRequests.delete(requestKey)
    },
    () => {
      if (productGoodsPageRequests.get(requestKey) === request)
        productGoodsPageRequests.delete(requestKey)
    }
  )
  return request
}

function rememberProductGoodsPage(
  cache: Map<string, ProductGoodsPageCacheEntry>,
  key: string,
  data: ProductGoodsResponse
) {
  if (cache.has(key)) cache.delete(key)
  cache.set(key, { data, cachedAt: Date.now() })

  while (cache.size > PRODUCT_GOODS_PAGE_CACHE_LIMIT) {
    const oldestKey = cache.keys().next().value
    if (!oldestKey) break
    cache.delete(oldestKey)
  }
}

function getCachedProductGoodsPage(
  cache: Map<string, ProductGoodsPageCacheEntry>,
  key: string
) {
  const entry = cache.get(key)
  if (!entry) return null

  if (Date.now() - entry.cachedAt > PRODUCT_GOODS_CLIENT_CACHE_TTL_MS) {
    cache.delete(key)
    return null
  }

  cache.delete(key)
  cache.set(key, entry)
  return entry
}

function createColumns(data: ProductGoodsResponse): TableColumn[] {
  const staticColumns: TableColumn[] = [
    {
      key: "year",
      label: "年份",
      group: "基础",
      render: (row) => value(row.year),
    },
    {
      key: "season",
      label: "季节",
      group: "基础",
      render: (row) => value(row.season),
    },
    {
      key: "platform",
      label: "所属平台",
      group: "基础",
      width: 120,
      render: (row) => value(row.platform),
    },
    {
      key: "category_l4",
      label: "四级分类",
      group: "基础",
      width: 120,
      render: (row) => value(row.category_l4),
    },
    {
      key: "first_order_date",
      label: "首单日期",
      group: "基础",
      width: 100,
      render: (row) => value(row.first_order_date),
    },
    {
      key: "factory_sku",
      label: "工厂货号",
      group: "基础",
      width: 110,
      render: (row) => value(row.factory_sku),
    },
    {
      key: "factory_code",
      label: "工厂代码",
      group: "基础",
      width: 95,
      render: (row) => value(row.factory_code),
    },
    {
      key: "factory_name",
      label: "工厂名称",
      group: "基础",
      width: 150,
      render: (row) => value(row.factory_name),
    },
    {
      key: "color",
      label: "颜色",
      group: "基础",
      render: (row) => value(row.color),
    },
    {
      key: "cost",
      label: "成本",
      group: "基础",
      render: (row) => value(row.cost),
    },
    {
      key: "product_role",
      label: "商品角色",
      group: "经营",
      render: (row) => value(row.product_role),
    },
    {
      key: "product_type",
      label: "类型",
      group: "经营",
      render: (row) => value(row.product_type),
    },
    {
      key: "douyin_hot",
      label: "抖音爆款",
      group: "经营",
      render: (row) => manualTag(row.douyin_hot),
    },
    {
      key: "clearance",
      label: "清仓",
      group: "经营",
      render: (row) => manualTag(row.clearance),
    },
    {
      key: "remark",
      label: "备注",
      group: "经营",
      width: 160,
      render: (row) => value(row.remark),
    },
    {
      key: "total_order_count",
      label: "总订单量",
      group: "销售",
      render: (row) => metric(row, "total_order_count"),
    },
    {
      key: "total_sales",
      label: "总销量",
      group: "销售",
      render: (row) => metric(row, "total_sales"),
    },
    {
      key: "stock_plus_purchase",
      label: "在仓库存+进货仓",
      group: "库存",
      render: (row) => metric(row, "stock_plus_purchase"),
    },
    {
      key: "in_transit_total",
      label: "在途库存",
      group: "库存",
      render: (row) => metric(row, "in_transit_total"),
    },
    {
      key: "return_qty",
      label: "回单",
      group: "库存",
      render: (row) => metric(row, "return_qty"),
    },
    {
      key: "post_replenishment_stock",
      label: "补单后库存",
      group: "库存",
      render: (row) => metric(row, "post_replenishment_stock"),
    },
    {
      key: "post_replenishment_turnover_days",
      label: "补单后周转天数",
      group: "库存",
      render: (row) => metric(row, "post_replenishment_turnover_days"),
    },
    {
      key: "day_over_day",
      label: "昨比前日",
      group: "销售",
      render: (row) => metric(row, "day_over_day"),
    },
    {
      key: "yesterday_sales",
      label: "昨日销量",
      group: "销售",
      render: (row) => metric(row, "yesterday_sales"),
    },
    {
      key: "normal_shelf_sales",
      label: "正价货架销量",
      group: "销售",
      render: (row) => metric(row, "normal_shelf_sales"),
    },
    {
      key: "clearance_sales",
      label: "清仓销量",
      group: "销售",
      render: (row) => metric(row, "clearance_sales"),
    },
    {
      key: "week_sales",
      label: "近7天周销量",
      group: "销售",
      render: (row) => metric(row, "week_sales"),
    },
    {
      key: "normal_shelf_week_sales",
      label: "正价货架7天销量",
      group: "销售",
      render: (row) => metric(row, "normal_shelf_week_sales"),
    },
    {
      key: "clearance_week_sales",
      label: "清仓7天销量",
      group: "销售",
      render: (row) => metric(row, "clearance_week_sales"),
    },
    {
      key: "last_week_sales",
      label: "上周销量",
      group: "销售",
      render: (row) => metric(row, "last_week_sales"),
    },
    {
      key: "same_week_sales",
      label: "同期周销",
      group: "销售",
      render: (row) => metric(row, "same_week_sales"),
    },
    {
      key: "same_week_non_douyin_sales",
      label: "同期非抖音周销",
      group: "销售",
      render: (row) => metric(row, "same_week_non_douyin_sales"),
    },
    {
      key: "stock_total",
      label: "在仓合计",
      group: "库存",
      render: (row) => value(row.stock_total),
    },
    {
      key: "shortage_total",
      label: "缺货合计",
      group: "库存",
      render: (row) => metric(row, "shortage_total"),
    },
    {
      key: "stock_health",
      label: "库存健康度提醒",
      group: "库存",
      width: 130,
      render: (row) => metric(row, "stock_health"),
    },
    {
      key: "broken_size_sku",
      label: "断码SKU",
      group: "库存",
      render: (row) => metric(row, "broken_size_sku"),
    },
    {
      key: "sales_size_total",
      label: "销售明细合计",
      group: "销售",
      render: (row) => metric(row, "sales_size_total"),
    },
    {
      key: "replenishment_total",
      label: "补单合计",
      group: "库存",
      render: (row) => metric(row, "replenishment_total"),
    },
    {
      key: "post_replenishment_total",
      label: "补单后合计",
      group: "库存",
      render: (row) => metric(row, "post_replenishment_total"),
    },
    {
      key: "three_day_change",
      label: "三天环比",
      group: "销售",
      render: (row) => metric(row, "three_day_change"),
    },
    {
      key: "month_sales",
      label: "月度销量",
      group: "销售",
      render: (row) => metric(row, "month_sales"),
    },
  ]
  for (const column of staticColumns) {
    const filterField = PRODUCT_GOODS_FILTER_FIELDS.find(
      (item) => item.value === column.key
    )
    if (filterField) column.filterField = filterField.value
  }
  const annual = data.annual_sales_columns.map((period) => ({
    key: `annual:${period}`,
    label: `${period}销量`,
    group: "年度销量" as const,
    render: (row: ProductGoodsItem) =>
      salesPeriodMatrix(row, "annual_sales", period),
  }))
  const monthly = data.monthly_sales_columns.map((period) => ({
    key: `monthly:${period}`,
    label: period,
    group: "月度销量" as const,
    render: (row: ProductGoodsItem) =>
      salesPeriodMatrix(row, "monthly_sales", period),
  }))
  const daily = data.daily_dates.map((day) => ({
    key: `daily:${day}`,
    label: dateLabel(day),
    group: "近14天每日销量" as const,
    render: (row: ProductGoodsItem) => value(row.daily_sales_by_date[day]),
  }))
  const sizeGroups: Array<
    [
      ColumnGroup,
      keyof Pick<
        ProductGoodsItem,
        | "stock_by_size"
        | "in_transit_by_size"
        | "inventory_by_size"
        | "shortage_by_size"
        | "sales_by_size"
        | "replenishment_by_size"
        | "post_replenishment_by_size"
      >,
    ]
  > = [
    ["在仓库存", "stock_by_size"],
    ["在途库存", "in_transit_by_size"],
    ["库存合计", "inventory_by_size"],
    ["缺货库存", "shortage_by_size"],
    ["销售明细", "sales_by_size"],
    ["补单明细", "replenishment_by_size"],
    ["补单后尺码", "post_replenishment_by_size"],
  ]
  const sizes = sizeGroups.flatMap(([group, source]) =>
    data.size_columns.map((size) => ({
      key: `${group}:${size}`,
      label: size,
      group,
      render: (row: ProductGoodsItem) => matrix(row, source, size),
    }))
  )
  const platforms = [
    ["日销量", "daily_platform_sales"],
    ["周销量", "weekly_platform_sales"],
    ["月销量", "monthly_platform_sales"],
  ] as Array<
    [
      ColumnGroup,
      keyof Pick<
        ProductGoodsItem,
        | "daily_platform_sales"
        | "weekly_platform_sales"
        | "monthly_platform_sales"
      >,
    ]
  >
  const platformColumns = platforms.flatMap(([group, source]) =>
    data.platform_columns.map((platform) => ({
      key: `${group}:${platform}`,
      label: platform,
      group,
      render: (row: ProductGoodsItem) => platformMatrix(row, source, platform),
    }))
  )
  return [
    ...staticColumns,
    ...annual,
    ...monthly,
    ...daily,
    ...sizes,
    ...platformColumns,
  ]
}

function getProductGoodsColumns(data: ProductGoodsResponse) {
  const schemaKey = JSON.stringify([
    data.annual_sales_columns,
    data.monthly_sales_columns,
    data.daily_dates,
    data.size_columns,
    data.platform_columns,
  ])
  const cachedColumns = productGoodsColumnsCache.get(schemaKey)
  if (cachedColumns) {
    productGoodsColumnsCache.delete(schemaKey)
    productGoodsColumnsCache.set(schemaKey, cachedColumns)
    return cachedColumns
  }

  const columns = createColumns(data)
  productGoodsColumnsCache.set(schemaKey, columns)
  while (productGoodsColumnsCache.size > PRODUCT_GOODS_PAGE_CACHE_LIMIT) {
    const oldestKey = productGoodsColumnsCache.keys().next().value
    if (!oldestKey) break
    productGoodsColumnsCache.delete(oldestKey)
  }
  return columns
}

function exportColumnValue(item: ProductGoodsItem, column: TableColumn) {
  const rendered = column.render(item)
  return typeof rendered === "string" || typeof rendered === "number"
    ? rendered
    : ""
}

function timestampForFilename(now: Date) {
  const date = [
    now.getFullYear(),
    String(now.getMonth() + 1).padStart(2, "0"),
    String(now.getDate()).padStart(2, "0"),
  ].join("")
  const time = [
    String(now.getHours()).padStart(2, "0"),
    String(now.getMinutes()).padStart(2, "0"),
    String(now.getSeconds()).padStart(2, "0"),
  ].join("")
  return `${date}_${time}`
}

function exportCsv(
  items: ProductGoodsItem[],
  columns: TableColumn[],
  filename: string,
  isStyleSummary: boolean
) {
  const headers = [
    "图片链接",
    ...(isStyleSummary ? ["款号"] : ["货号", "款号"]),
    ...columns.map((column) => `${column.group}-${column.label}`),
  ]
  const rows = items.map((item) => [
    item.image_url
      ? new URL(`/api${item.image_url}`, window.location.origin).toString()
      : "",
    ...(isStyleSummary
      ? [item.style_code]
      : [item.goods_code, item.style_code]),
    ...columns.map((column) => exportColumnValue(item, column)),
  ])
  const blob = new Blob(
    [
      "\uFEFF",
      [headers, ...rows].map((row) => row.map(csvCell).join(",")).join("\r\n"),
    ],
    { type: "text/csv;charset=utf-8" }
  )
  const link = document.createElement("a")
  link.href = URL.createObjectURL(blob)
  link.download = filename
  link.click()
  URL.revokeObjectURL(link.href)
}

const ProductGoodsGridRow = memo(function ProductGoodsGridRow({
  item,
  isStyleSummary,
  onPreviewImage,
  onSelectItem,
  visibleColumns,
}: {
  item: ProductGoodsItem
  isStyleSummary: boolean
  onPreviewImage: (item: ProductGoodsItem) => void
  onSelectItem: (item: ProductGoodsItem) => void
  visibleColumns: TableColumn[]
}) {
  return (
    <tr className="group transition-colors hover:bg-muted/50">
      <td className="sticky left-0 z-20 w-20 max-w-[5rem] min-w-[5rem] border-b border-border bg-card px-3 py-2 text-center group-hover:bg-muted">
        <button
          type="button"
          className={cn(
            "mx-auto inline-flex rounded-lg focus:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2",
            item.image_url && "cursor-zoom-in"
          )}
          onClick={() => onPreviewImage(item)}
          disabled={!item.image_url}
          aria-label={item.image_url ? "查看原图" : "暂无图片"}
        >
          {item.image_url ? (
            <img
              src={`/api${item.image_url}`}
              alt={item.goods_code || "商品图片"}
              className="h-12 w-12 rounded-lg border border-border object-cover"
              loading="lazy"
              decoding="async"
            />
          ) : (
            <ImageIcon className="h-4 w-4 text-muted-foreground/45" />
          )}
        </button>
      </td>
      <td className="sticky left-20 z-20 w-40 max-w-[10rem] min-w-[10rem] border-b border-border bg-card px-3 py-2 font-medium group-hover:bg-muted">
        {value(isStyleSummary ? item.style_code : item.goods_code)}
      </td>
      {!isStyleSummary && (
        <td className="sticky left-60 z-20 w-40 max-w-[10rem] min-w-[10rem] border-b border-border bg-card px-3 py-2 group-hover:bg-muted">
          {value(item.style_code)}
        </td>
      )}
      {visibleColumns.map((column) => (
        <td
          key={column.key}
          className="border-b border-border px-3 py-2 text-center align-middle tabular-nums"
        >
          {column.render(item)}
        </td>
      ))}
      <td className="sticky right-0 z-20 w-20 border-b border-border bg-card px-3 py-2 text-center group-hover:bg-muted">
        <Button
          variant="ghost"
          size="icon"
          onClick={() => onSelectItem(item)}
          aria-label="查看详情"
        >
          <ChevronRight className="h-4 w-4" />
        </Button>
      </td>
    </tr>
  )
})

const ProductGoodsGrid = memo(function ProductGoodsGrid({
  activeFilterFields,
  groups,
  items,
  isStyleSummary,
  loading,
  onOpenColumnFilter,
  onPreviewImage,
  onSelectItem,
  tableWidth,
  visibleColumns,
}: {
  activeFilterFields: ReadonlySet<ProductGoodsFilter["field"]>
  groups: Array<{ name: ColumnGroup; columns: TableColumn[] }>
  items: ProductGoodsItem[]
  isStyleSummary: boolean
  loading: boolean
  onOpenColumnFilter: (
    field: ProductGoodsFilter["field"],
    label: string,
    target: HTMLElement
  ) => void
  onPreviewImage: (item: ProductGoodsItem) => void
  onSelectItem: (item: ProductGoodsItem) => void
  tableWidth: number
  visibleColumns: TableColumn[]
}) {
  return (
    <div className="relative max-h-[72svh] min-h-[360px] overflow-auto">
      <table
        style={{ minWidth: tableWidth }}
        className={cn(
          "w-full border-separate border-spacing-0 text-[13px] transition-opacity duration-150",
          loading && items.length > 0 && "opacity-60"
        )}
        aria-busy={loading}
      >
        <thead className="sticky top-0 z-[60] bg-card">
          <tr className="text-xs text-muted-foreground">
            <th
              rowSpan={2}
              className="sticky left-0 z-[70] w-20 max-w-[5rem] min-w-[5rem] border-b border-border bg-card px-3 py-2.5 text-center font-medium"
            >
              图片
            </th>
            <th
              rowSpan={2}
              className="sticky left-20 z-[70] w-40 max-w-[10rem] min-w-[10rem] border-b border-border bg-card px-3 py-2.5 text-left font-medium"
            >
              <div className="flex items-center justify-between gap-1">
                <span>{isStyleSummary ? "款号" : "货号"}</span>
                <button
                  type="button"
                  className={cn(
                    "rounded p-0.5 transition-colors hover:bg-muted",
                    activeFilterFields.has(
                      isStyleSummary ? "style_code" : "goods_code"
                    )
                      ? "text-primary"
                      : "text-muted-foreground/80"
                  )}
                  onClick={(event) =>
                    onOpenColumnFilter(
                      isStyleSummary ? "style_code" : "goods_code",
                      isStyleSummary ? "款号" : "货号",
                      event.currentTarget
                    )
                  }
                  aria-label={`筛选${isStyleSummary ? "款号" : "货号"}`}
                  title={`筛选${isStyleSummary ? "款号" : "货号"}`}
                >
                  <Filter className="h-3.5 w-3.5" />
                </button>
              </div>
            </th>
            {!isStyleSummary && (
              <th
                rowSpan={2}
                className="sticky left-60 z-[70] w-40 max-w-[10rem] min-w-[10rem] border-b border-border bg-card px-3 py-2.5 text-left font-medium"
              >
                <div className="flex items-center justify-between gap-1">
                  <span>款号</span>
                  <button
                    type="button"
                    className={cn(
                      "rounded p-0.5 transition-colors hover:bg-muted",
                      activeFilterFields.has("style_code")
                        ? "text-primary"
                        : "text-muted-foreground/80"
                    )}
                    onClick={(event) =>
                      onOpenColumnFilter(
                        "style_code",
                        "款号",
                        event.currentTarget
                      )
                    }
                    aria-label="筛选款号"
                    title="筛选款号"
                  >
                    <Filter className="h-3.5 w-3.5" />
                  </button>
                </div>
              </th>
            )}
            {groups.map(({ name, columns: groupColumns }, groupIndex) => (
              <th
                key={`${name}-${groupIndex}-${groupColumns[0]?.key ?? "empty"}`}
                colSpan={groupColumns.length}
                className="border-b border-border bg-card px-3 py-2.5 text-center font-medium"
              >
                {name}
              </th>
            ))}
            <th
              rowSpan={2}
              className="sticky right-0 z-[70] w-20 border-b border-border bg-card px-3 py-2.5 text-center font-medium"
            >
              详情
            </th>
          </tr>
          <tr className="text-xs text-muted-foreground">
            {visibleColumns.map((column) => (
              <th
                key={column.key}
                style={{ minWidth: column.width ?? 78 }}
                className="border-b border-border bg-card px-2 py-2 text-center font-normal"
              >
                <div className="flex items-center justify-center gap-0.5">
                  <span className="truncate">{column.label}</span>
                  {column.filterField && (
                    <button
                      type="button"
                      className={cn(
                        "shrink-0 rounded p-0.5 transition-colors hover:bg-muted",
                        activeFilterFields.has(column.filterField)
                          ? "text-primary"
                          : "text-muted-foreground/80"
                      )}
                      onClick={(event) =>
                        onOpenColumnFilter(
                          column.filterField!,
                          column.label,
                          event.currentTarget
                        )
                      }
                      aria-label={`筛选${column.label}`}
                      title={`筛选${column.label}`}
                    >
                      <Filter className="h-3 w-3" />
                    </button>
                  )}
                </div>
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {items.length === 0 ? (
            <tr>
              <td
                colSpan={visibleColumns.length + (isStyleSummary ? 3 : 4)}
                className="px-4 py-16 text-center text-muted-foreground"
              >
                {loading ? "正在加载商品货品表..." : "暂无匹配商品"}
              </td>
            </tr>
          ) : (
            items.map((item) => (
              <ProductGoodsGridRow
                key={item.id}
                item={item}
                isStyleSummary={isStyleSummary}
                onPreviewImage={onPreviewImage}
                onSelectItem={onSelectItem}
                visibleColumns={visibleColumns}
              />
            ))
          )}
        </tbody>
      </table>
      {loading && items.length > 0 && (
        <div className="pointer-events-none absolute top-3 right-3 z-[80] rounded-full border border-border bg-card/95 px-3 py-1.5 text-xs text-muted-foreground shadow-sm">
          正在更新商品货品表...
        </div>
      )}
    </div>
  )
})

export function ProductGoodsPage() {
  const { hasPermission } = useAuth()
  const [brand, setBrand] = useState<Exclude<BrandKey, "all">>(DEFAULT_BRAND)
  const [data, setData] = useState<ProductGoodsResponse>({
    items: [],
    total: 0,
    page: 1,
    page_size: PAGE_SIZE,
    daily_dates: [],
    annual_sales_columns: [],
    monthly_sales_columns: [],
    size_columns: [],
    platform_columns: [],
    snapshot_date: null,
    snapshot_dates: [],
  })
  const [page, setPage] = useState(1)
  const [pageSize, setPageSize] = useState(PAGE_SIZE)
  const [pageInput, setPageInput] = useState("1")
  const [queryInput, setQueryInput] = useState("")
  const [query, setQuery] = useState("")
  const [filters, setFilters] = useState<ProductGoodsFilter[]>([])
  const [draftFilters, setDraftFilters] = useState<ProductGoodsFilter[]>([])
  const [filterOpen, setFilterOpen] = useState(false)
  const [filterError, setFilterError] = useState("")
  const [activeColumnFilter, setActiveColumnFilter] =
    useState<ActiveColumnFilter | null>(null)
  const [columnFilterData, setColumnFilterData] =
    useState<ProductGoodsFilterOptionsResponse | null>(null)
  const [columnFilterSearch, setColumnFilterSearch] = useState("")
  const [draftColumnValues, setDraftColumnValues] = useState<string[] | null>(
    null
  )
  const [columnFilterLoading, setColumnFilterLoading] = useState(false)
  const [columnFilterError, setColumnFilterError] = useState("")
  const [snapshotDate, setSnapshotDate] = useState("")
  const historyDateInputRef = useRef<HTMLInputElement>(null)
  const loadRequestIdRef = useRef(0)
  const columnFilterRequestIdRef = useRef(0)
  const pageCacheRef = useRef(productGoodsPageCache)
  const prefetchingPagesRef = useRef(productGoodsPagePrefetching)
  const refreshNonceRef = useRef<string | undefined>(undefined)
  const [reloadVersion, setReloadVersion] = useState(0)
  const [operationLogOpen, setOperationLogOpen] = useState(false)
  const [previewImage, setPreviewImage] = useState<{
    src: string
    alt: string
  } | null>(null)
  const [selectedItem, setSelectedItem] = useState<ProductGoodsItem | null>(
    null
  )
  const [loading, setLoading] = useState(true)
  const [isExporting, setIsExporting] = useState(false)
  const [exportProgress, setExportProgress] = useState<{
    loaded: number
    total: number
  } | null>(null)
  const [, startTransition] = useTransition()
  const [dataView, setDataView] = useState<ProductGoodsView>("goods")
  const [renderedDataView, setRenderedDataView] =
    useState<ProductGoodsView>("goods")
  const [columnMode, setColumnMode] = useState<"full" | "custom">("full")
  const [pickerOpen, setPickerOpen] = useState(false)
  const [customKeys, setCustomKeys] = useState<string[]>(DEFAULT_COLUMN_KEYS)
  const [draftKeys, setDraftKeys] = useState<string[]>(DEFAULT_COLUMN_KEYS)
  const [columnSearch, setColumnSearch] = useState("")
  const prefetchDataView = useCallback(
    (nextView: ProductGoodsView) => {
      if (nextView === dataView) return
      const nextPageSize =
        nextView === "style_summary" ? SUMMARY_PAGE_SIZE : pageSize
      const context: ProductGoodsPageContext = {
        brand,
        filters,
        pageSize: nextPageSize,
        query,
        snapshotDate,
        view: nextView,
      }
      const cacheKey = productGoodsPageCacheKey(context, 1)
      if (
        getCachedProductGoodsPage(pageCacheRef.current, cacheKey) ||
        prefetchingPagesRef.current.has(cacheKey)
      )
        return

      prefetchingPagesRef.current.add(cacheKey)
      void loadProductGoodsPage(context, 1)
        .then((response) => {
          rememberProductGoodsPage(pageCacheRef.current, cacheKey, response)
        })
        .catch(() => {
          // View prefetch is optional; the active request surfaces any failure.
        })
        .finally(() => {
          prefetchingPagesRef.current.delete(cacheKey)
        })
    },
    [brand, dataView, filters, pageSize, query, snapshotDate]
  )
  useEffect(() => {
    let cancelled = false
    const requestId = loadRequestIdRef.current + 1
    loadRequestIdRef.current = requestId
    const isCurrentRequest = () =>
      !cancelled && loadRequestIdRef.current === requestId
    const context: ProductGoodsPageContext = {
      brand,
      filters,
      pageSize,
      query,
      snapshotDate,
      view: dataView,
    }
    const cacheBust = refreshNonceRef.current
    refreshNonceRef.current = undefined
    const cacheKey = productGoodsPageCacheKey(context, page)

    function prefetchPage(pageToPrefetch: number, totalPageCount: number) {
      if (pageToPrefetch < 1 || pageToPrefetch > totalPageCount) return

      const prefetchKey = productGoodsPageCacheKey(context, pageToPrefetch)
      if (
        getCachedProductGoodsPage(pageCacheRef.current, prefetchKey) ||
        prefetchingPagesRef.current.has(prefetchKey)
      )
        return

      prefetchingPagesRef.current.add(prefetchKey)
      void loadProductGoodsPage(context, pageToPrefetch)
        .then((response) => {
          rememberProductGoodsPage(pageCacheRef.current, prefetchKey, response)
        })
        .catch(() => {
          // Prefetch is only a speed-up; the active request remains authoritative.
        })
        .finally(() => {
          prefetchingPagesRef.current.delete(prefetchKey)
        })
    }

    const cachedEntry = getCachedProductGoodsPage(
      pageCacheRef.current,
      cacheKey
    )
    if (cachedEntry) {
      setData(cachedEntry.data)
      setRenderedDataView(context.view)
      setLoading(false)
      const cachedTotalPages = Math.max(
        1,
        Math.ceil(cachedEntry.data.total / pageSize)
      )
      prefetchPage(page - 1, cachedTotalPages)
      prefetchPage(page + 1, cachedTotalPages)
      return () => {
        cancelled = true
      }
    }

    async function loadData() {
      setLoading(true)
      try {
        const response = await loadProductGoodsPage(context, page, cacheBust)
        if (!isCurrentRequest()) return
        rememberProductGoodsPage(pageCacheRef.current, cacheKey, response)
        setData(response)
        setRenderedDataView(context.view)
        const loadedTotalPages = Math.max(
          1,
          Math.ceil(response.total / pageSize)
        )
        prefetchPage(page - 1, loadedTotalPages)
        prefetchPage(page + 1, loadedTotalPages)
      } catch {
        // Keep the current page visible if a replacement request fails.
      } finally {
        if (isCurrentRequest()) setLoading(false)
      }
    }

    void loadData()
    return () => {
      cancelled = true
    }
  }, [
    brand,
    dataView,
    filters,
    page,
    pageSize,
    query,
    reloadVersion,
    snapshotDate,
  ])
  useEffect(() => {
    if (!activeColumnFilter) return
    const requestId = ++columnFilterRequestIdRef.current
    setColumnFilterLoading(true)
    setColumnFilterError("")
    void listProductGoodsFilterOptions({
      brand,
      field: activeColumnFilter.field,
      filters,
      query: query || undefined,
    })
      .then((response) => {
        if (requestId !== columnFilterRequestIdRef.current) return
        setColumnFilterData(response)
        setDraftColumnValues((current) => {
          if (current !== null) return current
          const fieldFilters = filters.filter(
            (item) => item.field === response.field
          )
          const includeFilter = fieldFilters.find(
            (item) => item.operator === "in"
          )
          if (includeFilter) return includeFilter.values ?? []
          const excludeFilter = fieldFilters.find(
            (item) => item.operator === "not_in"
          )
          if (excludeFilter) {
            const excluded = new Set(excludeFilter.values ?? [])
            return response.options
              .filter((item) => !excluded.has(item.value))
              .map((item) => item.value)
          }
          const selected = fieldFilters.flatMap((item) =>
            item.operator === "equals"
              ? [item.value ?? ""]
              : item.operator === "empty"
                ? [""]
                : []
          )
          return selected.length
            ? selected
            : response.options.map((item) => item.value)
        })
      })
      .catch((error: unknown) => {
        if (requestId === columnFilterRequestIdRef.current)
          setColumnFilterError(
            error instanceof Error ? error.message : "筛选项加载失败"
          )
      })
      .finally(() => {
        if (requestId === columnFilterRequestIdRef.current)
          setColumnFilterLoading(false)
      })
  }, [activeColumnFilter, brand, filters, query])
  const columns = useMemo(
    () => getProductGoodsColumns(data),
    [
      data.annual_sales_columns,
      data.daily_dates,
      data.monthly_sales_columns,
      data.platform_columns,
      data.size_columns,
    ]
  )
  const visibleColumns = useMemo(() => {
    const selected =
      columnMode === "full"
        ? columns
        : columns.filter((column) => customKeys.includes(column.key))
    return renderedDataView === "style_summary"
      ? selected.filter((column) => column.key !== "color")
      : selected
  }, [columnMode, columns, customKeys, renderedDataView])
  const deferredVisibleColumns = useDeferredValue(visibleColumns)
  const groups = useMemo(
    () =>
      deferredVisibleColumns.reduce<
        Array<{ name: ColumnGroup; columns: TableColumn[] }>
      >((result, column) => {
        const current = result.at(-1)
        if (current?.name === column.group) current.columns.push(column)
        else result.push({ name: column.group, columns: [column] })
        return result
      }, []),
    [deferredVisibleColumns]
  )
  const groupedPickerColumns = useMemo(
    () =>
      columns.reduce<Record<string, TableColumn[]>>(
        (result, column) => ({
          ...result,
          [column.group]: [...(result[column.group] ?? []), column],
        }),
        {}
      ),
    [columns]
  )
  const matchingColumnFilterOptions = useMemo(() => {
    const keyword = columnFilterSearch.trim().toLocaleLowerCase()
    if (!keyword) return columnFilterData?.options ?? []
    return (columnFilterData?.options ?? []).filter((item) =>
      item.value.toLocaleLowerCase().includes(keyword)
    )
  }, [columnFilterData, columnFilterSearch])
  const visibleColumnFilterOptions = useMemo(
    () => matchingColumnFilterOptions.slice(0, 300),
    [matchingColumnFilterOptions]
  )
  const hasHiddenColumnFilterOptions =
    matchingColumnFilterOptions.length > visibleColumnFilterOptions.length
  const filterableColumnButtons = useMemo<
    Array<{ field: ProductGoodsFilter["field"]; label: string }>
  >(
    () => [
      { field: "goods_code", label: "货号" },
      { field: "style_code", label: "款号" },
      ...visibleColumns.flatMap((column) =>
        column.filterField
          ? [{ field: column.filterField, label: column.label }]
          : []
      ),
    ],
    [visibleColumns]
  )
  const selectedColumnValues = useMemo(
    () =>
      new Set(
        draftColumnValues ??
          columnFilterData?.options.map((item) => item.value) ??
          []
      ),
    [columnFilterData, draftColumnValues]
  )
  const allVisibleColumnOptionsSelected =
    visibleColumnFilterOptions.length > 0 &&
    visibleColumnFilterOptions.every((item) =>
      selectedColumnValues.has(item.value)
    )
  const activeFilterFields = useMemo(
    () => new Set(filters.map((item) => item.field)),
    [filters]
  )
  const totalPages = Math.max(1, Math.ceil(data.total / pageSize))
  const canEdit = hasPermission("product.manage")
  useEffect(() => {
    setPageInput(String(page))
  }, [page])
  useEffect(() => {
    if (page > totalPages) setPage(totalPages)
  }, [page, totalPages])
  function openPicker() {
    setDraftKeys(customKeys)
    setColumnSearch("")
    setPickerOpen(true)
  }
  function toggleDraftKey(key: string) {
    setDraftKeys((current) =>
      current.includes(key)
        ? current.filter((item) => item !== key)
        : [...current, key]
    )
  }
  const openColumnFilter = useCallback(
    (
      field: ProductGoodsFilter["field"],
      label: string,
      target: HTMLElement
    ) => {
      const rect = target.getBoundingClientRect()
      setActiveColumnFilter({
        field,
        label,
        top: Math.min(rect.bottom + 6, Math.max(12, window.innerHeight - 560)),
        left: Math.max(12, Math.min(rect.left, window.innerWidth - 388)),
      })
      setColumnFilterData(null)
      setColumnFilterSearch("")
      setDraftColumnValues(null)
      setColumnFilterError("")
    },
    []
  )
  function toggleColumnFilterValue(value: string) {
    setDraftColumnValues((current) => {
      const values = new Set(
        current ?? columnFilterData?.options.map((item) => item.value) ?? []
      )
      if (values.has(value)) values.delete(value)
      else values.add(value)
      return [...values]
    })
  }
  function toggleAllVisibleColumnFilterOptions() {
    setDraftColumnValues((current) => {
      const values = new Set(
        current ?? columnFilterData?.options.map((item) => item.value) ?? []
      )
      if (allVisibleColumnOptionsSelected)
        visibleColumnFilterOptions.forEach((item) => values.delete(item.value))
      else visibleColumnFilterOptions.forEach((item) => values.add(item.value))
      return [...values]
    })
  }
  function closeColumnFilter() {
    setActiveColumnFilter(null)
    setColumnFilterData(null)
    setColumnFilterError("")
  }
  function clearActiveColumnFilter() {
    if (!activeColumnFilter) return
    setFilters((current) =>
      current.filter((item) => item.field !== activeColumnFilter.field)
    )
    setPage(1)
    closeColumnFilter()
  }
  function applyColumnFilter() {
    if (!activeColumnFilter || !columnFilterData) return
    const allValues = columnFilterData.options.map((item) => item.value)
    const selectedValues = allValues.filter((value) =>
      selectedColumnValues.has(value)
    )
    const selectedValueSet = new Set(selectedValues)
    const excludedValues = allValues.filter(
      (value) => !selectedValueSet.has(value)
    )
    if (
      selectedValues.length !== allValues.length &&
      Math.min(selectedValues.length, excludedValues.length) > 5_000
    ) {
      setColumnFilterError("请先搜索缩小范围，再进行大批量筛选")
      return
    }
    setFilters((current) => {
      const otherFilters = current.filter(
        (item) => item.field !== activeColumnFilter.field
      )
      if (selectedValues.length === allValues.length) return otherFilters
      return [
        ...otherFilters,
        selectedValues.length <= excludedValues.length
          ? {
              field: activeColumnFilter.field,
              operator: "in",
              values: selectedValues,
            }
          : {
              field: activeColumnFilter.field,
              operator: "not_in",
              values: excludedValues,
            },
      ]
    })
    setPage(1)
    closeColumnFilter()
  }
  function openFilters() {
    setDraftFilters(filters.map((item) => ({ ...item })))
    setFilterError("")
    setFilterOpen(true)
  }
  function addDraftFilter() {
    setDraftFilters((current) => [
      ...current,
      { field: "year", operator: "contains", value: "" },
    ])
  }
  function updateDraftFilter(
    index: number,
    updates: Partial<ProductGoodsFilter>
  ) {
    setDraftFilters((current) =>
      current.map((item, itemIndex) =>
        itemIndex === index ? { ...item, ...updates } : item
      )
    )
  }
  function applyFilters() {
    if (
      draftFilters.some(
        (item) =>
          (item.operator === "contains" || item.operator === "equals") &&
          !item.value?.trim()
      )
    ) {
      setFilterError("“包含”和“等于”需要填写筛选值")
      return
    }
    setFilters(
      draftFilters.map((item) => ({
        ...item,
        value: item.value?.trim() || undefined,
      }))
    )
    setFilterError("")
    setFilterOpen(false)
    setPage(1)
  }
  function clearFilters() {
    setFilters([])
    setDraftFilters([])
    setFilterError("")
    setPage(1)
  }
  async function saveManualFields(
    item: ProductGoodsItem,
    fields: Partial<ProductGoodsManualFields>
  ) {
    const payload: Record<
      string,
      string | boolean | number | Record<string, number> | null
    > = {}
    for (const [field, fieldValue] of Object.entries(fields)) {
      if (field === "douyin_hot" || field === "clearance")
        payload[field] = manualTag(fieldValue).trim() || null
      else payload[field] = fieldValue ?? null
    }
    await updateProductGoods(brand, item.id, payload)
    const metricFields = [
      "replenishment_total",
      "post_replenishment_stock",
      "post_replenishment_total",
      "post_replenishment_turnover_days",
    ] as const
    const updatedMetrics = { ...item.metrics }
    for (const field of metricFields)
      if (field in fields) updatedMetrics[field] = fields[field] ?? null
    const updatedItem = { ...item, ...fields, metrics: updatedMetrics }
    setSelectedItem(updatedItem)
    setData((current) => ({
      ...current,
      items: current.items.map((row) =>
        row.id === updatedItem.id ? updatedItem : row
      ),
    }))
    productGoodsPageCache.clear()
    refreshNonceRef.current = String(Date.now())
    setReloadVersion((current) => current + 1)
  }
  const previewProductImage = useCallback((item: ProductGoodsItem) => {
    if (!item.image_url) return
    setPreviewImage({
      src: `/api${item.image_url}`,
      alt: item.goods_code || item.style_code || "商品图片",
    })
  }, [])
  const selectProductItem = useCallback((item: ProductGoodsItem) => {
    setSelectedItem(item)
  }, [])
  const tableWidth =
    (renderedDataView === "style_summary" ? 285 : 445) +
    deferredVisibleColumns.reduce(
      (total, column) => total + (column.width ?? 78),
      0
    ) +
    76
  const brandLabel =
    GOODS_BRANDS.find((item) => item.key === brand)?.label ?? "商品"
  function exportCurrentPage() {
    exportCsv(
      data.items,
      visibleColumns,
      `${brandLabel}_${dataView === "style_summary" ? "款号汇总" : "商品货品表"}_当前页_${timestampForFilename(new Date())}.csv`,
      dataView === "style_summary"
    )
  }
  async function exportAllRows() {
    if (isExporting) return
    setIsExporting(true)
    setExportProgress({ loaded: 0, total: data.total })
    try {
      const loadExportPage = async (pageToLoad: number) =>
        normalizeProductGoodsResponse(
          await listProductGoods({
            brand,
            query: query || undefined,
            filters: filters.length ? filters : undefined,
            view: dataView,
            snapshotDate: snapshotDate || undefined,
            page: pageToLoad,
            pageSize: EXPORT_PAGE_SIZE,
          })
        )
      const firstResponse = await loadExportPage(1)
      const expectedTotal = firstResponse.total
      const pageCount = Math.max(1, Math.ceil(expectedTotal / EXPORT_PAGE_SIZE))
      const rowsByPage = new Map<number, ProductGoodsItem[]>([
        [1, firstResponse.items],
      ])
      let loadedCount = firstResponse.items.length
      setExportProgress({ loaded: loadedCount, total: expectedTotal })

      const remainingPages = Array.from(
        { length: pageCount - 1 },
        (_, index) => index + 2
      )
      let nextPageIndex = 0
      async function exportWorker() {
        while (nextPageIndex < remainingPages.length) {
          const pageToLoad = remainingPages[nextPageIndex]
          nextPageIndex += 1
          const response = await loadExportPage(pageToLoad)
          rowsByPage.set(pageToLoad, response.items)
          loadedCount += response.items.length
          setExportProgress({ loaded: loadedCount, total: expectedTotal })
        }
      }

      await Promise.all(
        Array.from(
          { length: Math.min(EXPORT_CONCURRENCY, remainingPages.length) },
          () => exportWorker()
        )
      )
      const allRows = Array.from(
        { length: pageCount },
        (_, index) => rowsByPage.get(index + 1) ?? []
      ).flat()
      exportCsv(
        allRows,
        visibleColumns,
        `${brandLabel}_${dataView === "style_summary" ? "款号汇总" : "商品货品表"}_${timestampForFilename(new Date())}.csv`,
        dataView === "style_summary"
      )
    } catch (error) {
      window.alert(
        error instanceof Error ? error.message : "商品货品表导出失败"
      )
    } finally {
      setIsExporting(false)
      setExportProgress(null)
    }
  }
  function selectBrand(nextBrand: Exclude<BrandKey, "all">) {
    if (nextBrand === brand) return
    setSelectedItem(null)
    startTransition(() => {
      setBrand(nextBrand)
      setSnapshotDate("")
      setPage(1)
    })
  }
  function selectDataView(nextView: ProductGoodsView) {
    if (nextView === dataView) return
    setSelectedItem(null)
    const nextPageSize =
      nextView === "style_summary" ? SUMMARY_PAGE_SIZE : pageSize
    startTransition(() => {
      setDataView(nextView)
      setPageSize(nextPageSize)
      setPage(1)
    })
  }
  function openHistoryDatePicker() {
    const input = historyDateInputRef.current
    if (!input) return
    input.focus()
    if (typeof input.showPicker === "function") {
      try {
        input.showPicker()
        return
      } catch {
        // Fall back for browsers that reject programmatic picker opening.
      }
    }
    input.click()
  }
  function selectHistoryDate(nextDate: string) {
    if (!nextDate || data.snapshot_dates.includes(nextDate)) {
      setSnapshotDate(nextDate)
      setPage(1)
    }
  }
  function refresh() {
    productGoodsPageCache.clear()
    refreshNonceRef.current = String(Date.now())
    setReloadVersion((current) => current + 1)
  }
  function changePageSize(nextSize: number) {
    setPageSize(nextSize)
    setPage(1)
  }
  function jumpToPage() {
    const requested = Number.parseInt(pageInput, 10)
    const nextPage = Number.isFinite(requested)
      ? Math.min(Math.max(requested, 1), totalPages)
      : page
    setPageInput(String(nextPage))
    if (nextPage !== page) setPage(nextPage)
  }
  return (
    <div className="app-page">
      <div className="app-content space-y-4">
        <div className="page-header">
          <div className="flex w-full flex-wrap items-start justify-between gap-3">
            <div>
              <h1 className="page-title">商品货品表</h1>
              <p className="page-subtitle">
                {brandLabel}
                {snapshotDate ? ` · 历史快照 ${snapshotDate}` : " · 当前数据"}
              </p>
              <div className="mt-3 flex w-full flex-wrap items-center gap-1">
                {GOODS_BRANDS.map((item) => (
                  <button
                    key={item.key}
                    type="button"
                    onClick={() => selectBrand(item.key)}
                    className={cn(
                      "cursor-pointer rounded-lg border border-transparent bg-muted/45 px-3 py-1.5 text-xs font-medium text-muted-foreground transition-all duration-150 hover:bg-muted hover:text-foreground",
                      brand === item.key &&
                        "border-border bg-background text-foreground shadow-sm"
                    )}
                  >
                    {item.label}
                  </button>
                ))}
              </div>
              <div className="mt-3 flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
                <span className="inline-flex h-7 items-center rounded-full border border-border bg-muted/40 px-3">
                  当前 {data.total.toLocaleString("zh-CN")} 条
                </span>
                <span className="inline-flex h-7 items-center rounded-full border border-border bg-muted/40 px-3">
                  显示 {visibleColumns.length} 列
                </span>
                <span className="inline-flex h-7 items-center rounded-full border border-border bg-muted/40 px-3">
                  视图 {columnMode === "full" ? "完整" : "自定义"}
                </span>
                <span className="inline-flex h-7 items-center rounded-full border border-border bg-muted/40 px-3">
                  数据{" "}
                  {renderedDataView === "style_summary"
                    ? "款号汇总"
                    : "货号明细"}
                </span>
              </div>
            </div>
            <div className="flex flex-wrap items-center gap-2">
              <div
                className={cn(
                  "inline-flex h-8 items-center gap-0.5 rounded-lg border p-0.5 shadow-sm transition-colors",
                  snapshotDate
                    ? "border-primary/30 bg-primary/5"
                    : "border-border bg-card"
                )}
                role="group"
                aria-label="数据日期"
              >
                <button
                  type="button"
                  aria-pressed={!snapshotDate}
                  onClick={() => {
                    setSnapshotDate("")
                    setPage(1)
                  }}
                  className={cn(
                    "inline-flex h-7 cursor-pointer items-center gap-1.5 rounded-md px-2.5 text-xs font-semibold transition-colors",
                    !snapshotDate
                      ? "bg-primary text-primary-foreground shadow-sm"
                      : "text-muted-foreground hover:bg-background hover:text-foreground"
                  )}
                >
                  <Check className="h-3.5 w-3.5" />
                  当前
                </button>
                <div className="relative">
                  <button
                    type="button"
                    aria-pressed={!!snapshotDate}
                    onClick={openHistoryDatePicker}
                    className={cn(
                      "inline-flex h-7 min-w-[9.5rem] cursor-pointer items-center gap-1.5 rounded-md border px-2.5 text-xs font-semibold transition-colors",
                      snapshotDate
                        ? "border-primary/35 bg-background text-foreground shadow-sm"
                        : "border-transparent text-muted-foreground hover:bg-muted/50 hover:text-foreground"
                    )}
                  >
                    <History
                      className={cn(
                        "h-3.5 w-3.5",
                        snapshotDate && "text-primary"
                      )}
                    />
                    <span>历史</span>
                    <span
                      className={cn(
                        "tabular-nums",
                        snapshotDate
                          ? "text-foreground"
                          : "text-muted-foreground"
                      )}
                    >
                      {snapshotDate || "选择日期"}
                    </span>
                    <CalendarDays className="ml-auto h-3.5 w-3.5 text-muted-foreground" />
                  </button>
                  <input
                    ref={historyDateInputRef}
                    type="date"
                    value={snapshotDate}
                    max={data.snapshot_dates[0] || undefined}
                    onChange={(event) => selectHistoryDate(event.target.value)}
                    className="pointer-events-none absolute top-0 left-0 h-px w-px opacity-0"
                    aria-label="选择历史快照日期"
                    tabIndex={-1}
                  />
                </div>
              </div>
              <Button
                variant="outline"
                className="h-8 px-3 text-xs font-semibold"
                onClick={refresh}
              >
                <RefreshCw className="h-4 w-4" />
                刷新
              </Button>
              <Button
                variant="outline"
                className="h-8 px-3 text-xs font-semibold"
                onClick={() => setOperationLogOpen(true)}
              >
                <History className="h-4 w-4" />
                操作日志
              </Button>
              <Button
                variant="outline"
                className="h-8 px-3 text-xs font-semibold"
                onClick={exportAllRows}
                disabled={isExporting || loading || data.total === 0}
              >
                <Download className="h-4 w-4" />
                {isExporting && exportProgress
                  ? `导出 ${Math.min(
                      exportProgress.loaded,
                      exportProgress.total
                    ).toLocaleString(
                      "zh-CN"
                    )}/${exportProgress.total.toLocaleString("zh-CN")}`
                  : "导出"}
              </Button>
            </div>
          </div>
        </div>
        <div className="surface-panel p-3">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div className="flex flex-wrap items-center gap-3">
              <div
                className="flex items-center gap-2"
                role="group"
                aria-label="数据视图"
              >
                <span className="shrink-0 text-xs font-medium text-muted-foreground">
                  数据
                </span>
                <div className="inline-flex h-9 items-center rounded-md border border-border bg-muted/35 p-0.5 shadow-sm">
                  {[
                    ["goods", "货号明细"],
                    ["style_summary", "款号汇总"],
                  ].map(([view, label]) => (
                    <button
                      key={view}
                      type="button"
                      onClick={() => selectDataView(view as ProductGoodsView)}
                      onPointerEnter={() =>
                        prefetchDataView(view as ProductGoodsView)
                      }
                      onFocus={() => prefetchDataView(view as ProductGoodsView)}
                      className={cn(
                        "h-8 cursor-pointer rounded px-3 text-sm font-medium transition-colors focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none",
                        dataView === view
                          ? "bg-background text-foreground shadow-sm"
                          : "text-muted-foreground hover:bg-background/70 hover:text-foreground"
                      )}
                      aria-pressed={dataView === view}
                    >
                      {label}
                    </button>
                  ))}
                </div>
              </div>
              <span
                className="hidden h-5 w-px bg-border sm:block"
                aria-hidden="true"
              />
              <div
                className="flex items-center gap-2"
                role="group"
                aria-label="列视图"
              >
                <span className="shrink-0 text-xs font-medium text-muted-foreground">
                  列
                </span>
                <div className="inline-flex h-9 items-center rounded-md border border-border bg-muted/35 p-0.5 shadow-sm">
                  {[
                    ["full", "完整视图"],
                    ["custom", "自定义"],
                  ].map(([mode, label]) => (
                    <button
                      key={mode}
                      type="button"
                      onClick={() => setColumnMode(mode as "full" | "custom")}
                      className={cn(
                        "h-8 cursor-pointer rounded px-3 text-sm font-medium transition-colors focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none",
                        columnMode === mode
                          ? "bg-background text-foreground shadow-sm"
                          : "text-muted-foreground hover:bg-background/70 hover:text-foreground"
                      )}
                      aria-pressed={columnMode === mode}
                    >
                      {label}
                    </button>
                  ))}
                </div>
              </div>
            </div>
            <div className="flex items-center gap-1">
              {columnMode === "custom" && (
                <Button
                  variant="outline"
                  size="icon"
                  className="h-8 w-8"
                  onClick={openPicker}
                  aria-label="配置自定义列"
                  title="配置自定义列"
                >
                  <SlidersHorizontal className="h-4 w-4" />
                </Button>
              )}
              <Button
                variant="outline"
                size="icon"
                className="h-8 w-8"
                onClick={exportCurrentPage}
                disabled={!data.items.length || isExporting}
                aria-label="导出当前页"
                title="导出当前页"
              >
                <Download className="h-4 w-4" />
              </Button>
            </div>
          </div>
        </div>
        <div className="surface-panel flex flex-wrap items-center gap-2 p-3">
          <div className="relative min-w-[260px] flex-1">
            <Search className="absolute top-2.5 left-3 h-4 w-4 text-muted-foreground" />
            <Input
              value={queryInput}
              onChange={(event) => setQueryInput(event.target.value)}
              onKeyDown={(event) =>
                event.key === "Enter" &&
                (setQuery(queryInput.trim()), setPage(1))
              }
              className="pl-9"
              placeholder="货号、款号、工厂货号、颜色"
            />
          </div>
          <Button
            size="sm"
            onClick={() => {
              setQuery(queryInput.trim())
              setPage(1)
            }}
          >
            <Search className="h-4 w-4" />
            查询
          </Button>
          <Button
            variant="outline"
            size="sm"
            onClick={() => {
              setQueryInput("")
              setQuery("")
              clearFilters()
            }}
          >
            <X className="h-4 w-4" />
            清除
          </Button>
        </div>
        <div className="hidden" aria-hidden="true">
          <span className="mr-2 shrink-0 text-xs text-muted-foreground">
            字段筛选
          </span>
          {filterableColumnButtons.map((column) => (
            <button
              key={column.field}
              type="button"
              onClick={(event) =>
                openColumnFilter(
                  column.field,
                  column.label,
                  event.currentTarget
                )
              }
              className={cn(
                "inline-flex h-7 shrink-0 items-center gap-1 border px-2 text-xs transition-colors",
                filters.some((item) => item.field === column.field)
                  ? "border-primary/40 bg-primary/10 text-primary"
                  : "border-border bg-background text-muted-foreground hover:border-primary/35 hover:text-foreground"
              )}
            >
              <span>{column.label}</span>
              <Filter className="h-3 w-3" />
            </button>
          ))}
        </div>
        {activeColumnFilter && (
          <div
            className="fixed z-[100] flex w-[min(24rem,calc(100vw-1.5rem))] flex-col overflow-hidden border border-border bg-card shadow-xl"
            style={{
              top: activeColumnFilter.top,
              left: activeColumnFilter.left,
            }}
          >
            <div className="flex items-center justify-between border-b border-border px-3 py-2">
              <div>
                <p className="text-sm font-medium">
                  {activeColumnFilter.label}
                </p>
                <p className="text-[11px] text-muted-foreground">
                  {columnFilterData
                    ? `${columnFilterData.total.toLocaleString("zh-CN")} 个筛选项`
                    : "正在读取筛选项"}
                </p>
              </div>
              <Button
                variant="ghost"
                size="icon"
                className="h-7 w-7"
                onClick={closeColumnFilter}
                aria-label="关闭字段筛选"
                title="关闭"
              >
                <X className="h-4 w-4" />
              </Button>
            </div>
            <div className="border-b border-border px-3 py-2">
              <div className="relative">
                <Search className="absolute top-2.5 left-2.5 h-3.5 w-3.5 text-muted-foreground" />
                <Input
                  value={columnFilterSearch}
                  onChange={(event) =>
                    setColumnFilterSearch(event.target.value)
                  }
                  className="h-8 pl-8 text-xs"
                  placeholder="搜索筛选项"
                  autoFocus
                />
              </div>
            </div>
            <div className="flex items-center justify-between border-b border-border bg-muted/20 px-3 py-2 text-xs">
              <label className="flex cursor-pointer items-center gap-2">
                <input
                  type="checkbox"
                  checked={allVisibleColumnOptionsSelected}
                  onChange={toggleAllVisibleColumnFilterOptions}
                  disabled={
                    !visibleColumnFilterOptions.length || columnFilterLoading
                  }
                />
                <span>全选/反选</span>
              </label>
              <span className="text-muted-foreground">
                已选 {selectedColumnValues.size}
              </span>
            </div>
            <div className="max-h-[21rem] min-h-[15rem] overflow-y-auto px-3 py-2">
              {columnFilterLoading && (
                <p className="px-1 py-8 text-center text-sm text-muted-foreground">
                  正在加载筛选项...
                </p>
              )}
              {!columnFilterLoading && columnFilterError && (
                <p className="px-1 py-8 text-center text-sm text-destructive">
                  {columnFilterError}
                </p>
              )}
              {!columnFilterLoading &&
                !columnFilterError &&
                hasHiddenColumnFilterOptions && (
                  <p className="mb-2 border border-border bg-muted/40 px-2 py-1.5 text-xs text-muted-foreground">
                    当前展示前 300 项，请输入货号搜索更多结果。
                  </p>
                )}
              {!columnFilterLoading &&
                !columnFilterError &&
                !visibleColumnFilterOptions.length && (
                  <p className="px-1 py-8 text-center text-sm text-muted-foreground">
                    没有匹配的筛选项
                  </p>
                )}
              {!columnFilterLoading &&
                !columnFilterError &&
                visibleColumnFilterOptions.map((item) => (
                  <label
                    key={item.value || "__empty"}
                    className="flex h-7 cursor-pointer items-center justify-between gap-2 px-1 text-xs hover:bg-muted/70"
                  >
                    <span className="flex min-w-0 items-center gap-2">
                      <input
                        type="checkbox"
                        checked={selectedColumnValues.has(item.value)}
                        onChange={() => toggleColumnFilterValue(item.value)}
                      />
                      <span className="truncate">{item.value || "(空白)"}</span>
                    </span>
                    <span className="shrink-0 text-muted-foreground">
                      {item.count.toLocaleString("zh-CN")}
                    </span>
                  </label>
                ))}
            </div>
            <div className="flex items-center justify-between border-t border-border px-3 py-2">
              <Button
                variant="ghost"
                size="sm"
                onClick={clearActiveColumnFilter}
              >
                清除此列
              </Button>
              <div className="flex gap-2">
                <Button variant="outline" size="sm" onClick={closeColumnFilter}>
                  取消
                </Button>
                <Button
                  size="sm"
                  onClick={applyColumnFilter}
                  disabled={columnFilterLoading || !columnFilterData}
                >
                  确定
                </Button>
              </div>
            </div>
          </div>
        )}
        <div className="table-panel">
          <ProductGoodsGrid
            activeFilterFields={activeFilterFields}
            groups={groups}
            items={data.items}
            isStyleSummary={renderedDataView === "style_summary"}
            loading={loading}
            onOpenColumnFilter={openColumnFilter}
            onPreviewImage={previewProductImage}
            onSelectItem={selectProductItem}
            tableWidth={tableWidth}
            visibleColumns={deferredVisibleColumns}
          />
          <div className="flex flex-wrap items-center justify-between gap-3 border-t border-border px-4 py-3">
            <p className="text-sm text-muted-foreground">
              共 {data.total.toLocaleString("zh-CN")} 条 · 第{" "}
              {data.total === 0 ? 0 : (page - 1) * pageSize + 1}-
              {Math.min(page * pageSize, data.total)} 条 · 第 {page} /{" "}
              {totalPages} 页
            </p>
            <div className="flex flex-wrap items-center gap-2">
              <div className="flex h-9 items-center gap-1.5 rounded-lg border border-border bg-muted/25 px-2 text-xs text-muted-foreground">
                <span>每页</span>
                <Select
                  value={String(pageSize)}
                  onChange={(event) =>
                    changePageSize(Number(event.target.value))
                  }
                  disabled={loading}
                  className="h-8 w-[4.5rem] border-0 bg-transparent px-1.5 py-0 text-center text-xs leading-none shadow-none hover:bg-background focus-visible:ring-0"
                >
                  {PAGE_SIZE_OPTIONS.map((option) => (
                    <option key={option} value={option}>
                      {option}
                    </option>
                  ))}
                </Select>
                <span>条</span>
              </div>
              <div className="flex h-9 items-center gap-1 rounded-lg border border-border bg-muted/25 px-1.5 text-xs text-muted-foreground">
                <span className="pl-0.5">跳至</span>
                <Input
                  type="number"
                  min={1}
                  max={totalPages}
                  inputMode="numeric"
                  value={pageInput}
                  onChange={(event) => setPageInput(event.target.value)}
                  onKeyDown={(event) => event.key === "Enter" && jumpToPage()}
                  disabled={loading || data.total === 0}
                  className="h-7 w-16 border-border/70 bg-background px-1 text-center text-xs tabular-nums"
                  aria-label="页码"
                />
                <span>页</span>
                <Button
                  variant="ghost"
                  size="icon"
                  className="h-7 w-7"
                  disabled={loading || data.total === 0}
                  onClick={jumpToPage}
                  aria-label="跳转页码"
                  title="跳转页码"
                >
                  <ArrowRight className="h-3.5 w-3.5" />
                </Button>
              </div>
              <div className="flex items-center gap-1">
                <Button
                  variant="outline"
                  size="icon"
                  disabled={page <= 1 || loading}
                  onClick={() => setPage(1)}
                  aria-label="第一页"
                  title="第一页"
                >
                  <ChevronsLeft className="h-4 w-4" />
                </Button>
                <Button
                  variant="outline"
                  size="icon"
                  disabled={page <= 1 || loading}
                  onClick={() => setPage((current) => current - 1)}
                  aria-label="上一页"
                  title="上一页"
                >
                  <ChevronLeft className="h-4 w-4" />
                </Button>
                {pageTokens(page, totalPages).map((token, index) =>
                  typeof token === "number" ? (
                    <Button
                      key={token}
                      variant={token === page ? "default" : "outline"}
                      size="icon"
                      disabled={loading}
                      onClick={() => setPage(token)}
                      aria-label={`第 ${token} 页`}
                    >
                      {token}
                    </Button>
                  ) : (
                    <span
                      key={`ellipsis-${index}`}
                      className="flex h-9 w-9 items-center justify-center text-muted-foreground"
                    >
                      <MoreHorizontal className="h-4 w-4" />
                    </span>
                  )
                )}
                <Button
                  variant="outline"
                  size="icon"
                  disabled={page >= totalPages || loading}
                  onClick={() => setPage((current) => current + 1)}
                  aria-label="下一页"
                  title="下一页"
                >
                  <ChevronRight className="h-4 w-4" />
                </Button>
                <Button
                  variant="outline"
                  size="icon"
                  disabled={page >= totalPages || loading}
                  onClick={() => setPage(totalPages)}
                  aria-label="最后一页"
                  title="最后一页"
                >
                  <ChevronsRight className="h-4 w-4" />
                </Button>
              </div>
            </div>
          </div>
        </div>
      </div>
      <Dialog
        open={filterOpen}
        onOpenChange={(open) => {
          setFilterOpen(open)
          if (!open) setFilterError("")
        }}
      >
        <DialogContent className="max-h-[88svh] max-w-[min(96vw,760px)] overflow-hidden p-0">
          <DialogHeader className="border-b border-border px-5 py-4">
            <DialogTitle className="text-base font-semibold">
              筛选商品货品
            </DialogTitle>
            <p className="mt-1 text-xs text-muted-foreground">
              所有条件同时满足，筛选结果会覆盖全部分页数据。
            </p>
          </DialogHeader>
          <div className="max-h-[60svh] space-y-3 overflow-y-auto px-5 py-4">
            {draftFilters.length === 0 ? (
              <div className="border border-dashed border-border px-4 py-8 text-center text-sm text-muted-foreground">
                暂未添加筛选条件
              </div>
            ) : (
              draftFilters.map((item, index) => (
                <div
                  key={`${item.field}-${index}`}
                  className="grid gap-2 rounded-lg border border-border bg-muted/15 p-3 sm:grid-cols-[minmax(0,1.2fr)_minmax(0,1fr)_minmax(0,1.25fr)_2.25rem]"
                >
                  <Select
                    value={item.field}
                    onChange={(event) =>
                      updateDraftFilter(index, {
                        field: event.target
                          .value as ProductGoodsFilter["field"],
                      })
                    }
                    aria-label={`筛选字段 ${index + 1}`}
                  >
                    <>
                      {PRODUCT_GOODS_FILTER_FIELDS.map((field) => (
                        <option key={field.value} value={field.value}>
                          {field.label}
                        </option>
                      ))}
                    </>
                  </Select>
                  <Select
                    value={item.operator}
                    onChange={(event) =>
                      updateDraftFilter(index, {
                        operator: event.target
                          .value as ProductGoodsFilter["operator"],
                      })
                    }
                    aria-label={`筛选方式 ${index + 1}`}
                  >
                    <>
                      {PRODUCT_GOODS_FILTER_OPERATORS.map((operator) => (
                        <option key={operator.value} value={operator.value}>
                          {operator.label}
                        </option>
                      ))}
                    </>
                  </Select>
                  {item.operator === "empty" ||
                  item.operator === "not_empty" ? (
                    <div className="flex h-9 items-center px-3 text-sm text-muted-foreground">
                      无需填写筛选值
                    </div>
                  ) : (
                    <Input
                      value={item.value ?? ""}
                      onChange={(event) =>
                        updateDraftFilter(index, { value: event.target.value })
                      }
                      placeholder="输入筛选值"
                      aria-label={`筛选值 ${index + 1}`}
                    />
                  )}
                  <Button
                    variant="ghost"
                    size="icon"
                    className="h-9 w-9 text-muted-foreground hover:text-destructive"
                    onClick={() =>
                      setDraftFilters((current) =>
                        current.filter((_, itemIndex) => itemIndex !== index)
                      )
                    }
                    aria-label="删除筛选条件"
                    title="删除筛选条件"
                  >
                    <Trash2 className="h-4 w-4" />
                  </Button>
                </div>
              ))
            )}
            <Button
              type="button"
              variant="outline"
              size="sm"
              onClick={addDraftFilter}
              disabled={draftFilters.length >= 20}
            >
              <Plus className="h-4 w-4" />
              添加条件
            </Button>
            {filterError && (
              <p className="text-sm text-destructive">{filterError}</p>
            )}
          </div>
          <div className="flex flex-wrap items-center justify-between gap-2 border-t border-border px-5 py-3">
            <Button
              variant="ghost"
              size="sm"
              onClick={() => {
                setDraftFilters([])
                setFilterError("")
              }}
            >
              重置条件
            </Button>
            <div className="flex gap-2">
              <Button
                variant="outline"
                size="sm"
                onClick={() => {
                  setFilterOpen(false)
                  setFilterError("")
                }}
              >
                取消
              </Button>
              <Button size="sm" onClick={applyFilters}>
                应用筛选
              </Button>
            </div>
          </div>
        </DialogContent>
      </Dialog>
      <Dialog open={pickerOpen} onOpenChange={setPickerOpen}>
        <DialogContent className="flex max-h-[88svh] max-w-[min(96vw,1120px)] flex-col overflow-hidden p-0">
          <DialogHeader className="border-b border-border px-5 py-4">
            <div className="flex flex-wrap items-start justify-between gap-3">
              <div>
                <DialogTitle className="text-base font-semibold">
                  自定义列
                </DialogTitle>
                <p className="mt-1 text-xs text-muted-foreground">
                  已选择 {draftKeys.length} / {columns.length} 列
                </p>
              </div>
              <div className="flex gap-2">
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() =>
                    setDraftKeys(columns.map((column) => column.key))
                  }
                >
                  全选
                </Button>
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => setDraftKeys(DEFAULT_COLUMN_KEYS)}
                >
                  默认
                </Button>
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => setDraftKeys([])}
                >
                  清空
                </Button>
              </div>
            </div>
            <div className="mt-3 h-1.5 overflow-hidden rounded-full bg-muted">
              <div
                className="h-full bg-primary"
                style={{
                  width: `${columns.length ? (draftKeys.length / columns.length) * 100 : 0}%`,
                }}
              />
            </div>
          </DialogHeader>
          <div className="border-b border-border bg-muted/20 px-5 py-3">
            <div className="relative">
              <Search className="absolute top-2.5 left-3 h-4 w-4 text-muted-foreground" />
              <Input
                value={columnSearch}
                onChange={(event) => setColumnSearch(event.target.value)}
                className="pl-9"
                placeholder="搜索列名"
              />
            </div>
          </div>
          <div className="min-h-0 flex-1 overflow-y-auto px-5 py-4">
            <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
              {Object.entries(groupedPickerColumns).map(
                ([group, groupColumns]) => {
                  const displayed = groupColumns.filter(
                    (column) =>
                      !columnSearch ||
                      column.label.includes(columnSearch) ||
                      column.key.includes(columnSearch)
                  )
                  if (!displayed.length) return null
                  const selected = groupColumns.filter((column) =>
                    draftKeys.includes(column.key)
                  ).length
                  return (
                    <section
                      key={group}
                      className="rounded-lg border border-border bg-background"
                    >
                      <div className="flex items-center justify-between border-b border-border px-3 py-2">
                        <div>
                          <p className="text-sm font-medium">{group}</p>
                          <p className="text-[11px] text-muted-foreground">
                            {selected}/{groupColumns.length}
                          </p>
                        </div>
                        <div className="flex gap-1">
                          <button
                            className="px-2 text-xs text-muted-foreground hover:text-foreground"
                            onClick={() =>
                              setDraftKeys((current) =>
                                Array.from(
                                  new Set([
                                    ...current,
                                    ...groupColumns.map((column) => column.key),
                                  ])
                                )
                              )
                            }
                          >
                            全选
                          </button>
                          <button
                            className="px-2 text-xs text-muted-foreground hover:text-foreground"
                            onClick={() =>
                              setDraftKeys((current) =>
                                current.filter(
                                  (key) =>
                                    !groupColumns.some(
                                      (column) => column.key === key
                                    )
                                )
                              )
                            }
                          >
                            清空
                          </button>
                        </div>
                      </div>
                      <div className="grid gap-1 p-2 sm:grid-cols-2">
                        {displayed.map((column) => {
                          const checked = draftKeys.includes(column.key)
                          return (
                            <label
                              key={column.key}
                              className={cn(
                                "flex h-8 cursor-pointer items-center gap-2 rounded-md border px-2 text-xs",
                                checked
                                  ? "border-primary/30 bg-primary/10"
                                  : "border-transparent hover:bg-muted"
                              )}
                            >
                              <input
                                type="checkbox"
                                className="sr-only"
                                checked={checked}
                                onChange={() => toggleDraftKey(column.key)}
                              />
                              <span
                                className={cn(
                                  "flex h-4 w-4 items-center justify-center rounded border",
                                  checked
                                    ? "border-primary bg-primary text-primary-foreground"
                                    : "border-border"
                                )}
                              >
                                {checked && <Check className="h-3 w-3" />}
                              </span>
                              <span className="truncate">{column.label}</span>
                            </label>
                          )
                        })}
                      </div>
                    </section>
                  )
                }
              )}
            </div>
          </div>
          <div className="flex justify-end gap-2 border-t border-border px-5 py-3">
            <Button
              variant="outline"
              size="sm"
              onClick={() => setPickerOpen(false)}
            >
              取消
            </Button>
            <Button
              size="sm"
              onClick={() => {
                setCustomKeys(draftKeys)
                setColumnMode("custom")
                setPickerOpen(false)
              }}
            >
              完成
            </Button>
          </div>
        </DialogContent>
      </Dialog>
      <OperationLogDialog
        module="product_goods"
        title="商品货品表操作日志"
        open={operationLogOpen}
        onOpenChange={setOperationLogOpen}
      />
      <Dialog
        open={previewImage !== null}
        onOpenChange={(open) => !open && setPreviewImage(null)}
      >
        <DialogContent className="max-h-[92svh] max-w-[min(94vw,1120px)] overflow-hidden bg-background p-0 shadow-2xl">
          <DialogHeader className="flex flex-row items-center justify-between gap-4 border-b border-border px-4 py-3 sm:px-5">
            <DialogTitle className="text-base font-semibold">
              原图预览
            </DialogTitle>
            <Button
              type="button"
              variant="ghost"
              size="icon"
              className="h-8 w-8 shrink-0"
              onClick={() => setPreviewImage(null)}
              aria-label="关闭原图预览"
            >
              <X className="h-4 w-4" />
            </Button>
          </DialogHeader>
          {previewImage && (
            <div className="flex h-[min(78svh,760px)] items-center justify-center bg-muted/20 p-4 sm:p-6">
              <img
                src={previewImage.src}
                alt={previewImage.alt}
                className="max-h-full w-auto max-w-full rounded-md object-contain shadow-sm"
              />
            </div>
          )}
        </DialogContent>
      </Dialog>
      {selectedItem && (
        <div
          aria-hidden="true"
          className="fixed inset-0 z-[80] bg-black/20"
          onClick={() => setSelectedItem(null)}
        />
      )}
      <ProductGoodsDetailDrawer
        item={selectedItem}
        data={data}
        canEdit={canEdit && renderedDataView === "goods"}
        onClose={() => setSelectedItem(null)}
        onSave={saveManualFields}
        onPreviewImage={(item) =>
          item.image_url &&
          setPreviewImage({
            src: `/api${item.image_url}`,
            alt: item.goods_code || item.style_code || "商品图片",
          })
        }
      />
    </div>
  )
}
