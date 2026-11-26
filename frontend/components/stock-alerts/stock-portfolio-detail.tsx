"use client"

import { useEffect, useRef, useState } from "react"
import Link from "next/link"
import dynamic from "next/dynamic"
import {
  ArrowUpRight,
  Boxes,
  CalendarDays,
  ChartNoAxesColumn,
  ChevronDown,
  ClipboardList,
  Ruler,
  TriangleAlert,
  X,
} from "lucide-react"
import { Button } from "@/components/ui/button"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogTitle,
} from "@/components/ui/dialog"
import { Input } from "@/components/ui/input"
import { Select } from "@/components/ui/select"
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs"
import { getStockPortfolioItem, saveStockClearance } from "@/lib/api"
import type {
  ClearanceDecision,
  PortfolioChild,
  PortfolioDetail,
} from "@/lib/stock-portfolio"
import { cn } from "@/lib/utils"
import { StockProductPhoto } from "./stock-product-photo"

const StockPlanningPanel = dynamic(() =>
  import("./stock-planning-panel").then((module) => module.StockPlanningPanel)
)

const tabs = [
  { id: "stock", title: "货号与尺码", icon: Boxes },
  { id: "sales", title: "渠道日销", icon: ChartNoAxesColumn },
  { id: "purchase", title: "采购与入库", icon: ClipboardList },
  { id: "planning", title: "补单与到货", icon: CalendarDays },
] as const
const windows = [1, 3, 7, 15, 30]
const number = new Intl.NumberFormat("zh-CN")
const date = new Intl.DateTimeFormat("zh-CN", { timeZone: "Asia/Shanghai" })
const qty = (value: number | null | undefined) =>
  value == null ? "—" : number.format(value)
const err = (value: unknown) =>
  value instanceof Error ? value.message : "操作未完成，请重试。"
const table =
  "w-full min-w-max text-left text-sm tabular-nums [&_th]:bg-muted/70 [&_th]:text-xs [&_th]:font-medium [&_th]:text-muted-foreground [&_td]:px-3 [&_td]:py-2.5 [&_th]:px-3 [&_th]:py-2.5 [&_tbody_tr]:border-t [&_tbody_tr:hover]:bg-muted/40"
const numeric = "text-right whitespace-nowrap"
const panel = "min-w-0 overflow-hidden rounded-xl border border-border bg-card"
const empty = "border-t px-4 py-5 text-sm text-muted-foreground sm:px-5"
const field = "text-xs text-muted-foreground"
type Receipt = NonNullable<PortfolioDetail["receipts"]>["by_product"][string]

function Value({ value }: { value?: number | null }) {
  return (
    <>
      {qty(value)}
      {value != null && (
        <span className="ml-1.5 text-xs font-medium text-muted-foreground">
          双
        </span>
      )}
    </>
  )
}

