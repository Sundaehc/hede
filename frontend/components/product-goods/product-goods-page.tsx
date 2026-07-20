"use client"

import { useCallback, useEffect, useMemo, useRef, useState, useTransition, type ReactNode } from "react"
import { ArrowRight, CalendarDays, Check, ChevronLeft, ChevronRight, ChevronsLeft, ChevronsRight, Download, History, ImageIcon, MoreHorizontal, RefreshCw, Search, SlidersHorizontal, X } from "lucide-react"

import { useAuth } from "@/components/auth/auth-provider"
import { Button } from "@/components/ui/button"
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog"
import { Input } from "@/components/ui/input"
import { Select } from "@/components/ui/select"
import { OperationLogDialog } from "@/components/operation-log-dialog"
import { ProductGoodsDetailDrawer, type ProductGoodsManualFields } from "@/components/product-goods/product-goods-detail-drawer"
import { listProductGoods, updateProductGoods } from "@/lib/api"
import { BRANDS, type BrandKey } from "@/lib/brands"
import type { ProductGoodsItem, ProductGoodsResponse } from "@/lib/types"
import { cn } from "@/lib/utils"

const PAGE_SIZE = 50
const PAGE_SIZE_OPTIONS = [50, 100, 200]
const GOODS_BRANDS = BRANDS.filter((item) => item.key !== "all") as Array<{ key: Exclude<BrandKey, "all">; label: string }>
const DEFAULT_BRAND: Exclude<BrandKey, "all"> = "cbanner_mens"
const DEFAULT_COLUMN_KEYS = ["year", "season", "platform", "category_l4", "first_order_date", "factory_sku", "factory_code", "factory_name", "color", "cost", "product_role", "product_type", "douyin_hot", "clearance", "remark", "total_order_count", "total_sales", "stock_plus_purchase", "in_transit_total", "return_qty", "post_replenishment_stock", "post_replenishment_turnover_days", "day_over_day", "yesterday_sales", "week_sales", "last_week_sales", "month_sales", "stock_total", "stock_health", "broken_size_sku"]
type ColumnGroup = "基础" | "经营" | "库存" | "销售" | "年度销量" | "月度销量" | "近14天每日销量" | "在仓库存" | "在途库存" | "库存合计" | "缺货库存" | "销售明细" | "补单明细" | "补单后尺码" | "日销量" | "周销量" | "月销量"
type TableColumn = { key: string; label: string; group: ColumnGroup; width?: number; render: (row: ProductGoodsItem) => ReactNode }

function value(value: unknown) { return value === null || value === undefined || value === "" ? "" : String(value) }
function dateLabel(value: string) { const date = new Date(`${value}T00:00:00`); return `${String(date.getMonth() + 1).padStart(2, "0")}-${String(date.getDate()).padStart(2, "0")}` }
function csvCell(value: unknown) { return `"${String(value ?? "").replaceAll('"', '""')}"` }
function pageTokens(currentPage: number, totalPages: number): Array<number | "ellipsis"> {
  if (totalPages <= 7) return Array.from({ length: totalPages }, (_, index) => index + 1)
  const tokens: Array<number | "ellipsis"> = [1]
  const start = Math.max(2, currentPage - 1); const end = Math.min(totalPages - 1, currentPage + 1)
  if (start > 2) tokens.push("ellipsis")
  for (let current = start; current <= end; current += 1) tokens.push(current)
  if (end < totalPages - 1) tokens.push("ellipsis")
  tokens.push(totalPages)
  return tokens
}

function metric(row: ProductGoodsItem, key: string) { return value(row.metrics?.[key]) }
function matrix(row: ProductGoodsItem, source: keyof Pick<ProductGoodsItem, "stock_by_size" | "in_transit_by_size" | "inventory_by_size" | "shortage_by_size" | "sales_by_size" | "replenishment_by_size" | "post_replenishment_by_size">, size: string) { return value(row[source]?.[size]) }
function platformMatrix(row: ProductGoodsItem, source: keyof Pick<ProductGoodsItem, "daily_platform_sales" | "weekly_platform_sales" | "monthly_platform_sales">, platform: string) { return value(row[source]?.[platform]) }
function salesPeriodMatrix(row: ProductGoodsItem, source: keyof Pick<ProductGoodsItem, "annual_sales" | "monthly_sales">, period: string) { return value(row[source]?.[period]) }
function manualTag(tag: unknown) { return tag === true ? "是" : tag === false ? "" : value(tag) }

