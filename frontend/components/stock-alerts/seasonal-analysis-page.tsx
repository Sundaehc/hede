"use client"

import { useEffect, useRef, useState } from "react"
import {
  Archive,
  ChartNoAxesCombined,
  ChevronLeft,
  ChevronRight,
  CircleHelp,
  LoaderCircle,
  RefreshCw,
  Search,
  Sparkles,
} from "lucide-react"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Select } from "@/components/ui/select"
import { getSeasonalAnalysis, getStockAlertOptions } from "@/lib/api"
import { subscribeBusinessDataChanges } from "@/lib/business-data-sync"
import { useSessionQueryState } from "@/lib/session-query-state"
import {
  STOCK_SOURCE_RESOURCES,
  useStockModuleOptions,
  useStockModuleQuery,
} from "@/lib/stock-module-query"
import type { SeasonalFilters, SeasonalResponse } from "@/lib/seasonal-analysis"
import { cn } from "@/lib/utils"
import { StockListState } from "./workspace-ui"
import { SeasonalItemReviewDialog } from "./seasonal-item-review"
import { StockProductPhoto } from "./stock-product-photo"

const formatter = new Intl.NumberFormat("zh-CN", { maximumFractionDigits: 2 })
const number = (value: number | string | null | undefined) =>
  value == null ? "—" : formatter.format(Number(value))
const percent = (value: number | null | undefined) =>
  value == null ? "—" : number(value) + "%"
const panel =
  "rounded-2xl border border-border/80 bg-card/75 shadow-xs backdrop-blur-xl"

function Skeleton({ className }: { className?: string }) {
  return (
    <span
      aria-hidden="true"
      className={cn(
        "block animate-pulse rounded-md bg-muted motion-reduce:animate-none",
        className
      )}
    />
  )
}

function DetailSkeleton() {
  return (
    <div aria-hidden="true" className="min-h-80 overflow-hidden border-t">
      <div className="flex h-10 items-center gap-8 bg-muted/35 px-5">
        {["w-32", "w-24", "w-20", "w-20", "w-24", "w-20"].map((width, i) => (
          <Skeleton key={i} className={cn("h-3 shrink-0", width)} />
        ))}
      </div>
      {Array.from({ length: 5 }, (_, i) => (
        <div key={i} className="flex h-16 items-center gap-8 border-t px-5">
          <div className="w-32 shrink-0 space-y-2">
            <Skeleton className="h-3 w-24" />
            <Skeleton className="h-2.5 w-16" />
          </div>
          {["w-24", "w-20", "w-20", "w-24", "w-20"].map((width, j) => (
            <Skeleton key={j} className={cn("h-3 shrink-0", width)} />
          ))}
        </div>
      ))}
    </div>
  )
}

function defaults(): SeasonalFilters {
  const now = new Date(Date.now() + 8 * 3600_000)
  return {
    brand: "cbanner_mens",
    year: now.getUTCFullYear(),
    quarter: Math.floor(now.getUTCMonth() / 3) + 1,
    season: "",
    query: "",
    status: "all",
    page: 1,
  }
}

function Stat({
  title,
  value,
  unit,
  note,
  loading = false,
}: {
  title: string
  value: string
  unit?: string
  note: string
  loading?: boolean
}) {
  return (
    <div className={cn(panel, "p-4 sm:p-5")}>
      <p className="text-xs font-medium text-muted-foreground">{title}</p>
      <p className="mt-3 flex items-baseline gap-1.5 text-3xl font-semibold tracking-tight tabular-nums">
        {loading ? (
          <Skeleton className="my-1 h-7 w-28" />
        ) : (
          <>
            {value}
            <span className="text-xs font-normal text-muted-foreground">
              {unit}
            </span>
          </>
        )}
      </p>
      <p className="mt-2 text-xs leading-5 text-muted-foreground">{note}</p>
    </div>
  )
}