function StockSizes({ stock }: { stock: PortfolioChild["stock"] }) {
  const sizeCount = new Set(stock.map(({ size }) => size)).size
  return (
    <details className="group/sizes border-t border-border">
      <summary className="flex min-h-11 cursor-pointer list-none items-center gap-2 rounded-b-xl px-4 py-2 text-sm font-medium text-primary hover:bg-muted/40 focus-visible:outline-2 focus-visible:outline-offset-[-2px] sm:px-5 [&::-webkit-details-marker]:hidden">
        <Ruler className="size-4 shrink-0" aria-hidden="true" />
        <span>查看尺码 / 分仓</span>
        <span className="ml-auto text-xs font-normal text-muted-foreground">
          {sizeCount} 个尺码 · {stock.length} 条记录
        </span>
        <ChevronDown
          className="size-4 shrink-0 text-muted-foreground group-open/sizes:rotate-180"
          aria-hidden="true"
        />
      </summary>
      <div className="overflow-x-auto border-t border-border">
        <table aria-label="尺码与分仓库存" className={table}>
          <thead>
            <tr>
              <th scope="col">尺码</th>
              <th scope="col">仓库</th>
              <th scope="col" className={numeric}>
                可售
              </th>
              <th scope="col" className={numeric}>
                采购在途
              </th>
            </tr>
          </thead>
          <tbody>
            {stock.map((row) => (
              <tr key={JSON.stringify([row.size, row.warehouse])}>
                <td className="font-medium">{row.size}</td>
                <td>{row.warehouse}</td>
                <td className={cn(numeric, "font-medium")}>
                  {qty(row.available)}
                </td>
                <td className={numeric}>{qty(row.transit)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </details>
  )
}

function StockChild({
  brand,
  item,
  receipt,
  manager,
  changed,
}: {
  brand: string
  item: PortfolioChild
  receipt?: Receipt
  manager: boolean
  changed: (productId: number, decision: ClearanceDecision) => void
}) {
  const [editing, setEditing] = useState(false)
  const [reason, setReason] = useState("")
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState("")
  const confirmed = item.clearance?.confirmed ?? false
  const facts = [
    ["档案上市", item.launch_date || "—"],
    ["采购首入", receipt?.first ?? "—"],
    ["最近入库", receipt?.last ?? "—"],
  ]
  return (
    <article className={panel}>
      <div className="p-4 sm:p-5">
        <div className="grid grid-cols-[auto_minmax(0,1fr)] items-start gap-x-3.5 gap-y-2.5 sm:grid-cols-[auto_minmax(0,1fr)_auto]">
          <StockProductPhoto item={item} />
          <div className="min-w-0">
            <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
              <h3 className="font-mono text-base font-semibold wrap-anywhere">
                {item.sku}
              </h3>
              {confirmed && (
                <span className="rounded-md bg-destructive/10 px-2 py-0.5 text-xs font-medium text-destructive">
                  已确认清仓
                </span>
              )}
            </div>
            <p className="mt-0.5 text-sm wrap-anywhere">
              {item.product_name || "品名待补"}
            </p>
            <p className="mt-1 text-xs wrap-anywhere text-muted-foreground">
              {[item.color, item.year, item.season_category, item.category]
                .filter(Boolean)
                .join(" · ")}
            </p>
          </div>
          {manager && !editing && (
            <Button
              type="button"
              size="sm"
              variant="outline"
              className="col-start-2 justify-self-start sm:col-start-3 sm:justify-self-end"
              onClick={() => {
                setReason("")
                setError("")
                setEditing(true)
              }}
            >
              {confirmed ? "解除清仓" : "确认清仓"}
            </Button>
          )}
        </div>
        <dl className="mt-4 grid grid-cols-2 overflow-hidden rounded-lg border border-border bg-card sm:grid-cols-3">
          <div className="border-r border-border bg-primary/8 px-3 py-2.5">
            <dt className={field}>当前可售</dt>
            <dd className="mt-0.5 font-semibold text-primary tabular-nums">
              <Value value={item.available_quantity} />
            </dd>
          </div>
          <div className="bg-muted/45 px-3 py-2.5 sm:border-r sm:border-border">
            <dt className={field}>采购在途</dt>
            <dd className="mt-0.5 font-semibold tabular-nums">
              <Value value={item.purchase_in_transit} />
            </dd>
          </div>
          <div className="col-span-2 border-t border-border bg-muted/45 px-3 py-2.5 sm:col-span-1 sm:border-t-0">
            <dt className={field}>累计正向入库</dt>
            <dd className="mt-0.5 font-semibold tabular-nums">
              <Value value={receipt?.quantity} />
            </dd>
          </div>
        </dl>
        <dl className="mt-3 grid grid-cols-3 gap-x-2 text-xs sm:gap-x-4">
          {facts.map(([label, value]) => (
            <div key={label} className="min-w-0">
              <dt className="text-muted-foreground">{label}</dt>
              <dd className="mt-0.5 wrap-anywhere tabular-nums">{value}</dd>
            </div>
          ))}
        </dl>
        {item.clearance && (
          <p className="mt-3 rounded-md bg-muted/45 px-3 py-2 text-xs leading-relaxed wrap-anywhere text-muted-foreground">
            <span className="font-medium text-foreground">
              {confirmed ? "确认记录" : "已解除清仓"}
            </span>
            {" · "}
            {item.clearance.reason}
            {" · "}
            {date.format(new Date(item.clearance.updated_at))}
          </p>
        )}
        {editing && (
          <form
            className="mt-4 rounded-lg border border-border bg-muted/30 p-3"
            onSubmit={async (event) => {
              event.preventDefault()
              if (!reason.trim() || saving) return
              setSaving(true)
              setError("")
              try {
                const response = await saveStockClearance(
                  brand,
                  item.id,
                  !confirmed,
                  reason.trim(),
                  item.clearance?.version ?? 0
                )
                changed(item.id, response.item)
                setEditing(false)
              } catch (error) {
                setError(err(error))
              } finally {
                setSaving(false)
              }
            }}
          >
            <p className="text-sm font-semibold">
              {confirmed ? "解除清仓" : "确认清仓"}
            </p>
            <p className="mt-1 text-xs text-muted-foreground">
              {confirmed
                ? "解除后，系统按现有规则重新评估此货号的补货建议。"
                : "确认后停止此货号的补货建议；已有采购单和待办由负责人复核。"}
            </p>
            <div className="mt-3 flex flex-wrap items-end justify-end gap-2">
              <label className="min-w-36 flex-1 text-xs font-medium">
                处理原因
                <Input
                  className="mt-1"
                  maxLength={1000}
                  value={reason}
                  onChange={(event) => setReason(event.target.value)}
                  required
                />
              </label>
              <Button
                type="button"
                variant="ghost"
                size="lg"
                disabled={saving}
                onClick={() => setEditing(false)}
              >
                取消
              </Button>
              <Button
                type="submit"
                variant={confirmed ? "default" : "destructive"}
                size="lg"
                disabled={!reason.trim() || saving}
              >
                {saving ? "正在保存…" : "保存"}
              </Button>
            </div>
            {error && (
              <p role="alert" className="mt-2 text-sm text-destructive">
                {error}
              </p>
            )}
          </form>
        )}
      </div>
      {item.stock.length > 0 && <StockSizes stock={item.stock} />}
    </article>
  )
}

function InventoryPanel({
  data,
  brand,
  manager,
  changed,
}: {
  data: PortfolioDetail
  brand: string
  manager: boolean
  changed: (productId: number, decision: ClearanceDecision) => void
}) {
  let available: number | null = null
  let transit: number | null = null
  let missing = 0
  for (const item of data.items) {
    if (item.available_quantity == null) missing++
    else available = (available ?? 0) + Math.max(0, item.available_quantity)
    if (item.purchase_in_transit != null)
      transit = (transit ?? 0) + item.purchase_in_transit
  }
  return (
    <div className="space-y-4">
      <dl className="grid grid-cols-2 overflow-hidden rounded-xl border border-border bg-card sm:grid-cols-[1.2fr_1fr_1fr]">
        <div className="col-span-2 border-b border-primary/15 bg-primary/8 px-4 py-3 sm:col-span-1 sm:border-r sm:border-b-0 sm:px-5">
          <dt className="text-xs font-medium text-primary">已匹配正可售合计</dt>
          <dd className="mt-1 text-2xl leading-tight font-semibold text-primary tabular-nums">
            <Value value={available} />
          </dd>
        </div>
        <div className="border-r border-border px-4 py-3 sm:px-5">
          <dt className={field}>已匹配采购在途</dt>
          <dd className="mt-1 text-xl leading-tight font-semibold tabular-nums">
            <Value value={transit} />
          </dd>
        </div>
        <div className="px-4 py-3 sm:px-5">
          <dt className={field}>档案货号</dt>
          <dd className="mt-1 text-xl leading-tight font-semibold tabular-nums">
            {number.format(data.items.length)}
            <span className="ml-1.5 text-xs font-medium text-muted-foreground">
              个
            </span>
          </dd>
        </div>
      </dl>
      {(data.unmatched_stock > 0 || missing > 0) && (
        <p className="flex items-start gap-2 rounded-lg border border-border bg-muted/40 px-3 py-2 text-xs leading-relaxed text-muted-foreground">
          <TriangleAlert
            className="mt-0.5 size-3.5 shrink-0"
            aria-hidden="true"
          />
          <span>
            {missing > 0 && `${missing} 个档案货号无库存快照，显示为「—」。`}
            {data.unmatched_stock > 0 &&
              `${data.unmatched_stock} 组库存编码无法唯一匹配，未计入合计。`}
          </span>
        </p>
      )}
      <section aria-label="档案货号" className="space-y-2.5">
        <h2 className="text-sm font-semibold">货号明细</h2>
        {data.items.map((item) => (
          <StockChild
            key={item.id}
            brand={brand}
            item={item}
            receipt={data.receipts?.by_product[item.id]}
            manager={manager}
            changed={changed}
          />
        ))}
      </section>
    </div>
  )
}

function SalesPanel({
  sales,
  days,
  setDays,
}: {
  sales: PortfolioDetail["sales"]
  days: number
  setDays: (value: number) => void
}) {
  return (
    <section aria-label="分渠道日销" className={panel}>
      <div className="flex flex-wrap items-center justify-between gap-3 px-4 py-3 sm:px-5">
        <div>
          <h2 className="text-sm font-semibold">分渠道日销</h2>
          <p className="mt-1 text-xs text-muted-foreground">
            截至 {sales.cutoff ?? "—"}
          </p>
        </div>
        <label className="flex shrink-0 items-center gap-2 text-xs text-muted-foreground">
          统计窗口
          <Select
            className="w-24"
            value={days}
            onChange={(event) => setDays(Number(event.target.value))}
          >
            {windows.map((size) => (
              <option key={size} value={size}>
                {size} 天
              </option>
            ))}
          </Select>
        </label>
      </div>
      {!!sales.unmatched && (
        <p className="border-t bg-muted/35 px-4 py-2 text-xs text-muted-foreground sm:px-5">
          {sales.unmatched} 组销售记录无法唯一匹配，表内仅统计已匹配记录。
        </p>
      )}
      {!sales.windows[days] ? (
        <p className={empty}>当前窗口日销未覆盖完整。</p>
      ) : !sales.channels.length ? (
        <p className={empty}>未查到已匹配的销售记录。</p>
      ) : (
        <div className="overflow-x-auto">
          <table className={table}>
            <thead>
              <tr>
                <th scope="col">平台 / 店铺</th>
                <th scope="col" className={numeric}>
                  销售
                </th>
                <th scope="col" className={numeric}>
                  退回
                </th>
                <th scope="col" className={numeric}>
                  净销
                </th>
              </tr>
            </thead>
            <tbody>
              {sales.channels.map(({ platform, shop, windows }) => {
                const metric = windows[days]
                return (
                  <tr key={JSON.stringify([platform, shop])}>
                    <td className="max-w-64">
                      <p className="font-medium">{platform}</p>
                      <p className="text-xs wrap-anywhere text-muted-foreground">
                        {shop}
                      </p>
                    </td>
                    <td className={numeric}>{qty(metric?.gross)}</td>
                    <td className={numeric}>{qty(metric?.returns)}</td>
                    <td className={cn(numeric, "font-semibold")}>
                      {qty(metric?.net)}
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      )}
    </section>
  )
}

function PurchasePanel({ data }: { data: PortfolioDetail }) {
  const skuById = new Map(data.items.map(({ id, sku }) => [id, sku]))
  return (
    <div className="space-y-4">
      <section aria-label="最近采购订单" className={panel}>
        <h2 className="px-4 py-3 text-sm font-semibold sm:px-5">
          最近采购订单
        </h2>
        {data.orders?.length ? (
          <div className="overflow-x-auto">
            <table className={table}>
              <thead>
                <tr>
                  <th scope="col">采购订单</th>
                  <th scope="col">货号</th>
                  <th scope="col">下单</th>
                  <th scope="col">约定到货</th>
                  <th scope="col" className={numeric}>
                    订货量
                  </th>
                </tr>
              </thead>
              <tbody>
                {data.orders.map((row) => (
                  <tr key={`${row.id}/${row.product_id}`}>
                    <td>
                      <Link
                        href={`/purchase-orders/${row.id}`}
                        className="inline-flex items-center gap-1 rounded-sm text-primary underline-offset-4 hover:underline"
                      >
                        {row.number || `#${row.id}`}{" "}
                        <ArrowUpRight className="size-3" aria-hidden="true" />
                      </Link>
                    </td>
                    <td className="font-mono">
                      {skuById.get(row.product_id) ?? "—"}
                    </td>
                    <td>{row.date ?? "—"}</td>
                    <td>{row.delivery_date ?? "—"}</td>
                    <td className={numeric}>{qty(row.quantity)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <p className={empty}>
            {data.orders
              ? "未查到已关联采购单。"
              : "无采购查看权限或采购来源尚未就绪。"}
          </p>
        )}
      </section>
      <section aria-label="近 90 天采购入库" className={panel}>
        <div className="px-4 py-3 sm:px-5">
          <h2 className="text-sm font-semibold">近 90 天采购入库</h2>
          <p className="mt-1 text-xs text-muted-foreground">
            最多展示 25 条已匹配的正向采购入库。
          </p>
        </div>
        {data.receipts?.recent?.length ? (
          <div className="overflow-x-auto">
            <table className={table}>
              <thead>
                <tr>
                  <th scope="col">入库日期</th>
                  <th scope="col">入仓单</th>
                  <th scope="col">采购单</th>
                  <th scope="col">货号</th>
                  <th scope="col" className={numeric}>
                    实收
                  </th>
                </tr>
              </thead>
              <tbody>
                {data.receipts.recent.map((row) => (
                  <tr
                    key={JSON.stringify([
                      row.product_id,
                      row.date,
                      row.inbound_id,
                      row.purchase_order_id,
                    ])}
                  >
                    <td>{row.date}</td>
                    <td>{row.inbound_id ?? "—"}</td>
                    <td>{row.purchase_order_id ?? "—"}</td>
                    <td className="font-mono">
                      {skuById.get(row.product_id) ?? "—"}
                    </td>
                    <td className={numeric}>{qty(row.quantity)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <p className={empty}>
            {data.receipts?.recent
              ? "未查到已匹配入库明细。"
              : "无库存查看权限或入库来源尚未就绪。"}
          </p>
        )}
      </section>
    </div>
  )
}

export function StockPortfolioDetail({
  brand,
  productId,
  manager,
  initialTab = "stock",
  onClose,
  onChanged,
}: {
  brand: string
  productId: number
  manager: boolean
  initialTab?: "stock" | "planning"
  onClose: () => void
  onChanged: () => void
}) {
  const [data, setData] = useState<PortfolioDetail | null>(null)
  const [error, setError] = useState("")
  const [attempt, setAttempt] = useState(0)
  const [days, setDays] = useState(30)
  const [planningId, setPlanningId] = useState(productId)
  const scroll = useRef<HTMLDivElement>(null)
  useEffect(() => {
    const controller = new AbortController()
    getStockPortfolioItem(brand, productId, controller.signal)
      .then((result) => {
        if (!controller.signal.aborted) setData(result)
      })
      .catch((error: unknown) => {
        if (!controller.signal.aborted) setError(err(error))
      })
    return () => controller.abort()
  }, [brand, productId, attempt])

  const changed = (id: number, clearance: ClearanceDecision) => {
    setData(
      (previous) =>
        previous && {
          ...previous,
          items: previous.items.map((item) =>
            item.id === id ? { ...item, clearance } : item
          ),
        }
    )
    onChanged()
  }
  return (
    <Dialog
      open
      onOpenChange={(open) => {
        if (!open) onClose()
      }}
    >
      <DialogContent className="flex h-[min(39rem,calc(100dvh-2rem))] flex-col overflow-hidden rounded-2xl bg-card p-0 text-card-foreground shadow-xl sm:h-[min(39rem,calc(100dvh-3rem))] sm:max-w-4xl">
        <header className="flex shrink-0 items-start justify-between gap-3 border-b border-border px-4 py-3.5 sm:px-6 sm:py-4">
          <div className="min-w-0">
            <p className="mb-1.5 flex flex-wrap items-center gap-x-2 text-xs font-medium text-muted-foreground">
              <span className="text-primary">单款进销存</span>
              {data && (
                <span className="border-l border-border pl-2">
                  原始货号下钻
                </span>
              )}
            </p>
            <DialogTitle className="font-mono text-xl leading-tight wrap-anywhere sm:text-2xl">
              {data?.original_sku || data?.items[0]?.sku || "商品明细"}
            </DialogTitle>
            <DialogDescription className="mt-1.5 flex flex-wrap items-center gap-1.5 text-xs">
              <CalendarDays className="size-3.5 shrink-0" aria-hidden="true" />
              库存快照{" "}
              <time dateTime={data?.stock_date ?? undefined}>
                {data?.stock_date ?? "待确认"}
              </time>
            </DialogDescription>
          </div>
          <Button
            type="button"
            variant="ghost"
            size="icon-lg"
            aria-label="关闭单款进销存"
            onClick={onClose}
          >
            <X aria-hidden="true" />
          </Button>
        </header>
        <Tabs
          defaultValue={initialTab}
          onValueChange={() => {
            if (scroll.current) scroll.current.scrollTop = 0
          }}
          className="min-h-0 flex-1 gap-0"
        >
          <div className="shrink-0 border-b border-border px-4 sm:px-6">
            <TabsList
              aria-label="单款进销存"
              className="grid h-auto w-full grid-cols-2 gap-x-1 rounded-none bg-transparent p-0 min-[420px]:grid-cols-4 sm:inline-grid sm:w-auto sm:grid-cols-[repeat(4,minmax(7rem,1fr))] sm:gap-4"
            >
              {tabs.map(({ id, title, icon: Icon }) => (
                <TabsTrigger
                  key={id}
                  value={id}
                  disabled={!data}
                  className="min-h-11 min-w-0 gap-1.5 rounded-none border-b-2 border-transparent px-1 text-xs transition-colors hover:text-foreground data-[state=active]:border-primary data-[state=active]:bg-transparent data-[state=active]:text-primary data-[state=active]:shadow-none sm:gap-2 sm:px-3 sm:text-sm"
                >
                  <Icon
                    className="size-3.5 shrink-0 sm:size-4"
                    aria-hidden="true"
                  />
                  {title}
                </TabsTrigger>
              ))}
            </TabsList>
          </div>
          <div
            ref={scroll}
            className="min-h-0 flex-1 overflow-y-auto overscroll-contain bg-muted/25 [scrollbar-gutter:stable]"
          >
            <div className="p-4 sm:px-6 sm:py-5">
              {error ? (
                <div className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-destructive/20 bg-destructive/5 p-4">
                  <p role="alert" className="text-sm text-destructive">
                    {error}
                  </p>
                  <Button
                    type="button"
                    variant="outline"
                    onClick={() => {
                      setError("")
                      setAttempt((value) => value + 1)
                    }}
                  >
                    重试
                  </Button>
                </div>
              ) : !data ? (
                <div
                  role="status"
                  className="rounded-xl border border-border bg-card p-4"
                >
                  <p className="text-sm text-muted-foreground">
                    正在读取单款进销存…
                  </p>
                  <div
                    aria-hidden="true"
                    className="mt-3 h-10 rounded-md bg-muted motion-safe:animate-pulse"
                  />
                </div>
              ) : (
                <>
                  <TabsContent value="stock">
                    <InventoryPanel
                      data={data}
                      brand={brand}
                      manager={manager}
                      changed={changed}
                    />
                  </TabsContent>
                  <TabsContent value="sales">
                    <SalesPanel
                      sales={data.sales}
                      days={days}
                      setDays={setDays}
                    />
                  </TabsContent>
                  <TabsContent value="purchase">
                    <PurchasePanel data={data} />
                  </TabsContent>
                  <TabsContent value="planning">
                    {data.items.length > 1 && (
                      <label className="mb-3 flex flex-wrap items-center gap-2 text-sm">
                        规划货号
                        <Select
                          className="w-44"
                          value={planningId}
                          onChange={(event) =>
                            setPlanningId(Number(event.target.value))
                          }
                        >
                          {data.items.map((item) => (
                            <option key={item.id} value={item.id}>
                              {item.sku}
                            </option>
                          ))}
                        </Select>
                      </label>
                    )}
                    <StockPlanningPanel
                      key={planningId}
                      brand={brand}
                      productId={planningId}
                      manager={manager}
                    />
                  </TabsContent>
                </>
              )}
            </div>
          </div>
        </Tabs>
      </DialogContent>
    </Dialog>
  )
}
