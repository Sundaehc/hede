"use client"

import { memo, useDeferredValue, useEffect, useMemo, useRef, useState, type ReactNode } from "react"
import {
  AlertTriangle,
  BarChart3,
  Boxes,
  CalendarDays,
  Check,
  ChevronDown,
  ChevronLeft,
  ChevronRight,
  ChevronsLeft,
  ChevronsRight,
  Download,
  History,
  ImageIcon,
  Layers3,
  MoreHorizontal,
  RefreshCw,
  Search,
  SlidersHorizontal,
  TrendingUp,
  X,
  type LucideIcon,
} from "lucide-react"

import { Button } from "@/components/ui/button"
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import { Input } from "@/components/ui/input"
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs"
import { BRANDS, type BrandKey } from "@/lib/brands"
import { ApiError, getFineTableSnapshotByDate, listFineTable } from "@/lib/api"
import type { FineTableItem, ProductListItem } from "@/lib/types"
import { cn } from "@/lib/utils"

const PAGE_SIZE = 50
const EXPORT_PAGE_SIZE = 200
const EXPORT_CONCURRENCY = 3
const DAILY_SALES_DISPLAY_DAYS = 5

type ViewKey = "all" | "missingImage" | "stockRisk"
type ColumnMode = "full" | "custom"
type ColumnGroup = "基础" | "价格" | "销售" | "库存" | "每日" | "尺码"
type PageToken = number | "start-ellipsis" | "end-ellipsis"
type FineTableBrandKey = Exclude<BrandKey, "all">
type TableColumn = {
  key: string
  label: string
  group: ColumnGroup
  dailyDateLabel?: string
  dailyMetricLabel?: "销售" | "UV"
  align?: "left" | "right" | "center"
  className?: string
  defaultVisible?: boolean
  render: (row: FineTableItem) => ReactNode
  exportValue?: (row: FineTableItem) => string | number | null | undefined
}

const viewTabs: { value: ViewKey; label: string }[] = [
  { value: "all", label: "全部" },
  { value: "missingImage", label: "暂无图片" },
  { value: "stockRisk", label: "缺货风险" },
]

const FINE_TABLE_BRANDS = BRANDS.filter((item) => item.key !== "all") as Array<{ key: FineTableBrandKey; label: string }>
const DEFAULT_FINE_TABLE_BRAND: FineTableBrandKey = "cbanner_mens"

const SIZE_STOCK_LABELS = [
  "34/220",
  "35/225",
  "36/230",
  "37/235",
  "38/240",
  "39/245",
  "40/250",
  "41/255",
  "42/260",
  "43/265",
  "44/270",
  "45/275",
  "46/280",
  "47/285",
]

const DEFAULT_COLUMN_KEYS = [
  "status",
  "group_name",
  "factory_code",
  "product_name",
  "main_style",
  "goods_tag",
  "cost",
  "final_price",
  "activity_profit",
  "margin_rate",
  "vip_daily_average_sales",
  "vip_projected_15d_sales",
  "other_daily_average_sales",
  "other_projected_15d_sales",
  "original_other_3d_sales",
  "original_other_7d_sales",
  "original_other_15d_sales",
  "original_other_30d_sales",
  "vip_3d_exposure",
  "vip_7d_exposure",
  "vip_30d_exposure",
  "stock_qty",
  "projected_5d_stock_no_inbound",
  "inbound_qty",
  "original_defect_stock",
  "original_inbound_qty",
  "original_order_in_transit_stock",
  "original_defect_in_transit_stock",
  "order_in_transit_stock",
  "defect_in_transit_stock",
  "vip_projected_15d_stock",
  "other_projected_15d_stock",
  "risk",
]

function getErrorMessage(error: unknown) {
  if (error instanceof ApiError) return error.message || `请求失败（${error.status}）`
  if (error instanceof Error) return error.message
  return "加载精细表数据失败"
}

function formatNumber(value: number) {
  return new Intl.NumberFormat("zh-CN").format(value)
}

function nullableDecimal2(value: number | null | undefined) {
  return value == null || !Number.isFinite(value) ? "-" : value.toFixed(2)
}

function nullableInteger(value: number | null | undefined) {
  return value == null || !Number.isFinite(value) ? "-" : Math.round(value).toString()
}

function formatPercent(value: number) {
  return `${(value * 100).toFixed(1)}%`
}

function nullableCurrency(value: number | null | undefined) {
  return value == null || !Number.isFinite(value) ? "-" : `¥${Math.round(value)}`
}

function nullableCost(value: number | null | undefined) {
  return value == null || !Number.isFinite(value) ? "-" : `¥${value.toFixed(1)}`
}

function nullablePercent(value: number | null | undefined) {
  return value == null ? "-" : formatPercent(value)
}

function tableAlignClass(align: TableColumn["align"] = "left") {
  if (align === "right") return "text-right tabular-nums"
  if (align === "center") return "text-center tabular-nums"
  return "text-left"
}

function csvCell(value: string | number | null | undefined) {
  const text = value == null ? "" : String(value)
  return `"${text.replace(/"/g, '""')}"`
}

function downloadCsv(filename: string, rows: (string | number | null | undefined)[][]) {
  const csv = rows.map((row) => row.map(csvCell).join(",")).join("\r\n")
  const blob = new Blob([`\uFEFF${csv}`], { type: "text/csv;charset=utf-8" })
  const url = URL.createObjectURL(blob)
  const link = document.createElement("a")
  link.href = url
  link.download = filename
  document.body.appendChild(link)
  link.click()
  link.remove()
  URL.revokeObjectURL(url)
}

function parsePercentValue(value: string | null | undefined) {
  if (!value) return null
  const normalized = value.trim().replace("%", "")
  const parsed = Number(normalized)
  return Number.isFinite(parsed) ? parsed / 100 : null
}

function exposureValue(uv: number, ctr: string | null | undefined) {
  const ctrValue = parsePercentValue(ctr)
  if (ctrValue == null || ctrValue === 0) return null
  return uv / ctrValue
}

function otherDailyAverage(row: FineTableItem) {
  return row.other_30d_sales / 30
}

function vipProjected15dSales(row: FineTableItem) {
  return row.vip_daily_average_sales * 15
}

function otherProjected15dSales(row: FineTableItem) {
  return otherDailyAverage(row) * 15
}

function projected5dStockNoInbound(row: FineTableItem) {
  return row.stock_qty - (row.vip_daily_average_sales * 5 + otherDailyAverage(row) * 5)
}

function vipProjected15dStock(row: FineTableItem) {
  return row.stock_qty + row.inbound_qty - vipProjected15dSales(row)
}

function otherProjected15dStock(row: FineTableItem) {
  return vipProjected15dStock(row) - otherProjected15dSales(row)
}

function orderInTransitStock(row: FineTableItem) {
  return row.inbound_qty - row.defect_in_transit_stock
}

function visibleDailySales(row: FineTableItem) {
  return row.daily_sales.slice(-DAILY_SALES_DISPLAY_DAYS)
}

function getPageTokens(currentPage: number, totalPages: number): PageToken[] {
  if (totalPages <= 7) {
    return Array.from({ length: totalPages }, (_, index) => index + 1)
  }

  const start = Math.max(2, currentPage - 1)
  const end = Math.min(totalPages - 1, currentPage + 1)
  const tokens: PageToken[] = [1]

  if (start > 2) {
    tokens.push("start-ellipsis")
  } else {
    for (let page = 2; page < start; page += 1) tokens.push(page)
  }

  for (let page = start; page <= end; page += 1) {
    tokens.push(page)
  }

  if (end < totalPages - 1) {
    tokens.push("end-ellipsis")
  } else {
    for (let page = end + 1; page < totalPages; page += 1) tokens.push(page)
  }

  tokens.push(totalPages)
  return tokens
}

function FineTablePagination({
  page,
  pageSize,
  total,
  totalPages,
  isLoading,
  onPageChange,
}: {
  page: number
  pageSize: number
  total: number
  totalPages: number
  isLoading: boolean
  onPageChange: (page: number) => void
}) {
  const [jumpValue, setJumpValue] = useState("")
  const start = total === 0 ? 0 : (page - 1) * pageSize + 1
  const end = total === 0 ? 0 : Math.min(page * pageSize, total)

  function goToPage(nextPage: number) {
    const normalized = Math.min(totalPages, Math.max(1, nextPage))
    if (normalized !== page) {
      onPageChange(normalized)
    }
  }

  return (
    <div className="flex flex-wrap items-center justify-between gap-3 border-t border-border px-4 py-3">
      <p className="text-sm text-muted-foreground">
        共 {formatNumber(total)} 条 · 第 {formatNumber(start)}-{formatNumber(end)} 条 · 第 {page} / {totalPages} 页
      </p>
      <div className="flex flex-wrap items-center gap-2">
        <div className="flex items-center gap-1">
          <Button variant="outline" size="icon" disabled={page <= 1 || isLoading} onClick={() => goToPage(1)} aria-label="第一页">
            <ChevronsLeft className="h-4 w-4" />
          </Button>
          <Button variant="outline" size="icon" disabled={page <= 1 || isLoading} onClick={() => goToPage(page - 1)} aria-label="上一页">
            <ChevronLeft className="h-4 w-4" />
          </Button>
          {getPageTokens(page, totalPages).map((token) => (
            typeof token === "number" ? (
              <Button
                key={token}
                variant={token === page ? "default" : "outline"}
                size="icon"
                disabled={isLoading}
                onClick={() => goToPage(token)}
                aria-label={`第 ${token} 页`}
              >
                {token}
              </Button>
            ) : (
              <span key={token} className="flex h-9 w-9 items-center justify-center text-muted-foreground">
                <MoreHorizontal className="h-4 w-4" />
              </span>
            )
          ))}
          <Button variant="outline" size="icon" disabled={page >= totalPages || isLoading} onClick={() => goToPage(page + 1)} aria-label="下一页">
            <ChevronRight className="h-4 w-4" />
          </Button>
          <Button variant="outline" size="icon" disabled={page >= totalPages || isLoading} onClick={() => goToPage(totalPages)} aria-label="最后一页">
            <ChevronsRight className="h-4 w-4" />
          </Button>
        </div>
        <form
          className="flex items-center gap-2"
          onSubmit={(event) => {
            event.preventDefault()
            const nextPage = Number(jumpValue)
            if (Number.isInteger(nextPage)) {
              goToPage(nextPage)
              setJumpValue("")
            }
          }}
        >
          <span className="text-sm text-muted-foreground">跳至</span>
          <Input
            value={jumpValue}
            onChange={(event) => setJumpValue(event.target.value.replace(/[^\d]/g, ""))}
            className="h-9 w-20 text-center"
            inputMode="numeric"
            placeholder={String(page)}
            aria-label="跳转页码"
            disabled={isLoading}
          />
          <Button type="submit" variant="outline" size="sm" disabled={isLoading || !jumpValue}>
            跳转
          </Button>
        </form>
      </div>
    </div>
  )
}

