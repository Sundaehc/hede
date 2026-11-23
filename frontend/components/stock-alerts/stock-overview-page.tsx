"use client"

import { useEffect, useRef, useState } from "react"
import Link from "next/link"
import {
  Archive,
  ArrowRight,
  Box,
  CalendarDays,
  ChevronLeft,
  ChevronRight,
  ClipboardList,
  Database,
  RefreshCw,
  Search,
  SlidersHorizontal,
  TriangleAlert,
} from "lucide-react"
import { useAuth } from "@/components/auth/auth-provider"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Select } from "@/components/ui/select"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import {
  getStockAlertOptions,
  getStockOverview,
  getStockOverviewWeek,
} from "@/lib/api"
import { subscribeBusinessDataChanges } from "@/lib/business-data-sync"
import { useSessionQueryState } from "@/lib/session-query-state"
import { alertKindLabels } from "@/lib/stock-alert-tasks"
import {
  STOCK_ALERT_RESOURCES,
  STOCK_SOURCE_RESOURCES,
  useStockModuleOptions,
  useStockModuleQuery,
} from "@/lib/stock-module-query"
import type {
  InventoryBucket,
  OverviewFilters,
  OverviewItem,
  OverviewResponse,
  OverviewWeek,
} from "@/lib/stock-overview"
import { cn } from "@/lib/utils"
import { StockOverviewPolicyDialog } from "./stock-overview-policy-dialog"
import {
  CreateStockAlertTaskDialog,
  StockAlertTaskDialog,
  TaskStatusBadge,
} from "./task-dialog"

const defaults: OverviewFilters = {
  brand: "cbanner_womens",
  kind: "all",
  query: "",
  page: 1,
}
const labels = { ...alertKindLabels, review: "数据待核对" }
const bucketLabels: Record<InventoryBucket["key"], [string, string]> = {
  selling: ["正常销售", "bg-emerald-600 dark:bg-emerald-400"],
  next_season: ["跨季待售", "bg-sky-600 dark:bg-sky-400"],
  size_imbalance: ["尺码不均衡", "bg-indigo-600 dark:bg-indigo-400"],
  clearance: ["待清货", "bg-rose-600 dark:bg-rose-400"],
  watch: ["继续观察", "bg-slate-500 dark:bg-slate-400"],
  review: ["数据待核对", "bg-amber-500 dark:bg-amber-400"],
}
const kinds = ["clearance", "zero", "replenish", "slow", "review"] as const
const number = new Intl.NumberFormat("zh-CN", { maximumFractionDigits: 1 })
const percent = new Intl.NumberFormat("zh-CN", {
  maximumFractionDigits: 1,
  style: "percent",
})
const fmt = (value: number | null | undefined, suffix = "") =>
  value == null ? "—" : `${number.format(value)}${suffix}`
const panel =
  "min-w-0 overflow-hidden rounded-2xl border border-border/80 bg-card/80 text-card-foreground shadow-xs"
const badge = "rounded-md bg-muted/70 px-2 py-1 text-xs text-muted-foreground"
const warning = "text-amber-800 dark:text-amber-300"

function NetSales({
  label,
  recent,
  monthly,
}: {
  label: string
  recent: number | null
  monthly: number | null
}) {
  return (
    <div className="min-w-0">
      <h3 className="text-sm font-medium text-muted-foreground">{label}</h3>
      <dl className="mt-3 grid gap-x-3 gap-y-2 @min-[18rem]/inventory:grid-cols-2">
        {(
          [
            ["近 7 天", recent],
            ["近 30 天", monthly],
          ] as const
        ).map(([period, value]) => (
          <div key={period}>
            <dt className="text-xs text-muted-foreground">{period}</dt>
            <dd className="mt-0.5 text-base font-semibold wrap-anywhere tabular-nums sm:text-xl">
              {fmt(value)}
              {value != null && (
                <span className="ml-1 text-xs font-normal text-muted-foreground">
                  双
                </span>
              )}
            </dd>
          </div>
        ))}
      </dl>
    </div>
  )
}