function normalizeProductGoodsResponse(response: ProductGoodsResponse): ProductGoodsResponse {
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

function createColumns(data: ProductGoodsResponse): TableColumn[] {
  const staticColumns: TableColumn[] = [
    { key: "year", label: "年份", group: "基础", render: (row) => value(row.year) },
    { key: "season", label: "季节", group: "基础", render: (row) => value(row.season) },
    { key: "platform", label: "所属平台", group: "基础", width: 120, render: (row) => value(row.platform) },
    { key: "category_l4", label: "四级分类", group: "基础", width: 120, render: (row) => value(row.category_l4) },
    { key: "first_order_date", label: "首单日期", group: "基础", width: 100, render: (row) => value(row.first_order_date) },
    { key: "factory_sku", label: "工厂货号", group: "基础", width: 110, render: (row) => value(row.factory_sku) },
    { key: "factory_code", label: "工厂代码", group: "基础", width: 95, render: (row) => value(row.factory_code) },
    { key: "factory_name", label: "工厂名称", group: "基础", width: 150, render: (row) => value(row.factory_name) },
    { key: "color", label: "颜色", group: "基础", render: (row) => value(row.color) },
    { key: "cost", label: "成本", group: "基础", render: (row) => value(row.cost) },
    { key: "product_role", label: "商品角色", group: "经营", render: (row) => value(row.product_role) },
    { key: "product_type", label: "类型", group: "经营", render: (row) => value(row.product_type) },
    { key: "douyin_hot", label: "抖音爆款", group: "经营", render: (row) => manualTag(row.douyin_hot) },
    { key: "clearance", label: "清仓", group: "经营", render: (row) => manualTag(row.clearance) },
    { key: "remark", label: "备注", group: "经营", width: 160, render: (row) => value(row.remark) },
    { key: "total_order_count", label: "总订单量", group: "销售", render: (row) => metric(row, "total_order_count") },
    { key: "total_sales", label: "总销量", group: "销售", render: (row) => metric(row, "total_sales") },
    { key: "stock_plus_purchase", label: "在仓库存+进货仓", group: "库存", render: (row) => metric(row, "stock_plus_purchase") },
    { key: "in_transit_total", label: "在途库存", group: "库存", render: (row) => metric(row, "in_transit_total") },
    { key: "return_qty", label: "回单", group: "库存", render: (row) => metric(row, "return_qty") },
    { key: "post_replenishment_stock", label: "补单后库存", group: "库存", render: (row) => metric(row, "post_replenishment_stock") },
    { key: "post_replenishment_turnover_days", label: "补单后周转天数", group: "库存", render: (row) => metric(row, "post_replenishment_turnover_days") },
    { key: "day_over_day", label: "昨比前日", group: "销售", render: (row) => metric(row, "day_over_day") },
    { key: "yesterday_sales", label: "昨日销量", group: "销售", render: (row) => metric(row, "yesterday_sales") },
    { key: "normal_shelf_sales", label: "正价货架销量", group: "销售", render: (row) => metric(row, "normal_shelf_sales") },
    { key: "clearance_sales", label: "清仓销量", group: "销售", render: (row) => metric(row, "clearance_sales") },
    { key: "week_sales", label: "近7天周销量", group: "销售", render: (row) => metric(row, "week_sales") },
    { key: "normal_shelf_week_sales", label: "正价货架7天销量", group: "销售", render: (row) => metric(row, "normal_shelf_week_sales") },
    { key: "clearance_week_sales", label: "清仓7天销量", group: "销售", render: (row) => metric(row, "clearance_week_sales") },
    { key: "last_week_sales", label: "上周销量", group: "销售", render: (row) => metric(row, "last_week_sales") },
    { key: "same_week_sales", label: "同期周销", group: "销售", render: (row) => metric(row, "same_week_sales") },
    { key: "same_week_non_douyin_sales", label: "同期非抖音周销", group: "销售", render: (row) => metric(row, "same_week_non_douyin_sales") },
    { key: "stock_total", label: "在仓合计", group: "库存", render: (row) => value(row.stock_total) },
    { key: "stock_health", label: "库存健康度提醒", group: "库存", width: 130, render: (row) => metric(row, "stock_health") },
    { key: "broken_size_sku", label: "断码SKU", group: "库存", render: (row) => metric(row, "broken_size_sku") },
    { key: "sales_size_total", label: "销售明细合计", group: "销售", render: (row) => metric(row, "sales_size_total") },
    { key: "replenishment_total", label: "补单合计", group: "库存", render: (row) => metric(row, "replenishment_total") },
    { key: "post_replenishment_total", label: "补单后合计", group: "库存", render: (row) => metric(row, "post_replenishment_total") },
    { key: "three_day_change", label: "三天环比", group: "销售", render: (row) => metric(row, "three_day_change") },
    { key: "month_sales", label: "月度销量", group: "销售", render: (row) => metric(row, "month_sales") },
  ]
  const annual = data.annual_sales_columns.map((period) => ({ key: `annual:${period}`, label: `${period}销量`, group: "年度销量" as const, render: (row: ProductGoodsItem) => salesPeriodMatrix(row, "annual_sales", period) }))
  const monthly = data.monthly_sales_columns.map((period) => ({ key: `monthly:${period}`, label: period, group: "月度销量" as const, render: (row: ProductGoodsItem) => salesPeriodMatrix(row, "monthly_sales", period) }))
  const daily = data.daily_dates.map((day) => ({ key: `daily:${day}`, label: dateLabel(day), group: "近14天每日销量" as const, render: (row: ProductGoodsItem) => value(row.daily_sales_by_date[day]) }))
  const sizeGroups: Array<[ColumnGroup, keyof Pick<ProductGoodsItem, "stock_by_size" | "in_transit_by_size" | "inventory_by_size" | "shortage_by_size" | "sales_by_size" | "replenishment_by_size" | "post_replenishment_by_size">]> = [["在仓库存", "stock_by_size"], ["在途库存", "in_transit_by_size"], ["库存合计", "inventory_by_size"], ["缺货库存", "shortage_by_size"], ["销售明细", "sales_by_size"], ["补单明细", "replenishment_by_size"], ["补单后尺码", "post_replenishment_by_size"]]
  const sizes = sizeGroups.flatMap(([group, source]) => data.size_columns.map((size) => ({ key: `${group}:${size}`, label: size, group, render: (row: ProductGoodsItem) => matrix(row, source, size) })))
  const platforms = [
    ["日销量", "daily_platform_sales"],
    ["周销量", "weekly_platform_sales"],
    ["月销量", "monthly_platform_sales"],
  ] as Array<[ColumnGroup, keyof Pick<ProductGoodsItem, "daily_platform_sales" | "weekly_platform_sales" | "monthly_platform_sales">]>
  const platformColumns = platforms.flatMap(([group, source]) => data.platform_columns.map((platform) => ({ key: `${group}:${platform}`, label: platform, group, render: (row: ProductGoodsItem) => platformMatrix(row, source, platform) })))
  return [...staticColumns, ...annual, ...monthly, ...daily, ...sizes, ...platformColumns]
}

function exportCsv(data: ProductGoodsResponse, columns: TableColumn[]) {
  const headers = ["图片", "货号", "款号", ...columns.map((column) => column.group.includes("销量") || column.group.includes("尺码") || column.group.includes("库存") ? `${column.group}-${column.label}` : column.label)]
  const rows = data.items.map((item) => [item.image_url ? "有" : "", item.goods_code, item.style_code, ...columns.map((column) => column.render(item))])
  const blob = new Blob(["\uFEFF", [headers, ...rows].map((row) => row.map(csvCell).join(",")).join("\r\n")], { type: "text/csv;charset=utf-8" })
  const link = document.createElement("a"); link.href = URL.createObjectURL(blob); link.download = "商品货品表.csv"; link.click(); URL.revokeObjectURL(link.href)
}

export function ProductGoodsPage() {
  const { hasPermission } = useAuth()
  const [brand, setBrand] = useState<Exclude<BrandKey, "all">>(DEFAULT_BRAND)
  const [data, setData] = useState<ProductGoodsResponse>({ items: [], total: 0, page: 1, page_size: PAGE_SIZE, daily_dates: [], annual_sales_columns: [], monthly_sales_columns: [], size_columns: [], platform_columns: [], snapshot_date: null, snapshot_dates: [] })
  const [page, setPage] = useState(1); const [pageSize, setPageSize] = useState(PAGE_SIZE); const [pageInput, setPageInput] = useState("1"); const [queryInput, setQueryInput] = useState(""); const [query, setQuery] = useState(""); const [platform, setPlatform] = useState("")
  const [snapshotDate, setSnapshotDate] = useState("")
  const historyDateInputRef = useRef<HTMLInputElement>(null)
  const requestIdRef = useRef(0)
  const refreshNonceRef = useRef<string | undefined>(undefined)
  const [operationLogOpen, setOperationLogOpen] = useState(false)
  const [previewImage, setPreviewImage] = useState<{ src: string; alt: string } | null>(null)
  const [selectedItem, setSelectedItem] = useState<ProductGoodsItem | null>(null)
  const [loading, setLoading] = useState(true)
  const [, startTransition] = useTransition()
  const [columnMode, setColumnMode] = useState<"full" | "custom">("full"); const [pickerOpen, setPickerOpen] = useState(false); const [customKeys, setCustomKeys] = useState<string[]>(DEFAULT_COLUMN_KEYS); const [draftKeys, setDraftKeys] = useState<string[]>(DEFAULT_COLUMN_KEYS); const [columnSearch, setColumnSearch] = useState("")
  const load = useCallback(async () => {
    const requestId = ++requestIdRef.current
    setLoading(true)
    try {
      const cacheBust = refreshNonceRef.current
      refreshNonceRef.current = undefined
      const response = await listProductGoods({ brand, query: query || undefined, platform: platform || undefined, snapshotDate: snapshotDate || undefined, page, pageSize, cacheBust })
      if (requestId === requestIdRef.current) setData(normalizeProductGoodsResponse(response))
    } finally {
      if (requestId === requestIdRef.current) setLoading(false)
    }
  }, [brand, page, pageSize, platform, query, snapshotDate])
  useEffect(() => { void load() }, [load])
  const columns = useMemo(() => createColumns(data), [data.annual_sales_columns, data.daily_dates, data.monthly_sales_columns, data.platform_columns, data.size_columns])
  const visibleColumns = useMemo(() => columnMode === "full" ? columns : columns.filter((column) => customKeys.includes(column.key)), [columnMode, columns, customKeys])
  const groups = useMemo(() => visibleColumns.reduce<Array<{ name: ColumnGroup; columns: TableColumn[] }>>((result, column) => { const current = result.at(-1); if (current?.name === column.group) current.columns.push(column); else result.push({ name: column.group, columns: [column] }); return result }, []), [visibleColumns])
  const groupedPickerColumns = useMemo(() => columns.reduce<Record<string, TableColumn[]>>((result, column) => ({ ...result, [column.group]: [...(result[column.group] ?? []), column] }), {}), [columns])
  const totalPages = Math.max(1, Math.ceil(data.total / pageSize)); const canEdit = hasPermission("product.manage")
  useEffect(() => { setPageInput(String(page)) }, [page])
  useEffect(() => { if (page > totalPages) setPage(totalPages) }, [page, totalPages])
  function openPicker() { setDraftKeys(customKeys); setColumnSearch(""); setPickerOpen(true) }
  function toggleDraftKey(key: string) { setDraftKeys((current) => current.includes(key) ? current.filter((item) => item !== key) : [...current, key]) }
  async function saveManualFields(item: ProductGoodsItem, fields: Partial<ProductGoodsManualFields>) {
    const payload: Record<string, string | boolean | number | Record<string, number> | null> = {}
    for (const [field, fieldValue] of Object.entries(fields)) {
      if (field === "douyin_hot" || field === "clearance") payload[field] = manualTag(fieldValue).trim() || null
      else payload[field] = fieldValue ?? null
    }
    await updateProductGoods(brand, item.id, payload)
    const metricFields = ["replenishment_total", "post_replenishment_stock", "post_replenishment_total", "post_replenishment_turnover_days"] as const
    const updatedMetrics = { ...item.metrics }
    for (const field of metricFields) if (field in fields) updatedMetrics[field] = fields[field] ?? null
    const updatedItem = { ...item, ...fields, metrics: updatedMetrics }
    setSelectedItem(updatedItem)
    setData((current) => ({ ...current, items: current.items.map((row) => row.id === updatedItem.id ? updatedItem : row) }))
    refreshNonceRef.current = String(Date.now())
    await load()
  }
  const tableWidth = 445 + visibleColumns.reduce((total, column) => total + (column.width ?? 78), 0) + 76
  const brandLabel = GOODS_BRANDS.find((item) => item.key === brand)?.label ?? "商品"
  function selectBrand(nextBrand: Exclude<BrandKey, "all">) {
    if (nextBrand === brand) return
    setSelectedItem(null)
    startTransition(() => {
      setBrand(nextBrand)
      setSnapshotDate("")
      setPage(1)
    })
  }
  function openHistoryPicker() { const input = historyDateInputRef.current; if (!input) return; input.showPicker?.(); input.focus() }
  function refresh() { refreshNonceRef.current = String(Date.now()); void load() }
  function changePageSize(nextSize: number) { setPageSize(nextSize); setPage(1) }
  function jumpToPage() {
    const requested = Number.parseInt(pageInput, 10)
    const nextPage = Number.isFinite(requested) ? Math.min(Math.max(requested, 1), totalPages) : page
    setPageInput(String(nextPage))
    if (nextPage !== page) setPage(nextPage)
  }
  return <div className="app-page"><div className="app-content space-y-4"><div className="page-header"><div className="flex w-full flex-wrap items-start justify-between gap-3"><div><h1 className="page-title">商品货品表</h1><p className="page-subtitle">{brandLabel}{snapshotDate ? ` · 历史快照 ${snapshotDate}` : " · 当前数据"}</p><div className="mt-3 flex w-full flex-wrap items-center gap-1">{GOODS_BRANDS.map((item) => <button key={item.key} type="button" onClick={() => selectBrand(item.key)} className={cn("cursor-pointer rounded-lg border border-transparent bg-muted/45 px-3 py-1.5 text-xs font-medium text-muted-foreground transition-all duration-150 hover:bg-muted hover:text-foreground", brand === item.key && "border-border bg-background text-foreground shadow-sm")}>{item.label}</button>)}</div><div className="mt-3 flex flex-wrap items-center gap-2 text-xs text-muted-foreground"><span className="inline-flex h-7 items-center rounded-full border border-border bg-muted/40 px-3">当前 {data.total.toLocaleString("zh-CN")} 条</span><span className="inline-flex h-7 items-center rounded-full border border-border bg-muted/40 px-3">显示 {visibleColumns.length} 列</span><span className="inline-flex h-7 items-center rounded-full border border-border bg-muted/40 px-3">视图 {columnMode === "full" ? "完整" : "自定义"}</span></div></div><div className="flex flex-wrap items-center gap-2"><div className="inline-flex h-8 items-center gap-0.5 rounded-lg border border-border bg-card p-0.5 shadow-sm" role="group" aria-label="数据日期"><button type="button" onClick={() => { setSnapshotDate(""); setPage(1) }} className={cn("inline-flex h-7 cursor-pointer items-center gap-1.5 rounded-md px-2.5 text-xs font-semibold transition-colors", !snapshotDate ? "bg-primary text-primary-foreground shadow-sm" : "text-muted-foreground hover:bg-muted/50 hover:text-foreground")}><Check className="h-3.5 w-3.5" />当前</button><div className="relative"><button type="button" onClick={openHistoryPicker} className={cn("inline-flex h-7 min-w-[9.5rem] cursor-pointer items-center gap-1.5 rounded-md border px-2.5 text-xs font-semibold transition-colors", snapshotDate ? "border-primary/35 bg-background text-foreground shadow-sm" : "border-transparent text-muted-foreground hover:bg-muted/50 hover:text-foreground")}><History className={cn("h-3.5 w-3.5", snapshotDate && "text-primary")} /><span>历史</span><span className="tabular-nums">{snapshotDate || "选择日期"}</span><CalendarDays className="ml-auto h-3.5 w-3.5 text-muted-foreground" /></button><input ref={historyDateInputRef} type="date" value={snapshotDate} max={data.snapshot_dates[0] || undefined} onChange={(event) => { setSnapshotDate(event.target.value); setPage(1) }} className="pointer-events-none absolute left-0 top-0 h-px w-px opacity-0" tabIndex={-1} /></div></div><Button variant="outline" className="h-8 px-3 text-xs font-semibold" onClick={refresh}><RefreshCw className="h-4 w-4" />刷新</Button><Button variant="outline" className="h-8 px-3 text-xs font-semibold" onClick={() => setOperationLogOpen(true)}><History className="h-4 w-4" />操作日志</Button><Button variant="outline" className="h-8 px-3 text-xs font-semibold" onClick={() => exportCsv(data, visibleColumns)} disabled={!data.items.length}><Download className="h-4 w-4" />导出</Button></div></div></div>
    <div className="surface-panel p-4"><div className="flex flex-wrap items-center justify-between gap-3"><div className="flex items-center gap-2" role="group" aria-label="列视图"><span className="text-sm font-medium">列视图</span>{[["full", "完整视图"], ["custom", "自定义"]].map(([mode, label]) => <button key={mode} type="button" onClick={() => { setColumnMode(mode as "full" | "custom"); if (mode === "custom") openPicker() }} className={cn("h-9 rounded-full px-4 text-sm font-medium transition-colors", columnMode === mode ? "bg-primary text-primary-foreground" : "bg-muted text-muted-foreground hover:bg-muted/70 hover:text-foreground")}>{label}</button>)}</div><div className="flex items-center gap-2">{columnMode === "custom" && <Button variant="outline" size="sm" onClick={openPicker}><SlidersHorizontal className="h-4 w-4" />配置列</Button>}<Button variant="outline" size="sm" onClick={() => exportCsv(data, visibleColumns)} disabled={!data.items.length}><Download className="h-4 w-4" />导出当前页</Button></div></div></div>
    <div className="surface-panel flex flex-wrap items-center gap-2 p-3"><div className="relative min-w-[260px] flex-1"><Search className="absolute left-3 top-2.5 h-4 w-4 text-muted-foreground" /><Input value={queryInput} onChange={(event) => setQueryInput(event.target.value)} onKeyDown={(event) => event.key === "Enter" && (setQuery(queryInput.trim()), setPage(1))} className="pl-9" placeholder="货号、款号、工厂货号、颜色" /></div><Input value={platform} onChange={(event) => { setPlatform(event.target.value); setPage(1) }} className="w-36" placeholder="所属平台" /><Button size="sm" onClick={() => { setQuery(queryInput.trim()); setPage(1) }}><Search className="h-4 w-4" />查询</Button><Button variant="outline" size="sm" onClick={() => { setQueryInput(""); setQuery(""); setPlatform(""); setPage(1) }}><X className="h-4 w-4" />清除</Button></div>
    <div className="table-panel"><div className="relative max-h-[72svh] min-h-[360px] overflow-auto"><table style={{ minWidth: tableWidth }} className={cn("w-full border-separate border-spacing-0 text-[13px] transition-opacity duration-150", loading && data.items.length > 0 && "opacity-60")} aria-busy={loading}><thead className="sticky top-0 z-[60] bg-card"><tr className="text-xs text-muted-foreground"><th rowSpan={2} className="sticky left-0 z-[70] w-20 min-w-[5rem] max-w-[5rem] border-b border-border bg-card px-3 py-2.5 text-center font-medium">图片</th><th rowSpan={2} className="sticky left-20 z-[70] w-40 min-w-[10rem] max-w-[10rem] border-b border-border bg-card px-3 py-2.5 text-left font-medium">货号</th><th rowSpan={2} className="sticky left-60 z-[70] w-40 min-w-[10rem] max-w-[10rem] border-b border-border bg-card px-3 py-2.5 text-left font-medium">款号</th>{groups.map(({ name, columns: groupColumns }, groupIndex) => <th key={`${name}-${groupIndex}-${groupColumns[0]?.key ?? "empty"}`} colSpan={groupColumns.length} className="border-b border-border bg-card px-3 py-2.5 text-center font-medium">{name}</th>)}<th rowSpan={2} className="sticky right-0 z-[70] w-20 border-b border-border bg-card px-3 py-2.5 text-center font-medium">详情</th></tr><tr className="text-xs text-muted-foreground">{visibleColumns.map((column) => <th key={column.key} style={{ minWidth: column.width ?? 78 }} className="border-b border-border bg-card px-2 py-2 text-center font-normal">{column.label}</th>)}</tr></thead><tbody>{data.items.length === 0 ? <tr><td colSpan={visibleColumns.length + 4} className="px-4 py-16 text-center text-muted-foreground">{loading ? "正在加载商品货品表..." : "暂无匹配商品"}</td></tr> : data.items.map((item) => <tr key={item.id} className="group transition-colors hover:bg-muted/50"><td className="sticky left-0 z-20 w-20 min-w-[5rem] max-w-[5rem] border-b border-border bg-card px-3 py-2 text-center group-hover:bg-muted"><button type="button" className={cn("mx-auto inline-flex rounded-lg focus:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2", item.image_url && "cursor-zoom-in")} onClick={() => item.image_url && setPreviewImage({ src: `/api${item.image_url}`, alt: item.goods_code || item.style_code || "商品图片" })} disabled={!item.image_url} aria-label={item.image_url ? "查看原图" : "暂无图片"}>{item.image_url ? <img src={`/api${item.image_url}`} alt={item.goods_code || "商品图片"} className="h-12 w-12 rounded-lg border border-border object-cover" /> : <ImageIcon className="h-4 w-4 text-muted-foreground/45" />}</button></td><td className="sticky left-20 z-20 w-40 min-w-[10rem] max-w-[10rem] border-b border-border bg-card px-3 py-2 font-medium group-hover:bg-muted">{value(item.goods_code)}</td><td className="sticky left-60 z-20 w-40 min-w-[10rem] max-w-[10rem] border-b border-border bg-card px-3 py-2 group-hover:bg-muted">{value(item.style_code)}</td>{visibleColumns.map((column) => <td key={column.key} className="border-b border-border px-3 py-2 text-center align-middle tabular-nums">{column.render(item)}</td>)}<td className="sticky right-0 z-20 w-20 border-b border-border bg-card px-3 py-2 text-center group-hover:bg-muted"><Button variant="ghost" size="icon" onClick={() => setSelectedItem(item)} aria-label="查看详情"><ChevronRight className="h-4 w-4" /></Button></td></tr>)}</tbody></table>{loading && data.items.length > 0 && <div className="pointer-events-none absolute right-3 top-3 z-[80] rounded-full border border-border bg-card/95 px-3 py-1.5 text-xs text-muted-foreground shadow-sm">正在更新商品货品表...</div>}</div><div className="flex flex-wrap items-center justify-between gap-3 border-t border-border px-4 py-3"><p className="text-sm text-muted-foreground">共 {data.total.toLocaleString("zh-CN")} 条 · 第 {data.total === 0 ? 0 : (page - 1) * pageSize + 1}-{Math.min(page * pageSize, data.total)} 条 · 第 {page} / {totalPages} 页</p><div className="flex flex-wrap items-center gap-2"><div className="flex h-9 items-center gap-1.5 rounded-lg border border-border bg-muted/25 px-2 text-xs text-muted-foreground"><span>每页</span><Select value={String(pageSize)} onChange={(event) => changePageSize(Number(event.target.value))} disabled={loading} className="h-8 w-[4.5rem] border-0 bg-transparent px-1.5 py-0 text-center text-xs leading-none shadow-none hover:bg-background focus-visible:ring-0">{PAGE_SIZE_OPTIONS.map((option) => <option key={option} value={option}>{option}</option>)}</Select><span>条</span></div><div className="flex h-9 items-center gap-1 rounded-lg border border-border bg-muted/25 px-1.5 text-xs text-muted-foreground"><span className="pl-0.5">跳至</span><Input type="number" min={1} max={totalPages} inputMode="numeric" value={pageInput} onChange={(event) => setPageInput(event.target.value)} onKeyDown={(event) => event.key === "Enter" && jumpToPage()} disabled={loading || data.total === 0} className="h-7 w-16 border-border/70 bg-background px-1 text-center text-xs tabular-nums" aria-label="页码" /><span>页</span><Button variant="ghost" size="icon" className="h-7 w-7" disabled={loading || data.total === 0} onClick={jumpToPage} aria-label="跳转页码" title="跳转页码"><ArrowRight className="h-3.5 w-3.5" /></Button></div><div className="flex items-center gap-1"><Button variant="outline" size="icon" disabled={page <= 1 || loading} onClick={() => setPage(1)} aria-label="第一页" title="第一页"><ChevronsLeft className="h-4 w-4" /></Button><Button variant="outline" size="icon" disabled={page <= 1 || loading} onClick={() => setPage((current) => current - 1)} aria-label="上一页" title="上一页"><ChevronLeft className="h-4 w-4" /></Button>{pageTokens(page, totalPages).map((token, index) => typeof token === "number" ? <Button key={token} variant={token === page ? "default" : "outline"} size="icon" disabled={loading} onClick={() => setPage(token)} aria-label={`第 ${token} 页`}>{token}</Button> : <span key={`ellipsis-${index}`} className="flex h-9 w-9 items-center justify-center text-muted-foreground"><MoreHorizontal className="h-4 w-4" /></span>)}<Button variant="outline" size="icon" disabled={page >= totalPages || loading} onClick={() => setPage((current) => current + 1)} aria-label="下一页" title="下一页"><ChevronRight className="h-4 w-4" /></Button><Button variant="outline" size="icon" disabled={page >= totalPages || loading} onClick={() => setPage(totalPages)} aria-label="最后一页" title="最后一页"><ChevronsRight className="h-4 w-4" /></Button></div></div></div></div></div>
    <Dialog open={pickerOpen} onOpenChange={setPickerOpen}><DialogContent className="flex max-h-[88svh] max-w-[min(96vw,1120px)] flex-col overflow-hidden p-0"><DialogHeader className="border-b border-border px-5 py-4"><div className="flex flex-wrap items-start justify-between gap-3"><div><DialogTitle className="text-base font-semibold">自定义列</DialogTitle><p className="mt-1 text-xs text-muted-foreground">已选择 {draftKeys.length} / {columns.length} 列</p></div><div className="flex gap-2"><Button variant="outline" size="sm" onClick={() => setDraftKeys(columns.map((column) => column.key))}>全选</Button><Button variant="outline" size="sm" onClick={() => setDraftKeys(DEFAULT_COLUMN_KEYS)}>默认</Button><Button variant="outline" size="sm" onClick={() => setDraftKeys([])}>清空</Button></div></div><div className="mt-3 h-1.5 overflow-hidden rounded-full bg-muted"><div className="h-full bg-primary" style={{ width: `${columns.length ? draftKeys.length / columns.length * 100 : 0}%` }} /></div></DialogHeader><div className="border-b border-border bg-muted/20 px-5 py-3"><div className="relative"><Search className="absolute left-3 top-2.5 h-4 w-4 text-muted-foreground" /><Input value={columnSearch} onChange={(event) => setColumnSearch(event.target.value)} className="pl-9" placeholder="搜索列名" /></div></div><div className="min-h-0 flex-1 overflow-y-auto px-5 py-4"><div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">{Object.entries(groupedPickerColumns).map(([group, groupColumns]) => { const displayed = groupColumns.filter((column) => !columnSearch || column.label.includes(columnSearch) || column.key.includes(columnSearch)); if (!displayed.length) return null; const selected = groupColumns.filter((column) => draftKeys.includes(column.key)).length; return <section key={group} className="rounded-lg border border-border bg-background"><div className="flex items-center justify-between border-b border-border px-3 py-2"><div><p className="text-sm font-medium">{group}</p><p className="text-[11px] text-muted-foreground">{selected}/{groupColumns.length}</p></div><div className="flex gap-1"><button className="px-2 text-xs text-muted-foreground hover:text-foreground" onClick={() => setDraftKeys((current) => Array.from(new Set([...current, ...groupColumns.map((column) => column.key)])))}>全选</button><button className="px-2 text-xs text-muted-foreground hover:text-foreground" onClick={() => setDraftKeys((current) => current.filter((key) => !groupColumns.some((column) => column.key === key)))}>清空</button></div></div><div className="grid gap-1 p-2 sm:grid-cols-2">{displayed.map((column) => { const checked = draftKeys.includes(column.key); return <label key={column.key} className={cn("flex h-8 cursor-pointer items-center gap-2 rounded-md border px-2 text-xs", checked ? "border-primary/30 bg-primary/10" : "border-transparent hover:bg-muted")}><input type="checkbox" className="sr-only" checked={checked} onChange={() => toggleDraftKey(column.key)} /><span className={cn("flex h-4 w-4 items-center justify-center rounded border", checked ? "border-primary bg-primary text-primary-foreground" : "border-border")}>{checked && <Check className="h-3 w-3" />}</span><span className="truncate">{column.label}</span></label> })}</div></section> })}</div></div><div className="flex justify-end gap-2 border-t border-border px-5 py-3"><Button variant="outline" size="sm" onClick={() => setPickerOpen(false)}>取消</Button><Button size="sm" onClick={() => { setCustomKeys(draftKeys); setColumnMode("custom"); setPickerOpen(false) }}>完成</Button></div></DialogContent></Dialog><OperationLogDialog module="product_goods" title="商品货品表操作日志" open={operationLogOpen} onOpenChange={setOperationLogOpen} />
    <Dialog open={previewImage !== null} onOpenChange={(open) => !open && setPreviewImage(null)}>
      <DialogContent className="max-h-[92svh] max-w-[min(94vw,1120px)] overflow-hidden bg-background p-0 shadow-2xl">
        <DialogHeader className="flex flex-row items-center justify-between gap-4 border-b border-border px-4 py-3 sm:px-5">
          <DialogTitle className="text-base font-semibold">原图预览</DialogTitle>
          <Button type="button" variant="ghost" size="icon" className="h-8 w-8 shrink-0" onClick={() => setPreviewImage(null)} aria-label="关闭原图预览"><X className="h-4 w-4" /></Button>
        </DialogHeader>
        {previewImage && <div className="flex h-[min(78svh,760px)] items-center justify-center bg-muted/20 p-4 sm:p-6"><img src={previewImage.src} alt={previewImage.alt} className="max-h-full w-auto max-w-full rounded-md object-contain shadow-sm" /></div>}
      </DialogContent>
    </Dialog>
    {selectedItem && <div aria-hidden="true" className="fixed inset-0 z-[80] bg-black/20" onClick={() => setSelectedItem(null)} />}
    <ProductGoodsDetailDrawer item={selectedItem} data={data} canEdit={canEdit} onClose={() => setSelectedItem(null)} onSave={saveManualFields} onPreviewImage={(item) => item.image_url && setPreviewImage({ src: `/api${item.image_url}`, alt: item.goods_code || item.style_code || "商品图片" })} />
  </div>
}
