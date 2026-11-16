"use client"

import { useEffect, useRef, useState, type SetStateAction } from "react"
import Link from "next/link"
import {
  Archive,
  ChevronLeft,
  ChevronRight,
  CircleHelp,
  PackageSearch,
  RefreshCw,
  Search,
  Settings2,
  Sparkles,
  TrendingDown,
} from "lucide-react"
import { useAuth } from "@/components/auth/auth-provider"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Select } from "@/components/ui/select"
import { StockAlertRuleDialog } from "./stock-alert-rule-dialog"
import {
  CreateStockAlertTaskDialog,
  StockAlertTaskDialog,
  TaskStatusBadge,
} from "./task-dialog"
import { getStockAlertOptions, getStockAlerts } from "@/lib/api"
import { subscribeBusinessDataChanges } from "@/lib/business-data-sync"
import { useSessionQueryState } from "@/lib/session-query-state"
import { STOCK_ALERT_RESOURCES, STOCK_SOURCE_RESOURCES, useStockModuleOptions, useStockModuleQuery } from "@/lib/stock-module-query"
import type {
  StockAlertFilters,
  StockAlertItem,
  StockAlertKind,
  StockAlertRule,
} from "@/lib/stock-alerts"
import { cn } from "@/lib/utils"
import {
  BatchSelectionBar,
  SelectionCheckbox,
  useBatchSelection,
} from "./batch-selection"
import { BatchTaskDialog } from "./batch-task-dialog"

const DEFAULT_FILTERS: StockAlertFilters = {
  brand: "cbanner_mens",
  season: "",
  query: "",
  status: "warning",
  page: 1,
}
const numberFormatter = new Intl.NumberFormat("zh-CN", {
  maximumFractionDigits: 2,
})
const number = (value: string | number) => numberFormatter.format(Number(value))
const titles = { zero: "新品零动销预警", slow: "低售罄、滞销预警" }

export function StockAlertsPage({ kind }: { kind: StockAlertKind }) {
  // Each menu keeps its own submitted filters and pagination.
  return <StockAlertsContent key={kind} kind={kind} />
}