function InventoryPanel({ data }: { data: OverviewResponse }) {
  const { inventory, sources } = data
  const review = inventory.buckets.find(({ key }) => key === "review")
  const reviewShare =
    review && inventory.available && review.units > 0
      ? review.units / inventory.available
      : null
  const reviewPercent =
    reviewShare == null
      ? null
      : reviewShare < 0.001
        ? "<0.1%"
        : reviewShare > 0.999 && reviewShare < 1
          ? ">99.9%"
          : percent.format(reviewShare)
  return (
    <section
      aria-label="整盘库存"
      className={cn(panel, "@container/inventory")}
    >
      <div className="grid @min-[48rem]/inventory:grid-cols-[minmax(0,1fr)_minmax(0,2fr)]">
        <div className="border-b bg-primary/[0.04] p-4 sm:px-5 @min-[48rem]/inventory:border-r @min-[48rem]/inventory:border-b-0">
          <h2 className="flex items-center justify-between gap-2 text-sm font-medium text-muted-foreground">
            整盘可售库存
            <Box className="size-4 shrink-0" aria-hidden="true" />
          </h2>
          <div className="mt-3 flex flex-wrap items-baseline gap-x-1.5">
            <strong className="text-3xl leading-none font-semibold tracking-tight wrap-anywhere tabular-nums">
              {fmt(inventory.available)}
            </strong>
            {inventory.available != null && (
              <span className="text-xs text-muted-foreground">双</span>
            )}
          </div>
          <p className="mt-2 text-xs leading-5 text-muted-foreground">
            {inventory.coverage_days == null
              ? "数据不足，暂无法估算库存覆盖天数"
              : `按近 30 天净销估算可覆盖 ${fmt(inventory.coverage_days, " 天")}`}
          </p>
        </div>
        <div className="p-4 sm:px-5">
          <div className="grid grid-cols-2 divide-x divide-border/80">
            <div className="pr-3 sm:pr-4">
              <NetSales
                label="非清仓净销"
                recent={inventory.regular_7}
                monthly={inventory.regular_30}
              />
            </div>
            <div className="pl-3 sm:pl-4">
              <NetSales
                label="清仓净销"
                recent={inventory.clearance_7}
                monthly={inventory.clearance_30}
              />
            </div>
          </div>
          <p className="mt-3 border-t border-border/80 pt-2.5 text-xs text-muted-foreground">
            近 30 天合计{" "}
            <strong className="ml-1 font-semibold text-foreground tabular-nums">
              {fmt(inventory.total_30, " 双")}
            </strong>
          </p>
        </div>
      </div>
      <div className="border-t px-4 py-3 sm:px-5">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <h3 className="text-sm font-semibold">库存分布</h3>
          {reviewPercent && (
            <span
              className={cn(
                "inline-flex items-center gap-1.5 text-xs font-medium",
                warning
              )}
            >
              <TriangleAlert className="size-3.5 shrink-0" aria-hidden="true" />
              待核对库存占 {reviewPercent}
            </span>
          )}
        </div>
        {inventory.available != null && inventory.available > 0 && (
          <div
            className="mt-2 flex h-2 overflow-hidden rounded-full bg-muted"
            aria-hidden="true"
          >
            {inventory.buckets
              .filter(({ units }) => units > 0)
              .map((bucket) => (
                <span
                  key={bucket.key}
                  className={bucketLabels[bucket.key][1]}
                  style={{ flex: bucket.units }}
                />
              ))}
          </div>
        )}
        {inventory.buckets.length > 0 ? (
          <ul className="mt-2.5 grid grid-cols-2 gap-2 @min-[30rem]/inventory:grid-cols-3 @min-[62rem]/inventory:grid-cols-6">
            {inventory.buckets.map((bucket) => (
              <li key={bucket.key} className="min-w-0 text-xs">
                <p className="flex items-center gap-1.5 font-medium">
                  <span
                    className={cn(
                      "size-2 shrink-0 rounded-full",
                      bucketLabels[bucket.key][1]
                    )}
                    aria-hidden="true"
                  />
                  {bucketLabels[bucket.key][0]}
                </p>
                <p className="mt-1 flex flex-wrap items-baseline gap-x-1.5 tabular-nums">
                  <strong className="font-semibold">
                    {fmt(bucket.units, " 双")}
                  </strong>
                  <span className="text-muted-foreground">
                    {fmt(bucket.styles, " 款色")}
                  </span>
                </p>
              </li>
            ))}
          </ul>
        ) : (
          <p className="mt-2 text-sm text-muted-foreground">
            暂无库存分布数据。
          </p>
        )}
      </div>
      <div className="border-t bg-muted/15 px-4 py-2.5 text-xs leading-5 text-muted-foreground sm:px-5">
        <div className="flex items-start gap-2">
          <Database className="mt-0.5 size-3.5 shrink-0" aria-hidden="true" />
          <div className="flex flex-wrap gap-x-4">
            <p className="flex flex-wrap gap-x-3 tabular-nums">
              <span>库存快照：{sources.stock_date ?? "待同步"}</span>
              <span>日销截至：{sources.sales_end ?? "待同步"}</span>
              <span>北京时间</span>
            </p>
            <p>
              只汇总唯一匹配的档案款色。{" "}
              {sources.unmatched_stock_rows > 0 &&
                `全部品牌有 ${fmt(sources.unmatched_stock_rows)} 个库存编码组未能唯一匹配。`}
            </p>
          </div>
        </div>
      </div>
      {!sources.aligned && (
        <p
          className={cn(
            "flex items-start gap-2 border-t border-amber-500/20 bg-amber-500/5 px-4 py-2.5 text-xs leading-5 font-medium sm:px-5",
            warning
          )}
        >
          <TriangleAlert
            className="mt-0.5 size-3.5 shrink-0"
            aria-hidden="true"
          />
          库存或日销有延迟，可查看当前数据，暂不生成可分配建议。
        </p>
      )}
    </section>
  )
}

