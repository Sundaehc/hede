"use client"

import { useEffect, useRef, useState } from "react"
import dynamic from "next/dynamic"
import Link from "next/link"
import { DropdownMenu } from "radix-ui"
import {
  ArrowRight,
  CalendarDays,
  ChevronLeft,
  ChevronRight,
  ClipboardList,
  Info,
  ListPlus,
  Ellipsis,
  RefreshCw,
  Search,
  SlidersHorizontal,
  X,
} from "lucide-react"
import { useAuth } from "@/components/auth/auth-provider"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Select } from "@/components/ui/select"
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs"
import {
  Dialog,
  DialogContent,
  DialogDescription,
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
  OverviewFilters,
  OverviewItem,
  OverviewResponse,
} from "@/lib/stock-overview"
import { cn } from "@/lib/utils"
import {
  BatchSelectionBar,
  SelectionCheckbox,
  useBatchSelection,
} from "./batch-selection"
import type { OverviewBatchItem } from "./batch-task-dialog"
import { StockOverviewPolicyDialog } from "./stock-overview-policy-dialog"
import {
  CreateStockAlertTaskDialog,
  StockAlertTaskDialog,
  TaskStatusBadge,
} from "./task-dialog"
import { StockProductPhoto } from "./stock-product-photo"
import {
  formatOverview as fmt,
  InventoryPanel,
  InventoryPanelLoading,
  overviewPanel as panel,
  overviewWarning as warning,
  WeeklyPanel,
} from "./stock-overview-panels"
import {
  StockPortfolioDetail,
  StockPortfolioPanel,
} from "./stock-portfolio-panel"

const BatchTaskDialog = dynamic(() =>
  import("./batch-task-dialog").then((module) => module.BatchTaskDialog)
)
const AutoAssignmentDialog = dynamic(() =>
  import("./stock-auto-assignment-dialog").then(
    (module) => module.StockAutoAssignmentDialog
  )
)
const CampaignDialog = dynamic(() =>
  import("./stock-phase-two-dialogs").then(
    (module) => module.StockCampaignDialog
  )
)
const ClearanceWeekDialog = dynamic(() =>
  import("./stock-phase-two-dialogs").then(
    (module) => module.StockClearanceWeekDialog
  )
)
const ArrivalsDialog = dynamic(() =>
  import("./stock-phase-two-dialogs").then(
    (module) => module.StockArrivalsDialog
  )
)
const recommendationKey = ({ id, kind }: OverviewItem) => `${id}/${kind}`

const weeklyResources = [
  ...STOCK_ALERT_RESOURCES,
  "stock-clearance-recovery",
] as const

const defaults: OverviewFilters = {
  brand: "cbanner_womens",
  kind: "all",
  query: "",
  page: 1,
}
const overviewTabs = [
  ["inventory", "库存概况"],
  ["queue", "处理建议"],
  ["portfolio", "库存货盘"],
  ["week", "上周复盘"],
] as const
const menuItemClass =
  "flex min-h-9 cursor-default items-center gap-2 rounded-md px-2.5 outline-none data-highlighted:bg-accent data-highlighted:text-accent-foreground data-disabled:opacity-45 [&_svg]:size-4"

const labels = { ...alertKindLabels, review: "数据待核对" }
const kinds = ["clearance", "zero", "replenish", "slow", "review"] as const