function SalesTrend({ rows }: { rows: SeasonalResponse["trend"] }) {
  const values = rows.flatMap((row) => (row.gross == null ? [] : [row.gross]))
  if (!values.length)
    return (
      <p className="flex h-40 items-center justify-center text-sm text-muted-foreground">
        暂无完整日销可绘制
      </p>
    )
  const max = Math.max(1, ...values)
  const width = 760,
    height = 124,
    padding = 8
  const segments: string[] = []
  let points: string[] = []
  for (let i = 0; i < rows.length; i++) {
    const value = rows[i].gross
    if (value == null) {
      if (points.length) segments.push(points.join(" "))
      points = []
    } else
      points.push(
        padding +
          (i * (width - padding * 2)) / Math.max(rows.length - 1, 1) +
          "," +
          (height - padding - (value * (height - padding * 2)) / max)
      )
  }
  if (points.length) segments.push(points.join(" "))
  return (
    <div className="mt-4">
      <div className="mb-2 flex justify-between text-[11px] text-muted-foreground">
        <span>销售双数 · 最高 {number(max)}</span>
        <span>缺失日期留空</span>
      </div>
      <svg
        viewBox={"0 0 " + width + " " + height}
        role="img"
        aria-label="季度新品每日销售趋势"
        className="h-32 w-full overflow-visible text-primary"
      >
        {[0, 1, 2].map((i) => (
          <line
            key={i}
            x1={padding}
            x2={width - padding}
            y1={padding + (i * (height - padding * 2)) / 2}
            y2={padding + (i * (height - padding * 2)) / 2}
            stroke="currentColor"
            strokeOpacity=".1"
            strokeDasharray="3 5"
          />
        ))}
        {segments.map((path, i) => (
          <polyline
            key={i}
            fill="none"
            stroke="currentColor"
            strokeWidth="2.5"
            strokeLinecap="round"
            strokeLinejoin="round"
            points={path}
          />
        ))}
      </svg>
      <div className="mt-1 flex justify-between text-[11px] text-muted-foreground">
        <span>{rows[0]?.date}</span>
        <span>{rows.at(-1)?.date}</span>
      </div>
    </div>
  )
}