function WeeklyPanel({
  week,
  error,
  retry,
}: {
  week: OverviewWeek | null
  error: string | null
  retry: () => void
}) {
  return (
    <section aria-labelledby="stock-overview-week" className={panel}>
      <div className="border-b border-border/80 px-4 py-4 sm:px-5">
        <h2
          id="stock-overview-week"
          className="flex items-center gap-2 text-sm font-semibold"
        >
          <CalendarDays
            className="size-4 text-muted-foreground"
            aria-hidden="true"
          />{" "}
          上周复盘
        </h2>
        {week && (
          <p className="mt-1 text-xs text-muted-foreground tabular-nums">
            {week.start} 至 {week.end}
          </p>
        )}
      </div>
      {error ? (
        <div className="space-y-2 p-4 sm:px-5">
          <p className="text-sm text-destructive" role="alert">
            {error}
          </p>
          <Button size="sm" variant="outline" onClick={retry}>
            重新加载
          </Button>
        </div>
      ) : week ? (
        <div className="space-y-4 p-4 sm:px-5">
          <dl className="grid grid-cols-3 divide-x">
            {(
              [
                ["新增待办", week.created],
                ["已完成", week.completed],
                ["到期未完成", week.overdue],
              ] as const
            ).map(([label, value]) => (
              <div
                key={label}
                className={cn(
                  "min-w-0 px-1 text-center",
                  label === "到期未完成" && value > 0 && warning
                )}
              >
                <dt
                  className="text-xs text-muted-foreground"
                  title={label === "到期未完成" ? "截至上周末" : undefined}
                >
                  {label}
                </dt>
                <dd className="mt-1 text-lg font-semibold wrap-anywhere tabular-nums">
                  {fmt(value)}
                  <span className="ml-0.5 text-xs font-normal text-muted-foreground">
                    项
                  </span>
                </dd>
              </div>
            ))}
          </dl>
          <div>
            <h3 className="text-xs font-medium text-muted-foreground">
              处理成效
            </h3>
            <dl className="mt-1 divide-y divide-border/70 text-xs">
              {(
                [
                  ["处理款净销", week.net_sales],
                  ["处理款尺码库存变化", week.stock_change],
                  ["清货款清仓净销", week.clearance_net_sales],
                ] as const
              ).map(([label, value]) => (
                <div
                  key={label}
                  className="flex flex-wrap items-baseline justify-between gap-x-3 gap-y-1 py-2"
                >
                  <dt className="text-muted-foreground">{label}</dt>
                  <dd className="font-medium tabular-nums">
                    {fmt(value, " 双")}
                  </dd>
                </div>
              ))}
            </dl>
          </div>
          <p className="border-t border-border/80 pt-3 text-xs leading-5 text-muted-foreground">
            观察上周已完成待办的 {fmt(week.completed_styles)}{" "}
            个款色。库存变化来自尺码历史快照，记录不全时显示「—」。观察值不能直接归因于某次处理，回收金额待财务口径接入。
          </p>
        </div>
      ) : (
        <p className="p-4 text-sm text-muted-foreground sm:px-5" role="status">
          正在读取上周记录…
        </p>
      )}
    </section>
  )
}