const decisionTone: Record<OverviewItem["kind"], string> = {
  zero: "border-amber-600/25 bg-amber-500/10 text-amber-900 dark:text-amber-200",
  slow: "border-amber-600/25 bg-amber-500/10 text-amber-900 dark:text-amber-200",
  clearance: "border-destructive/25 bg-destructive/5 text-destructive",
  replenish: "border-border bg-muted text-foreground",
  review: `border-amber-500/25 bg-amber-500/5 ${warning}`,
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
  const actionsBySize = new Map(
    item.sizes.map(({ name, quantity }) => [name, quantity])
  )
  const actionLabel =
    item.kind === "replenish"
      ? "建议补货"
      : item.kind === "clearance"
        ? "建议清货"
        : "建议处理"
  const identity = [item.product_name, item.color].filter(Boolean).join(" · ")
  const archive = [
    ["年份 / 季节", [item.year, item.season].filter(Boolean).join(" / ")],
    ["鞋面材质", item.upper_material],
    ["档案上市日", item.launch_date],
    ["计划退出日", item.exit_date],
    ["采购首入", item.first_inbound_date],
    ["最近入库", item.last_inbound_date],
    ["拟用清货渠道", item.channel],
  ]
  const sales = [
    ["非清仓净销", item.regular_7, item.regular_30],
    ["清仓净销", item.clearance_7, item.clearance_30],
  ] as const

  return (
    <Dialog
      open
      onOpenChange={(open) => {
        if (!open) close()
      }}
    >
      <DialogContent className="flex max-h-[min(92dvh,52rem)] flex-col overflow-hidden rounded-2xl bg-card p-0 text-card-foreground shadow-xl sm:max-w-[52rem]">
        <header className="relative shrink-0 border-b bg-muted/35 px-4 pt-4 pb-3.5 sm:px-6 sm:pt-5 sm:pb-4">
          <div className="flex items-center gap-3 pr-11 sm:gap-4">
            <StockProductPhoto item={item} detail />
            <div className="min-w-0">
              <div className="mb-2 flex flex-wrap items-center gap-x-2.5 gap-y-1.5">
                <span className="text-xs font-medium text-muted-foreground">
                  库存处理依据
                </span>
                <span
                  className={cn(
                    "rounded-md border px-2 py-0.5 text-xs font-semibold",
                    decisionTone[item.kind]
                  )}
                >
                  {labels[item.kind]}
                </span>
              </div>
              <DialogTitle className="font-mono text-xl leading-tight font-semibold tracking-tight wrap-anywhere sm:text-2xl">
                {item.sku}
              </DialogTitle>
              <DialogDescription className="mt-1 text-sm wrap-anywhere">
                {identity || "商品名称和颜色未记录"}
              </DialogDescription>
            </div>
          </div>
          <Button
            type="button"
            variant="ghost"
            size="icon"
            aria-label="关闭详情"
            className="absolute top-3 right-3 size-10 sm:right-4"
            onClick={close}
          >
            <X aria-hidden="true" />
          </Button>
        </header>

        <div
          role="region"
          aria-label="库存处理详情"
          tabIndex={0}
          className="min-h-0 overflow-y-auto overscroll-contain px-4 py-4 outline-offset-[-3px] focus-visible:outline-ring sm:px-6 sm:py-5"
        >
          <section
            aria-label="处理建议"
            className={cn(
              "rounded-lg border border-s-4 px-3 py-2.5 sm:px-4",
              decisionTone[item.kind]
            )}
          >
            <h3 className="text-xs font-semibold">处理建议</h3>
            <p className="mt-1 text-sm leading-relaxed wrap-anywhere text-foreground">
              {item.reason}
            </p>
          </section>

          <dl className="mt-4 grid grid-cols-3 divide-x overflow-hidden rounded-xl border bg-muted/25">
            {[
              ["总可售库存", fmt(item.available_quantity, " 双")],
              [
                "参考售罄率",
                item.sell_through_rate == null
                  ? "—"
                  : `${item.sell_through_rate}%`,
              ],
              [`${actionLabel}量`, fmt(item.quantity, " 双")],
            ].map(([label, value]) => (
              <div
                key={label}
                className="min-w-0 px-2.5 py-2.5 sm:px-4 sm:py-3"
              >
                <dt className="text-xs leading-4 text-muted-foreground">
                  {label}
                </dt>
                <dd className="mt-1 text-base leading-tight font-semibold wrap-anywhere tabular-nums sm:text-xl">
                  {value}
                </dd>
              </div>
            ))}
          </dl>

          <div className="mt-5 grid min-w-0 gap-5 md:grid-cols-[minmax(0,1.05fr)_minmax(0,1fr)]">
            <section aria-label="尺码库存" className="min-w-0">
              <div className="mb-2 flex items-baseline justify-between gap-2">
                <h3 className="text-sm font-semibold">尺码库存</h3>
                <span className="text-xs text-muted-foreground">
                  {item.size_inventory.length} 个尺码
                </span>
              </div>
              {item.size_inventory.length ? (
                <div className="overflow-hidden rounded-lg border">
                  <table
                    aria-label="尺码库存及处理建议"
                    className="w-full table-fixed text-sm tabular-nums"
                  >
                    <thead className="bg-muted/65 text-xs text-muted-foreground">
                      <tr>
                        <th
                          scope="col"
                          className="px-2.5 py-2 text-left font-medium sm:px-3"
                        >
                          尺码
                        </th>
                        <th
                          scope="col"
                          className="px-2.5 py-2 text-right font-medium sm:px-3"
                        >
                          可售库存
                        </th>
                        <th
                          scope="col"
                          className="px-2.5 py-2 text-right font-medium sm:px-3"
                        >
                          {actionLabel}
                        </th>
                      </tr>
                    </thead>
                    <tbody className="divide-y border-t">
                      {item.size_inventory.map((size) => {
                        const quantity = actionsBySize.get(size.name)
                        return (
                          <tr
                            key={size.name}
                            className={cn(quantity != null && "bg-muted/50")}
                          >
                            <th
                              scope="row"
                              className="px-2.5 py-2 text-left font-medium wrap-anywhere sm:px-3"
                            >
                              <span>{size.name}</span>
                              {size.core && (
                                <span className="ms-1 inline-block rounded bg-muted px-1 text-[11px] text-muted-foreground">
                                  核心
                                </span>
                              )}
                            </th>
                            <td
                              className={cn(
                                "px-2.5 py-2 text-right wrap-anywhere sm:px-3",
                                size.available == null &&
                                  "text-muted-foreground"
                              )}
                            >
                              {fmt(size.available, " 双")}
                            </td>
                            <td
                              className={cn(
                                "px-2.5 py-2 text-right wrap-anywhere sm:px-3",
                                quantity == null
                                  ? "text-muted-foreground"
                                  : "font-semibold"
                              )}
                            >
                              {fmt(quantity, " 双")}
                            </td>
                          </tr>
                        )
                      })}
                    </tbody>
                  </table>
                </div>
              ) : (
                <p className="rounded-lg border border-dashed px-3 py-4 text-sm text-muted-foreground">
                  暂无尺码库存明细
                </p>
              )}
            </section>

            <div className="min-w-0 space-y-4">
              <section aria-label="近期净销">
                <h3 className="mb-2 text-sm font-semibold">近期净销</h3>
                <div className="overflow-hidden rounded-lg border">
                  <table
                    aria-label="近 7 天与近 30 天净销"
                    className="w-full table-fixed text-sm tabular-nums"
                  >
                    <thead className="bg-muted/65 text-xs text-muted-foreground">
                      <tr>
                        <th
                          scope="col"
                          className="px-2.5 py-2 text-left font-medium"
                        >
                          口径
                        </th>
                        <th
                          scope="col"
                          className="px-2.5 py-2 text-right font-medium"
                        >
                          近 7 天
                        </th>
                        <th
                          scope="col"
                          className="px-2.5 py-2 text-right font-medium"
                        >
                          近 30 天
                        </th>
                      </tr>
                    </thead>
                    <tbody className="divide-y border-t">
                      {sales.map(([label, week, month]) => (
                        <tr key={label}>
                          <th
                            scope="row"
                            className="px-2.5 py-2 text-left font-medium"
                          >
                            {label}
                          </th>
                          <td className="px-2.5 py-2 text-right wrap-anywhere">
                            {fmt(week, " 双")}
                          </td>
                          <td className="px-2.5 py-2 text-right wrap-anywhere">
                            {fmt(month, " 双")}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </section>
              <section aria-label="商品与入库信息">
                <h3 className="mb-2 text-sm font-semibold">商品与入库信息</h3>
                <dl className="grid grid-cols-2 gap-x-3 gap-y-2.5 rounded-lg border px-2.5 py-2.5 text-sm sm:px-3">
                  {archive.map(([label, value]) => (
                    <div key={label} className="min-w-0">
                      <dt className="text-xs text-muted-foreground">{label}</dt>
                      <dd
                        className={cn(
                          "mt-0.5 wrap-anywhere tabular-nums",
                          !value && "text-muted-foreground"
                        )}
                      >
                        {value || "—"}
                      </dd>
                    </div>
                  ))}
                </dl>
              </section>
            </div>
          </div>
        </div>

        <footer className="flex shrink-0 flex-wrap items-center justify-between gap-x-5 gap-y-2 border-t bg-card px-4 pt-2.5 pb-3 sm:px-6 sm:py-3">
          <p className="flex min-w-0 flex-auto items-start gap-1.5 text-xs leading-4 text-muted-foreground sm:flex-1">
            <Info aria-hidden="true" className="mt-0.5 size-3.5 shrink-0" />
            <span>采购日期仅供参考，混批库存的实物库龄未确认。</span>
          </p>
          <div className="ml-auto flex shrink-0 items-center gap-2">
            <Button
              type="button"
              size="sm"
              variant="outline"
              className="min-h-9"
              onClick={close}
            >
              关闭
            </Button>
            {assign && (
              <Button
                type="button"
                size="sm"
                className="min-h-9"
                onClick={assign}
              >
                <ListPlus aria-hidden="true" />
                分配待办
              </Button>
            )}
          </div>
        </footer>
      </DialogContent>
    </Dialog>
  )
}

function PendingOverview({
  data,
  onOpen,
}: {
  data: OverviewResponse
  onOpen: (kind: OverviewFilters["kind"]) => void
}) {
  return (
    <section
      aria-labelledby="pending-overview"
      className={cn(panel, "@container/pending")}
    >
      <div className="flex flex-wrap items-center justify-between gap-2 border-b px-4 py-2.5 sm:px-5">
        <h2
          id="pending-overview"
          className="flex items-center gap-2 text-sm font-semibold"
        >
          <ClipboardList
            className="size-4 text-muted-foreground"
            aria-hidden="true"
          />
          待处理概览
        </h2>
        <Button
          variant="ghost"
          size="sm"
          className="shadow-none"
          onClick={() => onOpen("all")}
        >
          查看处理建议 <ArrowRight aria-hidden="true" />
        </Button>
      </div>
      <div className="grid @min-[56rem]/pending:grid-cols-[minmax(14rem,1fr)_3fr]">
        <dl className="grid grid-cols-2 divide-x border-b bg-muted/30 @min-[56rem]/pending:border-r @min-[56rem]/pending:border-b-0">
          <div className="min-w-0 px-4 py-3 sm:px-5">
            <dt className="text-xs text-muted-foreground">待分配</dt>
            <dd className="mt-1 font-mono text-2xl font-semibold tabular-nums">
              {fmt(data.assignable)}
            </dd>
          </div>
          <div className="min-w-0 px-4 py-3 sm:px-5">
            <dt className="text-xs text-muted-foreground">已有待办</dt>
            <dd className="mt-1 font-mono text-2xl font-semibold tabular-nums">
              {fmt(data.in_progress)}
            </dd>
          </div>
        </dl>
        <ul className="grid grid-cols-2 gap-1 p-2 @min-[34rem]/pending:grid-cols-5">
          {kinds.map((kind) => (
            <li key={kind} className="min-w-0">
              <Button
                variant="ghost"
                className="flex h-full min-h-14 w-full items-center justify-between gap-2 px-2.5 py-2 text-left whitespace-normal shadow-none @min-[34rem]/pending:flex-col @min-[34rem]/pending:items-start @min-[34rem]/pending:justify-center @min-[34rem]/pending:gap-0.5"
                aria-label={`${labels[kind]} ${fmt(data.counts[kind])} 项`}
                onClick={() => onOpen(kind)}
              >
                <span className="text-xs text-muted-foreground">
                  {labels[kind]}
                </span>
                <span
                  className={cn(
                    "font-mono text-lg font-semibold tabular-nums",
                    !data.counts[kind] && "text-muted-foreground",
                    data.counts[kind] > 0 &&
                      kind === "clearance" &&
                      "text-destructive",
                    data.counts[kind] > 0 && kind === "review" && warning
                  )}
                >
                  {fmt(data.counts[kind])}
                </span>
              </Button>
            </li>
          ))}
        </ul>
      </div>
    </section>
  )
}

function OverviewWeekTab({
  brand,
  revision,
  onRetry,
  onClearance,
}: {
  brand: string
  revision: number
  onRetry: () => void
  onClearance: (first: string) => void
}) {
  const { data, error } = useStockModuleQuery({
    group: "stock-overview-week",
    queryKey: brand,
    revision,
    resources: weeklyResources,
    load: (signal) => getStockOverviewWeek(brand, signal),
  })
  return (
    <WeeklyPanel
      week={data}
      error={error}
      retry={onRetry}
      onClearance={onClearance}
    />
  )
}

export function StockOverviewPage() {
  const { hasPermission } = useAuth()
  const manager = hasPermission("product.manage")
  const canViewArrivals = hasPermission("purchase.view")
  const [view, setView] = useState<string>("inventory")
  const [filters, setStoredFilters] = useSessionQueryState<OverviewFilters>(
    "stock-overview:filters",
    defaults
  )
  const selection = useBatchSelection<OverviewBatchItem>()
  const [batchItems, setBatchItems] = useState<OverviewBatchItem[] | null>(null)
  const setFilters = (next: OverviewFilters) => {
    if (
      next.brand !== filters.brand ||
      next.kind !== filters.kind ||
      next.query !== filters.query
    )
      selection.clear()
    setStoredFilters(next)
  }
  const [query, setQuery] = useState(filters.query)
  const [revision, setRevision] = useState(0)
  const [weekRevision, setWeekRevision] = useState(0)
  const [portfolioRefresh, setPortfolioRefresh] = useState(0)
  const [policyOpen, setPolicyOpen] = useState(false)
  const [autoOpen, setAutoOpen] = useState(false)
  const [campaignOpen, setCampaignOpen] = useState(false)
  const [arrivalsOpen, setArrivalsOpen] = useState(false)
  const [clearanceWeek, setClearanceWeek] = useState<string | null>(null)
  const [portfolioItem, setPortfolioItem] = useState<{
    brand: string
    id: number
    tab?: "planning"
  } | null>(null)
  const [detail, setDetail] = useState<OverviewItem | null>(null)
  const [assignment, setAssignment] = useState<OverviewItem | null>(null)
  const [taskId, setTaskId] = useState<number | null>(null)
  const [notice, setNotice] = useState("")
  const force = useRef(false)
  const focusQueue = useRef(false)
  useEffect(() => {
    if (view === "queue" && focusQueue.current) {
      focusQueue.current = false
      document.getElementById("stock-overview-queue")?.focus()
    }
  }, [view])
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
  useEffect(
    () =>
      subscribeBusinessDataChanges((resources) => {
        if (
          !resources.length ||
          resources.some((resource) => resource !== "stock-clearance-recovery")
        )
          setRevision((value) => value + 1)
        setWeekRevision((value) => value + 1)
      }),
    []
  )
  const refresh = () => {
    force.current = true
    setPortfolioRefresh((value) => value + 1)
    setRevision((value) => value + 1)
    setWeekRevision((value) => value + 1)
  }
  const summary = data ?? (loading ? previousData : null)
  const page = data?.page ?? filters.page
  const pages = data ? Math.max(1, Math.ceil(data.total / data.page_size)) : 1
  const totalSuggestions = summary
    ? kinds.reduce((total, kind) => total + summary.counts[kind], 0)
    : null
  const selectable =
    manager && data
      ? data.items.flatMap((item): OverviewBatchItem[] =>
          item.kind !== "review" && item.signature && !item.task
            ? [
                {
                  ...item,
                  kind: item.kind,
                  signature: item.signature,
                  productId: item.id,
                  id: recommendationKey(item),
                },
              ]
            : []
        )
      : []
  const availableByKey = new Map(selectable.map((item) => [item.id, item]))
  const checkedOnPage = selectable.filter((item) =>
    selection.selected.has(item.id)
  ).length
  const selectKind = (kind: OverviewFilters["kind"]) => {
    setFilters({ ...filters, kind, page: 1 })
  }
  const openQueue = (kind: OverviewFilters["kind"]) => {
    focusQueue.current = true
    setQuery("")
    setFilters({ ...filters, kind, query: "", page: 1 })
    setView("queue")
  }
  const clearQuery = () => {
    setQuery("")
    if (filters.query) setFilters({ ...filters, query: "", page: 1 })
  }
  return (
    <div className="@container/overview mx-auto w-full space-y-4 px-3 py-4 sm:space-y-5 sm:px-5 sm:py-5 lg:px-6">
      <header className="flex flex-wrap items-center justify-between gap-x-5 gap-y-3">
        <h1 className="text-2xl font-semibold tracking-tight sm:text-[1.75rem]">
          库存经营总览
        </h1>
        <div className="flex max-w-full min-w-0 flex-wrap items-end gap-2">
          <label className="min-w-0">
            <span className="sr-only">品牌</span>
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
          <DropdownMenu.Root>
            <DropdownMenu.Trigger asChild>
              <Button size="icon-lg" variant="outline" aria-label="更多操作">
                <Ellipsis aria-hidden="true" />
              </Button>
            </DropdownMenu.Trigger>
            <DropdownMenu.Portal>
              <DropdownMenu.Content
                align="end"
                sideOffset={6}
                className="z-50 min-w-36 rounded-lg border bg-popover p-1 text-sm text-popover-foreground shadow-md"
              >
                <DropdownMenu.Item
                  className={menuItemClass}
                  onSelect={() => setCampaignOpen(true)}
                >
                  <CalendarDays aria-hidden="true" /> 营销日历
                </DropdownMenu.Item>
                {canViewArrivals && (
                  <DropdownMenu.Item
                    className={menuItemClass}
                    onSelect={() => setArrivalsOpen(true)}
                  >
                    <ClipboardList aria-hidden="true" /> 到货清单
                  </DropdownMenu.Item>
                )}
                {manager && (
                  <>
                    <DropdownMenu.Separator className="my-1 border-t" />
                    <DropdownMenu.Item
                      className={menuItemClass}
                      disabled={!data || refreshing}
                      onSelect={() => setPolicyOpen(true)}
                    >
                      <SlidersHorizontal aria-hidden="true" /> 退出规则
                    </DropdownMenu.Item>
                    <DropdownMenu.Item
                      className={menuItemClass}
                      onSelect={() => setAutoOpen(true)}
                    >
                      <ListPlus aria-hidden="true" /> 自动派办
                    </DropdownMenu.Item>
                  </>
                )}
              </DropdownMenu.Content>
            </DropdownMenu.Portal>
          </DropdownMenu.Root>
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
      <Tabs
        defaultValue="inventory"
        value={view}
        onValueChange={setView}
        activationMode="manual"
      >
        <TabsList
          aria-label="总览分区"
          className="grid h-auto max-w-full grid-cols-4 gap-0.5 self-start rounded-lg bg-muted/65 p-0.5"
        >
          {overviewTabs.map(([key, title]) => (
            <TabsTrigger
              key={key}
              value={key}
              className="min-h-9 cursor-pointer rounded-md px-2 text-xs data-[state=active]:font-semibold data-[state=active]:ring-1 data-[state=active]:ring-border sm:px-4 sm:text-sm"
            >
              {title}
            </TabsTrigger>
          ))}
        </TabsList>
        <TabsContent value="inventory" className="space-y-3 sm:space-y-4">
          {summary ? (
            <>
              <InventoryPanel
                data={summary}
                onReview={() => openQueue("review")}
              />
              <PendingOverview data={summary} onOpen={openQueue} />
            </>
          ) : (
            loading && <InventoryPanelLoading />
          )}
        </TabsContent>
        <TabsContent value="queue">
          <section
            aria-labelledby="stock-overview-queue"
            className={cn(panel, "@container/queue")}
            aria-busy={loading || refreshing}
          >
            <div className="flex flex-wrap items-start justify-between gap-x-3 gap-y-2 px-4 py-4 sm:px-5">
              <div className="min-w-0">
                <h2
                  id="stock-overview-queue"
                  tabIndex={-1}
                  className="flex scroll-mt-16 items-center gap-2 rounded-sm text-base font-semibold tracking-tight focus-visible:outline-2 focus-visible:outline-offset-2"
                >
                  <ClipboardList
                    className="size-4 shrink-0 text-muted-foreground"
                    aria-hidden="true"
                  />
                  处理建议
                </h2>
                {summary ? (
                  <dl className="mt-2 flex flex-wrap gap-2 text-xs tabular-nums">
                    <div className="flex items-baseline gap-1.5 rounded-md bg-primary/[0.08] px-2 py-1">
                      <dt className="text-muted-foreground">待分配</dt>
                      <dd className="font-mono font-semibold">
                        {fmt(summary.assignable)}
                      </dd>
                    </div>
                    <div className="flex items-baseline gap-1.5 rounded-md border border-border/75 px-2 py-1">
                      <dt className="text-muted-foreground">已有待办</dt>
                      <dd className="font-mono font-semibold">
                        {fmt(summary.in_progress)}
                      </dd>
                    </div>
                  </dl>
                ) : (
                  <p className="mt-1 text-xs text-muted-foreground">
                    按处理类型、期限和影响数量排序
                  </p>
                )}
              </div>
              <Button
                asChild
                variant="outline"
                size="sm"
                className="shadow-none"
              >
                <Link href="/stock-alerts/tasks">
                  预警待办 <ArrowRight aria-hidden="true" />
                </Link>
              </Button>
            </div>
            <div className="flex flex-wrap items-center justify-between gap-2.5 border-y bg-muted/25 px-4 py-3 sm:px-5">
              <div
                role="group"
                aria-label="处理类型"
                className="flex flex-wrap gap-1.5"
              >
                {(["all", ...kinds] as const).map((kind) => {
                  const active = filters.kind === kind
                  const count =
                    kind === "all" ? totalSuggestions : summary?.counts[kind]
                  return (
                    <Button
                      key={kind}
                      type="button"
                      variant={active ? "default" : "outline"}
                      size="sm"
                      className="h-8 gap-1.5 px-2 text-xs shadow-none"
                      aria-pressed={active}
                      onClick={() => selectKind(kind)}
                    >
                      {kind === "all" ? "全部" : labels[kind]}
                      {count != null && (
                        <span
                          className={cn(
                            "rounded px-1 tabular-nums",
                            active
                              ? "bg-primary-foreground/15"
                              : "bg-muted text-muted-foreground"
                          )}
                        >
                          {fmt(count)}
                        </span>
                      )}
                    </Button>
                  )
                })}
              </div>
              <form
                className="flex w-full min-w-0 items-center gap-2 @min-[48rem]/queue:w-72"
                onSubmit={(event) => {
                  event.preventDefault()
                  setFilters({ ...filters, query: query.trim(), page: 1 })
                }}
              >
                <div className="relative min-w-0 flex-1">
                  <Search
                    className="pointer-events-none absolute top-1/2 left-3 size-4 -translate-y-1/2 text-muted-foreground"
                    aria-hidden="true"
                  />
                  <Input
                    aria-label="搜索货号、品名或颜色"
                    className="h-9 bg-background pr-9 pl-9"
                    placeholder="货号 / 品名 / 颜色"
                    maxLength={200}
                    value={query}
                    onChange={(event) => setQuery(event.target.value)}
                  />
                  {(query || filters.query) && (
                    <Button
                      type="button"
                      variant="ghost"
                      size="icon-sm"
                      aria-label="清空搜索"
                      onClick={clearQuery}
                      className="absolute top-1/2 right-1 -translate-y-1/2 shadow-none"
                    >
                      <X aria-hidden="true" />
                    </Button>
                  )}
                </div>
                <Button
                  type="submit"
                  size="lg"
                  variant="outline"
                  className="shadow-none"
                >
                  查询
                </Button>
              </form>
              {filters.query && (
                <p className="w-full text-xs leading-5 wrap-anywhere text-muted-foreground">
                  当前搜索：
                  <strong className="font-medium text-foreground">
                    {filters.query}
                  </strong>
                </p>
              )}
            </div>
            {manager &&
              (selectable.length > 0 || selection.selected.size > 0) && (
                <BatchSelectionBar
                  count={selection.selected.size}
                  error={selection.error}
                  onClear={selection.clear}
                >
                  <Button
                    size="sm"
                    disabled={loading || refreshing || !selection.selected.size}
                    onClick={() =>
                      setBatchItems([...selection.selected.values()])
                    }
                  >
                    批量分配待办
                  </Button>
                </BatchSelectionBar>
              )}
            {manager && selectable.length > 0 && (
              <label className="flex min-h-9 w-fit cursor-pointer items-center gap-2.5 px-4 text-xs text-muted-foreground sm:px-5">
                <SelectionCheckbox
                  label="选择本页可分配建议"
                  checked={checkedOnPage === selectable.length}
                  mixed={checkedOnPage > 0 && checkedOnPage < selectable.length}
                  disabled={loading || refreshing}
                  onChange={(checked) =>
                    selection.select(
                      checked
                        ? selectable.filter(
                            ({ id }) => !selection.selected.has(id)
                          )
                        : selectable,
                      checked
                    )
                  }
                />
                选择本页可分配建议
              </label>
            )}
            {data?.items.length ? (
              <ul className="divide-y divide-border/80">
                {data.items.map((item) => {
                  const key = recommendationKey(item)
                  const choice = availableByKey.get(key)
                  const selected = selection.selected.get(key)
                  return (
                    <li
                      key={key}
                      className={cn(
                        "grid gap-x-4 gap-y-2.5 px-4 py-3.5 transition-colors hover:bg-muted/25 sm:px-5 @min-[34rem]/queue:grid-cols-[minmax(0,1fr)_auto] @min-[34rem]/queue:items-center",
                        selected && "bg-primary/5"
                      )}
                    >
                      <div className="flex min-w-0 items-start gap-3">
                        {manager &&
                          (selectable.length > 0 ||
                            selection.selected.size > 0) && (
                            <div className="grid h-12 w-4 shrink-0 place-items-center">
                              {(choice || selected) && (
                                <SelectionCheckbox
                                  label={`选择 ${item.sku} · ${labels[item.kind]}`}
                                  checked={!!selected}
                                  disabled={refreshing}
                                  onChange={(checked) => {
                                    if (choice)
                                      selection.select([choice], checked)
                                    else if (!checked) selection.remove([key])
                                  }}
                                />
                              )}
                            </div>
                          )}
                        <StockProductPhoto item={item} />
                        <div className="min-w-0 flex-1">
                          <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
                            <button
                              type="button"
                              className="min-w-0 cursor-pointer rounded-sm font-mono text-sm font-semibold wrap-anywhere text-foreground underline-offset-4 hover:underline focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none"
                              onClick={() => setDetail(item)}
                            >
                              {item.sku}
                            </button>
                            <span
                              className={cn(
                                "rounded border px-1.5 py-0.5 text-xs font-medium",
                                decisionTone[item.kind]
                              )}
                            >
                              {labels[item.kind]}
                            </span>
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
                                建议处理{" "}
                                <strong className="font-semibold text-foreground">
                                  {fmt(item.quantity, " 双")}
                                </strong>
                                {item.sizes.length > 0 &&
                                  `（${item.sizes.map(({ name }) => name).join("、")}码）`}
                              </span>
                            )}
                            {item.due_date && (
                              <span className="inline-flex items-center gap-1">
                                <CalendarDays
                                  className="size-3 shrink-0"
                                  aria-hidden="true"
                                />
                                <time dateTime={item.due_date}>
                                  {item.due_date}
                                </time>{" "}
                                前处理
                              </span>
                            )}
                            {item.channel && (
                              <span className="wrap-anywhere">
                                {item.channel}
                              </span>
                            )}
                          </p>
                        </div>
                      </div>
                      <div
                        className={cn(
                          "flex min-w-0 flex-wrap items-center gap-2 @min-[34rem]/queue:max-w-60 @min-[34rem]/queue:justify-end @min-[34rem]/queue:pl-0",
                          manager &&
                            (selectable.length > 0 ||
                              selection.selected.size > 0)
                            ? "pl-[5.5rem]"
                            : "pl-[3.75rem]"
                        )}
                      >
                        <Button
                          type="button"
                          variant="ghost"
                          size="sm"
                          className="px-1.5 text-xs text-muted-foreground shadow-none"
                          onClick={() =>
                            setPortfolioItem({ brand: item.brand, id: item.id })
                          }
                        >
                          单款进销存 <ChevronRight aria-hidden="true" />
                        </Button>
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
                  )
                })}
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
                {(filters.kind !== "all" || filters.query) && (
                  <Button
                    type="button"
                    size="sm"
                    variant="outline"
                    className="mt-3 shadow-none"
                    onClick={() => {
                      setQuery("")
                      setFilters({
                        ...filters,
                        kind: "all",
                        query: "",
                        page: 1,
                      })
                    }}
                  >
                    清除筛选
                  </Button>
                )}
              </div>
            ) : null}
            {data && data.total > 0 && (
              <div className="flex flex-wrap items-center justify-between gap-2 border-t bg-muted/15 px-4 py-2.5 text-xs text-muted-foreground tabular-nums sm:px-5">
                <span>共 {fmt(data.total)} 条</span>
                {pages > 1 && (
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
                )}
              </div>
            )}
          </section>
        </TabsContent>
        <TabsContent value="portfolio" keepMounted>
          <StockPortfolioPanel
            overviewBrand={filters.brand}
            overviewBrandLabel={brandLabel}
            brands={brands}
            revision={revision}
            refreshCount={portfolioRefresh}
            onOpen={(brand, id) => setPortfolioItem({ brand, id })}
          />
        </TabsContent>
        <TabsContent value="week" keepMounted>
          <OverviewWeekTab
            brand={filters.brand}
            revision={weekRevision}
            onRetry={() => setWeekRevision((value) => value + 1)}
            onClearance={setClearanceWeek}
          />
        </TabsContent>
      </Tabs>
      {campaignOpen && (
        <CampaignDialog
          brand={filters.brand}
          canEdit={manager}
          onClose={() => setCampaignOpen(false)}
        />
      )}
      {arrivalsOpen && (
        <ArrivalsDialog
          brand={filters.brand}
          onClose={() => setArrivalsOpen(false)}
          openProduct={(id) => {
            setPortfolioItem({ brand: filters.brand, id, tab: "planning" })
            setArrivalsOpen(false)
          }}
        />
      )}
      {clearanceWeek && (
        <ClearanceWeekDialog
          brand={filters.brand}
          first={clearanceWeek}
          onClose={() => setClearanceWeek(null)}
          onSaved={() => setWeekRevision((value) => value + 1)}
        />
      )}
      {autoOpen && manager && (
        <AutoAssignmentDialog
          brand={filters.brand}
          onClose={() => setAutoOpen(false)}
        />
      )}
      {portfolioItem !== null && (
        <StockPortfolioDetail
          key={`${portfolioItem.brand}/${portfolioItem.id}`}
          brand={portfolioItem.brand}
          productId={portfolioItem.id}
          initialTab={portfolioItem.tab}
          manager={manager}
          onClose={() => setPortfolioItem(null)}
          onChanged={() => {
            selection.clear()
            setRevision((value) => value + 1)
          }}
        />
      )}
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
      {manager && batchItems && (
        <BatchTaskDialog
          mode="overview"
          brand={filters.brand}
          items={batchItems}
          onClose={() => setBatchItems(null)}
          onApplied={(report) => selection.remove(report.succeeded)}
        />
      )}
      {taskId != null && (
        <StockAlertTaskDialog id={taskId} onClose={() => setTaskId(null)} />
      )}
    </div>
  )
}
