"use client"

import { memo, useDeferredValue, useEffect, useMemo, useState, type ReactNode } from "react"
import {
  AlertTriangle,
  BarChart3,
  Boxes,
  ChevronDown,
  ChevronLeft,
  ChevronRight,
  ChevronsLeft,
  ChevronsRight,
  Download,
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
import { Input } from "@/components/ui/input"
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs"
import { ApiError, listFineTable } from "@/lib/api"
import type { FineTableItem, ProductListItem } from "@/lib/types"
import { cn } from "@/lib/utils"

const PAGE_SIZE = 80

type ViewKey = "all" | "missingImage"
type ColumnMode = "default" | "full" | "custom"
type ColumnGroup = "基础" | "价格" | "销售" | "库存" | "每日" | "尺码"
type PageToken = number | "start-ellipsis" | "end-ellipsis"
type TableColumn = {
  key: string
  label: string
  group: ColumnGroup
  align?: "left" | "right" | "center"
  className?: string
  defaultVisible?: boolean
  render: (row: FineTableItem) => ReactNode
}

const viewTabs: { value: ViewKey; label: string }[] = [
  { value: "all", label: "全部" },
  { value: "missingImage", label: "暂无图片" },
]

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
  "season",
  "cost",
  "final_price",
  "activity_profit",
  "margin_rate",
  "vip_7d_sales",
  "vip_daily_average_sales",
  "other_7d_sales",
  "total_30d_sales",
  "stock_qty",
  "inbound_qty",
  "projected_15d_stock",
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

function formatDecimal1(value: number) {
  return Number.isFinite(value) ? value.toFixed(1) : "-"
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
  return value == null ? "-" : `¥${Math.round(value)}`
}

function nullablePercent(value: number | null | undefined) {
  return value == null ? "-" : formatPercent(value)
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
  if (row.projected_15d_stock < 0) {
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
  const dailyColumns: TableColumn[] = dailyLabels.map((label, index) => ({
    key: `daily_sales_${index}`,
    label,
    group: "每日",
    align: "right",
    render: (row) => formatNumber(row.daily_sales[index]?.quantity ?? 0),
  }))

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
      label: "状态",
      group: "基础",
      defaultVisible: true,
      render: (row) => <StatusBadge row={row} />,
    },
    {
      key: "season",
      label: "季节",
      group: "基础",
      defaultVisible: true,
      render: (row) => (
        <div>
          <div className="text-sm">{row.season_category || "-"}</div>
          <div className="text-xs text-muted-foreground">{row.year || "-"}</div>
        </div>
      ),
    },
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

    { key: "cost", label: "成本", group: "价格", align: "right", defaultVisible: true, render: (row) => nullableCurrency(row.latest_purchase_price) },
    { key: "final_price", label: "到手价", group: "价格", align: "right", defaultVisible: true, render: (row) => nullableCurrency(row.final_price) },
    { key: "vip_price", label: "唯品价", group: "价格", align: "right", render: (row) => nullableCurrency(row.vip_price) },
    { key: "market_price", label: "市场价", group: "价格", align: "right", render: (row) => nullableCurrency(row.market_price) },
    { key: "price_band", label: "价格段", group: "价格", render: (row) => row.price_band || "-" },
    { key: "activity_profit", label: "活动毛利", group: "价格", align: "right", defaultVisible: true, render: (row) => nullableInteger(row.activity_profit) },
    {
      key: "margin_rate",
      label: "毛利率",
      group: "价格",
      align: "right",
      defaultVisible: true,
      render: (row) => (
        <span className={cn((row.margin_rate ?? 1) < 0.1 ? "text-rose-600" : "text-emerald-600")}>
          {nullableDecimal2(row.margin_rate)}
        </span>
      ),
    },
    { key: "discount_rate", label: "折扣率", group: "价格", align: "right", render: (row) => nullablePercent(row.discount_rate) },

    { key: "vip_1d_sales", label: "唯品1天", group: "销售", align: "right", render: (row) => formatNumber(row.vip_1d_sales) },
    { key: "vip_3d_sales", label: "唯品3天", group: "销售", align: "right", render: (row) => formatNumber(row.vip_3d_sales) },
    { key: "vip_7d_sales", label: "唯品7天", group: "销售", align: "right", defaultVisible: true, render: (row) => formatNumber(row.vip_7d_sales) },
    { key: "vip_15d_sales", label: "唯品15天", group: "销售", align: "right", render: (row) => formatNumber(row.vip_15d_sales) },
    { key: "vip_30d_sales", label: "唯品30天", group: "销售", align: "right", render: (row) => formatNumber(row.vip_30d_sales) },
    { key: "vip_daily_average_sales", label: "唯品日均", group: "销售", align: "right", defaultVisible: true, render: (row) => formatDecimal1(row.vip_daily_average_sales) },
    { key: "other_3d_sales", label: "其他3天", group: "销售", align: "right", render: (row) => formatNumber(row.other_3d_sales) },
    { key: "other_7d_sales", label: "其他7天", group: "销售", align: "right", defaultVisible: true, render: (row) => formatNumber(row.other_7d_sales) },
    { key: "other_15d_sales", label: "其他15天", group: "销售", align: "right", render: (row) => formatNumber(row.other_15d_sales) },
    { key: "other_30d_sales", label: "其他30天", group: "销售", align: "right", render: (row) => formatNumber(row.other_30d_sales) },
    { key: "total_30d_sales", label: "30天总销", group: "销售", align: "right", defaultVisible: true, render: (row) => formatNumber(row.vip_30d_sales + row.other_30d_sales) },
    { key: "vip_3d_uv", label: "3天UV", group: "销售", align: "right", render: (row) => formatNumber(row.vip_3d_uv) },
    { key: "vip_7d_uv", label: "7天UV", group: "销售", align: "right", render: (row) => formatNumber(row.vip_7d_uv) },
    { key: "vip_30d_uv", label: "30天UV", group: "销售", align: "right", render: (row) => formatNumber(row.vip_30d_uv) },
    { key: "vip_3d_ctr", label: "3天CTR", group: "销售", align: "right", render: (row) => row.vip_3d_ctr || "-" },
    { key: "vip_7d_ctr", label: "7天CTR", group: "销售", align: "right", render: (row) => row.vip_7d_ctr || "-" },
    { key: "vip_30d_ctr", label: "30天CTR", group: "销售", align: "right", render: (row) => row.vip_30d_ctr || "-" },
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

    { key: "stock_qty", label: "库存", group: "库存", align: "right", defaultVisible: true, render: (row) => formatNumber(row.stock_qty) },
    { key: "inbound_qty", label: "采购在途数", group: "库存", align: "right", defaultVisible: true, render: (row) => formatNumber(row.inbound_qty) },
    { key: "defect_stock", label: "次品库存", group: "库存", align: "right", defaultVisible: true, render: (row) => formatNumber(row.defect_stock) },
    { key: "off_shelf_stock", label: "下架仓", group: "库存", align: "right", render: (row) => formatNumber(row.off_shelf_stock) },
    { key: "order_occupy_stock", label: "订单占有", group: "库存", align: "right", render: (row) => formatNumber(row.order_occupy_stock) },
    { key: "purchase_diff", label: "采购差异", group: "库存", align: "right", render: (row) => formatNumber(row.purchase_diff) },
    {
      key: "projected_15d_stock",
      label: "15天后",
      group: "库存",
      align: "right",
      defaultVisible: true,
      render: (row) => (
        <span className={cn(row.projected_15d_stock < 0 && "text-rose-600")}>
          {formatNumber(row.projected_15d_stock)}
        </span>
      ),
    },
    { key: "risk", label: "风险", group: "库存", defaultVisible: true, render: (row) => <RiskBadge row={row} /> },
    ...dailyColumns,
    ...sizeColumns,
  ]
}

