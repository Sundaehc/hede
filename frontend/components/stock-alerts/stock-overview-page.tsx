"use client"

import { useEffect, useRef, useState } from "react"
import Link from "next/link"
import {
  ArrowRight,
  CalendarDays,
  ChevronLeft,
  ChevronRight,
  ClipboardList,
  RefreshCw,
  Search,
  SlidersHorizontal,
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
  selling: ["正常销售", "bg-emerald-600"],
  next_season: ["跨季待售", "bg-sky-600"],
  size_imbalance: ["尺码不均衡", "bg-amber-500"],
  clearance: ["待清货", "bg-rose-500"],
  watch: ["继续观察", "bg-slate-500"],
  review: ["数据待核对", "bg-stone-400"],
}
const kinds = ["clearance", "zero", "replenish", "slow", "review"] as const
const number = new Intl.NumberFormat("zh-CN", { maximumFractionDigits: 1 })
const fmt = (value: number | null | undefined, suffix = "") =>
  value == null ? "—" : `${number.format(value)}${suffix}`
const panel = "rounded-xl border bg-card text-card-foreground"

function InventoryPanel({ data }: { data: OverviewResponse }) {
  const { inventory, sources } = data
  const health =
    inventory.coverage_days == null
      ? "范围或数据不足，暂不估算覆盖天数"
      : `按近 30 天净销估算可覆盖 ${fmt(inventory.coverage_days, " 天")}`
  return (
    <section aria-label="整盘库存" className={panel}>
      <div className="grid gap-4 border-b px-4 py-5 sm:px-6 lg:grid-cols-[1.1fr_1.9fr]">
        <div>
          <p className="text-sm font-medium">整盘可售库存</p>
          <div className="mt-1 flex flex-wrap items-baseline gap-2">
            <strong className="font-mono text-4xl font-bold tracking-tight tabular-nums">
              {fmt(inventory.available)}
            </strong>
            {inventory.available != null && (
              <span className="text-sm text-muted-foreground">双</span>
            )}
          </div>
          <p className="mt-2 text-xs leading-5 text-muted-foreground">
            {health}
          </p>
        </div>
        <div className="grid grid-cols-2 gap-3 self-center border-l pl-4 sm:pl-6">
          <div>
            <p className="text-xs text-muted-foreground">
              非清仓净销 · 7 天 / 30 天
            </p>
            <p className="mt-2 font-mono text-base font-semibold tabular-nums sm:text-lg">
              {fmt(inventory.regular_7)}{" "}
              <span className="text-muted-foreground">/</span>{" "}
              {fmt(inventory.regular_30)}
            </p>
          </div>
          <div>
            <p className="text-xs text-muted-foreground">
              清仓净销 · 7 天 / 30 天
            </p>
            <p className="mt-2 font-mono text-base font-semibold tabular-nums sm:text-lg">
              {fmt(inventory.clearance_7)}{" "}
              <span className="text-muted-foreground">/</span>{" "}
              {fmt(inventory.clearance_30)}
            </p>
          </div>
          <p className="col-span-2 text-xs text-muted-foreground">
            近 30 天合计 {fmt(inventory.total_30, " 双")}
          </p>
        </div>
      </div>
      <div className="space-y-3 px-4 py-4 sm:px-6">
        {inventory.available ? (
          <div
            className="flex h-2 w-full overflow-hidden rounded-full bg-muted"
            aria-hidden="true"
          >
            {inventory.buckets
              .filter((bucket) => bucket.units > 0)
              .map((bucket) => (
                <span
                  key={bucket.key}
                  className={bucketLabels[bucket.key][1]}
                  style={{ flex: bucket.units }}
                />
              ))}
          </div>
        ) : null}
        <ul className="grid grid-cols-2 gap-x-3 gap-y-2 sm:grid-cols-3 lg:grid-cols-6">
          {inventory.buckets.map((bucket) => (
            <li key={bucket.key} className="flex items-start gap-2 text-xs">
              <span
                className={cn(
                  "mt-1 size-2 shrink-0 rounded-sm",
                  bucketLabels[bucket.key][1]
                )}
                aria-hidden="true"
              />
              <span>
                {bucketLabels[bucket.key][0]}{" "}
                <span className="block font-mono text-muted-foreground">
                  {fmt(bucket.units, " 双")} / {fmt(bucket.styles, " 款色")}
                </span>
              </span>
            </li>
          ))}
        </ul>
        <p className="text-xs leading-5 text-muted-foreground">
          库存 {sources.stock_date ?? "待同步"} · 日销截至{" "}
          {sources.sales_end ?? "待同步"} · 北京时间。只汇总唯一匹配的档案款色。
          {sources.unmatched_stock_rows > 0
            ? ` 全部品牌库存中有 ${fmt(sources.unmatched_stock_rows)} 个编码组未能唯一匹配。`
            : ""}
        </p>
        {!sources.aligned && (
          <p className="text-xs font-medium text-destructive">
            库存或日销有延迟，可查看当前数据，暂不生成可分配建议。
          </p>
        )}
      </div>
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
  const metrics = week
    ? ([
        ["新增待办", week.created, " 项"],
        ["已完成", week.completed, " 项"],
        ["周末已到期未完成", week.overdue, " 项"],
        ["处理款净销", week.net_sales, " 双"],
        ["处理款尺码库存变化", week.stock_change, " 双"],
        ["清货款清仓净销", week.clearance_net_sales, " 双"],
      ] as const)
    : []
  return (
    <section aria-label="上周复盘" className={cn(panel, "p-4 sm:p-5")}>
      <h2 className="flex items-center gap-2 text-sm font-semibold">
        <CalendarDays
          className="size-4 text-muted-foreground"
          aria-hidden="true"
        />
        上周复盘
      </h2>
      {error ? (
        <div className="mt-3 space-y-2">
          <p className="text-sm text-destructive" role="alert">
            {error}
          </p>
          <Button size="sm" variant="outline" onClick={retry}>
            重新加载
          </Button>
        </div>
      ) : week ? (
        <>
          <p className="mt-1 text-xs text-muted-foreground">
            {week.start} 至 {week.end}
          </p>
          <dl className="mt-4 grid grid-cols-2 gap-x-3 gap-y-4 lg:grid-cols-1 xl:grid-cols-2 xl:gap-y-3">
            {metrics.map(([label, value, suffix]) => (
              <div key={label} className="border-b pb-2">
                <dt className="text-xs text-muted-foreground">{label}</dt>
                <dd className="mt-1 font-mono text-lg font-semibold tabular-nums">
                  {fmt(value, suffix)}
                </dd>
              </div>
            ))}
          </dl>
          <p className="mt-4 text-xs leading-5 text-muted-foreground">
            以该周已完成待办的 {week.completed_styles}{" "}
            个款色作观察，库存变化使用尺码历史快照。没有完整记录时显示「—」；观察值不能直接归因为某次处理。回收金额待财务口径接入。
          </p>
        </>
      ) : (
        <p className="mt-3 text-sm text-muted-foreground" role="status">
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
    brands.find(({ value }) => value === filters.brand)?.label ?? filters.brand
  const { data, loading, error, refreshing } = useStockModuleQuery({
    group: "stock-overview",
    queryKey: JSON.stringify(filters),
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
  const page = data?.page ?? filters.page
  const pages = data ? Math.max(1, Math.ceil(data.total / data.page_size)) : 1
  return (
    <div className="mx-auto max-w-[1520px] space-y-5 pb-5">
      <header className="flex flex-wrap items-start justify-between gap-3 border-b pb-4">
        <div>
          <p className="mb-1 text-xs font-medium tracking-widest text-muted-foreground">
            存 / 经营分析
          </p>
          <h1 className="text-2xl font-semibold tracking-tight sm:text-3xl">
            库存经营总览
          </h1>
          <p className="mt-1.5 text-sm text-muted-foreground">
            看库存压在哪里，决定今天先处理什么。
          </p>
        </div>
        <div className="flex flex-wrap gap-2 self-end">
          <Select
            aria-label="品牌"
            className="min-w-36"
            value={filters.brand}
            onChange={(event) => {
              setNotice("")
              setFilters({ ...filters, brand: event.target.value, page: 1 })
            }}
          >
            {!brands.some(({ value }) => value === filters.brand) && (
              <option value={filters.brand}>
                {filters.brand === defaults.brand
                  ? "千百度女鞋"
                  : filters.brand}
              </option>
            )}
            {brands.map(({ value, label }) => (
              <option key={value} value={value}>
                {label}
              </option>
            ))}
          </Select>
          <Button
            variant="outline"
            onClick={refresh}
            disabled={loading || refreshing}
          >
            <RefreshCw className={cn(refreshing && "animate-spin")} />
            刷新
          </Button>
          {manager && (
            <Button
              variant="outline"
              disabled={!data || refreshing}
              onClick={() => setPolicyOpen(true)}
            >
              <SlidersHorizontal />
              退出规则
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
        <p className="rounded-md border bg-muted p-3 text-sm" role="status">
          {notice}
        </p>
      )}
      {error && (
        <p
          role="alert"
          className="rounded-md border p-3 text-sm text-destructive"
        >
          {error}{" "}
          <Button variant="link" onClick={refresh}>
            重试
          </Button>
        </p>
      )}
      {loading && (
        <p
          role="status"
          className="rounded-md border p-5 text-sm text-muted-foreground"
        >
          正在汇总库存和处理建议…
        </p>
      )}
      {data && <InventoryPanel data={data} />}
      <div className="grid items-start gap-4 lg:grid-cols-[minmax(0,1fr)_245px] xl:grid-cols-[minmax(0,1fr)_282px]">
        <section aria-label="今日优先处理" className={panel}>
          <div className="flex flex-wrap items-start justify-between gap-2 px-4 pt-4 sm:px-5">
            <div>
              <h2 className="flex items-center gap-2 text-base font-semibold">
                <ClipboardList
                  className="size-4 text-muted-foreground"
                  aria-hidden="true"
                />
                今日优先处理
              </h2>
              <p className="mt-1 text-xs leading-5 text-muted-foreground">
                {data
                  ? `${fmt(data.assignable)} 条待分配 · ${fmt(data.in_progress)} 条已有待办 · ${fmt(data.counts.review)} 条待核对`
                  : "按处理类型、期限和影响数量排序"}
              </p>
            </div>
            <Button asChild variant="ghost" size="sm">
              <Link href="/stock-alerts/tasks">
                预警待办 <ArrowRight aria-hidden="true" />
              </Link>
            </Button>
          </div>
          <form
            className="flex flex-wrap gap-2 p-4 sm:px-5"
            onSubmit={(event) => {
              event.preventDefault()
              setFilters({ ...filters, query: query.trim(), page: 1 })
            }}
          >
            <Select
              aria-label="处理类型"
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
                  {data ? `（${data.counts[kind]}）` : ""}
                </option>
              ))}
            </Select>
            <Input
              aria-label="搜索货号、品名或颜色"
              className="min-w-36 flex-1"
              placeholder="货号 / 品名 / 颜色"
              maxLength={200}
              value={query}
              onChange={(event) => setQuery(event.target.value)}
            />
            <Button type="submit" variant="outline">
              <Search aria-hidden="true" />
              查询
            </Button>
          </form>
          {data?.items.length ? (
            <ul className="divide-y border-t">
              {data.items.map((item) => (
                <li
                  key={`${item.id}/${item.kind}`}
                  className="grid gap-2 px-4 py-3 sm:grid-cols-[minmax(0,1fr)_auto] sm:items-center sm:px-5"
                >
                  <div className="min-w-0">
                    <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
                      <span
                        className={cn(
                          "rounded border px-1.5 py-0.5 text-xs",
                          item.kind === "clearance" &&
                            "border-rose-600/25 bg-rose-500/10 text-rose-800 dark:text-rose-300",
                          item.kind === "replenish" &&
                            "border-sky-600/25 bg-sky-500/10 text-sky-800 dark:text-sky-300"
                        )}
                      >
                        {labels[item.kind]}
                      </span>
                      <button
                        type="button"
                        className="font-mono text-sm font-semibold break-all underline-offset-4 hover:underline focus-visible:underline"
                        onClick={() => setDetail(item)}
                      >
                        {item.sku}
                      </button>
                      <span className="text-xs text-muted-foreground">
                        {[item.product_name, item.color]
                          .filter(Boolean)
                          .join(" · ")}
                      </span>
                    </div>
                    <p className="mt-1 text-sm leading-5">{item.reason}</p>
                    <p className="mt-1 text-xs leading-5 text-muted-foreground">
                      可售 {fmt(item.available_quantity, " 双")}
                      {item.quantity != null &&
                        ` · 建议 ${fmt(item.quantity, " 双")}（${item.sizes.map((size) => size.name).join("、")}码）`}
                      {item.due_date && ` · 建议 ${item.due_date} 前处理`}
                      {item.channel && ` · ${item.channel}`}
                    </p>
                  </div>
                  <div className="flex flex-wrap items-center gap-2 sm:justify-end">
                    {item.task ? (
                      <Button
                        size="sm"
                        variant="ghost"
                        onClick={() => setTaskId(item.task!.id)}
                      >
                        <TaskStatusBadge task={item.task} />
                        {item.task.assignee_name}
                      </Button>
                    ) : manager && item.signature ? (
                      <Button
                        size="sm"
                        variant="outline"
                        onClick={() => setAssignment(item)}
                      >
                        分配待办
                      </Button>
                    ) : (
                      <Button
                        size="sm"
                        variant="ghost"
                        onClick={() => setDetail(item)}
                      >
                        查看依据
                      </Button>
                    )}
                  </div>
                </li>
              ))}
            </ul>
          ) : (
            data && (
              <p className="border-t p-6 text-sm text-muted-foreground">
                当前筛选没有处理建议。
              </p>
            )
          )}
          {data && pages > 1 && (
            <div className="flex items-center justify-end gap-2 border-t p-3 text-xs text-muted-foreground">
              <span>
                {fmt(data.total)} 条 · {page} / {pages} 页
              </span>
              <Button
                size="icon-sm"
                variant="outline"
                aria-label="上一页"
                disabled={page <= 1}
                onClick={() => setFilters({ ...filters, page: page - 1 })}
              >
                <ChevronLeft />
              </Button>
              <Button
                size="icon-sm"
                variant="outline"
                aria-label="下一页"
                disabled={page >= pages}
                onClick={() => setFilters({ ...filters, page: page + 1 })}
              >
                <ChevronRight />
              </Button>
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
