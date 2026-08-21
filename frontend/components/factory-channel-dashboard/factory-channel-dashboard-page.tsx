"use client"

import { useCallback, useEffect, useMemo, useState } from "react"
import {
  BarChart3,
  CalendarDays,
  Factory,
  Info,
  Layers3,
  RefreshCw,
  Search,
  ShoppingBag,
  Sparkles,
  TriangleAlert,
} from "lucide-react"

import { Button } from "@/components/ui/button"
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

function MetricCard({
  label,
  value,
  hint,
  icon: Icon,
  tone,
}: {
  label: string
  value: string
  hint: string
  icon: typeof Factory
  tone: "slate" | "blue" | "violet" | "orange" | "emerald"
}) {
  const toneClass = {
    slate: "bg-slate-500/10 text-slate-600 dark:text-slate-300",
    blue: "bg-blue-500/10 text-blue-700 dark:text-blue-300",
    violet: "bg-violet-500/10 text-violet-700 dark:text-violet-300",
    orange: "bg-orange-500/10 text-orange-700 dark:text-orange-300",
    emerald: "bg-emerald-500/10 text-emerald-700 dark:text-emerald-300",
  }[tone]

  return (
    <div className="min-w-0 rounded-lg border border-border bg-card px-4 py-4 shadow-sm">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="text-xs font-medium text-muted-foreground">{label}</p>
          <p className="mt-2 truncate text-2xl font-semibold tabular-nums text-foreground">
            {value}
          </p>
        </div>
        <span className={cn("flex size-8 shrink-0 items-center justify-center rounded-md", toneClass)}>
          <Icon className="size-4" />
        </span>
      </div>
      <p className="mt-2 truncate text-xs text-muted-foreground">{hint}</p>
    </div>
  )
}

function ChannelBar({ item }: { item: FactoryChannelDashboardItem }) {
  const segments = [
    { key: "traditional", label: "传统", ratio: item.traditional_ratio, color: "bg-blue-600" },
    { key: "live", label: "直播", ratio: item.live_ratio, color: "bg-violet-500" },
    { key: "clearance", label: "清仓", ratio: item.clearance_ratio, color: "bg-orange-500" },
  ]

  return (
    <div className="min-w-0">
      <div className="flex h-2 overflow-hidden rounded-full bg-muted">
        {segments.map((segment) => (
          <span
            key={segment.key}
            className={segment.color}
            style={{ width: `${segment.ratio}%` }}
            title={`${segment.label} ${ratio(segment.ratio)}`}
          />
        ))}
      </div>
      <div className="mt-2 space-y-1 text-xs tabular-nums">
        <div className="flex items-center justify-between gap-2 text-blue-700 dark:text-blue-300">
          <span>传统</span>
          <span>{number(item.traditional_sales)} · {ratio(item.traditional_ratio)}{item.traditional_returns ? ` · 退 ${number(item.traditional_returns)}` : ""}</span>
        </div>
        <div className="flex items-center justify-between gap-2 text-violet-700 dark:text-violet-300">
          <span>直播</span>
          <span>{number(item.live_sales)} · {ratio(item.live_ratio)}{item.live_returns ? ` · 退 ${number(item.live_returns)}` : ""}</span>
        </div>
        <div className="flex items-center justify-between gap-2 text-orange-700 dark:text-orange-300">
          <span>清仓</span>
          <span>{number(item.clearance_sales)} · {ratio(item.clearance_ratio)}{item.clearance_returns ? ` · 退 ${number(item.clearance_returns)}` : ""}</span>
        </div>
      </div>
    </div>
  )
}

