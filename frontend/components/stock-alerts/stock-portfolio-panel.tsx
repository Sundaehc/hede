"use client"

import { useRef, useState } from "react"
import dynamic from "next/dynamic"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Select } from "@/components/ui/select"
import { getStockPortfolio } from "@/lib/api"
import {
  STOCK_ALERT_RESOURCES,
  STOCK_SOURCE_RESOURCES,
  useStockModuleQuery,
} from "@/lib/stock-module-query"
import {
  portfolioStatusLabels,
  type PortfolioFilters,
  type PortfolioStatus,
} from "@/lib/stock-portfolio"

const detail = () =>
  import("./stock-portfolio-detail").then(
    (module) => module.StockPortfolioDetail
  )
export const StockPortfolioDetail = dynamic(detail)
const defaults: PortfolioFilters = {
  year: "",
  season: "",
  category: "",
  status: "",
  query: "",
  page: 1,
}
const number = new Intl.NumberFormat("zh-CN")
const label = (value: string) => (value === "__unknown__" ? "档案待补" : value)

export function StockPortfolioPanel({
  brand,
  revision,
  refreshCount,
  onOpen,
}: {
  brand: string
  revision: number
  refreshCount: number
  onOpen: (id: number) => void
}) {
  const [filters, setFilters] = useState(defaults)
  const [query, setQuery] = useState("")
  const lastRefresh = useRef(refreshCount)
  const { data, previousData, refreshing, error } = useStockModuleQuery({
    group: "stock-portfolio",
    queryKey: JSON.stringify([brand, filters]),
    previousDataKey: brand,
    revision,
    resources: STOCK_ALERT_RESOURCES,
    factResources: STOCK_SOURCE_RESOURCES,
    load: (signal, refreshFacts) => {
      const refresh = refreshFacts || refreshCount !== lastRefresh.current
      lastRefresh.current = refreshCount
      return getStockPortfolio(brand, filters, signal, refresh)
    },
  })
  const shown = data ?? previousData
  const change = (field: "year" | "season" | "category", value: string) =>
    setFilters((previous) => ({ ...previous, [field]: value, page: 1 }))
  const setStatus = (status: PortfolioStatus | "") =>
    setFilters((previous) => ({ ...previous, status, page: 1 }))
  const pages = shown
    ? Math.max(1, Math.ceil(shown.total / shown.page_size))
    : 1
  return (
    <section
      aria-labelledby="stock-portfolio"
      className="@container/portfolio scroll-mt-6 rounded-2xl border border-border/80 bg-card p-4 shadow-xs sm:p-5"
    >
      <div className="mb-3 flex flex-wrap items-baseline justify-between gap-2">
        <h2 id="stock-portfolio" className="text-base font-semibold">
          库存货盘
        </h2>
        <div className="flex flex-wrap items-baseline gap-x-3 text-xs text-muted-foreground">
          <span>
            按原始货号汇总 · {shown?.sources.stock_date ?? "库存日期待确认"}
          </span>
          <span className="min-w-24" role="status">
            {refreshing ? (shown ? "正在更新…" : "正在读取货盘…") : null}
          </span>
        </div>
      </div>
      <form
        className="grid grid-cols-3 items-end gap-2 @min-[36rem]/portfolio:grid-cols-[repeat(3,minmax(0,8rem))_minmax(0,1fr)_auto]"
        onSubmit={(event) => {
          event.preventDefault()
          setFilters((previous) => ({
            ...previous,
            query: query.trim(),
            page: 1,
          }))
        }}
      >
        {(
          [
            ["year", "款式年份", shown?.years],
            ["season", "销售季节", shown?.seasons],
            ["category", "品类", shown?.categories],
          ] as const
        ).map(([field, title, values]) => (
          <label key={field} className="min-w-0 text-xs text-muted-foreground">
            {title}
            <Select
              className="mt-1"
              value={filters[field]}
              onChange={(event) => change(field, event.target.value)}
            >
              <option value="">全部</option>
              {(values ?? (filters[field] ? [filters[field]] : [])).map(
                (value) => (
                  <option key={value} value={value}>
                    {label(value)}
                  </option>
                )
              )}
            </Select>
          </label>
        ))}
        <label className="col-span-2 min-w-0 text-xs text-muted-foreground @min-[36rem]/portfolio:col-span-1">
          查找款式
          <Input
            className="mt-1"
            placeholder="货号、原始货号或品名"
            value={query}
            onChange={(event) => setQuery(event.target.value)}
          />
        </label>
        <Button type="submit" variant="outline">
          查询
        </Button>
      </form>
      {error && (
        <p role="alert" className="mt-3 text-sm text-destructive">
          {error}
        </p>
      )}
      {shown && (
        <div aria-busy={refreshing} aria-label="库存货盘结果" role="region">
          <p className="mt-3 text-xs text-muted-foreground">
            参考售罄{" "}
            {shown.sell_through == null ? (
              "—"
            ) : (
              <>
                {shown.sell_through}% · 仅统计资料完整的{" "}
                {shown.sell_through_covered} 个有货款色
              </>
            )}
          </p>
          <div className="my-3 flex flex-wrap gap-1.5" aria-label="库存状态">
            <Button
              size="sm"
              variant={filters.status === "" ? "secondary" : "ghost"}
              aria-pressed={!filters.status}
              onClick={() => setStatus("")}
            >
              全部{" "}
              {number.format(
                Object.values(shown.totals).reduce(
                  (sum, item) => sum + (item ?? 0),
                  0
                )
              )}{" "}
              双
            </Button>
            {(Object.keys(portfolioStatusLabels) as PortfolioStatus[]).map(
              (status) => (
                <Button
                  key={status}
                  size="sm"
                  variant={filters.status === status ? "secondary" : "ghost"}
                  aria-pressed={filters.status === status}
                  onClick={() => setStatus(status)}
                >
                  {portfolioStatusLabels[status]}{" "}
                  {number.format(shown.totals[status] ?? 0)} 双
                </Button>
              )
            )}
          </div>
          {!shown.items.length ? (
            <p className="py-3 text-sm text-muted-foreground">
              {data
                ? "当前筛选没有已匹配的正可售库存。"
                : "上次查询没有已匹配的正可售库存。"}
            </p>
          ) : (
            <div className="overflow-x-auto rounded-lg border">
              <table className="w-full min-w-[34rem] text-left text-sm">
                <thead className="bg-muted/50 text-xs text-muted-foreground">
                  <tr>
                    <th className="p-2.5">原始货号 / 商品</th>
                    <th className="p-2.5">有货款色</th>
                    <th className="p-2.5">可售</th>
                    <th className="p-2.5">已确认清仓</th>
                    <th className="p-2.5">状态</th>
                  </tr>
                </thead>
                <tbody className="divide-y">
                  {shown.items.map((item) => (
                    <tr key={item.product_id} className="hover:bg-muted/30">
                      <td className="p-2.5">
                        <button
                          type="button"
                          className="rounded font-mono font-semibold text-primary underline-offset-4 focus-visible:outline-2 enabled:hover:underline"
                          disabled={!data}
                          onFocus={() => void detail()}
                          onClick={() => onOpen(item.product_id)}
                        >
                          {item.sku}
                        </button>
                        <div className="text-xs text-muted-foreground">
                          {item.product_name}
                        </div>
                      </td>
                      <td className="p-2.5 tabular-nums">{item.children}</td>
                      <td className="p-2.5 tabular-nums">
                        {number.format(item.available_quantity)}
                      </td>
                      <td className="p-2.5 tabular-nums">
                        {number.format(item.confirmed_clearance_quantity)}
                      </td>
                      <td className="p-2.5 text-xs text-muted-foreground">
                        {item.statuses
                          .map((status) => portfolioStatusLabels[status])
                          .join(" / ")}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
          {pages > 1 && (
            <div className="mt-3 flex items-center gap-2 text-sm">
              <Button
                size="sm"
                variant="outline"
                disabled={!data || shown.page <= 1}
                onClick={() => setFilters({ ...filters, page: shown.page - 1 })}
              >
                上一页
              </Button>
              <span>
                第 {shown.page} / {pages} 页
              </span>
              <Button
                size="sm"
                variant="outline"
                disabled={!data || shown.page >= pages}
                onClick={() => setFilters({ ...filters, page: shown.page + 1 })}
              >
                下一页
              </Button>
            </div>
          )}
          {shown.sources.unmatched_stock_rows > 0 && (
            <p className="mt-3 text-xs text-muted-foreground">
              源库存有未能唯一匹配的编码组，未计入货盘。
            </p>
          )}
        </div>
      )}
    </section>
  )
}