function ProductThumb({ item }: { item: ProductListItem }) {
  const src = item.image_url ? `/api${item.image_url}` : null
  return (
    <div className="flex h-13 w-13 shrink-0 items-center justify-center overflow-hidden rounded-md ">
      {src ? (
        // eslint-disable-next-line @next/next/no-img-element
        <img src={src} alt={item.sku || item.original_sku || "商品图片"} className="h-full w-full object-contain" />
      ) : (
        <ImageIcon className="h-6 w-6 text-muted-foreground" />
      )}
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
    <div className="rounded-lg border border-border bg-card px-4 py-3 shadow-sm">
      <div className="flex items-center justify-between gap-3">
        <div>
          <p className="text-xs text-muted-foreground">{label}</p>
          <p className="mt-1 text-xl font-semibold tracking-normal">{value}</p>
        </div>
        <div
          className={cn(
            "flex h-9 w-9 items-center justify-center rounded-md",
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
  if (!row) return null
  const dailyValues = row.daily_sales.map((item) => item.quantity)
  const dailyTotal = dailyValues.reduce((sum, value) => sum + value, 0)
  const marketReference = row.latest_purchase_price == null ? null : Math.round((row.latest_purchase_price + 10) * 1.13 * 11)

  return (
    <div className="fixed inset-y-0 right-0 z-50 w-full max-w-xl border-l border-border bg-background shadow-2xl">
      <div className="flex h-full flex-col">
        <div className="flex items-start justify-between border-b border-border px-5 py-4">
          <div className="flex min-w-0 gap-3">
            <ProductThumb item={row} />
            <div className="min-w-0">
              <div className="flex flex-wrap items-center gap-2">
                <h2 className="truncate text-lg font-semibold">{row.sku || row.original_sku || "未命名商品"}</h2>
                <StatusBadge row={row} />
              </div>
              <p className="mt-1 text-sm text-muted-foreground">{row.original_sku || row.sku} · {row.year || "未分季节"}</p>
            </div>
          </div>
          <Button variant="ghost" size="icon" onClick={onClose} aria-label="关闭详情">
            <X className="h-4 w-4" />
          </Button>
        </div>

        <Tabs defaultValue="base" className="min-h-0 flex-1">
          <div className="border-b border-border px-5 py-3">
            <TabsList className="h-9 rounded-lg">
              <TabsTrigger value="base">基础</TabsTrigger>
              <TabsTrigger value="price">价格</TabsTrigger>
              <TabsTrigger value="sales">销售</TabsTrigger>
              <TabsTrigger value="stock">库存</TabsTrigger>
            </TabsList>
          </div>

          <div className="min-h-0 flex-1 overflow-y-auto px-5 py-5">
            <TabsContent value="base" className="space-y-4">
              <div className="grid grid-cols-2 gap-3">
                {[
                  ["商品ID", row.goods_id],
                  ["P-SPU", row.p_spu],
                  ["款号", row.style_code],
                  ["工厂货号", row.factory_sku],
                  ["组别", row.group_name],
                  ["三级分类", row.category_l3 || row.product_model],
                  ["季节分类", row.season_category],
                  ["首单日期", row.first_order_time],
                  ["鞋面材质", row.upper_material],
                  ["内里材质", row.lining_material],
                  ["大底材质", row.outsole_material],
                  ["鞋垫材质", row.insole_material],
                ].map(([label, value]) => (
                  <div key={label} className="rounded-lg border border-border bg-card p-3">
                    <p className="text-xs text-muted-foreground">{label}</p>
                    <p className="mt-1 break-words text-sm font-medium">{value || "-"}</p>
                  </div>
                ))}
              </div>
            </TabsContent>

            <TabsContent value="price" className="space-y-4">
              <div className="grid grid-cols-2 gap-3">
                <StatCard icon={SlidersHorizontal} label="今日到手价" value={nullableCurrency(row.final_price)} tone="good" />
                <StatCard icon={Layers3} label="价格段" value={row.price_band || "-"} />
                <StatCard icon={BarChart3} label="活动毛利" value={nullableInteger(row.activity_profit)} tone={(row.margin_rate ?? 1) < 0.12 ? "warn" : "good"} />
                <StatCard icon={BarChart3} label="毛利率" value={nullableDecimal2(row.margin_rate)} tone={(row.margin_rate ?? 1) < 0.12 ? "warn" : "good"} />
                <StatCard icon={TrendingUp} label="市场折扣率" value={nullablePercent(row.discount_rate)} />
              </div>
              <div className="rounded-lg border border-border">
                {[
                  ["成本", nullableCurrency(row.latest_purchase_price)],
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
            </TabsContent>

            <TabsContent value="sales" className="space-y-4">
              <div className="rounded-lg border border-border p-4">
                <div className="mb-3 flex items-center justify-between">
                  <p className="text-sm font-medium">近15天销售</p>
                  <span className="text-xs text-muted-foreground">合计 {formatNumber(dailyTotal)}</span>
                </div>
                <TrendBars values={dailyValues} />
              </div>
              <div className="grid grid-cols-3 gap-3">
                <StatCard icon={TrendingUp} label="唯品3天" value={formatNumber(row.vip_3d_sales)} />
                <StatCard icon={TrendingUp} label="唯品7天" value={formatNumber(row.vip_7d_sales)} />
                <StatCard icon={TrendingUp} label="唯品30天" value={formatNumber(row.vip_30d_sales)} />
                <StatCard icon={Boxes} label="其他3天" value={formatNumber(row.other_3d_sales)} />
                <StatCard icon={Boxes} label="其他7天" value={formatNumber(row.other_7d_sales)} />
                <StatCard icon={Boxes} label="其他30天" value={formatNumber(row.other_30d_sales)} />
              </div>
              <div className="rounded-lg border border-border">
                <div className="border-b border-border px-4 py-3 text-sm font-medium">其他平台30天店铺拆分</div>
                {row.shop_30d_sales.length > 0 ? row.shop_30d_sales.map((item) => (
                  <div key={item.shop_name} className="flex items-center justify-between border-b border-border px-4 py-2.5 last:border-b-0">
                    <span className="min-w-0 truncate text-sm text-muted-foreground">{item.shop_name || "未命名店铺"}</span>
                    <span className="ml-4 text-sm font-medium">{formatNumber(item.quantity)}</span>
                  </div>
                )) : (
                  <div className="px-4 py-6 text-center text-sm text-muted-foreground">暂无店铺销售</div>
                )}
              </div>
            </TabsContent>

            <TabsContent value="stock" className="space-y-4">
              <div className="grid grid-cols-2 gap-3">
                <StatCard icon={Boxes} label="聚水潭库存" value={formatNumber(row.stock_qty)} tone={row.stock_qty < row.vip_7d_sales ? "warn" : "neutral"} />
                <StatCard icon={AlertTriangle} label="15天后预计" value={formatNumber(row.projected_15d_stock)} tone={row.projected_15d_stock < 0 ? "risk" : "good"} />
                <StatCard icon={Layers3} label="采购在途数" value={formatNumber(row.inbound_qty)} />
                <StatCard icon={Boxes} label="次品库存" value={formatNumber(row.defect_stock)} />
              </div>
              <div className="rounded-lg border border-border p-4">
                <p className="mb-3 text-sm font-medium">尺码库存</p>
                <div className="grid grid-cols-4 gap-2">
                  {Object.entries(row.size_stock).map(([size, qty]) => (
                    <div key={size} className="rounded-md bg-muted px-3 py-2">
                      <p className="text-xs text-muted-foreground">{size}</p>
                      <p className="text-sm font-semibold">{qty}</p>
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
  onSelectRow: (row: FineTableItem) => void
  page: number
  total: number
  totalPages: number
  visibleColumns: TableColumn[]
}) {
  return (
    <div className="overflow-hidden rounded-lg border border-border bg-card shadow-sm">
      <div className="max-h-[calc(100svh-320px)] min-h-[420px] overflow-auto">
        <table
          className="w-full border-separate border-spacing-0 text-sm"
          style={{ minWidth: Math.max(1500, 360 + visibleColumns.length * 120) }}
        >
          <thead className="sticky top-0 z-20 bg-card">
            <tr className="text-xs text-muted-foreground">
              <th className="sticky left-0 z-30 w-20 border-b border-border bg-card px-3 py-3 text-left font-medium">图片</th>
              <th className="sticky left-20 z-30 w-40 border-b border-border bg-card px-3 py-3 text-left font-medium">货号</th>
              {visibleColumns.map((column) => (
                <th
                  key={column.key}
                  className={cn(
                    "border-b border-border px-3 py-3 font-medium",
                    column.align === "right" ? "text-right" : column.align === "center" ? "text-center" : "text-left",
                    column.className,
                  )}
                >
                  <span className="block whitespace-nowrap">{column.label}</span>
                  <span className="mt-0.5 block text-[10px] font-normal text-muted-foreground">{column.group}</span>
                </th>
              ))}
              <th className="sticky right-0 z-30 w-20 border-b border-border bg-card px-3 py-3 text-right font-medium">详情</th>
            </tr>
          </thead>
          <tbody>
            {isLoading && (
              <tr>
                <td colSpan={visibleColumns.length + 3} className="px-4 py-16 text-center text-muted-foreground">正在加载精细表数据...</td>
              </tr>
            )}
            {!isLoading && error && (
              <tr>
                <td colSpan={visibleColumns.length + 3} className="px-4 py-16 text-center text-destructive">{error}</td>
              </tr>
            )}
            {!isLoading && !error && filteredRows.length === 0 && (
              <tr>
                <td colSpan={visibleColumns.length + 3} className="px-4 py-16 text-center text-muted-foreground">暂无匹配商品</td>
              </tr>
            )}
            {!isLoading && !error && filteredRows.map((row) => (
              <tr key={`${row.brand}-${row.id}`} className="group hover:bg-muted/40">
                <td className="sticky left-0 z-10 border-b border-border bg-card px-3 py-2 group-hover:bg-muted">
                  <ProductThumb item={row} />
                </td>
                <td className="sticky left-20 z-10 border-b border-border bg-card px-3 py-2 group-hover:bg-muted">
                  <div className="min-w-0">
                    <p className="font-medium">{row.sku || "-"}</p>
                    <p className="mt-0.5 text-xs text-muted-foreground">{row.original_sku || row.factory_sku || "-"}</p>
                  </div>
                </td>
                {visibleColumns.map((column) => (
                  <td
                    key={column.key}
                    className={cn(
                      "border-b border-border px-3 py-2",
                      column.align === "right" ? "text-right" : column.align === "center" ? "text-center" : "text-left",
                      column.className,
                    )}
                  >
                    {column.render(row)}
                  </td>
                ))}
                <td className="sticky right-0 z-10 border-b border-border bg-card px-3 py-2 text-right group-hover:bg-muted">
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

export function FineTablePage() {
  const [items, setItems] = useState<FineTableItem[]>([])
  const [page, setPage] = useState(1)
  const [total, setTotal] = useState(0)
  const [queryInput, setQueryInput] = useState("")
  const [query, setQuery] = useState("")
  const [season, setSeason] = useState("all")
  const [view, setView] = useState<ViewKey>("all")
  const [selectedRow, setSelectedRow] = useState<FineTableItem | null>(null)
  const [isLoading, setIsLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [reloadToken, setReloadToken] = useState(0)
  const [latestOrderDate, setLatestOrderDate] = useState<string | null>(null)
  const [columnMode, setColumnMode] = useState<ColumnMode>("default")
  const [customColumnPickerOpen, setCustomColumnPickerOpen] = useState(true)
  const [customColumnKeys, setCustomColumnKeys] = useState<string[]>(DEFAULT_COLUMN_KEYS)

  useEffect(() => {
    let cancelled = false
    async function loadData() {
      setIsLoading(true)
      setError(null)
      try {
        const response = await listFineTable({
          page,
          pageSize: PAGE_SIZE,
          query: query || undefined,
          season,
        })
        if (cancelled) return
        setItems(response.items)
        setTotal(response.total)
        setLatestOrderDate(response.latest_order_date)
      } catch (loadError) {
        if (cancelled) return
        setItems([])
        setTotal(0)
        setLatestOrderDate(null)
        setError(getErrorMessage(loadError))
      } finally {
        if (!cancelled) setIsLoading(false)
      }
    }
    void loadData()
    return () => {
      cancelled = true
    }
  }, [page, query, reloadToken, season])

  const seasons = useMemo(() => {
    const values = new Set(items.map((row) => row.season_category).filter(Boolean) as string[])
    return ["all", ...Array.from(values).slice(0, 8)]
  }, [items])

  const deferredView = useDeferredValue(view)
  const filteredRows = useMemo(() => {
    return items.filter((row) => {
      if (deferredView === "missingImage") return !row.image_url
      return true
    })
  }, [deferredView, items])

  const stats = useMemo(() => {
    const risk = items.filter((row) => row.projected_15d_stock < 0).length
    const missing = items.filter((row) => !row.image_url).length
    const sales7 = items.reduce((sum, row) => sum + row.vip_7d_sales + row.other_7d_sales, 0)
    return { risk, missing, sales7 }
  }, [items])

  const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE))
  const dailyLabels = useMemo(() => {
    const sample = items.find((row) => row.daily_sales.length > 0)
    return sample?.daily_sales.map((item) => item.date.slice(5)) ?? []
  }, [items])
  const tableColumns = useMemo(() => createTableColumns(dailyLabels), [dailyLabels])
  const visibleColumns = useMemo(() => {
    if (columnMode === "full") return tableColumns
    if (columnMode === "custom") {
      const selected = new Set(customColumnKeys)
      return tableColumns.filter((column) => selected.has(column.key))
    }
    return tableColumns.filter((column) => column.defaultVisible)
  }, [columnMode, customColumnKeys, tableColumns])
  const groupedColumns = useMemo(() => {
    return tableColumns.reduce<Record<ColumnGroup, TableColumn[]>>((acc, column) => {
      acc[column.group] = [...(acc[column.group] ?? []), column]
      return acc
    }, {} as Record<ColumnGroup, TableColumn[]>)
  }, [tableColumns])

  function toggleCustomColumn(key: string) {
    setCustomColumnKeys((current) => (
      current.includes(key)
        ? current.filter((item) => item !== key)
        : [...current, key]
    ))
  }

  return (
    <div className="min-h-svh bg-muted/30 px-5 py-6">
      <div className="mx-auto flex w-full max-w-[1600px] flex-col gap-4">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <h1 className="text-2xl font-semibold tracking-normal">商品精细表</h1>
            <p className="mt-1 text-sm text-muted-foreground">
              千百度女鞋{latestOrderDate ? ` · 订单截止 ${latestOrderDate}` : ""}
            </p>
          </div>
          <div className="flex items-center gap-2">
            <Button variant="outline" size="sm" onClick={() => setReloadToken((current) => current + 1)}>
              <RefreshCw className="h-4 w-4" />
              刷新
            </Button>
            <Button variant="outline" size="sm">
              <Download className="h-4 w-4" />
              导出
            </Button>
          </div>
        </div>

        <div className="grid gap-3 md:grid-cols-4">
          <StatCard icon={Boxes} label="当前页商品" value={formatNumber(items.length)} />
          <StatCard icon={AlertTriangle} label="缺货风险" value={formatNumber(stats.risk)} tone="risk" />
          <StatCard icon={TrendingUp} label="7天销量" value={formatNumber(stats.sales7)} tone="good" />
          <StatCard icon={ImageIcon} label="暂无图片" value={formatNumber(stats.missing)} tone={stats.missing > 0 ? "warn" : "neutral"} />
        </div>

        <div className="rounded-lg border border-border bg-card p-3 shadow-sm">
          <div className="flex flex-wrap items-center gap-2">
            <div className="relative min-w-72 flex-1">
              <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
              <Input
                value={queryInput}
                onChange={(event) => setQueryInput(event.target.value)}
                onKeyDown={(event) => {
                  if (event.key === "Enter") {
                    setPage(1)
                    setQuery(queryInput.trim())
                  }
                }}
                placeholder="搜索货号、原始货号、工厂货号"
                className="pl-9"
              />
            </div>
            <Button
              onClick={() => {
                setPage(1)
                setQuery(queryInput.trim())
              }}
            >
              查询
            </Button>
            <div className="flex flex-wrap gap-1.5">
              {seasons.map((value) => (
                <button
                  key={value}
                  type="button"
                  onClick={() => {
                    setSeason(value)
                    setPage(1)
                  }}
                  className={cn(
                    "h-9 cursor-pointer rounded-md px-3 text-sm font-medium transition-colors",
                    season === value ? "bg-primary text-primary-foreground" : "bg-muted text-muted-foreground hover:bg-muted/70 hover:text-foreground",
                  )}
                >
                  {value === "all" ? "全部季节" : value}
                </button>
              ))}
            </div>
          </div>
        </div>

        <div className="rounded-lg border border-border bg-card p-3 shadow-sm">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div className="flex items-center gap-2">
              <span className="text-sm font-medium">列视图</span>
              {[
                ["default", "运营视图"],
                ["full", "完整视图"],
                ["custom", "自定义"],
              ].map(([value, label]) => (
                <button
                  key={value}
                  type="button"
                  onClick={() => {
                    setColumnMode(value as ColumnMode)
                    if (value === "custom") {
                      setCustomColumnPickerOpen(true)
                    }
                  }}
                  className={cn(
                    "h-9 cursor-pointer rounded-md px-3 text-sm font-medium transition-colors",
                    columnMode === value ? "bg-primary text-primary-foreground" : "bg-muted text-muted-foreground hover:bg-muted/70 hover:text-foreground",
                  )}
                >
                  {label}
                </button>
              ))}
            </div>
            <div className="flex items-center gap-2">
              <p className="text-sm text-muted-foreground">显示 {visibleColumns.length} 列</p>
              {columnMode === "custom" && (
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  onClick={() => setCustomColumnPickerOpen((current) => !current)}
                  aria-expanded={customColumnPickerOpen}
                  aria-controls="fine-table-column-picker"
                >
                  <ChevronDown className={cn("h-4 w-4 transition-transform", customColumnPickerOpen && "rotate-180")} />
                  {customColumnPickerOpen ? "收起" : "展开"}
                </Button>
              )}
            </div>
          </div>
          {columnMode === "custom" && customColumnPickerOpen && (
            <div id="fine-table-column-picker" className="mt-3 grid gap-3 border-t border-border pt-3 md:grid-cols-3 xl:grid-cols-6">
              {(Object.keys(groupedColumns) as ColumnGroup[]).map((group) => (
                <div key={group} className="space-y-2">
                  <div className="text-xs font-medium text-muted-foreground">{group}</div>
                  <div className="space-y-1.5">
                    {groupedColumns[group]?.map((column) => (
                      <label key={column.key} className="flex cursor-pointer items-center gap-2 text-sm">
                        <input
                          type="checkbox"
                          checked={customColumnKeys.includes(column.key)}
                          onChange={() => toggleCustomColumn(column.key)}
                          className="h-4 w-4 accent-primary"
                        />
                        <span className="truncate">{column.label}</span>
                      </label>
                    ))}
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>

        <Tabs value={view} defaultValue="all" onValueChange={(value) => setView(value as ViewKey)}>
          <div className="flex items-center justify-between gap-3">
            <TabsList className="rounded-lg">
              {viewTabs.map((tab) => (
                <TabsTrigger key={tab.value} value={tab.value}>{tab.label}</TabsTrigger>
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
              onSelectRow={setSelectedRow}
              page={page}
              total={total}
              totalPages={totalPages}
              visibleColumns={visibleColumns}
            />
          </TabsContent>
        </Tabs>
      </div>
      {selectedRow && <div className="fixed inset-0 z-40 bg-black/20" onClick={() => setSelectedRow(null)} />}
      <DetailDrawer row={selectedRow} onClose={() => setSelectedRow(null)} />
    </div>
  )
}