function SeasonTable({
  title,
  items,
}: {
  title: string
  items: FactoryChannelDashboardItem[]
}) {
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
    <section className="overflow-hidden rounded-lg border border-border bg-card shadow-sm">
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-border px-5 py-4">
        <div>
          <h2 className="text-base font-semibold text-foreground">{title}</h2>
          <p className="mt-1 text-xs text-muted-foreground">
            {items.length ? `${number(items.length)} 家工厂 · ${number(totals.styleCount)} 款` : "暂无符合条件的工厂数据"}
          </p>
        </div>
        <span className="rounded-md bg-muted px-2.5 py-1 text-xs font-medium tabular-nums text-muted-foreground">
          销量 {number(totals.totalSales)}
        </span>
      </div>
      <div className="overflow-hidden">
        <table className="w-full table-fixed border-collapse text-sm">
          <colgroup>
            <col className="w-[47%]" />
            <col className="w-[9%]" />
            <col className="w-[15%]" />
            <col className="w-[29%]" />
          </colgroup>
          <thead className="bg-muted/55 text-xs text-muted-foreground">
            <tr className="border-b border-border">
              <th className="px-5 py-3 text-left font-medium">工厂</th>
              <th className="px-3 py-3 text-center font-medium">款数</th>
              <th className="px-3 py-3 text-right font-medium">销量汇总</th>
              <th className="px-3 py-3 text-left font-medium sm:px-5">渠道占比</th>
            </tr>
          </thead>
          <tbody>
            {items.map((item) => (
              <tr key={`${item.factory_name}-${item.factory_code ?? ""}`} className="border-b border-border/70 last:border-0 hover:bg-muted/35">
                <td className="px-3 py-3 sm:px-5">
                  <div className="break-words font-medium leading-5 text-foreground">{item.factory_name}</div>
                  {item.factory_code && <div className="mt-0.5 text-xs text-muted-foreground">{item.factory_code}</div>}
                </td>
                <td className="px-3 py-3 text-center tabular-nums text-foreground">{number(item.style_count)}</td>
                <td className="px-3 py-3 text-right font-medium tabular-nums text-foreground">{number(item.total_sales)}</td>
                <td className="px-3 py-3 sm:px-5"><ChannelBar item={item} /></td>
              </tr>
            ))}
            {!items.length && (
              <tr>
                <td colSpan={4} className="px-5 py-10 text-center text-sm text-muted-foreground">
                  当前筛选条件下暂无数据
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </section>
  )
}

export function FactoryChannelDashboardPage() {
  const [brand, setBrand] = useState<DashboardBrand>(DEFAULT_BRAND)
  const [routeContextReady, setRouteContextReady] = useState(false)
  const [salesYear, setSalesYear] = useState("")
  const [factoryQuery, setFactoryQuery] = useState("")
  const [dateStart, setDateStart] = useState("")
  const [dateEnd, setDateEnd] = useState("")
  const [data, setData] = useState<FactoryChannelDashboardResponse | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState("")
  const [refreshToken, setRefreshToken] = useState(0)

  useEffect(() => {
    const params = new URLSearchParams(window.location.search)
    const nextBrand = params.get("brand")
    const nextSalesYear = params.get("sales_year")
    if (nextBrand && DASHBOARD_BRANDS.some((item) => item.key === nextBrand)) {
      setBrand(nextBrand as DashboardBrand)
    }
    if (nextSalesYear && /^\d{4}$/.test(nextSalesYear)) setSalesYear(nextSalesYear)
    setRouteContextReady(true)
  }, [])

  const loadDashboard = useCallback(async () => {
    if (!routeContextReady) return
    setLoading(true)
    setError("")
    try {
      const response = await getFactoryChannelDashboard({
        brand,
        salesYear: salesYear ? Number(salesYear) : undefined,
        dateStart: dateStart || undefined,
        dateEnd: dateEnd || undefined,
      })
      setData(response)
      if (!salesYear) setSalesYear(String(response.sales_year))
    } catch (requestError) {
      setData(null)
      setError(requestError instanceof Error ? requestError.message : "看板数据加载失败")
    } finally {
      setLoading(false)
    }
  }, [brand, dateEnd, dateStart, routeContextReady, salesYear])

  useEffect(() => {
    void loadDashboard()
  }, [loadDashboard, refreshToken])

  function resetFilters() {
    setSalesYear("")
    setFactoryQuery("")
    setDateStart("")
    setDateEnd("")
  }

  const summary = data?.summary
  const selectedBrand = DASHBOARD_BRANDS.find((item) => item.key === brand)
  const seasonalItems = data?.seasons ?? []
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
          result.total_returns += item.total_returns
          result.traditional_sales += item.traditional_sales
          result.traditional_net_sales += item.traditional_net_sales
          result.traditional_returns += item.traditional_returns
          result.live_sales += item.live_sales
          result.live_net_sales += item.live_net_sales
          result.live_returns += item.live_returns
          result.clearance_sales += item.clearance_sales
          result.clearance_net_sales += item.clearance_net_sales
          result.clearance_returns += item.clearance_returns
        }
        result.factory_count = factoryKeys.size
        return result
      },
      {
        factory_count: 0,
        style_count: 0,
        total_sales: 0,
        total_net_sales: 0,
        total_returns: 0,
        traditional_sales: 0,
        traditional_net_sales: 0,
        traditional_returns: 0,
        live_sales: 0,
        live_net_sales: 0,
        live_returns: 0,
        clearance_sales: 0,
        clearance_net_sales: 0,
        clearance_returns: 0,
      }
    )
  }, [filteredSeasons])
  const summaryTotal = filteredSummary.total_sales

  return (
    <main className="min-h-svh bg-background px-5 py-6 md:px-7">
      <div className="mx-auto max-w-[1680px]">
        <header className="flex flex-col gap-5 border-b border-border pb-5 xl:flex-row xl:items-end xl:justify-between">
          <div>
            <div className="flex items-center gap-2 text-primary">
              <BarChart3 className="size-4" />
              <span className="text-xs font-semibold tracking-wide">商品经营分析</span>
            </div>
            <h1 className="mt-2 text-2xl font-semibold tracking-normal text-foreground">工厂销量与渠道占比</h1>
          </div>
          <div className="flex items-center gap-2 text-xs text-muted-foreground">
            <CalendarDays className="size-3.5" />
            销售数据截至 {dateLabel(data?.latest_sales_date ?? null)}
          </div>
        </header>

        <section className="mt-5 rounded-lg border border-border bg-card p-4 shadow-sm">
          <div className="flex flex-col gap-3 xl:flex-row xl:items-end">
            <div className="grid flex-1 gap-3 sm:grid-cols-2 lg:grid-cols-3 2xl:grid-cols-5">
              <label className="grid gap-1.5 text-xs font-medium text-muted-foreground">
                品牌
                <Select value={brand} onChange={(event) => setBrand(event.target.value as DashboardBrand)}>
                  {DASHBOARD_BRANDS.map((item) => <option key={item.key} value={item.key}>{item.label}</option>)}
                </Select>
              </label>
              <label className="grid gap-1.5 text-xs font-medium text-muted-foreground">
                销售年份
                <Select value={salesYear} onChange={(event) => setSalesYear(event.target.value)}>
                  {!salesYear && <option value="">自动选择最新</option>}
                  {(data?.available_sales_years ?? []).map((year) => <option key={year} value={year}>{year} 年</option>)}
                </Select>
              </label>
              <label className="grid gap-1.5 text-xs font-medium text-muted-foreground">
                工厂名称
                <div className="relative">
                  <Search className="pointer-events-none absolute left-3 top-1/2 size-3.5 -translate-y-1/2 text-muted-foreground" />
                  <Input
                    value={factoryQuery}
                    onChange={(event) => setFactoryQuery(event.target.value)}
                    placeholder="名称或工厂代码"
                    className="pl-9"
                  />
                </div>
              </label>
              <label className="grid gap-1.5 text-xs font-medium text-muted-foreground">
                开始日期
                <Input className="cursor-pointer [&::-webkit-calendar-picker-indicator]:cursor-pointer" type="date" value={dateStart} onChange={(event) => setDateStart(event.target.value)} />
              </label>
              <label className="grid gap-1.5 text-xs font-medium text-muted-foreground">
                结束日期
                <Input className="cursor-pointer [&::-webkit-calendar-picker-indicator]:cursor-pointer" type="date" value={dateEnd} onChange={(event) => setDateEnd(event.target.value)} />
              </label>
            </div>
            <div className="flex shrink-0 gap-2">
              <Button type="button" variant="outline" onClick={resetFilters}>重置</Button>
              <Button type="button" onClick={() => setRefreshToken((value) => value + 1)} disabled={loading}>
                <RefreshCw className={cn("size-3.5", loading && "animate-spin")} />
                刷新
              </Button>
            </div>
          </div>
          {(salesYear === "2024" || data?.sales_year === 2024) && (
            <div className="mt-3 flex items-start gap-2 rounded-md border border-amber-500/30 bg-amber-500/10 px-3 py-2 text-xs leading-5 text-amber-800 dark:text-amber-200">
              <Info className="mt-0.5 size-3.5 shrink-0" />
              <p><span className="font-medium">2024 年数据说明：</span>当前历史数据覆盖 2024 年 5 月 1 日至 12 月 31 日，缺少 1 至 4 月，不是完整年度；年度销量和渠道占比仅代表现有数据范围。</p>
            </div>
          )}
        </section>

        {error && (
          <div className="mt-5 flex items-start gap-3 rounded-lg border border-destructive/30 bg-destructive/5 px-4 py-3 text-sm text-destructive">
            <TriangleAlert className="mt-0.5 size-4 shrink-0" />
            <span>{error}</span>
          </div>
        )}

        {loading && !data ? (
          <div className="mt-5 grid gap-4 md:grid-cols-3 xl:grid-cols-5">
            {Array.from({ length: 5 }, (_, index) => <div key={index} className="h-32 animate-pulse rounded-lg border border-border bg-muted/45" />)}
          </div>
        ) : data && summary ? (
          <>
            <section className="mt-5 grid gap-4 sm:grid-cols-2 xl:grid-cols-5">
              <MetricCard label="工厂数" value={number(filteredSummary.factory_count)} hint={`${selectedBrand?.label ?? ""}符合筛选的工厂`} icon={Factory} tone="slate" />
              <MetricCard label="季款数" value={number(filteredSummary.style_count)} hint="按去除末尾颜色的款号去重" icon={Layers3} tone="blue" />
              <MetricCard label="销量汇总" value={number(filteredSummary.total_sales)} hint={`销售 ${data.sales_year} 年 · 净销量 ${number(filteredSummary.total_net_sales)} · 退货 ${number(filteredSummary.total_returns)}`} icon={ShoppingBag} tone="slate" />
              <MetricCard label="传统赛道" value={ratio(summaryTotal ? filteredSummary.traditional_sales / summaryTotal * 100 : 0)} hint={`销量 ${number(filteredSummary.traditional_sales)}`} icon={BarChart3} tone="blue" />
              <MetricCard label="直播 / 清仓" value={`${ratio(summaryTotal ? filteredSummary.live_sales / summaryTotal * 100 : 0)} / ${ratio(summaryTotal ? filteredSummary.clearance_sales / summaryTotal * 100 : 0)}`} hint={`直播 ${number(filteredSummary.live_sales)} · 清仓 ${number(filteredSummary.clearance_sales)}`} icon={Sparkles} tone="violet" />
            </section>

            <div className="mt-5 grid gap-5 2xl:grid-cols-2">
              {filteredSeasons.map((season) => <SeasonTable key={season.key} title={season.label} items={season.items} />)}
            </div>
          </>
        ) : null}
      </div>
    </main>
  )
}