export function SeasonalAnalysisPage() {
  const [filters, setFilters] = useSessionQueryState<SeasonalFilters>(
    "seasonal-analysis:filters",
    defaults()
  )
  const [draft, setDraft] = useState(filters)
  const [reviewId, setReviewId] = useState<number | null>(null)
  const [revision, setRevision] = useState(0)
  const force = useRef(false)
  const options = useStockModuleOptions(getStockAlertOptions)
  const { data, previousData, error, loading, refreshing } =
    useStockModuleQuery({
      group: "seasonal-analysis",
      queryKey: JSON.stringify(filters),
      previousDataKey: JSON.stringify([
        filters.brand,
        filters.year,
        filters.quarter,
        filters.season,
        filters.query,
      ]),
      revision,
      resources: STOCK_SOURCE_RESOURCES,
      factResources: STOCK_SOURCE_RESOURCES,
      load: (signal, changed) => {
        const refresh = force.current || changed
        force.current = false
        return getSeasonalAnalysis(filters, { signal, refresh })
      },
    })
  useEffect(
    () =>
      subscribeBusinessDataChanges((resources) => {
        if (
          !resources.length ||
          resources.some((resource) =>
            STOCK_SOURCE_RESOURCES.includes(resource)
          )
        ) {
          force.current = true
          setRevision((value) => value + 1)
        }
      }),
    []
  )
  const refresh = () => {
    force.current = true
    setRevision((value) => value + 1)
  }
  const shown = data ?? previousData
  const overviewLoading = !shown && loading
  const overviewBusy = refreshing && (!shown || !!data)
  const detailLoading = !data && loading
  const followup =
    filters.status === "arrivals" || filters.status === "zero"
      ? filters.status
      : null
  const statusText = error
    ? "查询未完成，请重试"
    : refreshing
      ? shown
        ? data
          ? "正在刷新当前分析…"
          : followup
            ? "正在读取跟进清单…"
            : `正在加载第 ${filters.page} 页明细…`
        : "正在查询季度分析…"
      : "日销截至 " + (shown?.sales_end ?? "未就绪")
  const summary = shown?.summary
  const review = data?.items.find((item) => item.id === reviewId)
  const followupNotes = {
    arrivals:
      "所选季度首次采购入库、当前有可售库存、档案缺少有效上市日期。点击货号查到货和销量；此清单不计入季度新品指标。",
    zero: "截至季度统计日上市满 15 天、日销完整且没有正向销售，当前仍有可售库存。点击货号查看复盘。",
  }
  const brand =
    options.data?.brands.find((item) => item.value === filters.brand)?.label ??
    filters.brand
  const pages = Math.max(
    1,
    Math.ceil((shown?.total ?? 0) / (shown?.page_size ?? 25))
  )
  const years = Array.from(
    new Set([
      filters.year,
      draft.year,
      defaults().year,
      ...(shown?.years ?? []),
    ])
  ).sort((a, b) => b - a)
  return (
    <div className="space-y-5 p-4 sm:p-6">
      <header className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <p className="mb-2 flex items-center gap-1.5 text-xs text-muted-foreground">
            <Archive className="size-3.5" aria-hidden="true" />存 / 新品经营分析
          </p>
          <h1 className="flex items-center gap-2 text-xl font-semibold">
            <ChartNoAxesCombined
              className="size-5 text-primary"
              aria-hidden="true"
            />
            季度新品分析
          </h1>
          <p className="mt-1.5 text-sm text-muted-foreground">
            从整盘到单款，查看新品的动销、销售贡献与首单表现。
          </p>
        </div>
        <Button variant="outline" onClick={refresh} disabled={refreshing}>
          <RefreshCw
            className={cn(
              "size-4",
              refreshing && "animate-spin motion-reduce:animate-none"
            )}
            aria-hidden="true"
          />
          刷新
        </Button>
      </header>
      <form
        className={cn(panel, "flex flex-wrap items-end gap-3 p-4")}
        onSubmit={(event) => {
          event.preventDefault()
          if (refreshing) return
          setFilters({
            ...draft,
            query: draft.query.trim(),
            page: 1,
            status: "all",
          })
        }}
      >
        <label className="w-40 text-xs text-muted-foreground">
          品牌
          <Select
            aria-label="品牌"
            className="mt-1.5"
            value={draft.brand}
            onChange={(event) =>
              setDraft((value) => ({
                ...value,
                brand: event.target.value,
                season: "",
              }))
            }
          >
            {!options.data?.brands.length && (
              <option value={draft.brand}>{draft.brand}</option>
            )}
            {options.data?.brands.map((item) => (
              <option key={item.value} value={item.value}>
                {item.label}
              </option>
            ))}
          </Select>
        </label>
        <label className="w-28 text-xs text-muted-foreground">
          上市年份
          <Select
            aria-label="上市年份"
            className="mt-1.5"
            value={draft.year}
            onChange={(event) =>
              setDraft((value) => ({
                ...value,
                year: Number(event.target.value),
                season: "",
              }))
            }
          >
            {years.map((year) => (
              <option key={year} value={year}>
                {year}年
              </option>
            ))}
          </Select>
        </label>
        <label className="w-32 text-xs text-muted-foreground">
          上市季度
          <Select
            aria-label="上市季度"
            className="mt-1.5"
            value={draft.quarter}
            onChange={(event) =>
              setDraft((value) => ({
                ...value,
                quarter: Number(event.target.value),
              }))
            }
          >
            {[1, 2, 3, 4].map((q) => (
              <option key={q} value={q}>
                第{q}季度
              </option>
            ))}
          </Select>
        </label>
        <label className="w-28 text-xs text-muted-foreground">
          季节
          <Select
            aria-label="季节"
            className="mt-1.5"
            value={draft.season}
            onChange={(event) =>
              setDraft((value) => ({ ...value, season: event.target.value }))
            }
          >
            <option value="">全部季节</option>
            {Array.from(new Set([draft.season, ...(shown?.seasons ?? [])]))
              .filter(Boolean)
              .map((season) => (
                <option key={season} value={season}>
                  {season}
                </option>
              ))}
          </Select>
        </label>
        <label className="min-w-44 flex-1 text-xs text-muted-foreground">
          商品搜索
          <Input
            aria-label="商品搜索"
            className="mt-1.5"
            maxLength={200}
            placeholder="货号、原始货号、品名、颜色"
            value={draft.query}
            onChange={(event) =>
              setDraft((value) => ({ ...value, query: event.target.value }))
            }
          />
        </label>
        <Button type="submit" disabled={refreshing} className="min-w-24">
          {refreshing ? (
            <LoaderCircle
              className="size-4 animate-spin motion-reduce:animate-none"
              aria-hidden="true"
            />
          ) : (
            <Search className="size-4" aria-hidden="true" />
          )}
          {refreshing ? "查询中…" : "查询"}
        </Button>
      </form>
      {options.error && (
        <p role="alert" className="text-sm text-destructive">
          品牌选项加载失败，请重新进入页面。
        </p>
      )}
      {error && (
        <div
          role="alert"
          className="flex items-center justify-between rounded-xl border border-destructive/30 bg-destructive/5 p-4 text-sm text-destructive"
        >
          <span>{error}</span>
          <Button variant="outline" size="sm" onClick={refresh}>
            重试
          </Button>
        </div>
      )}
      <div className="flex flex-wrap items-center justify-between gap-2 text-xs text-muted-foreground">
        <p>
          <span className="font-medium text-foreground">
            {brand} · {filters.year} Q{filters.quarter}
          </span>
          　按上市日期归季 · {filters.season || "全部季节"}
        </p>
        <div className="flex min-h-7 flex-wrap items-center gap-x-3 gap-y-1">
          <p
            role="status"
            aria-live="polite"
            aria-atomic="true"
            className={cn(
              "inline-flex items-center gap-1.5 rounded-full px-2.5 py-1",
              refreshing && "bg-muted/70 text-foreground"
            )}
          >
            {refreshing && (
              <LoaderCircle
                className="size-3 animate-spin motion-reduce:animate-none"
                aria-hidden="true"
              />
            )}
            {statusText}
          </p>
          {shown && <span>库存 {shown.stock_date ?? "未就绪"}</span>}
        </div>
      </div>
      {shown &&
        (shown.summary.missing_days > 0 ||
          shown.summary.sell_through_rate == null ||
          shown.missing_launch_count > 0) && (
          <div
            role="status"
            className="rounded-xl border border-amber-500/25 bg-amber-500/5 px-4 py-3 text-xs leading-6 text-amber-800 dark:text-amber-300"
          >
            {shown.summary.missing_days > 0
              ? "本季日销缺少 " +
                shown.summary.missing_days +
                " 天，暂不显示完整季度销量。"
              : ""}
            {shown.summary.sell_through_rate == null
              ? " 部分商品缺少采购入库或完整日销，整体参考售罄率暂不可算；可查看「数据待核对」。"
              : ""}
            {shown.missing_launch_count > 0
              ? " 另有 " +
                shown.missing_launch_count +
                " 项商品缺少有效上市日期，未归入季度。"
              : ""}
          </div>
        )}
      <section
        aria-label="季度经营概览"
        aria-busy={overviewBusy}
        className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4"
      >
        <Stat
          title="季度新品"
          loading={overviewLoading}
          value={number(summary?.product_count)}
          unit="款色"
          note="按商品档案款色计数，包含已售罄商品"
        />
        <Stat
          title="季度进货"
          loading={overviewLoading}
          value={number(summary?.inbound_quantity)}
          unit="双"
          note="本季新品在该季度内的正向采购入库"
        />
        <Stat
          title="新品销售占比"
          loading={overviewLoading}
          value={percent(summary?.sales_share)}
          note="新品销售双数 ÷ 同品牌同期已匹配销售双数"
        />
        <Stat
          title="整体参考售罄率"
          loading={overviewLoading}
          value={percent(summary?.sell_through_rate)}
          note="净销 ÷ 累计正向入库，含上市前备货"
        />
      </section>
      <div className="grid gap-4 xl:grid-cols-[minmax(0,1.35fr)_minmax(340px,1fr)]">
        <section
          className={cn(panel, "p-5")}
          aria-label="新品销售趋势"
          aria-busy={overviewBusy}
        >
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div>
              <h2 className="text-sm font-semibold">新品销售走势</h2>
              <p className="mt-1 text-xs text-muted-foreground">
                仅统计该季上市商品
                {overviewLoading
                  ? "，正在读取日销数据"
                  : "，截止 " + (summary?.cutoff ?? "未就绪")}
              </p>
            </div>
            <div className="flex gap-5 text-right">
              <div>
                <p className="text-[11px] text-muted-foreground">销售</p>
                <p className="text-lg font-semibold tabular-nums">
                  {overviewLoading ? (
                    <Skeleton className="my-1 h-5 w-14" />
                  ) : (
                    <>
                      {number(summary?.gross_sales)}
                      <span className="ml-1 text-xs font-normal">双</span>
                    </>
                  )}
                </p>
              </div>
              <div>
                <p className="text-[11px] text-muted-foreground">净销售</p>
                <p className="text-lg font-semibold tabular-nums">
                  {overviewLoading ? (
                    <Skeleton className="my-1 h-5 w-14" />
                  ) : (
                    <>
                      {number(summary?.net_sales)}
                      <span className="ml-1 text-xs font-normal">双</span>
                    </>
                  )}
                </p>
              </div>
            </div>
          </div>
          {overviewLoading ? (
            <div aria-hidden="true" className="mt-4 space-y-3">
              <Skeleton className="h-3 w-28" />
              <Skeleton className="h-32 w-full" />
              <div className="flex justify-between">
                <Skeleton className="h-3 w-16" />
                <Skeleton className="h-3 w-16" />
              </div>
            </div>
          ) : (
            <SalesTrend rows={shown?.trend ?? []} />
          )}
        </section>
        <section
          className={cn(panel, "p-5")}
          aria-label="上市后动销观察"
          aria-busy={overviewBusy}
        >
          <h2 className="flex items-center gap-2 text-sm font-semibold">
            <Sparkles className="size-4 text-primary" aria-hidden="true" />
            上市后动销观察
          </h2>
          <p className="mt-1 text-xs leading-5 text-muted-foreground">
            有过正向销售即算动销，未满观察期单独列出。
          </p>
          <div className="mt-4 space-y-4">
            {(
              shown?.activity ??
              [3, 7, 15].map((days) => ({
                days,
                eligible: 0,
                valid: 0,
                active: 0,
                pending: 0,
                immature: 0,
                rate: null,
              }))
            ).map((item) => (
              <div key={item.days}>
                <div className="flex items-baseline justify-between gap-3">
                  <h3 className="text-xs font-medium">前{item.days}天动销率</h3>
                  <span className="font-semibold tabular-nums">
                    {overviewLoading ? (
                      <Skeleton className="h-5 w-14" />
                    ) : (
                      percent(item.rate)
                    )}
                  </span>
                </div>
                <div className="mt-1.5 h-1.5 overflow-hidden rounded-full bg-muted">
                  <div
                    className="h-full rounded-full bg-primary/75"
                    style={{
                      width: Math.min(100, Math.max(0, item.rate ?? 0)) + "%",
                    }}
                  />
                </div>
                <p className="mt-1.5 text-[11px] text-muted-foreground">
                  {!shown ? (
                    overviewLoading ? (
                      <Skeleton className="h-3.5 w-56 max-w-full" />
                    ) : (
                      "观察数据未就绪"
                    )
                  ) : (
                    <>
                      已动销 {item.active} / 有效 {item.valid} 款色 · 未满期{" "}
                      {item.immature} · 待核对 {item.pending}
                    </>
                  )}
                </p>
              </div>
            ))}
          </div>
        </section>
      </div>
      <section
        className={cn(panel, "overflow-hidden")}
        aria-label="跨季度对比"
        aria-busy={overviewBusy}
      >
        <div className="px-5 py-4">
          <h2 className="text-sm font-semibold">跨季度对比</h2>
          <p className="mt-1 text-xs text-muted-foreground">
            各季指标按上市当季统计；「所选季度净销」观察同一批商品在当前所选季度的销售，便于比较跨季表现。
          </p>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full text-left text-xs">
            <thead className="border-y bg-muted/35 text-muted-foreground">
              <tr>
                {[
                  "上市季度",
                  "新品款色",
                  "季度进货 / 双",
                  "上市当季净销 / 双",
                  "所选季度净销 / 双",
                  "销售占比",
                  "参考售罄率",
                  "仅首单 / 款色",
                  "统计截至",
                ].map((label) => (
                  <th
                    key={label}
                    className="px-5 py-3 font-medium whitespace-nowrap"
                  >
                    {label}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {overviewLoading &&
                [1, 2, 3, 4].map((quarter) => (
                  <tr
                    key={quarter}
                    aria-hidden="true"
                    className="h-12 border-b last:border-0"
                  >
                    {Array.from({ length: 9 }, (_, i) => (
                      <td key={i} className="px-5 py-3">
                        <Skeleton className="h-3 w-16" />
                      </td>
                    ))}
                  </tr>
                ))}
              {shown?.quarters.map((row) => (
                <tr
                  key={row.quarter}
                  className={cn(
                    "border-b last:border-0",
                    row.quarter === filters.quarter && "bg-primary/5"
                  )}
                >
                  <td className="px-5 py-3">
                    <button
                      type="button"
                      disabled={refreshing}
                      onClick={() => {
                        setDraft((current) => ({
                          ...current,
                          quarter: row.quarter,
                        }))
                        setFilters((current) => ({
                          ...current,
                          quarter: row.quarter,
                          page: 1,
                        }))
                      }}
                      className="cursor-pointer rounded font-medium text-primary underline-offset-4 hover:underline focus-visible:outline-2 focus-visible:outline-ring disabled:cursor-wait disabled:opacity-50"
                    >
                      Q{row.quarter}
                    </button>
                  </td>
                  <td className="px-5 py-3 tabular-nums">
                    {number(row.product_count)}
                  </td>
                  <td className="px-5 py-3 tabular-nums">
                    {number(row.inbound_quantity)}
                  </td>
                  <td className="px-5 py-3 tabular-nums">
                    {number(row.net_sales)}
                  </td>
                  <td className="px-5 py-3 tabular-nums">
                    {number(row.period_net_sales)}
                  </td>
                  <td className="px-5 py-3 tabular-nums">
                    {percent(row.sales_share)}
                  </td>
                  <td className="px-5 py-3 tabular-nums">
                    {percent(row.sell_through_rate)}
                  </td>
                  <td className="px-5 py-3 tabular-nums">
                    {row.single_order_count}
                  </td>
                  <td className="px-5 py-3 whitespace-nowrap text-muted-foreground">
                    {row.cutoff ?? "尚未进入统计期"}
                    {row.missing_days > 0 && (
                      <span className="ml-2 text-amber-700 dark:text-amber-400">
                        缺{row.missing_days}天
                      </span>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>
      <section
        aria-label="首单与补货对比"
        aria-busy={overviewBusy}
        className="grid gap-3 md:grid-cols-3"
      >
        {overviewLoading &&
          [1, 2, 3].map((i) => (
            <div
              key={i}
              aria-hidden="true"
              className={cn(panel, "space-y-4 px-5 py-4")}
            >
              <Skeleton className="h-4 w-32" />
              <Skeleton className="h-8 w-24" />
              <Skeleton className="h-4 w-48 max-w-full" />
            </div>
          ))}
        {shown?.order_groups.map((group) => (
          <div key={group.order_state} className={cn(panel, "px-5 py-4")}>
            <div className="flex items-center justify-between gap-2">
              <h2 className="text-sm font-medium">
                {group.order_state === "single"
                  ? "仅首单商品"
                  : group.order_state === "multiple"
                    ? "有补货记录商品"
                    : "采购记录待核对"}
              </h2>
              <span className="text-xs text-muted-foreground">
                {group.product_count} 款色
              </span>
            </div>
            <p className="mt-3 text-2xl font-semibold tabular-nums">
              {percent(group.sell_through_rate)}
              <span className="ml-2 text-xs font-normal text-muted-foreground">
                参考售罄率
              </span>
            </p>
            <p className="mt-2 text-xs text-muted-foreground">
              净销量 {number(group.net_sales)} 双 · 累计入库{" "}
              {number(group.received_quantity)} 双
            </p>
          </div>
        ))}
      </section>
      <section
        className={cn(panel, "overflow-hidden")}
        aria-label="新品商品明细"
        aria-busy={refreshing}
      >
        <div className="flex flex-wrap items-center justify-between gap-3 p-4 sm:px-5">
          <div>
            <h2 className="text-sm font-semibold">新品商品明细</h2>
            <p className="mt-1 text-xs text-muted-foreground">
              {followup
                ? followupNotes[followup]
                : "销售按该季统计，库存为当前快照。点击货号看单款复盘，点击本季进货双数查入库明细。"}
            </p>
          </div>
          <div className="flex flex-wrap gap-1 rounded-xl bg-muted/50 p-1">
            {(
              [
                ["all", "全部"],
                ["single", "仅首单未补货"],
                ["pending", "数据待核对"],
                ["arrivals", "到货待补上市日期"],
                ["zero", "上市满 15 天零动销"],
              ] as const
            ).map(([status, label]) => (
              <button
                key={status}
                type="button"
                aria-pressed={filters.status === status}
                disabled={refreshing}
                onClick={() =>
                  setFilters((current) => ({ ...current, status, page: 1 }))
                }
                className={cn(
                  "cursor-pointer rounded-lg px-3 py-1.5 text-xs outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:cursor-wait disabled:opacity-50",
                  filters.status === status
                    ? "bg-card font-medium shadow-xs"
                    : "text-muted-foreground hover:text-foreground"
                )}
              >
                {label}{" "}
                <span className="ml-1 tabular-nums">
                  {(status === "arrivals" || status === "zero") &&
                  !shown?.followup_ready?.[status]
                    ? status === "zero" && followup !== "zero"
                      ? ""
                      : "—"
                    : (shown?.counts[status] ?? "—")}
                </span>
              </button>
            ))}
          </div>
        </div>
        {detailLoading ? (
          <DetailSkeleton />
        ) : !data || !shown ? (
          <StockListState
            icon={ChartNoAxesCombined}
            title={error ? "分析暂不可用" : "正在汇总季度新品"}
            description={
              error
                ? "请重试，或检查数据源是否已同步。"
                : "正在对齐上市日期、采购入库及日销数据。"
            }
            loading={loading && !error}
          />
        ) : followup && !data?.followup_ready?.[followup] ? (
          <StockListState
            icon={CircleHelp}
            title="跟进数据未就绪"
            description={
              followup === "arrivals"
                ? "等采购入库和库存快照齐备后显示。"
                : "等季度日销与库存对齐后核实零动销。"
            }
          />
        ) : !shown.items.length ? (
          <StockListState
            icon={Search}
            title="当前条件下没有商品"
            description={
              followup
                ? followupNotes[followup]
                : "可切换季度、季节或商品关键词。"
            }
          />
        ) : (
          <div className="min-h-80 overflow-x-auto">
            <table className="w-full text-left text-xs">
              <thead className="border-y bg-muted/35 text-muted-foreground">
                <tr>
                  {[
                    "商品",
                    "季节 / 上市日期",
                    "本季进货",
                    "累计入库参考",
                    "销售 / 净销",
                    "参考售罄率",
                    "当前可售库存",
                    "入库日期",
                    "核对事项",
                  ].map((label) => (
                    <th
                      key={label}
                      className="px-4 py-3 font-medium whitespace-nowrap"
                    >
                      {label}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {shown.items.map((item) => (
                  <tr
                    key={item.id}
                    className="border-b transition-colors last:border-0 hover:bg-muted/20"
                  >
                    <td className="min-w-44 px-4 py-3">
                      <div className="flex items-start gap-2.5">
                        <StockProductPhoto item={item} />
                        <div className="min-w-0 flex-1">
                          <button
                            type="button"
                            disabled={!data}
                            onClick={() => setReviewId(item.id)}
                            aria-label={`复盘 ${item.sku}`}
                            className="cursor-pointer rounded-sm font-medium text-primary underline-offset-2 outline-none hover:underline focus-visible:ring-2 focus-visible:ring-ring disabled:cursor-default disabled:text-foreground"
                          >
                            {item.sku}
                          </button>
                          <p className="mt-1 text-muted-foreground">
                            {[item.product_name, item.color]
                              .filter(Boolean)
                              .join(" · ") || "—"}
                          </p>
                          {item.original_sku && (
                            <p className="mt-1 text-[11px] text-muted-foreground">
                              原始货号 {item.original_sku}
                            </p>
                          )}
                        </div>
                      </div>
                    </td>
                    <td className="px-4 py-3 whitespace-nowrap">
                      <p>{item.season || "—"}</p>
                      <p className="mt-1 text-muted-foreground">
                        {item.launch_date ?? "待核对"}
                      </p>
                    </td>
                    <td className="px-4 py-3 tabular-nums">
                      {item.inbound_quantity == null ? (
                        "—"
                      ) : (
                        <button
                          type="button"
                          disabled={!data}
                          onClick={() => setReviewId(item.id)}
                          aria-label={`查看 ${item.sku} 本季进货明细，共 ${number(item.inbound_quantity)} 双`}
                          className="cursor-pointer rounded-sm text-primary underline decoration-primary/40 underline-offset-4 outline-none hover:decoration-current focus-visible:ring-2 focus-visible:ring-ring disabled:cursor-default disabled:text-foreground"
                        >
                          {number(item.inbound_quantity)}
                        </button>
                      )}
                    </td>
                    <td className="px-4 py-3 tabular-nums">
                      {number(item.received_quantity)}
                    </td>
                    <td className="px-4 py-3 whitespace-nowrap tabular-nums">
                      {number(item.gross_sales)} / {number(item.net_sales)}
                    </td>
                    <td className="px-4 py-3 tabular-nums">
                      {percent(item.sell_through_rate)}
                    </td>
                    <td className="px-4 py-3 tabular-nums">
                      {number(item.available_quantity)}
                    </td>
                    <td className="min-w-36 px-4 py-3 align-top whitespace-nowrap tabular-nums">
                      {item.inbound_dates?.length ? (
                        <div className="space-y-1">
                          {item.inbound_dates.slice(0, 2).map((day) => (
                            <p key={day}>{day}</p>
                          ))}
                          {item.inbound_dates.length > 2 ? (
                            <details className="text-muted-foreground">
                              <summary className="cursor-pointer rounded-sm text-[11px] outline-none focus-visible:ring-2 focus-visible:ring-ring">
                                其余 {item.inbound_dates.length - 2} 个入库日期
                              </summary>
                              <div className="mt-1 space-y-1 text-foreground">
                                {item.inbound_dates.slice(2).map((day) => (
                                  <p key={day}>{day}</p>
                                ))}
                              </div>
                            </details>
                          ) : null}
                        </div>
                      ) : (
                        <span className="text-muted-foreground">
                          {shown.purchase_ready && shown.sales_end
                            ? "暂无入库记录"
                            : "入库数据未就绪"}
                        </span>
                      )}
                    </td>
                    <td className="max-w-64 min-w-48 px-4 py-3 text-[11px] leading-5 text-muted-foreground">
                      {item.pending_reasons.join("；") || "—"}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        <div className="flex items-center justify-between gap-3 border-t px-4 py-3 text-xs text-muted-foreground">
          <span>
            共 {data?.total ?? "—"} 款色 · 每页 {data?.page_size ?? 25} 项
          </span>
          <div className="flex items-center gap-2">
            <Button
              variant="outline"
              size="sm"
              aria-label="上一页"
              disabled={!data || data.page <= 1 || refreshing}
              onClick={() =>
                setFilters((current) => ({
                  ...current,
                  page: (data?.page ?? 1) - 1,
                }))
              }
            >
              <ChevronLeft className="size-4" aria-hidden="true" />
            </Button>
            <span className="tabular-nums">
              {filters.page} / {data ? pages : "—"}
            </span>
            <Button
              variant="outline"
              size="sm"
              aria-label="下一页"
              disabled={!data || data.page >= pages || refreshing}
              onClick={() =>
                setFilters((current) => ({
                  ...current,
                  page: (data?.page ?? 1) + 1,
                }))
              }
            >
              <ChevronRight className="size-4" aria-hidden="true" />
            </Button>
          </div>
        </div>
      </section>
      {review && data && (
        <SeasonalItemReviewDialog
          key={`${filters.brand}-${filters.year}-${filters.quarter}-${review.id}`}
          item={review}
          filters={filters}
          stockDate={data.stock_date}
          revision={revision}
          onClose={() => setReviewId(null)}
        />
      )}
      <details className={cn(panel, "px-5 py-4")}>
        <summary className="cursor-pointer text-xs font-medium">
          <CircleHelp
            className="mr-1.5 inline size-4 text-muted-foreground"
            aria-hidden="true"
          />
          统计口径与数据核对
        </summary>
        <ul className="mt-3 list-disc space-y-1.5 pl-5 text-xs leading-6 text-muted-foreground">
          {shown?.source_issues.map((note) => (
            <li key={note}>{note}</li>
          ))}
        </ul>
        <p className="mt-3 text-xs text-muted-foreground">
          当前品牌缺失或无效上市日期：{shown?.missing_launch_count ?? "—"}{" "}
          项；本年新品及无有效上市日期商品候选中未唯一匹配库存编码组：
          {shown?.unmatched_stock_rows ?? "—"}
          ；本次采购候选未唯一匹配编码组：
          {shown?.unmatched_purchase_rows ?? "—"}。
        </p>
      </details>
    </div>
  )
}