function StockAlertsContent({ kind }: { kind: StockAlertKind }) {
  const { hasPermission } = useAuth()
  const [filters, setStoredFilters] = useSessionQueryState<StockAlertFilters>(
    `stock-alerts:${kind}:filters`,
    DEFAULT_FILTERS
  )
  const selection = useBatchSelection<StockAlertItem>()
  const setFilters = (value: SetStateAction<StockAlertFilters>) => {
    const next = typeof value === "function" ? value(filters) : value
    if (
      JSON.stringify({ ...filters, page: 1 }) !==
      JSON.stringify({ ...next, page: 1 })
    )
      selection.clear()
    setStoredFilters(next)
  }
  const [batchItems, setBatchItems] = useState<StockAlertItem[] | null>(null)
  const [draft, setDraft] = useState({
    brand: filters.brand,
    season: filters.season,
    query: filters.query,
  })
  const options = useStockModuleOptions(getStockAlertOptions)
  const brands = options.data?.brands ?? []
  const optionsError = Boolean(options.error)
  const [revision, setRevision] = useState(0)
  const [editingRule, setEditingRule] = useState<StockAlertRule | null>(null)
  const [creatingTask, setCreatingTask] = useState<StockAlertItem | null>(null)
  const [taskId, setTaskId] = useState<number | null>(null)
  const forceRefresh = useRef(false)
  const { data, previousData, error, loading, refreshing } = useStockModuleQuery({
    group: "stock-alerts", queryKey: JSON.stringify([kind, filters]), revision,
    resources: STOCK_ALERT_RESOURCES, factResources: STOCK_SOURCE_RESOURCES,
    load: (signal, refreshFacts) => {
      const refresh = forceRefresh.current || refreshFacts
      forceRefresh.current = false
      return getStockAlerts(filters, kind, { signal, refresh })
    },
  })
  const selectable =
    data?.items.filter((item) => item.warning && !item.task) ?? []
  const selectedOnPage = selectable.filter((item) =>
    selection.selected.has(item.id)
  ).length
  const Icon = kind === "zero" ? Sparkles : TrendingDown
  const brandLabel =
    brands.find((brand) => brand.value === filters.brand)?.label ??
    filters.brand

  useEffect(
    () =>
      subscribeBusinessDataChanges((resources) => {
        if (resources.length) {
          forceRefresh.current = !resources.every(
            (resource) =>
              resource === "stock-alert-rules" ||
              resource === "stock-alert-tasks"
          )
          setRevision((value) => value + 1)
        }
      }),
    []
  )

  const refresh = () => {
    forceRefresh.current = true
    setRevision((value) => value + 1)
  }
  const page = data?.page ?? filters.page
  const pages = Math.max(
    1,
    Math.ceil((data?.total ?? 0) / (data?.page_size ?? 25))
  )
  const sourceLabel =
    data?.rule.source === "season"
      ? "季节专属规则"
      : data?.rule.source === "brand"
        ? "品牌通用规则"
        : "默认规则"
  const value = (input: string | number) =>
    loading || !data?.ready ? "—" : number(input)

  return (
    <div className="space-y-5 p-4 sm:p-6">
      <header className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <p className="mb-2 flex items-center gap-1.5 text-xs text-muted-foreground">
            <Archive className="size-3.5" aria-hidden="true" />存 / 库存预警
          </p>
          <h1 className="flex items-center gap-2 text-xl font-semibold">
            <Icon className="size-5 text-amber-600" aria-hidden="true" />
            {titles[kind]}
          </h1>
          <p className="mt-1.5 text-sm text-muted-foreground">
            {kind === "zero"
              ? "关注已上市、有库存但尚未产生销售的商品。"
              : "结合上市时间、入库与销售表现，及时跟进积压商品。"}
          </p>
        </div>
        <div className="flex items-center gap-2">
          {hasPermission("product.manage") && (
            <Button
              variant="outline"
              disabled={loading || !data}
              onClick={() => {
                if (data) setEditingRule(data.rule)
              }}
            >
              <Settings2 className="size-4" aria-hidden="true" />
              设置规则
            </Button>
          )}
          <Button variant="outline" disabled={refreshing} onClick={refresh}>
            <RefreshCw
              className={cn("size-4", refreshing && "animate-spin")}
              aria-hidden="true"
            />
            刷新
          </Button>
        </div>
      </header>

      <div className="grid gap-3 sm:grid-cols-3">
        <button
          type="button"
          aria-pressed={filters.status === "warning"}
          onClick={() =>
            setFilters((current) => ({
              ...current,
              status: "warning",
              page: 1,
            }))
          }
          className={cn(
            "rounded-xl border bg-card p-4 text-left outline-none hover:border-amber-500/60 focus-visible:ring-2 focus-visible:ring-ring",
            filters.status === "warning" && "border-amber-500/40 bg-amber-500/5"
          )}
        >
          <p className="text-sm font-medium">待跟进商品</p>
          <p className="mt-3 text-3xl font-semibold tabular-nums">
            {value(data?.counts.warning ?? 0)}
            <span className="ml-1 text-xs font-normal text-muted-foreground">
              项
            </span>
          </p>
          <p className="mt-2 text-xs text-muted-foreground">
            符合当前品牌、季节规则的全部商品
          </p>
        </button>
        <div className="rounded-xl border bg-card p-4">
          <p className="text-sm font-medium">预警可售库存</p>
          <p className="mt-3 text-3xl font-semibold tabular-nums">
            {value(data?.warning_stock ?? 0)}
            <span className="ml-1 text-xs font-normal text-muted-foreground">
              双
            </span>
          </p>
          <p className="mt-2 text-xs text-muted-foreground">
            当前筛选下待跟进商品的可售库存合计
          </p>
        </div>
        <button
          type="button"
          aria-pressed={filters.status === "pending"}
          onClick={() =>
            setFilters((current) => ({
              ...current,
              status: "pending",
              page: 1,
            }))
          }
          className={cn(
            "rounded-xl border bg-card p-4 text-left outline-none hover:border-primary/50 focus-visible:ring-2 focus-visible:ring-ring",
            filters.status === "pending" && "border-primary/60 bg-primary/5"
          )}
        >
          <p className="flex items-center justify-between text-sm font-medium">
            数据待核对
            <CircleHelp
              className="size-4 text-muted-foreground"
              aria-hidden="true"
            />
          </p>
          <p className="mt-3 text-3xl font-semibold tabular-nums">
            {value(data?.counts.pending ?? 0)}
            <span className="ml-1 text-xs font-normal text-muted-foreground">
              项
            </span>
          </p>
          <p className="mt-2 text-xs text-muted-foreground">
            日期或日销不完整的商品单独列出
          </p>
        </button>
      </div>

      <form
        className="flex flex-wrap items-end gap-3 rounded-xl border bg-card p-4"
        onSubmit={(event) => {
          event.preventDefault()
          setFilters({
            ...draft,
            query: draft.query.trim(),
            status: "warning",
            page: 1,
          })
        }}
      >
        <label className="w-44 text-xs text-muted-foreground">
          品牌
          <Select
            aria-label="品牌"
            className="mt-1.5"
            value={draft.brand}
            onChange={(event) =>
              setDraft((current) => ({
                ...current,
                brand: event.target.value,
                season: "",
              }))
            }
          >
            {!brands.some((brand) => brand.value === draft.brand) && (
              <option value={draft.brand}>
                {draft.brand === "cbanner_mens" ? "千百度男鞋" : draft.brand}
              </option>
            )}
            {brands.map((brand) => (
              <option key={brand.value} value={brand.value}>
                {brand.label}
              </option>
            ))}
          </Select>
        </label>
        <label className="w-36 text-xs text-muted-foreground">
          季节
          <Select
            aria-label="季节"
            className="mt-1.5"
            value={draft.season}
            onChange={(event) =>
              setDraft((current) => ({
                ...current,
                season: event.target.value,
              }))
            }
          >
            <option value="">全部季节</option>
            {(data ?? previousData)?.seasons.map((season) => (
              <option key={season} value={season}>
                {season}
              </option>
            ))}
          </Select>
        </label>
        <label className="min-w-48 flex-1 text-xs text-muted-foreground">
          商品搜索
          <Input
            aria-label="商品搜索"
            className="mt-1.5"
            value={draft.query}
            maxLength={200}
            placeholder="货号、原始货号、品名、颜色"
            onChange={(event) =>
              setDraft((current) => ({ ...current, query: event.target.value }))
            }
          />
        </label>
        <Button type="submit">
          <Search className="size-4" aria-hidden="true" />
          查询
        </Button>
        <Button
          type="button"
          variant="ghost"
          onClick={() => {
            const cleared = { brand: filters.brand, season: "", query: "" }
            setDraft(cleared)
            setFilters({ ...cleared, status: "warning", page: 1 })
          }}
        >
          清空
        </Button>
      </form>
      {optionsError && (
        <p role="alert" className="text-sm text-destructive">
          品牌选项加载失败，请重新进入页面。
        </p>
      )}
      {error && (
        <div
          role="alert"
          className="flex items-center justify-between gap-3 rounded-lg border border-destructive/30 p-4 text-sm text-destructive"
        >
          <span>{error}</span>
          <Button size="sm" variant="outline" onClick={refresh}>
            重试
          </Button>
        </div>
      )}

      {data && (
        <div className="space-y-2 rounded-lg border-l-4 border-amber-500 bg-amber-500/5 px-4 py-3 text-xs leading-6">
          <p className="font-medium">
            {brandLabel} · {filters.season || "全部季节"} · {sourceLabel}
            ：上市满 {data.rule.age_days} 天
            {kind === "zero"
              ? "，上市后无销售"
              : `，参考售罄率低于 ${number(data.rule.rate)}%`}
            ，且有可售库存。
          </p>
          <p className="text-muted-foreground">
            库存快照 {data.stock_date ?? "未接入"} · 日销截止{" "}
            {data.sales_end ?? "未接入"} ·
            上市时间取商品档案，平台上架时间尚未接入。
            {kind === "slow" && "采购退货数据不全，售罄率为参考值。"}
          </p>
          {!filters.season && (
            <p className="text-muted-foreground">
              全部季节列表按各商品的季节专属规则优先计算；未设置的季节使用品牌通用规则。
            </p>
          )}
        </div>
      )}

      <section
        className="overflow-hidden rounded-xl border bg-card"
        aria-label="预警商品列表"
        aria-busy={refreshing}
      >
        <div className="flex flex-wrap items-center justify-between gap-2 border-b px-4 py-3">
          <h2 className="shrink-0 text-sm font-semibold">
            {filters.status === "warning" ? "待跟进清单" : "数据待核对清单"}
          </h2>
          <Button asChild variant="outline" size="sm">
            <Link href="/stock-alerts/tasks">预警待办</Link>
          </Button>
          <span
            role="status"
            className="w-full text-xs text-muted-foreground sm:w-auto"
          >
            {refreshing
              ? "正在核对库存及日销…"
              : error
                ? "加载失败"
                : `共 ${number(data?.total ?? 0)} 项 · 按可售库存降序`}
          </span>
        </div>
        {hasPermission("product.manage") && (
          <BatchSelectionBar
            count={selection.selected.size}
            error={selection.error}
            onClear={selection.clear}
          >
            <Button
              size="sm"
              disabled={!selection.selected.size}
              onClick={() =>
                setBatchItems(Array.from(selection.selected.values()))
              }
            >
              批量分配待办
            </Button>
          </BatchSelectionBar>
        )}
        <div className="h-[min(65vh,600px)] min-h-80 overflow-auto [scrollbar-gutter:stable]">
          <table className="w-full min-w-[1160px] table-fixed text-left text-xs">
            <thead className="sticky top-0 z-10 bg-muted text-muted-foreground">
              <tr>
                {hasPermission("product.manage") && (
                  <th className="w-12 px-3 py-3">
                    <SelectionCheckbox
                      label="选择本页可分配商品"
                      checked={
                        selectable.length > 0 &&
                        selectedOnPage === selectable.length
                      }
                      mixed={
                        selectedOnPage > 0 && selectedOnPage < selectable.length
                      }
                      disabled={loading || !selectable.length}
                      onChange={(checked) =>
                        selection.select(selectable, checked)
                      }
                    />
                  </th>
                )}
                {[
                  "商品 / 年份季节",
                  "上市日期 / 天数",
                  "采购首入 / 最近入库",
                  "可售库存",
                  "采购入库参考",
                  "上市后销售 / 净销",
                  kind === "zero" ? "最近销售" : "参考售罄率",
                  "规则及跟进建议",
                  "处理待办",
                ].map((label, index) => (
                  <th
                    key={label}
                    className={cn(
                      "px-3 py-3 font-medium",
                      index === 0 || index === 7 ? "w-56" : "w-36",
                      index >= 3 && index <= 6 && "text-right"
                    )}
                  >
                    {label}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody className="divide-y">
              {!loading &&
                !error &&
                data?.items.map((item) => (
                  <tr key={item.id} className="align-top hover:bg-muted/30">
                    {hasPermission("product.manage") && (
                      <td className="px-3 py-3">
                        <SelectionCheckbox
                          label={`选择 ${item.sku}（#${item.id}）`}
                          checked={selection.selected.has(item.id)}
                          disabled={
                            (!item.warning || !!item.task) &&
                            !selection.selected.has(item.id)
                          }
                          onChange={(checked) =>
                            selection.select([item], checked)
                          }
                        />
                      </td>
                    )}
                    <td className="px-3 py-3">
                      <p className="font-mono font-medium break-all">
                        {item.sku}
                      </p>
                      <p className="mt-1 text-muted-foreground">
                        {[item.product_name, item.color]
                          .filter(Boolean)
                          .join(" · ") || "—"}
                      </p>
                      <p className="mt-1 text-muted-foreground">
                        {[item.year, item.season].filter(Boolean).join(" / ") ||
                          "—"}
                      </p>
                    </td>
                    <td className="px-3 py-3 tabular-nums">
                      {item.launch_date ?? "未填写"}
                      <p className="mt-1 text-muted-foreground">
                        {item.listed_days === null
                          ? "待核对"
                          : `${item.listed_days} 天`}
                      </p>
                    </td>
                    <td className="px-3 py-3 tabular-nums">
                      {item.first_inbound_date ?? "—"}
                      <p className="mt-1 text-muted-foreground">
                        {item.last_inbound_date ?? "—"}
                      </p>
                    </td>
                    <td className="px-3 py-3 text-right text-sm font-semibold tabular-nums">
                      {number(item.available_quantity)}
                    </td>
                    <td className="px-3 py-3 text-right tabular-nums">
                      {number(item.purchase_received_reference)}
                    </td>
                    <td className="px-3 py-3 text-right tabular-nums">
                      {number(item.gross_sales)} / {number(item.net_sales)}
                      <p className="mt-1 text-muted-foreground">
                        退回 {number(item.sales_returns)}
                      </p>
                    </td>
                    <td className="px-3 py-3 text-right font-medium tabular-nums">
                      {kind === "zero"
                        ? (item.last_sales_date ?? "—")
                        : item.sell_through_rate === null
                          ? "—"
                          : `${number(item.sell_through_rate)}%`}
                    </td>
                    <td className="px-3 py-3 leading-5">
                      {item.pending_reasons.length ? (
                        <p className="text-amber-800 dark:text-amber-300">
                          {item.pending_reasons.join("；")}
                        </p>
                      ) : (
                        <>
                          <p className="font-medium">
                            上市满 {item.rule_age_days} 天
                            {kind === "slow" &&
                              ` / 低于 ${number(item.rule_rate)}%`}
                          </p>
                          <p className="mt-1 text-muted-foreground">
                            {kind === "zero"
                              ? "核对渠道铺货、商品上架及销售数据"
                              : "核对补货及退货记录，评估调拨或促销"}
                          </p>
                        </>
                      )}
                    </td>
                    <td className="px-3 py-3">
                      {item.task ? (
                        <div className="space-y-2">
                          <TaskStatusBadge task={item.task} />
                          <p className="text-muted-foreground">
                            {item.task.assignee_name} · {item.task.due_date}
                          </p>
                          <Button
                            size="sm"
                            variant="outline"
                            onClick={() => setTaskId(item.task!.id)}
                          >
                            查看待办
                          </Button>
                        </div>
                      ) : item.warning && hasPermission("product.manage") ? (
                        <Button
                          size="sm"
                          variant="outline"
                          onClick={() => setCreatingTask(item)}
                        >
                          分配待办
                        </Button>
                      ) : (
                        <span className="text-muted-foreground">—</span>
                      )}
                    </td>
                  </tr>
                ))}
            </tbody>
          </table>
          {!loading && !error && data?.items.length === 0 && (
            <div className="flex h-56 flex-col items-center justify-center gap-2 text-sm text-muted-foreground">
              <PackageSearch className="size-8 opacity-50" aria-hidden="true" />
              <p>
                {!data.ready
                  ? "数据源未就绪，请先补齐库存及日销"
                  : "当前筛选下没有此类商品"}
              </p>
            </div>
          )}
        </div>
        <footer className="flex flex-wrap items-center justify-between gap-3 border-t px-4 py-3 text-xs text-muted-foreground">
          <span>缺少日销或上市日期的商品进入待核对清单</span>
          <div className="flex items-center gap-3">
            <Button
              variant="outline"
              size="icon-sm"
              aria-label="上一页"
              disabled={loading || page <= 1}
              onClick={() =>
                setFilters((current) => ({ ...current, page: page - 1 }))
              }
            >
              <ChevronLeft className="size-4" />
            </Button>
            <span className="tabular-nums">
              {page} / {pages}
            </span>
            <Button
              variant="outline"
              size="icon-sm"
              aria-label="下一页"
              disabled={loading || page >= pages}
              onClick={() =>
                setFilters((current) => ({ ...current, page: page + 1 }))
              }
            >
              <ChevronRight className="size-4" />
            </Button>
          </div>
        </footer>
      </section>
      {data && (
        <details className="rounded-lg border bg-card px-4 py-3 text-xs">
          <summary className="cursor-pointer font-medium text-muted-foreground">
            数据来源与计算口径
          </summary>
          <div className="mt-2 space-y-1 leading-6 text-muted-foreground">
            {data.source_issues.map((issue) => (
              <p key={issue}>{issue}</p>
            ))}
            {data.unmatched_stock_rows > 0 && (
              <p>
                全部品牌库存中有 {number(data.unmatched_stock_rows)}{" "}
                组编码无法唯一匹配商品档案，未纳入预警。
              </p>
            )}
            <p>
              缓存最长 2
              分钟，刷新立即重查。预警自动计算，不自动变更商品、库存或单据。
            </p>
          </div>
        </details>
      )}
      {editingRule && (
        <StockAlertRuleDialog
          brand={filters.brand}
          brandLabel={brandLabel}
          season={filters.season}
          kind={kind}
          rule={editingRule}
          onClose={() => setEditingRule(null)}
          onSaved={() => {
            setEditingRule(null)
            setRevision((value) => value + 1)
          }}
        />
      )}
      {creatingTask && (
        <CreateStockAlertTaskDialog
          item={creatingTask}
          kind={kind}
          brandLabel={brandLabel}
          onClose={() => setCreatingTask(null)}
          onCreated={(task) => {
            setCreatingTask(null)
            setTaskId(task.id)
          }}
        />
      )}
      {batchItems && (
        <BatchTaskDialog
          mode="create"
          items={batchItems}
          brand={filters.brand}
          kind={kind}
          onClose={() => setBatchItems(null)}
          onApplied={(report) => {
            selection.remove(report.succeeded)
            setRevision((value) => value + 1)
          }}
        />
      )}
      {taskId !== null && (
        <StockAlertTaskDialog
          key={taskId}
          id={taskId}
          onClose={() => setTaskId(null)}
        />
      )}
    </div>
  )
}