function DecisionDetail({
  item,
  close,
  assign,
}: {
  item: OverviewItem
  close: () => void
  assign?: () => void
}) {
  const fields = [
    ["年份 / 季节", [item.year, item.season].filter(Boolean).join(" / ")],
    ["鞋面材质", item.upper_material],
    ["档案上市日", item.launch_date],
    [
      "采购首入 / 最近入库",
      [item.first_inbound_date, item.last_inbound_date]
        .filter(Boolean)
        .join(" / "),
    ],
    ["计划退出日", item.exit_date],
    [
      "参考售罄率",
      item.sell_through_rate != null ? `${item.sell_through_rate}%` : null,
    ],
    [
      "近 7 / 30 天非清仓净销",
      `${fmt(item.regular_7)} / ${fmt(item.regular_30)}`,
    ],
    [
      "近 7 / 30 天清仓净销",
      `${fmt(item.clearance_7)} / ${fmt(item.clearance_30)}`,
    ],
    ["拟用清货渠道", item.channel],
  ]
  return (
    <Dialog
      open
      onOpenChange={(open) => {
        if (!open) close()
      }}
    >
      <DialogContent className="max-h-[90svh] overflow-y-auto sm:max-w-2xl">
        <DialogHeader>
          <DialogTitle>
            {labels[item.kind]} · {item.sku}
          </DialogTitle>
          <DialogDescription>
            {[item.product_name, item.color].filter(Boolean).join(" · ")}
          </DialogDescription>
        </DialogHeader>
        <p className="rounded-lg border bg-muted/50 p-3 text-sm leading-6">
          {item.reason}
        </p>
        <dl className="grid grid-cols-2 gap-3 text-sm">
          {fields.map(([label, value]) => (
            <div key={label}>
              <dt className="text-xs text-muted-foreground">{label}</dt>
              <dd className="mt-0.5">{value || "—"}</dd>
            </div>
          ))}
        </dl>
        {item.size_inventory.length > 0 && (
          <div className="overflow-x-auto rounded-lg border">
            <table className="w-full text-sm">
              <thead className="bg-muted text-left text-xs">
                <tr>
                  <th className="p-2">尺码</th>
                  <th className="p-2">可售库存</th>
                  <th className="p-2">建议处理</th>
                </tr>
              </thead>
              <tbody>
                {item.size_inventory.map((size) => (
                  <tr key={size.name} className="border-t">
                    <td className="p-2">
                      {size.name}
                      {size.core ? " · 核心" : ""}
                    </td>
                    <td className="p-2">{fmt(size.available, " 双")}</td>
                    <td className="p-2">
                      {fmt(
                        item.sizes.find((action) => action.name === size.name)
                          ?.quantity,
                        " 双"
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        <div className="flex flex-wrap items-center justify-between gap-3">
          <p className="text-xs text-muted-foreground">
            采购日期仅供参考；混批库存的实物库龄未确认。
          </p>
          {assign && <Button onClick={assign}>分配待办</Button>}
        </div>
      </DialogContent>
    </Dialog>
  )
}

export function StockOverviewPage() {
  const { hasPermission } = useAuth()
  const manager = hasPermission("product.manage")
  const [filters, setFilters] = useSessionQueryState<OverviewFilters>(
    "stock-overview:filters",
    defaults
  )
  const [query, setQuery] = useState(filters.query)
  const [revision, setRevision] = useState(0)
  const [weekRevision, setWeekRevision] = useState(0)
  const [policyOpen, setPolicyOpen] = useState(false)
  const [detail, setDetail] = useState<OverviewItem | null>(null)
  const [assignment, setAssignment] = useState<OverviewItem | null>(null)
  const [taskId, setTaskId] = useState<number | null>(null)
  const [notice, setNotice] = useState("")
  const force = useRef(false)
  const options = useStockModuleOptions(getStockAlertOptions)
  const brands = options.data?.brands ?? []
  const brandLabel =
    brands.find(({ value }) => value === filters.brand)?.label ??
    (filters.brand === defaults.brand ? "千百度女鞋" : filters.brand)
  const { data, previousData, loading, error, refreshing } =
    useStockModuleQuery({
      group: "stock-overview",
      queryKey: JSON.stringify(filters),
      previousDataKey: filters.brand,
      revision,
      resources: STOCK_ALERT_RESOURCES,
      factResources: STOCK_SOURCE_RESOURCES,
      load: (signal, refreshFacts) => {
        const refresh = force.current || refreshFacts
        force.current = false
        return getStockOverview(filters, { signal, refresh })
      },
    })
  const weekly = useStockModuleQuery({
    group: "stock-overview-week",
    queryKey: filters.brand,
    revision: weekRevision,
    resources: STOCK_ALERT_RESOURCES,
    load: (signal) => getStockOverviewWeek(filters.brand, signal),
  })
  useEffect(
    () =>
      subscribeBusinessDataChanges(() => {
        setRevision((value) => value + 1)
        setWeekRevision((value) => value + 1)
      }),
    []
  )
  const refresh = () => {
    force.current = true
    setRevision((value) => value + 1)
    setWeekRevision((value) => value + 1)
  }
  const summary = data ?? (loading ? previousData : null)
  const page = data?.page ?? filters.page
  const pages = data ? Math.max(1, Math.ceil(data.total / data.page_size)) : 1
  return (
    <div className="@container/overview mx-auto max-w-[1600px] space-y-4 p-4 sm:space-y-5 sm:p-6">
      <header className="flex flex-wrap items-center justify-between gap-4">
        <div>
          <p className="mb-2 flex items-center gap-1.5 text-xs text-muted-foreground">
            <Archive className="size-3.5" aria-hidden="true" />存 / 经营分析
          </p>
          <h1 className="text-2xl font-semibold tracking-tight">
            库存经营总览
          </h1>
          <p className="mt-1.5 text-sm text-muted-foreground">
            查看库存分布，安排今天的处理顺序。
          </p>
        </div>
        <div className="flex max-w-full min-w-0 flex-wrap items-end gap-2">
          <label className="min-w-0 basis-full @min-[32rem]/overview:basis-auto">
            <span className="mb-1 block text-xs font-medium text-muted-foreground">
              品牌
            </span>
            <Select
              className="h-9 min-w-0 @min-[32rem]/overview:w-40"
              value={filters.brand}
              onChange={(event) => {
                setNotice("")
                setFilters({ ...filters, brand: event.target.value, page: 1 })
              }}
            >
              {!brands.some(({ value }) => value === filters.brand) && (
                <option value={filters.brand}>{brandLabel}</option>
              )}
              {brands.map(({ value, label }) => (
                <option key={value} value={value}>
                  {label}
                </option>
              ))}
            </Select>
          </label>
          <Button
            size="lg"
            variant="outline"
            onClick={refresh}
            disabled={loading || refreshing}
          >
            <RefreshCw
              className={cn(refreshing && "motion-safe:animate-spin")}
              aria-hidden="true"
            />
            刷新
          </Button>
          {manager && (
            <Button
              size="lg"
              variant="outline"
              disabled={!summary || refreshing}
              onClick={() => setPolicyOpen(true)}
            >
              <SlidersHorizontal aria-hidden="true" /> 退出规则
            </Button>
          )}
        </div>
      </header>
      {options.error && (
        <p className="text-sm text-muted-foreground">
          未能更新品牌选项，当前品牌仍可查询。
        </p>
      )}
      {notice && (
        <p
          className="rounded-lg border bg-muted/50 px-4 py-3 text-sm"
          role="status"
        >
          {notice}
        </p>
      )}
      {error && (
        <div className="flex flex-wrap items-center gap-2 rounded-lg border border-destructive/25 bg-destructive/5 px-4 py-2 text-sm text-destructive">
          <p role="alert">{error}</p>
          <Button variant="link" onClick={refresh}>
            重试
          </Button>
        </div>
      )}
      {summary ? (
        <InventoryPanel data={summary} />
      ) : (
        loading && (
          <div className={cn(panel, "p-5")}>
            <div
              aria-hidden="true"
              className="mb-4 h-2 w-28 rounded-full bg-muted motion-safe:animate-pulse"
            />
            <p className="text-sm text-muted-foreground" role="status">
              正在汇总库存和处理建议…
            </p>
          </div>
        )
      )}
      <div className="grid items-start gap-4 @min-[55rem]/overview:grid-cols-[minmax(0,1fr)_minmax(16rem,21%)]">
        <section
          aria-labelledby="stock-overview-queue"
          className={cn(panel, "@container/queue")}
          aria-busy={refreshing}
        >
          <div className="space-y-2 px-4 py-3 sm:px-5">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <h2
                id="stock-overview-queue"
                className="flex items-center gap-2 text-sm font-semibold"
              >
                <ClipboardList
                  className="size-4 text-muted-foreground"
                  aria-hidden="true"
                />
                今日优先处理
              </h2>
              <Button asChild variant="outline" size="sm">
                <Link href="/stock-alerts/tasks">
                  预警待办 <ArrowRight aria-hidden="true" />
                </Link>
              </Button>
            </div>
            {summary ? (
              <div className="flex flex-wrap items-center gap-2 text-xs tabular-nums">
                <span className={badge}>
                  待分配{" "}
                  <strong className="ml-1 font-semibold">
                    {fmt(summary.assignable)}
                  </strong>{" "}
                  条
                </span>
                <span className={badge}>
                  已有待办{" "}
                  <strong className="ml-1 font-semibold">
                    {fmt(summary.in_progress)}
                  </strong>{" "}
                  条
                </span>
                <Button
                  type="button"
                  size="sm"
                  variant="outline"
                  disabled={
                    summary.counts.review === 0 && filters.kind !== "review"
                  }
                  aria-pressed={filters.kind === "review"}
                  onClick={() =>
                    setFilters({
                      ...filters,
                      kind: filters.kind === "review" ? "all" : "review",
                      page: 1,
                    })
                  }
                  className="h-7 px-2 text-xs shadow-none aria-pressed:border-primary/40 aria-pressed:bg-primary/5"
                >
                  {summary.counts.review > 0 && (
                    <TriangleAlert
                      className="text-amber-600 dark:text-amber-400"
                      aria-hidden="true"
                    />
                  )}
                  <span>
                    待核对{" "}
                    <strong className="ml-1 font-semibold">
                      {fmt(summary.counts.review)}
                    </strong>{" "}
                    条
                  </span>
                  <ChevronRight aria-hidden="true" />
                </Button>
              </div>
            ) : (
              <p className="text-xs text-muted-foreground">
                按处理类型、期限和影响数量排序
              </p>
            )}
          </div>
          <form
            className="grid grid-cols-[minmax(0,1fr)_auto] gap-2 border-y bg-muted/15 px-4 py-2.5 sm:px-5 @min-[30rem]/queue:grid-cols-[minmax(0,9.5rem)_minmax(0,1fr)_auto]"
            onSubmit={(event) => {
              event.preventDefault()
              setFilters({ ...filters, query: query.trim(), page: 1 })
            }}
          >
            <Select
              aria-label="处理类型"
              className="col-span-2 @min-[30rem]/queue:col-span-1"
              value={filters.kind}
              onChange={(event) =>
                setFilters({
                  ...filters,
                  kind: event.target.value as OverviewFilters["kind"],
                  page: 1,
                })
              }
            >
              <option value="all">全部类型</option>
              {kinds.map((kind) => (
                <option value={kind} key={kind}>
                  {labels[kind]}
                  {summary ? `（${fmt(summary.counts[kind])}）` : ""}
                </option>
              ))}
            </Select>
            <div className="relative min-w-0">
              <Search
                className="pointer-events-none absolute top-1/2 left-3 size-4 -translate-y-1/2 text-muted-foreground"
                aria-hidden="true"
              />
              <Input
                aria-label="搜索货号、品名或颜色"
                className="pl-9"
                placeholder="货号 / 品名 / 颜色"
                maxLength={200}
                value={query}
                onChange={(event) => setQuery(event.target.value)}
              />
            </div>
            <Button type="submit" size="lg" className="px-3.5">
              查询
            </Button>
          </form>
          {data?.items.length ? (
            <ul className="divide-y divide-border/80">
              {data.items.map((item) => (
                <li
                  key={`${item.id}/${item.kind}`}
                  className="grid gap-x-4 gap-y-2 px-4 py-3 transition-colors hover:bg-muted/30 sm:px-5 @min-[32rem]/queue:grid-cols-[minmax(0,1fr)_auto] @min-[32rem]/queue:items-center"
                >
                  <div className="min-w-0">
                    <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
                      <span
                        className={cn(
                          badge,
                          "py-0.5",
                          item.kind === "review" && "bg-amber-500/10",
                          item.kind === "review" && warning
                        )}
                      >
                        {labels[item.kind]}
                      </span>
                      <button
                        type="button"
                        className="min-w-0 cursor-pointer rounded-sm font-mono text-sm font-semibold wrap-anywhere text-foreground underline-offset-4 hover:underline focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none"
                        onClick={() => setDetail(item)}
                      >
                        {item.sku}
                      </button>
                      {(item.product_name || item.color) && (
                        <span className="min-w-0 text-xs wrap-anywhere text-muted-foreground">
                          {[item.product_name, item.color]
                            .filter(Boolean)
                            .join(" · ")}
                        </span>
                      )}
                    </div>
                    <p className="mt-1.5 text-sm leading-5 wrap-anywhere">
                      {item.reason}
                    </p>
                    <p className="mt-1.5 flex flex-wrap items-baseline gap-x-3 gap-y-1 text-xs leading-5 text-muted-foreground tabular-nums">
                      <span>
                        可售{" "}
                        <strong className="font-semibold text-foreground">
                          {fmt(item.available_quantity, " 双")}
                        </strong>
                      </span>
                      {item.quantity != null && (
                        <span>
                          建议 {fmt(item.quantity, " 双")}（
                          {item.sizes.map((size) => size.name).join("、")}码）
                        </span>
                      )}
                      {item.due_date && (
                        <span>建议 {item.due_date} 前处理</span>
                      )}
                      {item.channel && (
                        <span className="wrap-anywhere">{item.channel}</span>
                      )}
                    </p>
                  </div>
                  <div className="flex flex-wrap items-center gap-2 @min-[32rem]/queue:max-w-44 @min-[32rem]/queue:justify-end">
                    {item.task ? (
                      <Button
                        size="sm"
                        variant="ghost"
                        className="h-auto max-w-full flex-wrap justify-start py-1.5 whitespace-normal shadow-none"
                        onClick={() => setTaskId(item.task!.id)}
                      >
                        <TaskStatusBadge task={item.task} />
                        <span className="min-w-0 wrap-anywhere">
                          {item.task.assignee_name}
                        </span>
                      </Button>
                    ) : manager && item.signature ? (
                      <Button size="sm" onClick={() => setAssignment(item)}>
                        分配待办
                      </Button>
                    ) : (
                      <Button
                        size="sm"
                        variant="outline"
                        className="shadow-none"
                        onClick={() => setDetail(item)}
                      >
                        查看依据 <ChevronRight aria-hidden="true" />
                      </Button>
                    )}
                  </div>
                </li>
              ))}
            </ul>
          ) : loading && summary ? (
            <p
              className="px-4 py-6 text-sm text-muted-foreground sm:px-5"
              role="status"
            >
              正在读取处理列表…
            </p>
          ) : data ? (
            <div className="px-4 py-7 text-center sm:px-5">
              <h3 className="text-sm font-medium">当前筛选没有处理建议</h3>
              <p className="mt-1 text-xs text-muted-foreground">
                {filters.kind !== "all" || filters.query
                  ? "可更换类型或搜索词后再查。"
                  : "当前品牌没有待处理的库存建议。"}
              </p>
            </div>
          ) : null}
          {data && pages > 1 && (
            <div className="flex flex-wrap items-center justify-between gap-2 border-t bg-muted/15 px-4 py-2.5 text-xs text-muted-foreground tabular-nums sm:px-5">
              <span>共 {fmt(data.total)} 条</span>
              <div className="flex items-center gap-2">
                <span>
                  第 {page} / {pages} 页
                </span>
                <Button
                  size="icon-sm"
                  variant="outline"
                  aria-label="上一页"
                  disabled={page <= 1}
                  onClick={() => setFilters({ ...filters, page: page - 1 })}
                >
                  <ChevronLeft aria-hidden="true" />
                </Button>
                <Button
                  size="icon-sm"
                  variant="outline"
                  aria-label="下一页"
                  disabled={page >= pages}
                  onClick={() => setFilters({ ...filters, page: page + 1 })}
                >
                  <ChevronRight aria-hidden="true" />
                </Button>
              </div>
            </div>
          )}
        </section>
        <WeeklyPanel
          week={weekly.data}
          error={weekly.error}
          retry={() => setWeekRevision((value) => value + 1)}
        />
      </div>
      {policyOpen && data && (
        <StockOverviewPolicyDialog
          brand={filters.brand}
          brandLabel={brandLabel}
          scopes={data.scopes}
          policies={data.policies}
          close={() => setPolicyOpen(false)}
          saved={() => {
            setPolicyOpen(false)
            setNotice("退出规则已保存，正在更新处理建议。")
          }}
        />
      )}
      {detail && (
        <DecisionDetail
          item={detail}
          close={() => setDetail(null)}
          assign={
            manager && detail.signature
              ? () => {
                  setAssignment(detail)
                  setDetail(null)
                }
              : undefined
          }
        />
      )}
      {assignment && assignment.kind !== "review" && (
        <CreateStockAlertTaskDialog
          item={{
            ...assignment,
            available_quantity: String(assignment.available_quantity),
          }}
          kind={assignment.kind}
          recommendation={assignment}
          brandLabel={brandLabel}
          onClose={() => setAssignment(null)}
          onCreated={(task) => {
            setAssignment(null)
            setNotice(`已分配待办 #${task.id}，负责人：${task.assignee_name}。`)
          }}
        />
      )}
      {taskId != null && (
        <StockAlertTaskDialog id={taskId} onClose={() => setTaskId(null)} />
      )}
    </div>
  )
}