function statusLabel(row: FineTableItem) {
  if (row.goods_status) return row.goods_status
  if (row.status_key === "online") return "商品上线"
  if (row.status_key === "partial") return "部分上线"
  if (row.status_key === "offline") return "已下线"
  return "未知"
}

function riskLabel(row: FineTableItem) {
  if (Math.min(vipProjected15dStock(row), otherProjected15dStock(row)) < 0) return "15天后缺口"
  if (row.stock_qty < row.vip_7d_sales + row.other_7d_sales) return "低库存"
  return "正常"
}

function hasStockRisk(row: FineTableItem) {
  return riskLabel(row) !== "正常"
}

function tableColumnExportValue(row: FineTableItem, column: TableColumn) {
  if (column.exportValue) return column.exportValue(row)
  if (column.key.startsWith("daily_sales_")) {
    const [, , indexValue, metric] = column.key.split("_")
    const index = Number(indexValue)
    if (metric === "uv") return visibleDailySales(row)[index]?.uv ?? 0
    return visibleDailySales(row)[index]?.quantity ?? 0
  }
  if (column.key.startsWith("size_")) {
    const size = column.key.replace("size_", "")
    return row.size_stock[size] ?? 0
  }

  switch (column.key) {
    case "status":
      return statusLabel(row)
    case "category_l3":
      return row.category_l3 || row.product_model || ""
    case "cost":
      return row.latest_purchase_price
    case "activity_profit":
      return row.activity_profit == null ? "" : Math.round(row.activity_profit)
    case "margin_rate":
      return nullableDecimal2(row.margin_rate)
    case "vip_daily_average_sales":
      return nullableInteger(row.vip_daily_average_sales)
    case "vip_projected_15d_sales":
      return nullableInteger(vipProjected15dSales(row))
    case "other_daily_average_sales":
      return nullableInteger(otherDailyAverage(row))
    case "other_projected_15d_sales":
      return nullableInteger(otherProjected15dSales(row))
    case "vip_3d_exposure":
      return nullableInteger(exposureValue(row.vip_3d_uv, row.vip_3d_ctr))
    case "vip_7d_exposure":
      return nullableInteger(exposureValue(row.vip_7d_uv, row.vip_7d_ctr))
    case "vip_30d_exposure":
      return nullableInteger(exposureValue(row.vip_30d_uv, row.vip_30d_ctr))
    case "vip_3d_sales_change_rate":
      return nullablePercent(row.vip_3d_sales_change_rate)
    case "vip_3d_uv_change_rate":
      return nullablePercent(row.vip_3d_uv_change_rate)
    case "vip_3d_ctr_change_rate":
      return nullablePercent(row.vip_3d_ctr_change_rate)
    case "vip_3d_conversion_change_rate":
      return nullablePercent(row.vip_3d_conversion_change_rate)
    case "vip_7d_sales_change_rate":
      return nullablePercent(row.vip_7d_sales_change_rate)
    case "vip_7d_uv_change_rate":
      return nullablePercent(row.vip_7d_uv_change_rate)
    case "vip_7d_ctr_change_rate":
      return nullablePercent(row.vip_7d_ctr_change_rate)
    case "vip_7d_conversion_change_rate":
      return nullablePercent(row.vip_7d_conversion_change_rate)
    case "projected_5d_stock_no_inbound":
      return nullableInteger(projected5dStockNoInbound(row))
    case "vip_projected_15d_stock":
      return nullableInteger(vipProjected15dStock(row))
    case "other_projected_15d_stock":
      return nullableInteger(otherProjected15dStock(row))
    case "order_in_transit_stock":
      return orderInTransitStock(row)
    case "risk":
      return riskLabel(row)
    default: {
      const value = (row as Record<string, unknown>)[column.key]
      if (value == null) return ""
      if (typeof value === "string" || typeof value === "number") return value
      if (typeof value === "boolean") return value ? "是" : "否"
      return ""
    }
  }
}

function buildFineTableCsvRows(rows: FineTableItem[], visibleColumns: TableColumn[]) {
  return [
    ["货号", "原始货号", ...visibleColumns.map((column) => column.dailyMetricLabel ? `${column.label}${column.dailyMetricLabel}` : column.label)],
    ...rows.map((row) => [
      row.sku || "",
      row.original_sku || "",
      ...visibleColumns.map((column) => tableColumnExportValue(row, column)),
    ]),
  ]
}

function timestampForFilename(date: Date) {
  const pad = (value: number) => String(value).padStart(2, "0")
  return [
    date.getFullYear(),
    pad(date.getMonth() + 1),
    pad(date.getDate()),
    "_",
    pad(date.getHours()),
    pad(date.getMinutes()),
    pad(date.getSeconds()),
  ].join("")
}

function StatusBadge({ row }: { row: FineTableItem }) {
  const status = row.status_key
  return (
    <span
      className={cn(
        "inline-flex h-6 items-center rounded-md px-2 text-xs font-medium",
        status === "online" && "bg-emerald-50 text-emerald-700 dark:bg-emerald-950/40 dark:text-emerald-300",
        status === "partial" && "bg-amber-50 text-amber-700 dark:bg-amber-950/40 dark:text-amber-300",
        (status === "offline" || status === "unknown") && "bg-zinc-100 text-zinc-600 dark:bg-zinc-800 dark:text-zinc-300",
      )}
    >
      {statusLabel(row)}
    </span>
  )
}

function RiskBadge({ row }: { row: FineTableItem }) {
  if (Math.min(vipProjected15dStock(row), otherProjected15dStock(row)) < 0) {
    return <span className="inline-flex rounded-md bg-rose-50 px-2 py-1 text-xs font-medium text-rose-700 dark:bg-rose-950/40 dark:text-rose-300">15天后缺口</span>
  }
  if (row.stock_qty < row.vip_7d_sales + row.other_7d_sales) {
    return <span className="inline-flex rounded-md bg-amber-50 px-2 py-1 text-xs font-medium text-amber-700 dark:bg-amber-950/40 dark:text-amber-300">低库存</span>
  }
  return <span className="inline-flex rounded-md bg-slate-100 px-2 py-1 text-xs font-medium text-slate-600 dark:bg-slate-800 dark:text-slate-300">正常</span>
}

function ChangeRateText({ value }: { value: number | null | undefined }) {
  if (value == null) return "-"
  return (
    <span className={cn(value > 0 ? "text-emerald-600" : value < 0 ? "text-rose-600" : "text-muted-foreground")}>
      {value > 0 ? "+" : ""}{formatPercent(value)}
    </span>
  )
}

