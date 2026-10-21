"use client"

import { useSessionQueryState } from "@/lib/session-query-state"

import { useEffect, useId, useMemo, useRef, useState } from "react"
import {
  ArrowLeftRight,
  BarChart3,
  CalendarDays,
  ChevronDown,
  Clock3,
  Factory,
  Layers3,
  RefreshCw,
  Search,
  ShoppingBag,
  SlidersHorizontal,
  Snowflake,
  Sparkles,
  Sun,
  TriangleAlert,
  X,
} from "lucide-react"

import { Button } from "@/components/ui/button"
import { DateRangeControl } from "@/components/ui/date-range-control"
import { Input } from "@/components/ui/input"
import { Select } from "@/components/ui/select"
import { getFactoryChannelDashboard } from "@/lib/api"
import { BRANDS, type BrandKey } from "@/lib/brands"
import type {
  FactoryChannelDashboardItem,
  FactoryChannelDashboardResponse,
} from "@/lib/types"
import { cn } from "@/lib/utils"

type DashboardBrand = Exclude<BrandKey, "all">

const DASHBOARD_BRANDS = BRANDS.filter((brand) => brand.key !== "all") as Array<{
  key: DashboardBrand
  label: string
}>
const DEFAULT_BRAND: DashboardBrand = "cbanner_mens"
const EMPTY_SEASONS: FactoryChannelDashboardResponse["seasons"] = []

const numberFormatter = new Intl.NumberFormat("zh-CN")

function number(value: number) {
  return numberFormatter.format(value)
}

function ratio(value: number) {
  return `${value.toFixed(1)}%`
}

function dateLabel(value: string | null) {
  if (!value) return "暂无销售数据"
  const date = new Date(`${value}T00:00:00`)
  return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, "0")}-${String(date.getDate()).padStart(2, "0")}`
}

function compactDateRanges(values: string[]) {
  const dates = [...new Set(values)].sort()
  if (!dates.length) return ""
  const groups: Array<{ start: string; end: string }> = []
  for (const value of dates) {
    const previous = groups.at(-1)
    if (!previous) {
      groups.push({ start: value, end: value })
      continue
    }
    const nextDate = new Date(`${previous.end}T00:00:00`)
    nextDate.setDate(nextDate.getDate() + 1)
    const nextValue = [
      nextDate.getFullYear(),
      String(nextDate.getMonth() + 1).padStart(2, "0"),
      String(nextDate.getDate()).padStart(2, "0"),
    ].join("-")
    if (value === nextValue) previous.end = value
    else groups.push({ start: value, end: value })
  }
  const visibleGroups = groups.slice(0, 5)
  const text = visibleGroups
    .map((group) => group.start === group.end ? group.start : `${group.start} 至 ${group.end}`)
    .join("、")
  return groups.length > visibleGroups.length ? `${text} 等` : text
}

function MetricCard({
  label,
  value,
  hint,
  icon: Icon,
  tone,
  prominent = false,
}: {
  label: string
  value: string
  hint: string
  icon: typeof Factory
  tone: "slate" | "blue" | "violet"
  prominent?: boolean
}) {
  const toneClass = {
    slate: "bg-slate-500/10 text-slate-600 dark:text-slate-300",
    blue: "bg-blue-500/10 text-blue-700 dark:text-blue-300",
    violet: "bg-violet-500/10 text-violet-700 dark:text-violet-300",
  }[tone]

  return (
    <div className={cn(
      "min-w-0 rounded-xl border bg-card px-3.5 py-3 sm:px-4",
      prominent ? "col-span-2 border-blue-500/25 bg-blue-500/[0.04] sm:col-span-1" : "border-border"
    )}>
      <div className="flex items-center gap-2">
        <span className={cn("flex size-6 shrink-0 items-center justify-center rounded-md", toneClass)}>
          <Icon className="size-3.5" aria-hidden="true" />
        </span>
        <p className="text-xs font-medium text-muted-foreground">{label}</p>
      </div>
      <p className={cn(
        "mt-2 break-words text-[clamp(1.125rem,1.65vw,1.75rem)] leading-tight font-semibold tracking-tight tabular-nums",
        prominent ? "text-blue-700 dark:text-blue-300" : "text-foreground"
      )}>{value}</p>
      <p className="mt-1.5 text-xs leading-5 text-muted-foreground">{hint}</p>
    </div>
  )
}

type ChannelBreakdown = Pick<FactoryChannelDashboardItem,
  "traditional_sales" | "live_sales" | "clearance_sales" |
  "traditional_ratio" | "live_ratio" | "clearance_ratio"
>

function ChannelBar({ item }: { item: ChannelBreakdown }) {
  const segments = [
    { key: "traditional", label: "传统", sales: item.traditional_sales, ratio: item.traditional_ratio, color: "bg-blue-600", textColor: "text-blue-700 dark:text-blue-300" },
    { key: "live", label: "直播", sales: item.live_sales, ratio: item.live_ratio, color: "bg-violet-500", textColor: "text-violet-700 dark:text-violet-300" },
    { key: "clearance", label: "清仓", sales: item.clearance_sales, ratio: item.clearance_ratio, color: "bg-orange-500", textColor: "text-orange-700 dark:text-orange-300" },
  ]

  return (
    <div className="min-w-0">
      <div className="flex h-1.5 overflow-hidden rounded-full bg-muted" aria-hidden="true">
        {segments.map((segment) => (
          <span
            key={segment.key}
            className={segment.color}
            style={{ width: `${segment.ratio}%` }}
            title={`${segment.label} ${ratio(segment.ratio)}`}
          />
        ))}
      </div>
      <div className="mt-1.5 grid grid-cols-3 gap-2 text-[11px] leading-4 tabular-nums">
        {segments.map((segment) => (
          <div key={segment.key} className="min-w-0">
            <p className={cn("flex items-center gap-1 whitespace-nowrap", segment.textColor)}>
              <span>{segment.label}</span>
              <span>{ratio(segment.ratio)}</span>
            </p>
            <p className="mt-0.5 font-medium text-foreground">{number(segment.sales)}</p>
          </div>
        ))}
      </div>
    </div>
  )
}

function SeasonTable({
  title,
  items,
  seasonKey,
}: {
  title: string
  items: FactoryChannelDashboardItem[]
  seasonKey: FactoryChannelDashboardResponse["seasons"][number]["key"]
}) {
  const headingId = useId()
  const isSpringSummer = seasonKey === "spring_summer"
  const SeasonIcon = isSpringSummer ? Sun : Snowflake
  const totals = useMemo(
    () =>
      items.reduce(
        (summary, item) => ({
          styleCount: summary.styleCount + item.style_count,
          totalSales: summary.totalSales + item.total_sales,
          traditionalSales: summary.traditionalSales + item.traditional_sales,
          liveSales: summary.liveSales + item.live_sales,
          clearanceSales: summary.clearanceSales + item.clearance_sales,
        }),
        { styleCount: 0, totalSales: 0, traditionalSales: 0, liveSales: 0, clearanceSales: 0 }
      ),
    [items]
  )

  return (
    <section aria-labelledby={headingId} className="min-w-0 overflow-hidden rounded-xl border border-border bg-card">
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-border px-4 py-3">
        <div className="flex min-w-0 items-center gap-2.5">
          <span className={cn(
            "flex size-9 shrink-0 items-center justify-center rounded-lg",
            isSpringSummer ? "bg-emerald-500/10 text-emerald-700 dark:text-emerald-300" : "bg-amber-500/10 text-amber-700 dark:text-amber-300"
          )}>
            <SeasonIcon className="size-4" aria-hidden="true" />
          </span>
          <div>
            <h2 id={headingId} className="text-sm font-semibold text-foreground">{title}</h2>
            <p className="mt-0.5 text-xs text-muted-foreground">
              {items.length ? `${number(items.length)} 家工厂 · ${number(totals.styleCount)} 款` : "暂无符合条件的工厂数据"}
            </p>
          </div>
        </div>
        <p className="text-xs text-muted-foreground">销量 <span className="ml-1 text-base font-semibold tabular-nums text-foreground">{number(totals.totalSales)}</span></p>
      </div>
      <p className="flex items-center justify-end gap-1.5 border-b border-border/60 px-4 py-1.5 text-[11px] text-muted-foreground sm:hidden">
        <ArrowLeftRight className="size-3" aria-hidden="true" />左右滑动查看完整渠道数据
      </p>
      <div role="region" aria-label={`${title}工厂明细`} tabIndex={0} className="max-h-[580px] overflow-auto outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-ring">
        <table aria-label={`${title}销量与渠道占比`} className="w-full min-w-[560px] table-fixed border-separate border-spacing-0 text-sm">
          <colgroup>
            <col className="w-[30%]" />
            <col className="w-[10%]" />
            <col className="w-[17%]" />
            <col className="w-[43%]" />
          </colgroup>
          <thead className="sticky top-0 z-10 bg-muted text-xs text-muted-foreground">
            <tr>
              <th scope="col" className="border-b border-border px-4 py-2.5 text-left font-medium">工厂 / 代码</th>
              <th scope="col" className="border-b border-border px-2 py-2.5 text-right font-medium">款数</th>
              <th scope="col" className="border-b border-border px-3 py-2.5 text-right font-medium">销量汇总</th>
              <th scope="col" className="border-b border-border px-4 py-2.5 text-left font-medium">渠道占比 / 销量</th>
            </tr>
          </thead>
          <tbody>
            {items.map((item) => (
              <tr key={`${item.factory_name}-${item.factory_code ?? ""}`} className="transition-colors even:bg-muted/15 hover:bg-muted/50 [&>td]:border-b [&>td]:border-border/60">
                <td className="px-4 py-2.5">
                  <div className="break-words font-medium leading-5 text-foreground">{item.factory_name}</div>
                  {item.factory_code && <div className="mt-0.5 font-mono text-[11px] text-muted-foreground">{item.factory_code}</div>}
                </td>
                <td className="px-2 py-2.5 text-right tabular-nums text-muted-foreground">{number(item.style_count)}</td>
                <td className="px-3 py-2.5 text-right font-semibold tabular-nums text-foreground">{number(item.total_sales)}</td>
                <td className="px-4 py-2.5"><ChannelBar item={item} /></td>
              </tr>
            ))}
            {!items.length && (
              <tr>
                <td colSpan={4} className="px-5 py-12 text-center text-sm text-muted-foreground">
                  <Factory className="mx-auto mb-3 size-7 text-muted-foreground/50" aria-hidden="true" />
                  <p className="font-medium text-foreground">当前筛选条件下暂无数据</p>
                  <p className="mt-1 text-xs">可调整品牌、销售年份或工厂名称后重试</p>
                </td>
              </tr>
            )}
          </tbody>
          {items.length > 0 && (
            <tfoot className="sticky bottom-0 bg-muted text-xs font-medium tabular-nums">
              <tr className="[&>td]:border-t [&>td]:border-border">
                <th scope="row" className="border-t border-border px-4 py-2.5 text-left">本季合计</th>
                <td className="px-2 py-2.5 text-right">{number(totals.styleCount)}</td>
                <td className="px-3 py-2.5 text-right">{number(totals.totalSales)}</td>
                <td className="px-4 py-2.5">
                  <ChannelBar item={{
                    traditional_sales: totals.traditionalSales,
                    live_sales: totals.liveSales,
                    clearance_sales: totals.clearanceSales,
                    traditional_ratio: totals.totalSales ? totals.traditionalSales / totals.totalSales * 100 : 0,
                    live_ratio: totals.totalSales ? totals.liveSales / totals.totalSales * 100 : 0,
                    clearance_ratio: totals.totalSales ? totals.clearanceSales / totals.totalSales * 100 : 0,
                  }} />
                </td>
              </tr>
            </tfoot>
          )}
        </table>
      </div>
    </section>
  )
}

export function FactoryChannelDashboardPage() {
  const factorySearchId = useId()
  const [brand, setBrand] = useSessionQueryState<DashboardBrand>("factory-channel-dashboard:brand", DEFAULT_BRAND)
  const [appliedRouteContext, setAppliedRouteContext] = useSessionQueryState("factory-channel-dashboard:routeContext", "")
  const routeContextInitializedRef = useRef(false)
  const [routeContextReady, setRouteContextReady] = useState(false)
  const [salesYear, setSalesYear] = useSessionQueryState("factory-channel-dashboard:salesYear", "")
  const [factoryQuery, setFactoryQuery] = useSessionQueryState("factory-channel-dashboard:factoryQuery", "")
  const [dateStart, setDateStart] = useSessionQueryState("factory-channel-dashboard:dateStart", "")
  const [dateEnd, setDateEnd] = useSessionQueryState("factory-channel-dashboard:dateEnd", "")
  const [data, setData] = useState<FactoryChannelDashboardResponse | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState("")
  const [refreshToken, setRefreshToken] = useState(0)
  const autoSelectedQueryRef = useRef("")
  const handledRefreshRef = useRef(0)

  useEffect(() => {
    if (routeContextInitializedRef.current) return
    routeContextInitializedRef.current = true
    const params = new URLSearchParams(window.location.search)
    if (window.location.search && appliedRouteContext === window.location.search) {
      setRouteContextReady(true)
      return
    }
    setAppliedRouteContext(window.location.search)
    const nextBrand = params.get("brand")
    const nextSalesYear = params.get("sales_year")
    if (nextBrand && DASHBOARD_BRANDS.some((item) => item.key === nextBrand)) {
      setBrand(nextBrand as DashboardBrand)
    }
    if (nextSalesYear && /^\d{4}$/.test(nextSalesYear)) setSalesYear(nextSalesYear)
    setRouteContextReady(true)
  }, [appliedRouteContext, setAppliedRouteContext, setBrand, setSalesYear])

  useEffect(() => {
    if (!routeContextReady) return
    const queryKey = JSON.stringify([brand, salesYear, dateStart, dateEnd, refreshToken])
    if (autoSelectedQueryRef.current === queryKey) {
      autoSelectedQueryRef.current = ""
      return
    }
    autoSelectedQueryRef.current = ""
    const controller = new AbortController()
    const forceRefresh = refreshToken !== handledRefreshRef.current
    handledRefreshRef.current = refreshToken
    setLoading(true)
    setError("")
    async function loadDashboard() {
      try {
        const response = await getFactoryChannelDashboard({
          brand,
          salesYear: salesYear ? Number(salesYear) : undefined,
          dateStart: dateStart || undefined,
          dateEnd: dateEnd || undefined,
          cacheBust: forceRefresh ? String(refreshToken) : undefined,
        }, { signal: controller.signal })
        if (controller.signal.aborted) return
        setData(response)
        if (!salesYear) {
          const selectedYear = String(response.sales_year)
          autoSelectedQueryRef.current = JSON.stringify([brand, selectedYear, dateStart, dateEnd, refreshToken])
          setSalesYear(selectedYear)
        }
      } catch (requestError) {
        if (controller.signal.aborted) return
        setData(null)
        setError(requestError instanceof Error ? requestError.message : "看板数据加载失败")
      } finally {
        if (!controller.signal.aborted) setLoading(false)
      }
    }
    void loadDashboard()
    return () => controller.abort()
  }, [brand, dateEnd, dateStart, refreshToken, routeContextReady, salesYear, setSalesYear])

  function resetFilters() {
    setSalesYear("")
    setFactoryQuery("")
    setDateStart("")
    setDateEnd("")
  }

  const summary = data?.summary
  const selectedBrand = DASHBOARD_BRANDS.find((item) => item.key === brand)
  const seasonalItems = data?.seasons ?? EMPTY_SEASONS
  const normalizedFactoryQuery = factoryQuery.trim().toLocaleLowerCase()
  const filteredSeasons = useMemo(
    () => seasonalItems.map((season) => ({
      ...season,
      items: normalizedFactoryQuery
        ? season.items.filter((item) => (
          item.factory_name.toLocaleLowerCase().includes(normalizedFactoryQuery) ||
          item.factory_code?.toLocaleLowerCase().includes(normalizedFactoryQuery)
        ))
        : season.items,
    })),
    [normalizedFactoryQuery, seasonalItems]
  )
  const filteredSummary = useMemo(() => {
    const factoryKeys = new Set<string>()
    return filteredSeasons.reduce(
      (result, season) => {
        for (const item of season.items) {
          factoryKeys.add(`${item.factory_name}|${item.factory_code ?? ""}`)
          result.style_count += item.style_count
          result.total_sales += item.total_sales
          result.total_net_sales += item.total_net_sales
          result.traditional_sales += item.traditional_sales
          result.traditional_net_sales += item.traditional_net_sales
          result.live_sales += item.live_sales
          result.live_net_sales += item.live_net_sales
          result.clearance_sales += item.clearance_sales
          result.clearance_net_sales += item.clearance_net_sales
        }
        result.factory_count = factoryKeys.size
        return result
      },
      {
        factory_count: 0,
        style_count: 0,
        total_sales: 0,
        total_net_sales: 0,
        traditional_sales: 0,
        traditional_net_sales: 0,
        live_sales: 0,
        live_net_sales: 0,
        clearance_sales: 0,
        clearance_net_sales: 0,
      }
    )
  }, [filteredSeasons])
  const summaryTotal = filteredSummary.total_sales
  const salesDateCoverage = data?.sales_date_coverage
  const incompleteSources = salesDateCoverage?.sources.filter((source) => source.missing_date_count > 0) ?? []
  const pendingRefreshSources = salesDateCoverage?.sources.filter((source) => source.pending_refresh_date_count > 0) ?? []

  return (
    <main className="min-h-svh bg-background px-3 py-4 sm:px-5 lg:px-6">
      <div className="@container mx-auto max-w-[1680px]">
        <header className="flex flex-wrap items-center justify-between gap-3">
          <div className="flex min-w-0 items-center gap-3">
            <span className="flex size-10 shrink-0 items-center justify-center rounded-xl border border-border bg-card text-foreground">
              <Factory className="size-5" aria-hidden="true" />
            </span>
            <div>
              <div className="flex flex-wrap items-center gap-2">
                <h1 className="text-xl font-semibold tracking-tight text-foreground">工厂渠道看板</h1>
                <span className="rounded-md border border-border bg-card px-1.5 py-0.5 text-[11px] font-medium text-muted-foreground">商品经营分析</span>
              </div>
              <p className="mt-0.5 text-xs leading-5 text-muted-foreground">按季节对比工厂销量与传统、直播、清仓渠道结构</p>
            </div>
          </div>
          <div role="status" className="flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
            <span className="flex items-center gap-1.5 rounded-md border border-border bg-card px-2.5 py-1.5 tabular-nums">
              <CalendarDays className="size-3.5" aria-hidden="true" />
              {data?.latest_sales_date ? `销售数据截至 ${dateLabel(data.latest_sales_date)}` : loading ? "正在加载销售数据" : "暂无销售数据"}
            </span>
            {loading && data && <span>正在更新，暂显示上次结果</span>}
          </div>
        </header>

        <section aria-label="看板筛选" className="mt-4 rounded-xl border border-border bg-card px-3 py-3 sm:px-4">
          <div className="flex flex-wrap items-end gap-x-4 gap-y-3">
            <div className="grid w-full min-w-0 grid-cols-2 gap-3 sm:grid-cols-[minmax(0,1fr)_minmax(0,0.8fr)_minmax(0,1.2fr)] xl:w-auto xl:flex-1">
              <label className="grid gap-1.5 text-xs font-medium text-muted-foreground">
                品牌
                <Select className="h-8 min-w-0 py-1 text-xs text-foreground shadow-none" value={brand} onChange={(event) => setBrand(event.target.value as DashboardBrand)}>
                  {DASHBOARD_BRANDS.map((item) => <option key={item.key} value={item.key}>{item.label}</option>)}
                </Select>
              </label>
              <label className="grid gap-1.5 text-xs font-medium text-muted-foreground">
                销售年份
                <Select className="h-8 min-w-0 py-1 text-xs text-foreground shadow-none" value={salesYear} onChange={(event) => setSalesYear(event.target.value)}>
                  {!salesYear && <option value="">自动选择最新</option>}
                  {(data?.available_sales_years ?? []).map((year) => <option key={year} value={year}>{year} 年</option>)}
                </Select>
              </label>
              <div className="col-span-2 grid min-w-0 gap-1.5 text-xs font-medium text-muted-foreground sm:col-span-1">
                <label htmlFor={factorySearchId}>工厂名称</label>
                <div className="relative">
                  <Search className="pointer-events-none absolute left-2.5 top-1/2 size-3.5 -translate-y-1/2 text-muted-foreground" aria-hidden="true" />
                  <Input
                    id={factorySearchId}
                    value={factoryQuery}
                    onChange={(event) => setFactoryQuery(event.target.value)}
                    placeholder="名称或工厂代码"
                    className="h-8 pr-8 pl-8 text-xs text-foreground shadow-none"
                  />
                  {factoryQuery && (
                    <button type="button" aria-label="清除工厂筛选" onClick={() => setFactoryQuery("")} className="absolute top-1/2 right-1 flex size-6 -translate-y-1/2 cursor-pointer items-center justify-center rounded-md text-muted-foreground hover:bg-muted hover:text-foreground focus-visible:outline-2 focus-visible:outline-ring">
                      <X className="size-3.5" aria-hidden="true" />
                    </button>
                  )}
                </div>
              </div>
            </div>
            <DateRangeControl size="sm" start={dateStart} end={dateEnd} onStartChange={setDateStart} onEndChange={setDateEnd} />
            <div className="ml-auto flex shrink-0 gap-2">
              <Button type="button" variant="outline" onClick={resetFilters} className="text-xs shadow-none">重置</Button>
              <Button type="button" onClick={() => setRefreshToken((value) => value + 1)} disabled={loading}>
                <RefreshCw className={cn("size-3.5", loading && "motion-safe:animate-spin")} aria-hidden="true" />
                刷新
              </Button>
            </div>
          </div>
        </section>

        {!!pendingRefreshSources.length && (
          <details className="group mt-3 rounded-lg border border-sky-500/25 bg-sky-500/5 text-sky-950 dark:text-sky-100">
            <summary className="flex cursor-pointer list-none flex-wrap items-center gap-2 px-3 py-2 text-xs focus-visible:rounded-lg focus-visible:outline-2 focus-visible:outline-ring [&::-webkit-details-marker]:hidden">
              <Clock3 className="size-3.5 shrink-0 text-sky-600 dark:text-sky-300" aria-hidden="true" />
              <span className="font-semibold">昨日销售数据等待今日自动更新</span>
              <span className="text-sky-900/75 dark:text-sky-100/75">正常刷新窗口内，不计为缺失</span>
              <span className="ml-auto flex items-center gap-1">查看详情<ChevronDown className="size-3.5 transition-transform group-open:rotate-180" aria-hidden="true" /></span>
            </summary>
            <div className="border-t border-sky-500/15 px-3 py-2 text-xs leading-5">
              <p className="text-sky-900/80 dark:text-sky-100/75">
                {compactDateRanges(salesDateCoverage?.pending_refresh_dates ?? [])} 尚在正常刷新窗口内，暂不计为数据缺失。
              </p>
              <div className="mt-1.5 grid gap-x-6 gap-y-0.5 lg:grid-cols-2">
                {pendingRefreshSources.map((source) => (
                  <p key={source.source} className="min-w-0 break-words">
                    <span className="font-medium">{source.label}：</span>
                    每日 {source.refresh_starts_at} 开始，预计 {source.refresh_expected_by} 前完成
                  </p>
                ))}
              </div>
            </div>
          </details>
        )}

        {!!salesDateCoverage?.missing_date_count && (
          <details className="group mt-3 rounded-lg border border-amber-500/30 bg-amber-500/5 text-amber-900 dark:text-amber-100">
            <summary className="flex cursor-pointer list-none flex-wrap items-center gap-2 px-3 py-2 text-xs focus-visible:rounded-lg focus-visible:outline-2 focus-visible:outline-ring [&::-webkit-details-marker]:hidden">
              <TriangleAlert className="size-3.5 shrink-0 text-amber-600 dark:text-amber-300" aria-hidden="true" />
              <span className="font-semibold">销售数据存在缺失日期</span>
              <span>共 {salesDateCoverage.missing_date_count} 天不完整，结果仅基于已有数据</span>
              <span className="ml-auto flex items-center gap-1">查看详情<ChevronDown className="size-3.5 transition-transform group-open:rotate-180" aria-hidden="true" /></span>
            </summary>
            <div className="border-t border-amber-500/15 px-3 py-2 text-xs leading-5">
              <p className="text-amber-800/90 dark:text-amber-100/80">
                统计范围 {salesDateCoverage.expected_start} 至 {salesDateCoverage.expected_end}，共 {salesDateCoverage.missing_date_count} 个日期的数据不完整，当前销量及渠道占比仅基于已有数据。
              </p>
              <div className="mt-1.5 grid gap-x-6 gap-y-0.5 lg:grid-cols-2">
                {incompleteSources.map((source) => (
                  <p key={source.source} className="min-w-0 break-words">
                    <span className="font-medium">{source.label}缺 {source.missing_date_count} 天：</span>
                    {compactDateRanges(source.missing_dates)}
                  </p>
                ))}
              </div>
            </div>
          </details>
        )}

        {error && (
          <div role="alert" className="mt-3 flex items-start gap-3 rounded-lg border border-destructive/30 bg-destructive/5 px-4 py-3 text-sm text-destructive">
            <TriangleAlert className="mt-0.5 size-4 shrink-0" aria-hidden="true" />
            <span>{error}</span>
          </div>
        )}

        {loading && !data ? (
          <section aria-label="正在加载看板" aria-busy="true" className="mt-4 space-y-4">
            <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 xl:grid-cols-5">
              {Array.from({ length: 5 }, (_, index) => <div key={index} className="h-28 rounded-xl border border-border bg-muted/45 motion-safe:animate-pulse" />)}
            </div>
            <div className="grid gap-4 @min-[1140px]:grid-cols-2">
              {[0, 1].map((index) => <div key={index} className="h-72 rounded-xl border border-border bg-muted/30 motion-safe:animate-pulse" />)}
            </div>
          </section>
        ) : data && summary ? (
          <div aria-busy={loading} className={cn("mt-4 space-y-4 transition-opacity motion-reduce:transition-none", loading && "opacity-60")}>
            <section aria-label="销量概览" className="grid grid-cols-2 gap-3 sm:grid-cols-3 xl:grid-cols-5">
              <MetricCard
                label="销量汇总"
                value={number(filteredSummary.total_sales)}
                hint={`销售 ${data.sales_year} 年 · 净销量 ${number(filteredSummary.total_net_sales)}`}
                icon={ShoppingBag}
                tone="blue"
                prominent
              />
              <MetricCard label="工厂数" value={number(filteredSummary.factory_count)} hint={`${selectedBrand?.label ?? ""}符合筛选的工厂`} icon={Factory} tone="slate" />
              <MetricCard label="季款数" value={number(filteredSummary.style_count)} hint="按去除末尾颜色的款号去重" icon={Layers3} tone="blue" />
              <MetricCard label="传统赛道" value={ratio(summaryTotal ? filteredSummary.traditional_sales / summaryTotal * 100 : 0)} hint={`销量 ${number(filteredSummary.traditional_sales)}`} icon={BarChart3} tone="blue" />
              <MetricCard label="直播 / 清仓" value={`${ratio(summaryTotal ? filteredSummary.live_sales / summaryTotal * 100 : 0)} / ${ratio(summaryTotal ? filteredSummary.clearance_sales / summaryTotal * 100 : 0)}`} hint={`直播 ${number(filteredSummary.live_sales)} · 清仓 ${number(filteredSummary.clearance_sales)}`} icon={Sparkles} tone="violet" />
            </section>

            <div>
              <div className="mb-2.5 flex flex-wrap items-center justify-between gap-2 px-0.5">
                <div className="flex items-center gap-2">
                  <h2 className="text-sm font-semibold text-foreground">分季工厂明细</h2>
                  {normalizedFactoryQuery && <span className="flex items-center gap-1 text-xs text-muted-foreground"><SlidersHorizontal className="size-3" aria-hidden="true" />已按工厂筛选</span>}
                </div>
                <div aria-label="渠道颜色图例" className="flex items-center gap-3 text-[11px] text-muted-foreground">
                  <span className="flex items-center gap-1.5"><span className="size-1.5 rounded-full bg-blue-600" />传统</span>
                  <span className="flex items-center gap-1.5"><span className="size-1.5 rounded-full bg-violet-500" />直播</span>
                  <span className="flex items-center gap-1.5"><span className="size-1.5 rounded-full bg-orange-500" />清仓</span>
                </div>
              </div>
              <div className="grid items-start gap-4 @min-[1140px]:grid-cols-2">
                {filteredSeasons.map((season) => <SeasonTable key={season.key} seasonKey={season.key} title={season.label} items={season.items} />)}
              </div>
              {!filteredSeasons.length && (
                <div className="rounded-xl border border-dashed border-border bg-card px-4 py-12 text-center">
                  <Factory className="mx-auto mb-3 size-7 text-muted-foreground/50" aria-hidden="true" />
                  <p className="text-sm font-medium">暂无工厂渠道数据</p>
                  <p className="mt-1 text-xs text-muted-foreground">请调整品牌、销售年份或日期范围</p>
                </div>
              )}
            </div>
          </div>
        ) : null}
      </div>
    </main>
  )
}