function createTableColumns(dailyLabels: string[]): TableColumn[] {
  const dailyColumns: TableColumn[] = dailyLabels.flatMap((label, index) => [
    {
      key: `daily_sales_${index}_quantity`,
      label,
      dailyDateLabel: label,
      dailyMetricLabel: "销售" as const,
      group: "每日" as const,
      align: "center" as const,
      className: "min-w-16",
      render: (row: FineTableItem) => formatNumber(visibleDailySales(row)[index]?.quantity ?? 0),
    },
    {
      key: `daily_sales_${index}_uv`,
      label,
      dailyDateLabel: label,
      dailyMetricLabel: "UV" as const,
      group: "每日" as const,
      align: "center" as const,
      className: "min-w-16",
      render: (row: FineTableItem) => formatNumber(visibleDailySales(row)[index]?.uv ?? 0),
    },
  ])

  const sizeColumns: TableColumn[] = SIZE_STOCK_LABELS.map((label) => ({
    key: `size_${label}`,
    label,
    group: "尺码",
    align: "right",
    render: (row) => formatNumber(row.size_stock[label] ?? 0),
  }))

  return [
    {
      key: "status",
      label: "上下线状态",
      group: "基础",
      defaultVisible: true,
      render: (row) => <StatusBadge row={row} />,
    },
    { key: "group_name", label: "组别", group: "基础", className: "min-w-28", defaultVisible: true, render: (row) => row.group_name || "-" },
    { key: "factory_code", label: "工厂代码", group: "基础", className: "min-w-28", defaultVisible: true, render: (row) => row.factory_code || "-" },
    { key: "product_name", label: "品名", group: "基础", className: "min-w-28", defaultVisible: true, render: (row) => row.product_name || "-" },
    { key: "main_style", label: "主款式", group: "基础", className: "min-w-28", defaultVisible: true, render: (row) => row.main_style || "-" },
    { key: "style_code", label: "款号", group: "基础", render: (row) => row.style_code || "-" },
    { key: "goods_id", label: "商品ID", group: "基础", className: "min-w-40", render: (row) => row.goods_id || "-" },
    { key: "p_spu", label: "P-SPU", group: "基础", className: "min-w-44", render: (row) => row.p_spu || "-" },
    { key: "category_l3", label: "三级分类", group: "基础", render: (row) => row.category_l3 || row.product_model || "-" },
    { key: "factory_sku", label: "工厂货号", group: "基础", render: (row) => row.factory_sku || "-" },
    { key: "execution_standard", label: "执行标", group: "基础", className: "min-w-36", render: (row) => row.execution_standard || "-" },
    { key: "upper_material", label: "鞋面材质", group: "基础", render: (row) => row.upper_material || "-" },
    { key: "lining_material", label: "内里材质", group: "基础", render: (row) => row.lining_material || "-" },
    { key: "outsole_material", label: "大底材质", group: "基础", render: (row) => row.outsole_material || "-" },
    { key: "insole_material", label: "鞋垫材质", group: "基础", render: (row) => row.insole_material || "-" },
    { key: "first_order_time", label: "首单日期", group: "基础", render: (row) => row.first_order_time || "-" },
    { key: "sales_tag", label: "畅销度", group: "基础", className: "min-w-36", render: (row) => row.sales_tag || "-" },
    {
      key: "goods_tag",
      label: "小灯塔",
      group: "基础",
      className: "min-w-24",
      defaultVisible: true,
      render: (row) => row.goods_tag ? (
        <span className="inline-flex h-6 items-center rounded-md bg-amber-50 px-2 text-xs font-medium text-amber-700 dark:bg-amber-950/40 dark:text-amber-300">
          {row.goods_tag}
        </span>
      ) : "-",
    },

    { key: "cost", label: "成本", group: "价格", align: "right", defaultVisible: true, render: (row) => nullableCost(row.latest_purchase_price) },
    { key: "final_price", label: "到手价", group: "价格", align: "right", defaultVisible: true, render: (row) => nullableCurrency(row.final_price) },
    { key: "vip_price", label: "唯品价", group: "价格", align: "right", render: (row) => nullableCurrency(row.vip_price) },
    { key: "market_price", label: "市场价", group: "价格", align: "right", render: (row) => nullableCurrency(row.market_price) },
    { key: "price_band", label: "价格段", group: "价格", render: (row) => row.price_band || "-" },
    { key: "activity_profit", label: "活动毛利", group: "价格", align: "right", defaultVisible: true, render: (row) => nullableInteger(row.activity_profit) },
    {
      key: "margin_rate",
      label: "活动毛利率",
      group: "价格",
      align: "right",
      defaultVisible: true,
      render: (row) => (
        <span className={cn((row.margin_rate ?? 1) < 0.1 ? "text-rose-600" : "text-emerald-600")}>
          {nullableDecimal2(row.margin_rate)}
        </span>
      ),
    },
    { key: "vip_1d_sales", label: "唯品1天", group: "销售", align: "right", render: (row) => formatNumber(row.vip_1d_sales) },
    { key: "vip_3d_sales", label: "唯品3天", group: "销售", align: "right", render: (row) => formatNumber(row.vip_3d_sales) },
    { key: "vip_15d_sales", label: "唯品15天", group: "销售", align: "right", render: (row) => formatNumber(row.vip_15d_sales) },
    { key: "vip_30d_sales", label: "唯品30天", group: "销售", align: "right", render: (row) => formatNumber(row.vip_30d_sales) },
    { key: "vip_daily_average_sales", label: "唯品日均", group: "销售", align: "right", defaultVisible: true, render: (row) => nullableInteger(row.vip_daily_average_sales) },
    { key: "vip_projected_15d_sales", label: "唯品15天预计", group: "销售", align: "right", defaultVisible: true, render: (row) => nullableInteger(vipProjected15dSales(row)) },
    { key: "other_3d_sales", label: "其他3天", group: "销售", align: "right", render: (row) => formatNumber(row.other_3d_sales) },
    { key: "other_15d_sales", label: "其他15天", group: "销售", align: "right", render: (row) => formatNumber(row.other_15d_sales) },
    { key: "other_30d_sales", label: "其他30天", group: "销售", align: "right", render: (row) => formatNumber(row.other_30d_sales) },
    { key: "other_daily_average_sales", label: "其他日均", group: "销售", align: "right", defaultVisible: true, render: (row) => nullableInteger(otherDailyAverage(row)) },
    { key: "other_projected_15d_sales", label: "其他15天预计", group: "销售", align: "right", defaultVisible: true, render: (row) => nullableInteger(otherProjected15dSales(row)) },
    { key: "original_other_3d_sales", label: "其他原始3天", group: "销售", align: "right", defaultVisible: true, render: (row) => formatNumber(row.original_other_3d_sales) },
    { key: "original_other_7d_sales", label: "其他原始7天", group: "销售", align: "right", defaultVisible: true, render: (row) => formatNumber(row.original_other_7d_sales) },
    { key: "original_other_15d_sales", label: "其他原始15天", group: "销售", align: "right", defaultVisible: true, render: (row) => formatNumber(row.original_other_15d_sales) },
    { key: "original_other_30d_sales", label: "其他原始30天", group: "销售", align: "right", defaultVisible: true, render: (row) => formatNumber(row.original_other_30d_sales) },
    { key: "vip_3d_uv", label: "3天UV", group: "销售", align: "right", render: (row) => formatNumber(row.vip_3d_uv) },
    { key: "vip_7d_uv", label: "7天UV", group: "销售", align: "right", render: (row) => formatNumber(row.vip_7d_uv) },
    { key: "vip_30d_uv", label: "30天UV", group: "销售", align: "right", render: (row) => formatNumber(row.vip_30d_uv) },
    { key: "vip_3d_ctr", label: "3天CTR", group: "销售", align: "right", render: (row) => row.vip_3d_ctr || "-" },
    { key: "vip_7d_ctr", label: "7天CTR", group: "销售", align: "right", render: (row) => row.vip_7d_ctr || "-" },
    { key: "vip_30d_ctr", label: "30天CTR", group: "销售", align: "right", render: (row) => row.vip_30d_ctr || "-" },
    { key: "vip_3d_exposure", label: "3天曝光", group: "销售", align: "right", render: (row) => nullableInteger(exposureValue(row.vip_3d_uv, row.vip_3d_ctr)) },
    { key: "vip_7d_exposure", label: "7天曝光", group: "销售", align: "right", render: (row) => nullableInteger(exposureValue(row.vip_7d_uv, row.vip_7d_ctr)) },
    { key: "vip_30d_exposure", label: "30天曝光", group: "销售", align: "right", render: (row) => nullableInteger(exposureValue(row.vip_30d_uv, row.vip_30d_ctr)) },
    { key: "vip_3d_conversion", label: "3天转化", group: "销售", align: "right", render: (row) => row.vip_3d_conversion || "-" },
    { key: "vip_7d_conversion", label: "7天转化", group: "销售", align: "right", render: (row) => row.vip_7d_conversion || "-" },
    { key: "vip_30d_conversion", label: "30天转化", group: "销售", align: "right", render: (row) => row.vip_30d_conversion || "-" },
    { key: "vip_3d_sales_change_rate", label: "3天销售环比", group: "销售", align: "right", render: (row) => <ChangeRateText value={row.vip_3d_sales_change_rate} /> },
    { key: "vip_3d_uv_change_rate", label: "3天UV环比", group: "销售", align: "right", render: (row) => <ChangeRateText value={row.vip_3d_uv_change_rate} /> },
    { key: "vip_3d_ctr_change_rate", label: "3天CTR环比", group: "销售", align: "right", render: (row) => <ChangeRateText value={row.vip_3d_ctr_change_rate} /> },
    { key: "vip_3d_conversion_change_rate", label: "3天转化环比", group: "销售", align: "right", render: (row) => <ChangeRateText value={row.vip_3d_conversion_change_rate} /> },
    { key: "vip_7d_sales_change_rate", label: "7天销售环比", group: "销售", align: "right", render: (row) => <ChangeRateText value={row.vip_7d_sales_change_rate} /> },
    { key: "vip_7d_uv_change_rate", label: "7天UV环比", group: "销售", align: "right", render: (row) => <ChangeRateText value={row.vip_7d_uv_change_rate} /> },
    { key: "vip_7d_ctr_change_rate", label: "7天CTR环比", group: "销售", align: "right", render: (row) => <ChangeRateText value={row.vip_7d_ctr_change_rate} /> },
    { key: "vip_7d_conversion_change_rate", label: "7天转化环比", group: "销售", align: "right", render: (row) => <ChangeRateText value={row.vip_7d_conversion_change_rate} /> },
    { key: "vip_30d_reject_count", label: "30天拒退", group: "销售", align: "right", render: (row) => formatNumber(row.vip_30d_reject_count) },
    { key: "vip_30d_reject_rate", label: "30天拒退率", group: "销售", align: "right", render: (row) => row.vip_30d_reject_rate || "-" },

    { key: "stock_qty", label: "聚水潭库存", group: "库存", align: "right", defaultVisible: true, render: (row) => formatNumber(row.stock_qty) },
    {
      key: "projected_5d_stock_no_inbound",
      label: "现有5天后预计库存(不加未到)",
      group: "库存",
      align: "right",
      defaultVisible: true,
      render: (row) => {
        const value = projected5dStockNoInbound(row)
        return (
          <span className={cn(value < 0 && "text-rose-600")}>
            {nullableInteger(value)}
          </span>
        )
      },
    },
    { key: "inbound_qty", label: "采购在途数", group: "库存", align: "right", defaultVisible: true, render: (row) => formatNumber(row.inbound_qty) },
    { key: "defect_stock", label: "次品库存", group: "库存", align: "right", defaultVisible: true, render: (row) => formatNumber(row.defect_stock) },
    { key: "original_defect_stock", label: "原始货号次品仓汇总", group: "库存", align: "right", defaultVisible: true, render: (row) => formatNumber(row.original_defect_stock ?? 0) },
    { key: "original_inbound_qty", label: "原始货号采购在途数量汇总", group: "库存", align: "right", defaultVisible: true, render: (row) => formatNumber(row.original_inbound_qty ?? 0) },
    { key: "original_order_in_transit_stock", label: "原始货号已下订单未到数量汇总", group: "库存", align: "right", defaultVisible: true, render: (row) => formatNumber(row.original_order_in_transit_stock ?? 0) },
    { key: "original_defect_in_transit_stock", label: "原始货号打次未到数量汇总", group: "库存", align: "right", defaultVisible: true, render: (row) => formatNumber(row.original_defect_in_transit_stock ?? 0) },
    { key: "off_shelf_stock", label: "下架仓商品数量", group: "库存", align: "right", defaultVisible: true, render: (row) => formatNumber(row.off_shelf_stock) },
    { key: "order_occupy_stock", label: "订单占有", group: "库存", align: "right", render: (row) => formatNumber(row.order_occupy_stock) },
    { key: "order_in_transit_stock", label: "已下订单未到数量", group: "库存", align: "right", defaultVisible: true, render: (row) => formatNumber(orderInTransitStock(row)) },
    { key: "defect_in_transit_stock", label: "打次未到数量", group: "库存", align: "right", defaultVisible: true, render: (row) => formatNumber(row.defect_in_transit_stock) },
    {
      key: "vip_projected_15d_stock",
      label: "15天后库存减唯品会",
      group: "库存",
      align: "right",
      defaultVisible: true,
      render: (row) => {
        const value = vipProjected15dStock(row)
        return (
          <span className={cn(value < 0 && "text-rose-600")}>
            {nullableInteger(value)}
          </span>
        )
      },
    },
    {
      key: "other_projected_15d_stock",
      label: "15天后库存减其他平台",
      group: "库存",
      align: "right",
      defaultVisible: true,
      render: (row) => {
        const value = otherProjected15dStock(row)
        return (
          <span className={cn(value < 0 && "text-rose-600")}>
            {nullableInteger(value)}
          </span>
        )
      },
    },
    { key: "risk", label: "风险", group: "库存", defaultVisible: true, render: (row) => <RiskBadge row={row} /> },
    ...dailyColumns,
    ...sizeColumns,
  ]
}

function ProductThumb({ item, className }: { item: ProductListItem; className?: string }) {
  const src = item.image_url ? `/api${item.image_url}` : null
  return (
    <div className={cn("flex h-13 w-13 shrink-0 items-center justify-center overflow-hidden rounded-lg border border-border bg-muted/40", className)}>
      {src ? (
        // eslint-disable-next-line @next/next/no-img-element
        <img
          src={src}
          alt={item.sku || item.original_sku || "商品图片"}
          width={52}
          height={52}
          loading="lazy"
          decoding="async"
          className="h-full w-full object-contain"
        />
      ) : (
        <ImageIcon className="h-6 w-6 text-muted-foreground" />
      )}
    </div>
  )
}

function DetailFieldCard({ label, value, wide = false }: { label: string; value: ReactNode; wide?: boolean }) {
  return (
    <div className={cn("rounded-lg border border-border bg-card px-3 py-2.5", wide && "sm:col-span-2")}>
      <p className="text-[11px] text-muted-foreground">{label}</p>
      <div className="mt-1 break-words text-sm font-medium leading-5">{value || "-"}</div>
    </div>
  )
}

function DetailSection({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section className="space-y-3">
      <div className="flex items-center gap-2">
        <span className="h-4 w-1 rounded-full bg-foreground/80" />
        <h3 className="text-sm font-semibold">{title}</h3>
      </div>
      {children}
    </section>
  )
}

function HeaderMetric({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-lg border border-border bg-background/65 px-3 py-2">
      <p className="text-[11px] text-muted-foreground">{label}</p>
      <p className="mt-0.5 text-sm font-semibold tabular-nums">{value}</p>
    </div>
  )
}

function StatCard({
  icon: Icon,
  label,
  value,
  tone = "neutral",
}: {
  icon: LucideIcon
  label: string
  value: string
  tone?: "neutral" | "risk" | "good" | "warn"
}) {
  return (
    <div className="overflow-hidden rounded-xl border border-border bg-card shadow-sm">
      <div
        className={cn(
          "h-1 w-full",
          tone === "neutral" && "bg-slate-200 dark:bg-slate-700",
          tone === "risk" && "bg-rose-400",
          tone === "good" && "bg-emerald-400",
          tone === "warn" && "bg-amber-400",
        )}
      />
      <div className="flex items-start justify-between gap-3 px-4 py-3">
        <div className="min-w-0">
          <p className="text-xs text-muted-foreground">{label}</p>
          <p className="mt-1 truncate text-[1.6rem] font-semibold leading-none tracking-normal">{value}</p>
        </div>
        <div
          className={cn(
            "flex h-9 w-9 shrink-0 items-center justify-center rounded-lg",
            tone === "neutral" && "bg-slate-100 text-slate-700 dark:bg-slate-800 dark:text-slate-200",
            tone === "risk" && "bg-rose-50 text-rose-700 dark:bg-rose-950/40 dark:text-rose-300",
            tone === "good" && "bg-emerald-50 text-emerald-700 dark:bg-emerald-950/40 dark:text-emerald-300",
            tone === "warn" && "bg-amber-50 text-amber-700 dark:bg-amber-950/40 dark:text-amber-300",
          )}
        >
          <Icon className="h-4 w-4" />
        </div>
      </div>
    </div>
  )
}

function TrendBars({ values }: { values: number[] }) {
  const max = Math.max(...values, 1)
  return (
    <div className="flex h-10 items-end gap-0.5">
      {values.map((value, index) => (
        <span
          key={`${value}-${index}`}
          className="w-1.5 rounded-t-sm bg-slate-400/70 dark:bg-slate-500"
          style={{ height: `${Math.max(10, (value / max) * 100)}%` }}
        />
      ))}
    </div>
  )
}

function DetailDrawer({ row, onClose }: { row: FineTableItem | null; onClose: () => void }) {
  const drawerRef = useRef<HTMLDivElement | null>(null)
  const previouslyFocusedRef = useRef<HTMLElement | null>(null)

  useEffect(() => {
    if (!row) return

    previouslyFocusedRef.current = document.activeElement instanceof HTMLElement ? document.activeElement : null
    drawerRef.current?.focus()

    return () => {
      previouslyFocusedRef.current?.focus()
    }
  }, [row])

  if (!row) return null
  const dailyValues = visibleDailySales(row).map((item) => item.quantity)
  const dailyTotal = dailyValues.reduce((sum, value) => sum + value, 0)
  const marketReference = row.latest_purchase_price == null ? null : Math.round((row.latest_purchase_price + 10) * 1.13 * 11)
  const maxShopQuantity = Math.max(...row.shop_30d_sales.map((item) => item.quantity), 1)

  return (
    <div
      ref={drawerRef}
      role="dialog"
      aria-modal="true"
      aria-labelledby="fine-table-detail-title"
      tabIndex={-1}
      className="fixed inset-y-0 right-0 z-50 w-full max-w-2xl border-l border-border bg-background/95 shadow-2xl outline-none backdrop-blur"
      onKeyDown={(event) => {
        if (event.key === "Escape") {
          event.preventDefault()
          onClose()
          return
        }

        if (event.key !== "Tab") return

        const focusable = Array.from(
          drawerRef.current?.querySelectorAll<HTMLElement>(
            "button:not([disabled]), [href], input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex='-1'])",
          ) ?? [],
        )
        if (focusable.length === 0) return

        const first = focusable[0]
        const last = focusable[focusable.length - 1]
        if (event.shiftKey && document.activeElement === first) {
          event.preventDefault()
          last.focus()
        } else if (!event.shiftKey && document.activeElement === last) {
          event.preventDefault()
          first.focus()
        }
      }}
    >
      <div className="flex h-full flex-col">
        <div className="border-b border-border bg-card/90 px-5 py-5">
          <div className="flex items-start justify-between gap-4">
            <div className="flex min-w-0 gap-4">
              <ProductThumb item={row} className="h-20 w-20 rounded-xl bg-background" />
              <div className="min-w-0">
                <div className="flex flex-wrap items-center gap-2">
                  <h2 id="fine-table-detail-title" className="truncate text-xl font-semibold">{row.sku || row.original_sku || "未命名商品"}</h2>
                  <StatusBadge row={row} />
                </div>
                <p className="mt-1 text-sm text-muted-foreground">{row.product_name || row.original_sku || row.sku || "-"}</p>
                <div className="mt-3 flex flex-wrap gap-1.5 text-xs text-muted-foreground">
                  <span className="rounded-full border border-border bg-muted/40 px-2.5 py-1">{row.original_sku || "无原始货号"}</span>
                  <span className="rounded-full border border-border bg-muted/40 px-2.5 py-1">{row.group_name || "未分组"}</span>
                  {row.main_style ? <span className="rounded-full border border-border bg-muted/40 px-2.5 py-1">{row.main_style}</span> : null}
                </div>
              </div>
            </div>
            <Button variant="ghost" size="icon" onClick={onClose} aria-label="关闭详情">
              <X className="h-4 w-4" />
            </Button>
          </div>
          <div className="mt-4 grid grid-cols-2 gap-2 sm:grid-cols-4">
            <HeaderMetric label="聚水潭库存" value={formatNumber(row.stock_qty)} />
            <HeaderMetric label="唯品3天" value={formatNumber(row.vip_3d_sales)} />
            <HeaderMetric label="其他3天" value={formatNumber(row.other_3d_sales)} />
            <HeaderMetric label="风险" value={riskLabel(row)} />
          </div>
        </div>

        <Tabs defaultValue="base" className="min-h-0 flex-1">
          <div className="sticky top-0 z-10 border-b border-border bg-background/95 px-5 py-3 backdrop-blur">
            <TabsList className="grid h-10 w-full grid-cols-4 rounded-xl bg-muted/50 p-1">
              <TabsTrigger className="rounded-lg text-xs" value="base">基础</TabsTrigger>
              <TabsTrigger className="rounded-lg text-xs" value="price">价格</TabsTrigger>
              <TabsTrigger className="rounded-lg text-xs" value="sales">销售</TabsTrigger>
              <TabsTrigger className="rounded-lg text-xs" value="stock">库存</TabsTrigger>
            </TabsList>
          </div>

          <div className="min-h-0 flex-1 overflow-y-auto px-5 py-5">
            <TabsContent value="base" className="space-y-4">
              <DetailSection title="商品识别">
                <div className="grid gap-2 sm:grid-cols-2">
                  <DetailFieldCard label="品名" value={row.product_name} wide />
                  <DetailFieldCard label="商品ID" value={row.goods_id} />
                  <DetailFieldCard label="P-SPU" value={row.p_spu} />
                  <DetailFieldCard label="款号" value={row.style_code} />
                  <DetailFieldCard label="工厂代码" value={row.factory_code} />
                  <DetailFieldCard label="工厂货号" value={row.factory_sku} />
                  <DetailFieldCard label="组别" value={row.group_name} />
                  <DetailFieldCard label="主款式" value={row.main_style} />
                </div>
              </DetailSection>
              <DetailSection title="分类与材质">
                <div className="grid gap-2 sm:grid-cols-2">
                  <DetailFieldCard label="三级分类" value={row.category_l3 || row.product_model} />
                  <DetailFieldCard label="首单日期" value={row.first_order_time} />
                  <DetailFieldCard label="执行标准" value={row.execution_standard} />
                  <DetailFieldCard label="鞋面材质" value={row.upper_material} />
                  <DetailFieldCard label="内里材质" value={row.lining_material} />
                  <DetailFieldCard label="大底材质" value={row.outsole_material} />
                  <DetailFieldCard label="鞋垫材质" value={row.insole_material} />
                </div>
              </DetailSection>
            </TabsContent>

            <TabsContent value="price" className="space-y-4">
              <div className="grid gap-3 sm:grid-cols-2">
                <StatCard icon={SlidersHorizontal} label="今日到手价" value={nullableCurrency(row.final_price)} tone="good" />
                <StatCard icon={Layers3} label="价格段" value={row.price_band || "-"} />
                <StatCard icon={BarChart3} label="活动毛利" value={nullableInteger(row.activity_profit)} tone={(row.margin_rate ?? 1) < 0.12 ? "warn" : "good"} />
                <StatCard icon={BarChart3} label="毛利率" value={nullableDecimal2(row.margin_rate)} tone={(row.margin_rate ?? 1) < 0.12 ? "warn" : "good"} />
              </div>
              <DetailSection title="价格结构">
              <div className="overflow-hidden rounded-xl border border-border bg-card">
                {[
                  ["成本", nullableCost(row.latest_purchase_price)],
                  ["唯品价", nullableCurrency(row.vip_price)],
                  ["市场价", nullableCurrency(row.market_price)],
                  ["市场价参考", nullableCurrency(marketReference)],
                ].map(([label, value]) => (
                  <div key={label} className="flex items-center justify-between border-b border-border px-4 py-3 last:border-b-0">
                    <span className="text-sm text-muted-foreground">{label}</span>
                    <span className="font-medium">{value}</span>
                  </div>
                ))}
              </div>
              </DetailSection>
            </TabsContent>

            <TabsContent value="sales" className="space-y-4">
              <div className="rounded-xl border border-border bg-card p-4 shadow-sm">
                <div className="mb-3 flex items-center justify-between">
                  <p className="text-sm font-medium">近15天销售</p>
                  <span className="text-xs text-muted-foreground">合计 {formatNumber(dailyTotal)}</span>
                </div>
                <TrendBars values={dailyValues} />
              </div>
              <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
                <StatCard icon={TrendingUp} label="唯品3天" value={formatNumber(row.vip_3d_sales)} />
                <StatCard icon={TrendingUp} label="唯品30天" value={formatNumber(row.vip_30d_sales)} />
                <StatCard icon={TrendingUp} label="唯品15天预计" value={nullableInteger(vipProjected15dSales(row))} />
                <StatCard icon={Boxes} label="其他3天" value={formatNumber(row.other_3d_sales)} />
                <StatCard icon={Boxes} label="其他30天" value={formatNumber(row.other_30d_sales)} />
                <StatCard icon={Boxes} label="其他日均" value={nullableInteger(otherDailyAverage(row))} />
                <StatCard icon={Boxes} label="其他15天预计" value={nullableInteger(otherProjected15dSales(row))} />
                <StatCard icon={TrendingUp} label="3天曝光" value={nullableInteger(exposureValue(row.vip_3d_uv, row.vip_3d_ctr))} />
                <StatCard icon={TrendingUp} label="7天曝光" value={nullableInteger(exposureValue(row.vip_7d_uv, row.vip_7d_ctr))} />
                <StatCard icon={TrendingUp} label="30天曝光" value={nullableInteger(exposureValue(row.vip_30d_uv, row.vip_30d_ctr))} />
                <StatCard icon={Boxes} label="其他原始3天" value={formatNumber(row.original_other_3d_sales)} />
                <StatCard icon={Boxes} label="其他原始7天" value={formatNumber(row.original_other_7d_sales)} />
                <StatCard icon={Boxes} label="其他原始15天" value={formatNumber(row.original_other_15d_sales)} />
                <StatCard icon={Boxes} label="其他原始30天" value={formatNumber(row.original_other_30d_sales)} />
              </div>
              <div className="overflow-hidden rounded-xl border border-border bg-card">
                <div className="border-b border-border px-4 py-3 text-sm font-medium">其他平台30天店铺拆分</div>
                {row.shop_30d_sales.length > 0 ? row.shop_30d_sales.map((item) => (
                  <div key={item.shop_name} className="border-b border-border px-4 py-2.5 last:border-b-0">
                    <div className="flex items-center justify-between gap-3">
                      <span className="min-w-0 truncate text-sm text-muted-foreground">{item.shop_name || "未命名店铺"}</span>
                      <span className="text-sm font-medium tabular-nums">{formatNumber(item.quantity)}</span>
                    </div>
                    <div className="mt-2 h-1.5 overflow-hidden rounded-full bg-muted">
                      <div className="h-full rounded-full bg-foreground/75" style={{ width: `${Math.max(4, (item.quantity / maxShopQuantity) * 100)}%` }} />
                    </div>
                  </div>
                )) : (
                  <div className="px-4 py-6 text-center text-sm text-muted-foreground">暂无店铺销售</div>
                )}
              </div>
            </TabsContent>

            <TabsContent value="stock" className="space-y-4">
              <div className="grid gap-3 sm:grid-cols-2">
                <StatCard icon={Boxes} label="聚水潭库存" value={formatNumber(row.stock_qty)} tone={row.stock_qty < row.vip_7d_sales ? "warn" : "neutral"} />
                <StatCard icon={AlertTriangle} label="现有5天后预计库存(不加未到)" value={nullableInteger(projected5dStockNoInbound(row))} tone={projected5dStockNoInbound(row) < 0 ? "risk" : "good"} />
                <StatCard icon={AlertTriangle} label="15天后库存减唯品会" value={nullableInteger(vipProjected15dStock(row))} tone={vipProjected15dStock(row) < 0 ? "risk" : "good"} />
                <StatCard icon={AlertTriangle} label="15天后库存减其他平台" value={nullableInteger(otherProjected15dStock(row))} tone={otherProjected15dStock(row) < 0 ? "risk" : "good"} />
                <StatCard icon={Layers3} label="采购在途数" value={formatNumber(row.inbound_qty)} />
                <StatCard icon={Boxes} label="次品库存" value={formatNumber(row.defect_stock)} />
                <StatCard icon={Boxes} label="原始货号次品仓汇总" value={formatNumber(row.original_defect_stock ?? 0)} />
                <StatCard icon={Layers3} label="原始货号采购在途数量汇总" value={formatNumber(row.original_inbound_qty ?? 0)} />
                <StatCard icon={Layers3} label="原始货号已下订单未到数量汇总" value={formatNumber(row.original_order_in_transit_stock ?? 0)} />
                <StatCard icon={Boxes} label="原始货号打次未到数量汇总" value={formatNumber(row.original_defect_in_transit_stock ?? 0)} />
                <StatCard icon={Boxes} label="下架仓商品数量" value={formatNumber(row.off_shelf_stock)} />
                <StatCard icon={Layers3} label="已下订单未到数量" value={formatNumber(orderInTransitStock(row))} />
                <StatCard icon={Boxes} label="打次未到数量" value={formatNumber(row.defect_in_transit_stock)} />
              </div>
              <div className="rounded-xl border border-border bg-card p-4 shadow-sm">
                <p className="mb-3 text-sm font-medium">尺码库存</p>
                <div className="grid grid-cols-4 gap-2 sm:grid-cols-5">
                  {Object.entries(row.size_stock).map(([size, qty]) => (
                    <div key={size} className="rounded-lg border border-border bg-muted/45 px-3 py-2">
                      <p className="text-xs text-muted-foreground">{size}</p>
                      <p className="text-sm font-semibold tabular-nums">{formatNumber(qty)}</p>
                    </div>
                  ))}
                </div>
              </div>
            </TabsContent>
          </div>
        </Tabs>
      </div>
    </div>
  )
}

const FineTableGrid = memo(function FineTableGrid({
  error,
  filteredRows,
  isLoading,
  onPageChange,
  onPreviewImage,
  onSelectRow,
  page,
  total,
  totalPages,
  visibleColumns,
}: {
  error: string | null
  filteredRows: FineTableItem[]
  isLoading: boolean
  onPageChange: (page: number) => void
  onPreviewImage: (row: FineTableItem) => void
  onSelectRow: (row: FineTableItem) => void
  page: number
  total: number
  totalPages: number
  visibleColumns: TableColumn[]
}) {
  const hasDailyColumns = visibleColumns.some((column) => column.dailyMetricLabel)
  const tableMinWidth = Math.max(
    1500,
    500 + visibleColumns.reduce((sum, column) => sum + (column.dailyMetricLabel ? 68 : 120), 0),
  )
  const headerCells: ReactNode[] = []
  for (let index = 0; index < visibleColumns.length; index += 1) {
    const column = visibleColumns[index]
    if (column.dailyMetricLabel) {
      const dateLabel = column.dailyDateLabel ?? column.label
      let span = 1
      while (
        index + span < visibleColumns.length
        && visibleColumns[index + span].dailyMetricLabel
        && (visibleColumns[index + span].dailyDateLabel ?? visibleColumns[index + span].label) === dateLabel
      ) {
        span += 1
      }
      headerCells.push(
        <th key={`daily-${dateLabel}-${index}`} colSpan={span} className="border-b border-border px-3 py-2 text-center font-medium">
          <span className="block whitespace-nowrap">{dateLabel}</span>
        </th>,
      )
      index += span - 1
      continue
    }

    headerCells.push(
      <th
        key={column.key}
        rowSpan={hasDailyColumns ? 2 : 1}
        className={cn(
          "border-b border-border px-3 py-2.5 font-medium",
          tableAlignClass(column.align),
          column.className,
        )}
      >
        <span className="block whitespace-nowrap">{column.label}</span>
        <span className="mt-0.5 block text-[10px] font-normal text-muted-foreground">{column.group}</span>
      </th>,
    )
  }

  return (
    <div className="table-panel">
      <div className="max-h-[72svh] min-h-[360px] overflow-auto">
        <table
          className="w-full border-separate border-spacing-0 text-[13px]"
          style={{ minWidth: tableMinWidth }}
        >
          <thead className="sticky top-0 z-20 bg-card/95 backdrop-blur">
            <tr className="text-xs text-muted-foreground">
              <th rowSpan={hasDailyColumns ? 2 : 1} className="sticky left-0 z-30 w-20 border-b border-border bg-card/95 px-3 py-2.5 text-center font-medium">图片</th>
              <th rowSpan={hasDailyColumns ? 2 : 1} className="sticky left-20 z-30 w-40 border-b border-border bg-card/95 px-3 py-2.5 text-left font-medium">货号</th>
              <th rowSpan={hasDailyColumns ? 2 : 1} className="sticky left-60 z-30 w-40 border-b border-border bg-card/95 px-3 py-2.5 text-left font-medium">原始货号</th>
              {headerCells}
              <th rowSpan={hasDailyColumns ? 2 : 1} className="sticky right-0 z-30 w-20 border-b border-border bg-card px-3 py-3 text-center font-medium">详情</th>
            </tr>
            {hasDailyColumns && (
              <tr className="text-xs text-muted-foreground">
                {visibleColumns.filter((column) => column.dailyMetricLabel).map((column) => (
                  <th
                    key={column.key}
                    className={cn(
                      "border-b border-border px-3 py-2 text-center font-medium",
                      column.className,
                    )}
                  >
                    {column.dailyMetricLabel}
                  </th>
                ))}
              </tr>
            )}
          </thead>
          <tbody>
            {isLoading && (
              <tr>
                <td colSpan={visibleColumns.length + 4} className="px-4 py-16 text-center text-muted-foreground">正在加载精细表数据...</td>
              </tr>
            )}
            {!isLoading && error && (
              <tr>
                <td colSpan={visibleColumns.length + 4} className="px-4 py-16 text-center text-destructive">{error}</td>
              </tr>
            )}
            {!isLoading && !error && filteredRows.length === 0 && (
              <tr>
                <td colSpan={visibleColumns.length + 4} className="px-4 py-16 text-center text-muted-foreground">暂无匹配商品</td>
              </tr>
            )}
            {!isLoading && !error && filteredRows.map((row) => (
              <tr key={`${row.brand}-${row.id}`} className="group transition-colors hover:bg-muted/50">
                <td className="sticky left-0 z-10 border-b border-border bg-card px-3 py-2 text-center group-hover:bg-muted/40">
                  <button
                    type="button"
                    className={cn(
                      "inline-flex rounded-lg focus:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2",
                      row.image_url && "cursor-zoom-in",
                    )}
                    onClick={() => {
                      if (!row.image_url) return
                      onPreviewImage(row)
                    }}
                    disabled={!row.image_url}
                    aria-label={row.image_url ? "查看原图" : "暂无图片"}
                  >
                    <ProductThumb item={row} />
                  </button>
                </td>
                <td className="sticky left-20 z-10 border-b border-border bg-card px-3 py-2 text-left group-hover:bg-muted/40">
                  <p className="truncate font-medium">{row.sku || "-"}</p>
                </td>
                <td className="sticky left-60 z-10 border-b border-border bg-card px-3 py-2 text-left group-hover:bg-muted/40">
                  <p className="truncate text-sm">{row.original_sku || "-"}</p>
                </td>
                {visibleColumns.map((column) => (
                  <td
                    key={column.key}
                    className={cn(
                      "border-b border-border px-3 py-2 align-middle",
                      tableAlignClass(column.align),
                      column.className,
                    )}
                  >
                    {column.render(row)}
                  </td>
                ))}
                <td className="sticky right-0 z-10 border-b border-border bg-card px-3 py-2 text-center group-hover:bg-muted/40">
                  <Button variant="ghost" size="icon" onClick={() => onSelectRow(row)} aria-label="查看详情">
                    <ChevronRight className="h-4 w-4" />
                  </Button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <FineTablePagination
        page={page}
        pageSize={PAGE_SIZE}
        total={total}
        totalPages={totalPages}
        isLoading={isLoading}
        onPageChange={onPageChange}
      />
    </div>
  )
})

function formatDateInputValue(date: Date) {
  const year = date.getFullYear()
  const month = String(date.getMonth() + 1).padStart(2, "0")
  const day = String(date.getDate()).padStart(2, "0")
  return `${year}-${month}-${day}`
}

function getMaxHistoryDate() {
  const date = new Date()
  date.setDate(date.getDate() - 1)
  return formatDateInputValue(date)
}

export function FineTablePage() {
  const [brand, setBrand] = useState<FineTableBrandKey>(DEFAULT_FINE_TABLE_BRAND)
  const [items, setItems] = useState<FineTableItem[]>([])
  const [page, setPage] = useState(1)
  const [total, setTotal] = useState(0)
  const [queryInput, setQueryInput] = useState("")
  const [query, setQuery] = useState("")
  const [view, setView] = useState<ViewKey>("all")
  const [selectedRow, setSelectedRow] = useState<FineTableItem | null>(null)
  const [isLoading, setIsLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [reloadToken, setReloadToken] = useState(0)
  const [latestOrderDate, setLatestOrderDate] = useState<string | null>(null)
  const [columnMode, setColumnMode] = useState<ColumnMode>("full")
  const [customColumnPickerOpen, setCustomColumnPickerOpen] = useState(false)
  const [customColumnKeys, setCustomColumnKeys] = useState<string[]>(DEFAULT_COLUMN_KEYS)
  const [draftCustomColumnKeys, setDraftCustomColumnKeys] = useState<string[]>(DEFAULT_COLUMN_KEYS)
  const [columnSearch, setColumnSearch] = useState("")
  const [showSelectedColumnsOnly, setShowSelectedColumnsOnly] = useState(false)
  const [collapsedColumnGroups, setCollapsedColumnGroups] = useState<ColumnGroup[]>([])
  const [isExporting, setIsExporting] = useState(false)
  const [exportProgress, setExportProgress] = useState<{ loaded: number; total: number } | null>(null)
  const [previewImage, setPreviewImage] = useState<{ src: string; alt: string } | null>(null)
  const [historyDate, setHistoryDate] = useState("")
  const [snapshotLabel, setSnapshotLabel] = useState<string | null>(null)
  const loadRequestIdRef = useRef(0)
  const maxHistoryDate = getMaxHistoryDate()

  useEffect(() => {
    let cancelled = false
    const requestId = loadRequestIdRef.current + 1
    loadRequestIdRef.current = requestId
    const isCurrentRequest = () => !cancelled && loadRequestIdRef.current === requestId

    async function loadData() {
      setIsLoading(true)
      setError(null)
      try {
        const response = historyDate
          ? await getFineTableSnapshotByDate({
            brand,
            snapshotDate: historyDate,
            page,
            pageSize: PAGE_SIZE,
            query: query || undefined,
          })
          : await listFineTable({
            brand,
            page,
            pageSize: PAGE_SIZE,
            query: query || undefined,
          })
        if (!isCurrentRequest()) return
        setItems(response.items)
        setTotal(response.total)
        if ("snapshot" in response) {
          setLatestOrderDate(response.snapshot.latest_order_date)
          setSnapshotLabel(response.snapshot.snapshot_date)
        } else {
          setLatestOrderDate(response.latest_order_date)
          setSnapshotLabel(null)
        }
      } catch (loadError) {
        if (!isCurrentRequest()) return
        setItems([])
        setTotal(0)
        setLatestOrderDate(null)
        setSnapshotLabel(historyDate || null)
        setError(getErrorMessage(loadError))
      } finally {
        if (isCurrentRequest()) setIsLoading(false)
      }
    }
    void loadData()
    return () => {
      cancelled = true
    }
  }, [brand, historyDate, page, query, reloadToken])

  const deferredView = useDeferredValue(view)
  const filteredRows = useMemo(() => {
    return items.filter((row) => {
      if (deferredView === "missingImage") return !row.image_url
      if (deferredView === "stockRisk") return hasStockRisk(row)
      return true
    })
  }, [deferredView, items])

  const stats = useMemo(() => {
    const risk = items.filter(hasStockRisk).length
    const missing = items.filter((row) => !row.image_url).length
    const sales7 = items.reduce((sum, row) => sum + row.vip_7d_sales + row.other_7d_sales, 0)
    return { risk, missing, sales7 }
  }, [items])

  const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE))
  const dailyLabels = useMemo(() => {
    const sample = items.find((row) => row.daily_sales.length > 0)
    return sample ? visibleDailySales(sample).map((item) => item.date.slice(5)) : []
  }, [items])
  const tableColumns = useMemo(() => createTableColumns(dailyLabels), [dailyLabels])
  const visibleColumns = useMemo(() => {
    if (columnMode === "custom") {
      const selected = new Set(customColumnKeys)
      return tableColumns.filter((column) => selected.has(column.key))
    }
    return tableColumns
  }, [columnMode, customColumnKeys, tableColumns])
  const deferredVisibleColumns = useDeferredValue(visibleColumns)
  const isColumnViewSettling = deferredVisibleColumns !== visibleColumns
  const draftCustomColumnKeySet = useMemo(() => new Set(draftCustomColumnKeys), [draftCustomColumnKeys])
  const collapsedColumnGroupSet = useMemo(() => new Set(collapsedColumnGroups), [collapsedColumnGroups])
  const groupedColumns = useMemo(() => {
    return tableColumns.reduce<Record<ColumnGroup, TableColumn[]>>((acc, column) => {
      acc[column.group] = [...(acc[column.group] ?? []), column]
      return acc
    }, {} as Record<ColumnGroup, TableColumn[]>)
  }, [tableColumns])
  const columnSearchTerm = columnSearch.trim().toLowerCase()
  const visibleGroupedColumns = useMemo(() => {
    return (Object.keys(groupedColumns) as ColumnGroup[]).reduce<Record<ColumnGroup, TableColumn[]>>((acc, group) => {
      const columns = groupedColumns[group] ?? []
      acc[group] = columns.filter((column) => {
        if (showSelectedColumnsOnly && !draftCustomColumnKeySet.has(column.key)) return false
        if (!columnSearchTerm) return true
        return column.label.toLowerCase().includes(columnSearchTerm) || column.key.toLowerCase().includes(columnSearchTerm)
      })
      return acc
    }, {} as Record<ColumnGroup, TableColumn[]>)
  }, [columnSearchTerm, draftCustomColumnKeySet, groupedColumns, showSelectedColumnsOnly])
  const currentBrandLabel = useMemo(() => {
    return FINE_TABLE_BRANDS.find((item) => item.key === brand)?.label ?? "商品"
  }, [brand])

  function openCustomColumnPicker() {
    setDraftCustomColumnKeys(customColumnKeys)
    setColumnSearch("")
    setShowSelectedColumnsOnly(false)
    setCustomColumnPickerOpen(true)
  }

  function toggleDraftCustomColumn(key: string) {
    setDraftCustomColumnKeys((current) => (
      current.includes(key)
        ? current.filter((item) => item !== key)
        : [...current, key]
    ))
  }

  function setDraftCustomColumnGroup(group: ColumnGroup, selected: boolean) {
    const groupKeys = groupedColumns[group]?.map((column) => column.key) ?? []
    const groupKeySet = new Set(groupKeys)
    setDraftCustomColumnKeys((current) => {
      if (selected) {
        return Array.from(new Set([...current, ...groupKeys]))
      }
      return current.filter((key) => !groupKeySet.has(key))
    })
  }

  function selectAllDraftCustomColumns() {
    setDraftCustomColumnKeys(tableColumns.map((column) => column.key))
  }

  function resetDraftCustomColumns() {
    setDraftCustomColumnKeys(DEFAULT_COLUMN_KEYS)
  }

  function clearDraftCustomColumns() {
    setDraftCustomColumnKeys([])
  }

  function applyCustomColumns() {
    setCustomColumnKeys(draftCustomColumnKeys)
    setCustomColumnPickerOpen(false)
  }

  function toggleColumnGroupCollapsed(group: ColumnGroup) {
    setCollapsedColumnGroups((current) => (
      current.includes(group)
        ? current.filter((item) => item !== group)
        : [...current, group]
    ))
  }

  function handleBrandChange(nextBrand: FineTableBrandKey) {
    if (nextBrand === brand) return
    loadRequestIdRef.current += 1
    setBrand(nextBrand)
    setPage(1)
    setItems([])
    setTotal(0)
    setLatestOrderDate(null)
    setError(null)
    setIsLoading(true)
    setSelectedRow(null)
    setPreviewImage(null)
    setSnapshotLabel(historyDate || null)
  }

  function clearHistoryDate() {
    if (!historyDate) return
    setHistoryDate("")
    setSnapshotLabel(null)
    setPage(1)
    setItems([])
    setTotal(0)
    setError(null)
  }

  function handleHistoryDateChange(nextDate: string) {
    if (nextDate && nextDate > maxHistoryDate) {
      setHistoryDate("")
      setSnapshotLabel(null)
      setPage(1)
      setItems([])
      setTotal(0)
      setError("历史日期只能选择今天以前")
      return
    }
    setHistoryDate(nextDate)
    setPage(1)
    setItems([])
    setTotal(0)
    setError(null)
  }

  async function handleExport() {
    setIsExporting(true)
    setExportProgress({ loaded: 0, total })
    try {
      const loadExportPage = (pageToLoad: number) => (
        historyDate
          ? getFineTableSnapshotByDate({
            brand,
            snapshotDate: historyDate,
            page: pageToLoad,
            pageSize: EXPORT_PAGE_SIZE,
            query: query || undefined,
          })
          : listFineTable({
            brand,
            page: pageToLoad,
            pageSize: EXPORT_PAGE_SIZE,
            query: query || undefined,
          })
      )
      const firstResponse = await loadExportPage(1)
      const expectedTotal = firstResponse.total
      const pageCount = Math.max(1, Math.ceil(expectedTotal / EXPORT_PAGE_SIZE))
      const rowsByPage = new Map<number, FineTableItem[]>([[1, firstResponse.items]])
      setExportProgress({ loaded: firstResponse.items.length, total: expectedTotal })

      const remainingPages = Array.from({ length: pageCount - 1 }, (_, index) => index + 2)
      let nextPageIndex = 0
      let loadedCount = firstResponse.items.length

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
        Array.from({ length: Math.min(EXPORT_CONCURRENCY, remainingPages.length) }, () => exportWorker()),
      )

      const allRows = Array.from({ length: pageCount }, (_, index) => rowsByPage.get(index + 1) ?? []).flat()

      const rowsForExport = allRows.filter((row) => {
        if (view === "missingImage") return !row.image_url
        if (view === "stockRisk") return hasStockRisk(row)
        return true
      })
      const csvRows = buildFineTableCsvRows(rowsForExport, visibleColumns)
      const brandLabel = FINE_TABLE_BRANDS.find((item) => item.key === brand)?.label ?? "商品"
      downloadCsv(`${brandLabel}_商品精细表_${timestampForFilename(new Date())}.csv`, csvRows)
    } catch (exportError) {
      window.alert(getErrorMessage(exportError))
    } finally {
      setIsExporting(false)
      setExportProgress(null)
    }
  }

  return (
    <div className="app-page">
      <div className="app-content-wide">
        <div className="page-header">
          <div className="flex w-full flex-wrap items-start justify-between gap-3">
            <div>
              <h1 className="page-title">商品精细表</h1>
              <p className="page-subtitle">
                {currentBrandLabel}{latestOrderDate ? ` · 订单截止 ${latestOrderDate}` : ""}
              </p>
              {snapshotLabel && (
                <p className="mt-1 text-xs text-muted-foreground">历史快照 {snapshotLabel}</p>
              )}
              <Tabs
                value={brand}
                defaultValue={DEFAULT_FINE_TABLE_BRAND}
                onValueChange={(value) => {
                  handleBrandChange(value as FineTableBrandKey)
                }}
                className="mt-3"
              >
                <TabsList className="h-auto w-full flex-wrap justify-start gap-1 bg-transparent p-0">
                  {FINE_TABLE_BRANDS.map((item) => (
                    <TabsTrigger
                      key={item.key}
                      value={item.key}
                      className="cursor-pointer rounded-lg border border-transparent bg-muted/45 px-3 py-1.5 text-xs font-medium text-muted-foreground transition-all duration-150 hover:bg-muted hover:text-foreground data-[state=active]:border-border data-[state=active]:bg-background data-[state=active]:text-foreground data-[state=active]:shadow-sm"
                    >
                      {item.label}
                    </TabsTrigger>
                  ))}
                </TabsList>
              </Tabs>
              <div className="mt-3 flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
                <span className="inline-flex h-7 items-center rounded-full border border-border bg-muted/40 px-3">当前 {formatNumber(total)} 条</span>
                <span className="inline-flex h-7 items-center rounded-full border border-border bg-muted/40 px-3">显示 {formatNumber(visibleColumns.length)} 列</span>
                <span className="inline-flex h-7 items-center rounded-full border border-border bg-muted/40 px-3">视图 {columnMode === "full" ? "完整" : "自定义"}</span>
              </div>
            </div>
            <div className="flex flex-wrap items-center gap-2">
              <div
                className={cn(
                  "inline-flex h-8 items-center gap-0.5 rounded-lg border p-0.5 shadow-sm transition-colors",
                  historyDate ? "border-primary/30 bg-primary/5" : "border-border bg-card",
                )}
                role="group"
                aria-label="数据日期"
              >
                <button
                  type="button"
                  aria-pressed={!historyDate}
                  onClick={clearHistoryDate}
                  className={cn(
                    "inline-flex h-7 cursor-pointer items-center gap-1.5 rounded-md px-2.5 text-xs font-semibold transition-colors",
                    !historyDate
                      ? "bg-primary text-primary-foreground shadow-sm"
                      : "text-muted-foreground hover:bg-background hover:text-foreground",
                  )}
                >
                  <Check className="h-3.5 w-3.5" />
                  当前
                </button>
                <label
                  className={cn(
                    "relative inline-flex h-7 min-w-[9.5rem] cursor-pointer items-center gap-1.5 rounded-md border px-2.5 text-xs font-semibold transition-colors",
                    historyDate
                      ? "border-primary/35 bg-background text-foreground shadow-sm"
                      : "border-transparent text-muted-foreground hover:bg-muted/50 hover:text-foreground",
                  )}
                >
                  <History className={cn("h-3.5 w-3.5", historyDate && "text-primary")} />
                  <span>历史</span>
                  <span className={cn("tabular-nums", historyDate ? "text-foreground" : "text-muted-foreground")}>
                    {historyDate || "选择日期"}
                  </span>
                  <CalendarDays className="ml-auto h-3.5 w-3.5 text-muted-foreground" />
                  <input
                    type="date"
                    value={historyDate}
                    max={maxHistoryDate}
                    onChange={(event) => handleHistoryDateChange(event.target.value)}
                    className="absolute inset-0 h-full w-full cursor-pointer opacity-0"
                    aria-label="选择历史快照日期"
                  />
                </label>
              </div>
              <Button variant="outline" className="h-8 px-3 text-xs font-semibold" onClick={() => setReloadToken((current) => current + 1)}>
                <RefreshCw className="h-4 w-4" />
                刷新
              </Button>
              <Button variant="outline" className="h-8 px-3 text-xs font-semibold" onClick={handleExport} disabled={isExporting || isLoading}>
                <Download className="h-4 w-4" />
                {isExporting && exportProgress
                  ? `导出 ${formatNumber(Math.min(exportProgress.loaded, exportProgress.total))}/${formatNumber(exportProgress.total)}`
                  : "导出"}
              </Button>
            </div>
          </div>
        </div>

        <div className="grid gap-3 md:grid-cols-4">
          <StatCard icon={Boxes} label="当前页商品" value={formatNumber(items.length)} />
          <StatCard icon={AlertTriangle} label="当前页缺货风险" value={formatNumber(stats.risk)} tone="risk" />
          <StatCard icon={TrendingUp} label="当前页7天销量" value={formatNumber(stats.sales7)} tone="good" />
          <StatCard icon={ImageIcon} label="当前页暂无图片" value={formatNumber(stats.missing)} tone={stats.missing > 0 ? "warn" : "neutral"} />
        </div>

        <div className="surface-panel p-4">
          <div className="flex flex-col gap-3">
            <form
              className="flex flex-wrap items-start gap-2"
              onSubmit={(event) => {
                event.preventDefault()
                setPage(1)
                setQuery(queryInput.trim())
              }}
            >
              <div className="relative min-w-72 flex-1">
                <Search className="pointer-events-none absolute left-3 top-3 h-4 w-4 text-muted-foreground" />
                <textarea
                  value={queryInput}
                  onChange={(event) => setQueryInput(event.target.value)}
                  aria-label="搜索货号、原始货号"
                  placeholder="搜索货号、原始货号；每行一个，也可用逗号分隔"
                  rows={3}
                  className="flex min-h-20 w-full resize-y rounded-md border border-input bg-transparent px-3 py-2 pl-9 text-sm shadow-sm transition-colors placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring disabled:cursor-not-allowed disabled:opacity-50"
                />
              </div>
              <div className="flex items-center gap-2">
                <Button type="submit">
                  查询
                </Button>
                {queryInput && (
                  <Button
                    type="button"
                    variant="outline"
                    onClick={() => {
                      setQueryInput("")
                      setQuery("")
                      setPage(1)
                    }}
                  >
                    清空
                  </Button>
                )}
              </div>
            </form>

          </div>
        </div>

        <div className="surface-panel p-4">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div className="flex items-center gap-2" role="group" aria-label="列视图">
              <span className="text-sm font-medium">列视图</span>
              {[
                ["full", "完整视图"],
                ["custom", "自定义"],
              ].map(([value, label]) => (
                <button
                  key={value}
                  type="button"
                  aria-pressed={columnMode === value}
                  onClick={() => {
                    setColumnMode(value as ColumnMode)
                    if (value === "custom") {
                      openCustomColumnPicker()
                    } else {
                      setCustomColumnPickerOpen(false)
                    }
                  }}
                  className={cn(
                    "h-9 cursor-pointer rounded-full px-4 text-sm font-medium transition-colors",
                    columnMode === value ? "bg-primary text-primary-foreground" : "bg-muted text-muted-foreground hover:bg-muted/70 hover:text-foreground",
                  )}
                >
                  {label}
                </button>
              ))}
            </div>
            <div className="flex items-center gap-2">
              <p className="text-sm text-muted-foreground">
                显示 {visibleColumns.length} 列{isColumnViewSettling ? " · 更新中" : ""}
              </p>
              {columnMode === "custom" && (
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  onClick={openCustomColumnPicker}
                >
                  <SlidersHorizontal className="h-4 w-4" />
                  配置列
                </Button>
              )}
            </div>
          </div>
        </div>

        <Tabs value={view} defaultValue="all" onValueChange={(value) => setView(value as ViewKey)}>
          <div className="flex items-center justify-between gap-3">
            <TabsList className="rounded-xl bg-muted/50 p-1">
              {viewTabs.map((tab) => (
                <TabsTrigger key={tab.value} className="rounded-lg px-4 text-sm" value={tab.value}>{tab.label}</TabsTrigger>
              ))}
            </TabsList>
            <p className="text-sm text-muted-foreground">
              {formatNumber(filteredRows.length)} / {formatNumber(total)} 条
            </p>
          </div>

          <TabsContent value={view} className="mt-0">
            <FineTableGrid
              error={error}
              filteredRows={filteredRows}
              isLoading={isLoading}
              onPageChange={setPage}
              onPreviewImage={(row) => {
                if (!row.image_url) return
                setPreviewImage({
                  src: `/api${row.image_url}`,
                  alt: row.sku || row.original_sku || "商品图片",
                })
              }}
              onSelectRow={setSelectedRow}
              page={page}
              total={total}
              totalPages={totalPages}
              visibleColumns={deferredVisibleColumns}
            />
          </TabsContent>
        </Tabs>
      </div>
      <Dialog open={customColumnPickerOpen} onOpenChange={(open) => !open && setCustomColumnPickerOpen(false)}>
        <DialogContent className="flex max-h-[88svh] max-w-[min(96vw,1120px)] flex-col overflow-hidden p-0">
          <DialogHeader className="border-b border-border px-4 py-3 sm:px-5">
            <div className="flex flex-wrap items-start justify-between gap-3">
              <div>
                <DialogTitle className="text-base font-semibold">自定义列</DialogTitle>
                <p className="mt-1 text-xs text-muted-foreground">
                  已选择 <span className="font-semibold text-foreground">{draftCustomColumnKeys.length}</span> / {tableColumns.length} 列
                </p>
              </div>
              <div className="flex flex-wrap items-center gap-1.5">
                <Button type="button" variant="outline" size="sm" className="h-8" onClick={selectAllDraftCustomColumns}>
                  全选
                </Button>
                <Button type="button" variant="outline" size="sm" className="h-8" onClick={resetDraftCustomColumns}>
                  默认
                </Button>
                <Button type="button" variant="outline" size="sm" className="h-8" onClick={clearDraftCustomColumns}>
                  清空
                </Button>
              </div>
            </div>
            <div className="mt-3 h-1.5 overflow-hidden rounded-full bg-muted">
              <div
                className="h-full rounded-full bg-primary transition-all"
                style={{ width: `${tableColumns.length === 0 ? 0 : (draftCustomColumnKeys.length / tableColumns.length) * 100}%` }}
              />
            </div>
          </DialogHeader>

          <div className="border-b border-border bg-muted/20 px-4 py-3 sm:px-5">
            <div className="flex flex-col gap-2 md:flex-row md:items-center">
              <div className="relative min-w-0 flex-1">
                <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
                <Input
                  value={columnSearch}
                  onChange={(event) => setColumnSearch(event.target.value)}
                  placeholder="搜索列名"
                  aria-label="搜索列名"
                  className="h-9 pl-9"
                />
              </div>
              <button
                type="button"
                aria-pressed={showSelectedColumnsOnly}
                onClick={() => setShowSelectedColumnsOnly((current) => !current)}
                className={cn(
                  "inline-flex h-9 shrink-0 cursor-pointer items-center justify-center rounded-md border px-3 text-sm font-medium transition-colors",
                  showSelectedColumnsOnly
                    ? "border-primary/30 bg-primary/10 text-primary"
                    : "border-border bg-background text-muted-foreground hover:text-foreground",
                )}
              >
                只看已选
              </button>
            </div>
          </div>

          <div className="min-h-0 flex-1 overflow-y-auto px-4 py-3 sm:px-5">
            <div className="grid gap-2 md:grid-cols-2 xl:grid-cols-3">
              {(Object.keys(groupedColumns) as ColumnGroup[]).map((group) => {
                const columns = groupedColumns[group] ?? []
                const visibleGroupColumns = visibleGroupedColumns[group] ?? []
                const selectedCount = columns.filter((column) => draftCustomColumnKeySet.has(column.key)).length
                const allSelected = selectedCount === columns.length
                const partiallySelected = selectedCount > 0 && !allSelected
                const selectedPercent = columns.length === 0 ? 0 : (selectedCount / columns.length) * 100
                const isCollapsed = collapsedColumnGroupSet.has(group) && !columnSearchTerm
                if (visibleGroupColumns.length === 0) return null

                return (
                  <section
                    key={group}
                    className={cn(
                      "min-h-0 rounded-lg border bg-background transition-colors",
                      selectedCount > 0 ? "border-primary/25" : "border-border",
                    )}
                  >
                    <div className="border-b border-border/70 p-3">
                      <div className="flex items-start justify-between gap-2">
                        <button
                          type="button"
                          className="min-w-0 flex-1 text-left"
                          onClick={() => toggleColumnGroupCollapsed(group)}
                          aria-expanded={!isCollapsed}
                        >
                          <div className="flex min-w-0 items-center gap-2">
                            <ChevronDown className={cn("h-4 w-4 shrink-0 text-muted-foreground transition-transform", isCollapsed && "-rotate-90")} />
                            <span className="truncate text-sm font-medium text-foreground">{group}</span>
                            <span
                              className={cn(
                                "shrink-0 rounded-full px-2 py-0.5 text-[11px] font-medium",
                                allSelected
                                  ? "bg-primary text-primary-foreground"
                                  : partiallySelected
                                    ? "bg-primary/10 text-primary"
                                    : "bg-muted text-muted-foreground",
                              )}
                            >
                              {selectedCount}/{columns.length}
                            </span>
                          </div>
                          <div className="mt-2 h-1 overflow-hidden rounded-full bg-muted">
                            <div className="h-full rounded-full bg-primary/70 transition-all" style={{ width: `${selectedPercent}%` }} />
                          </div>
                        </button>
                        <div className="flex shrink-0 items-center gap-1">
                          <button
                            type="button"
                            className="h-7 rounded-md px-2.5 text-[11px] font-medium text-muted-foreground hover:bg-muted hover:text-foreground"
                            onClick={() => setDraftCustomColumnGroup(group, true)}
                            aria-label={`${group} 全选`}
                          >
                            全选
                          </button>
                          <button
                            type="button"
                            className="h-7 rounded-md px-2.5 text-[11px] font-medium text-muted-foreground hover:bg-muted hover:text-foreground"
                            onClick={() => setDraftCustomColumnGroup(group, false)}
                            aria-label={`${group} 清空`}
                          >
                            清空
                          </button>
                        </div>
                      </div>
                    </div>
                    {!isCollapsed && (
                      <div className="grid max-h-64 gap-1 overflow-y-auto p-2 sm:grid-cols-2">
                        {visibleGroupColumns.map((column) => {
                          const checked = draftCustomColumnKeySet.has(column.key)
                          return (
                            <label
                              key={column.key}
                              className={cn(
                                "group flex h-8 cursor-pointer items-center gap-2 rounded-md border px-2 text-xs transition-colors",
                                checked
                                  ? "border-primary/30 bg-primary/10 text-foreground"
                                  : "border-transparent bg-background text-muted-foreground hover:border-border hover:bg-muted/40 hover:text-foreground",
                              )}
                            >
                              <input
                                type="checkbox"
                                checked={checked}
                                onChange={() => toggleDraftCustomColumn(column.key)}
                                className="peer sr-only"
                              />
                              <span
                                aria-hidden="true"
                                className={cn(
                                  "flex h-4 w-4 shrink-0 items-center justify-center rounded border transition-colors",
                                  checked
                                    ? "border-primary bg-primary text-primary-foreground"
                                    : "border-border bg-background group-hover:border-primary/50",
                                )}
                              >
                                {checked && <Check className="h-3 w-3" />}
                              </span>
                              <span className="min-w-0 truncate">{column.label}</span>
                            </label>
                          )
                        })}
                      </div>
                    )}
                  </section>
                )
              })}
            </div>
            {Object.values(visibleGroupedColumns).every((columns) => columns.length === 0) && (
              <div className="flex h-32 items-center justify-center rounded-lg border border-dashed border-border text-sm text-muted-foreground">
                没有匹配的列
              </div>
            )}
          </div>

          <div className="flex flex-wrap items-center justify-between gap-3 border-t border-border bg-background px-4 py-3 sm:px-5">
            <p className="text-xs text-muted-foreground">
              当前表格仍显示 {formatNumber(customColumnKeys.length)} 列，完成后更新为 {formatNumber(draftCustomColumnKeys.length)} 列
            </p>
            <div className="flex items-center gap-2">
              <Button type="button" variant="outline" size="sm" onClick={() => setCustomColumnPickerOpen(false)}>
                取消
              </Button>
              <Button type="button" size="sm" onClick={applyCustomColumns}>
                完成
              </Button>
            </div>
          </div>
        </DialogContent>
      </Dialog>
      {selectedRow && <div aria-hidden="true" className="fixed inset-0 z-40 bg-black/20" onClick={() => setSelectedRow(null)} />}
      <DetailDrawer row={selectedRow} onClose={() => setSelectedRow(null)} />
      <Dialog open={previewImage !== null} onOpenChange={(open) => !open && setPreviewImage(null)}>
        <DialogContent className="max-h-[92svh] max-w-[min(94vw,1120px)] overflow-hidden bg-background p-0 shadow-2xl">
          <DialogHeader className="flex flex-row items-center justify-between gap-4 border-b border-border px-4 py-3 sm:px-5">
            <DialogTitle className="text-base font-semibold">原图预览</DialogTitle>
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
          {previewImage ? (
            <div className="flex h-[min(78svh,760px)] items-center justify-center bg-muted/20 p-4 sm:p-6">
              {/* eslint-disable-next-line @next/next/no-img-element */}
              <img
                src={previewImage.src}
                alt={previewImage.alt}
                className="max-h-full w-auto max-w-full rounded-md object-contain shadow-sm"
              />
            </div>
          ) : null}
        </DialogContent>
      </Dialog>
    </div>
  )
}
