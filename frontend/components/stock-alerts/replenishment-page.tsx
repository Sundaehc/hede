"use client"

import { useEffect, useRef, useState } from "react"
import {
  Archive,
  ChevronLeft,
  ChevronRight,
  PackageSearch,
  RefreshCw,
  Search,
  Settings2,
  Truck,
} from "lucide-react"
import { useAuth } from "@/components/auth/auth-provider"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Select } from "@/components/ui/select"
import { getReplenishment, getStockAlertOptions } from "@/lib/api"
import { subscribeBusinessDataChanges } from "@/lib/business-data-sync"
import { useSessionQueryState } from "@/lib/session-query-state"
import type {
  ReplenishmentFilters,
  ReplenishmentResponse,
  SupplierReplenishmentSummary,
} from "@/lib/stock-replenishment"
import { cn } from "@/lib/utils"
import { ReplenishmentRuleDialog } from "./replenishment-rule-dialog"

const DEFAULT_FILTERS: ReplenishmentFilters = {
  brand: "cbanner_mens",
  supplier: "",
  query: "",
  window_days: 30,
  deduct_transit: false,
  status: "suggested",
  page: 1,
}
const formatter = new Intl.NumberFormat("zh-CN", { maximumFractionDigits: 2 })
const number = (value: string | number) => formatter.format(Number(value))

function MinimumLabel({ summary }: { summary: SupplierReplenishmentSummary }) {
  if (summary.min_order_qty === null)
    return <span className="text-muted-foreground">未设置起订量</span>
  return (
    <span
      className={
        summary.meets_moq
          ? "text-emerald-700 dark:text-emerald-300"
          : "text-amber-800 dark:text-amber-300"
      }
    >
      {summary.meets_moq
        ? "已达起订量"
        : `未达起订量，还差 ${number(summary.moq_gap ?? 0)} 双`}
    </span>
  )
}

export function ReplenishmentPage() {
  const { hasPermission } = useAuth()
  const canManage = hasPermission("product.manage")
  const [filters, setFilters] = useSessionQueryState<ReplenishmentFilters>(
    "stock-alerts:replenishment:filters",
    DEFAULT_FILTERS
  )
  const [draft, setDraft] = useState(filters)
  const [brands, setBrands] = useState<Array<{ value: string; label: string }>>(
    []
  )
  const [optionsError, setOptionsError] = useState(false)
  const [revision, setRevision] = useState(0)
  const [editingSupplier, setEditingSupplier] = useState<string | null>(null)
  const [result, setResult] = useState<{
    key: string
    data: ReplenishmentResponse | null
    error: string | null
  } | null>(null)
  const bypassCache = useRef(false)
  const key = JSON.stringify([filters, revision])
  const loading = result?.key !== key
  const data = result?.key === key ? result.data : null
  const error = result?.key === key ? result.error : null
  const brandLabel =
    brands.find(({ value }) => value === filters.brand)?.label ?? filters.brand
  const page = data?.page ?? filters.page
  const pages = Math.max(
    1,
    Math.ceil((data?.total ?? 0) / (data?.page_size ?? 25))
  )

  useEffect(() => {
    const controller = new AbortController()
    getStockAlertOptions(controller.signal)
      .then((response) => {
        if (!controller.signal.aborted) setBrands(response.brands)
      })
      .catch(() => {
        if (!controller.signal.aborted) setOptionsError(true)
      })
    return () => controller.abort()
  }, [])

  useEffect(
    () =>
      subscribeBusinessDataChanges((resources) => {
        if (resources.length) {
          bypassCache.current = !resources.every(
            (resource) => resource === "stock-alert-rules"
          )
          setRevision((value) => value + 1)
        }
      }),
    []
  )

  useEffect(() => {
    const controller = new AbortController()
    const refresh = bypassCache.current
    bypassCache.current = false
    getReplenishment(filters, { signal: controller.signal, refresh })
      .then((response) => {
        if (!controller.signal.aborted)
          setResult({ key, data: response, error: null })
      })
      .catch((cause: unknown) => {
        if (!controller.signal.aborted)
          setResult({
            key,
            data: null,
            error:
              cause instanceof Error
                ? cause.message
                : "补货建议加载失败，请重试",
          })
      })
    return () => controller.abort()
  }, [filters, key])

  const metric = (value: number) =>
    loading || !data?.ready ? "—" : number(value)
  const edit = (supplier: string) => {
    if (canManage && supplier) setEditingSupplier(supplier)
  }

  return (
    <div className="space-y-5 p-4 sm:p-6">
      <header className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <p className="mb-2 flex items-center gap-1.5 text-xs text-muted-foreground">
            <Archive className="size-3.5" aria-hidden="true" />存 / 补货计划
          </p>
          <h1 className="flex items-center gap-2 text-xl font-semibold">
            <Truck className="size-5 text-amber-600" aria-hidden="true" />
            补货建议
          </h1>
          <p className="mt-1.5 text-sm text-muted-foreground">
            估算现有库存可售天数与尺码缺口，按供应商合计核对起订量。
          </p>
        </div>
        <div className="flex gap-2">
          {canManage && (
            <Button
              variant="outline"
              disabled={loading || !filters.supplier}
              onClick={() => edit(filters.supplier)}
            >
              <Settings2 className="size-4" aria-hidden="true" />
              设置供应商规则
            </Button>
          )}
          <Button
            variant="outline"
            disabled={loading}
            onClick={() => {
              bypassCache.current = true
              setRevision((value) => value + 1)
            }}
          >
            <RefreshCw
              className={cn("size-4", loading && "animate-spin")}
              aria-hidden="true"
            />
            刷新
          </Button>
        </div>
      </header>

      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        {(
          [
            ["suggested", "需要补货"],
            ["pending", "数据或规则待完善"],
            ["all", "全部相关商品"],
          ] as const
        ).map(([status, label]) => (
          <button
            key={status}
            type="button"
            aria-pressed={filters.status === status}
            onClick={() =>
              setFilters((current) => ({ ...current, status, page: 1 }))
            }
            className={cn(
              "rounded-xl border bg-card p-4 text-left outline-none hover:border-amber-500/60 focus-visible:ring-2 focus-visible:ring-ring",
              filters.status === status && "border-amber-500/50 bg-amber-500/5"
            )}
          >
            <p className="text-sm font-medium">{label}</p>
            <p className="mt-3 text-3xl font-semibold tabular-nums">
              {metric(data?.counts[status] ?? 0)}
              <span className="ml-1 text-xs font-normal text-muted-foreground">
                项
              </span>
            </p>
          </button>
        ))}
        <div className="rounded-xl border bg-card p-4">
          <p className="text-sm font-medium">建议补货合计</p>
          <p className="mt-3 text-3xl font-semibold tabular-nums">
            {metric(data?.suggested_quantity ?? 0)}
            <span className="ml-1 text-xs font-normal text-muted-foreground">
              双
            </span>
          </p>
          <p className="mt-2 text-xs text-muted-foreground">
            当前供应商及搜索范围的有效建议
          </p>
        </div>
      </div>

      <form
        className="space-y-3 rounded-xl border bg-card p-4"
        onSubmit={(event) => {
          event.preventDefault()
          setFilters({
            ...draft,
            query: draft.query.trim(),
            status: filters.status,
            page: 1,
          })
        }}
      >
        <div className="flex flex-wrap items-end gap-3">
          <label className="w-44 space-y-1.5 text-xs text-muted-foreground">
            <span>品牌</span>
            <Select
              aria-label="品牌"
              value={draft.brand}
              disabled={loading}
              onChange={(event) =>
                setDraft((current) => ({
                  ...current,
                  brand: event.target.value,
                  supplier: "",
                }))
              }
            >
              {!brands.length && (
                <option value={draft.brand}>{draft.brand}</option>
              )}
              {brands.map((brand) => (
                <option key={brand.value} value={brand.value}>
                  {brand.label}
                </option>
              ))}
            </Select>
          </label>
          <label className="w-52 space-y-1.5 text-xs text-muted-foreground">
            <span>供应商</span>
            <Select
              aria-label="供应商"
              value={draft.supplier}
              disabled={loading || draft.brand !== filters.brand}
              onChange={(event) =>
                setDraft((current) => ({
                  ...current,
                  supplier: event.target.value,
                }))
              }
            >
              <option value="">全部供应商</option>
              {Object.keys(data?.supplier_options ?? {}).map((supplier) => (
                <option key={supplier} value={supplier}>
                  {supplier}
                </option>
              ))}
            </Select>
          </label>
          <label className="w-32 space-y-1.5 text-xs text-muted-foreground">
            <span>销量统计</span>
            <Select
              aria-label="销量统计天数"
              value={draft.window_days}
              disabled={loading}
              onChange={(event) =>
                setDraft((current) => ({
                  ...current,
                  window_days: Number(event.target.value),
                }))
              }
            >
              {[7, 15, 30].map((days) => (
                <option key={days} value={days}>
                  近 {days} 天
                </option>
              ))}
            </Select>
          </label>
          <label className="min-w-48 flex-1 space-y-1.5 text-xs text-muted-foreground">
            <span>商品搜索</span>
            <Input
              aria-label="商品搜索"
              placeholder="货号、原始货号、品名、颜色"
              value={draft.query}
              disabled={loading}
              onChange={(event) =>
                setDraft((current) => ({
                  ...current,
                  query: event.target.value,
                }))
              }
            />
          </label>
          <Button type="submit" disabled={loading}>
            <Search className="size-4" aria-hidden="true" />
            查询
          </Button>
        </div>
        <label className="flex items-center gap-2 text-xs text-muted-foreground">
          <input
            type="checkbox"
            checked={draft.deduct_transit}
            disabled={loading}
            onChange={(event) =>
              setDraft((current) => ({
                ...current,
                deduct_transit: event.target.checked,
              }))
            }
          />
          抵扣采购在途（假设全部能按时到货，勾选后点击查询）
        </label>
        {draft.brand !== filters.brand && (
          <p className="text-xs text-muted-foreground">
            切换品牌后请先查询，再选择该品牌的供应商。
          </p>
        )}
      </form>
      {optionsError && (
        <p role="alert" className="text-sm text-destructive">
          品牌选项加载失败，请刷新页面重试。
        </p>
      )}
      {error && (
        <p
          role="alert"
          className="rounded-lg border border-destructive/30 p-3 text-sm text-destructive"
        >
          {error}
        </p>
      )}

      <details
        className="rounded-xl border bg-card"
        open={filters.supplier ? true : undefined}
        aria-busy={loading}
      >
        <summary className="cursor-pointer px-4 py-3 text-sm font-medium">
          供应商起订汇总 ·{" "}
          {loading ? "—" : (data?.supplier_summaries.length ?? 0)} 家
          <span className="ml-3 text-xs font-normal text-muted-foreground">
            按当前品牌全部商品汇总，搜索及分页不改变起订进度
          </span>
        </summary>
        <div className="h-44 overflow-auto border-t">
          <table className="w-full min-w-[720px] text-left text-xs">
            <thead className="sticky top-0 bg-muted text-muted-foreground">
              <tr>
                {[
                  "供应商",
                  "有效建议合计",
                  "合计起订量",
                  "起订进度",
                  "待完善商品",
                  "规则",
                ].map((label) => (
                  <th key={label} className="px-4 py-2 font-medium">
                    {label}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody className="divide-y">
              {data?.supplier_summaries.map((summary) => (
                <tr key={summary.supplier}>
                  <td className="px-4 py-2 font-medium">{summary.supplier}</td>
                  <td className="px-4 py-2 tabular-nums">
                    {number(summary.suggested_quantity)} 双 /{" "}
                    {summary.suggested_products} 项
                  </td>
                  <td className="px-4 py-2 tabular-nums">
                    {summary.min_order_qty === null
                      ? "未填写"
                      : `${number(summary.min_order_qty)} 双`}
                  </td>
                  <td className="px-4 py-2">
                    <MinimumLabel summary={summary} />
                  </td>
                  <td className="px-4 py-2">{summary.pending_products} 项</td>
                  <td className="px-4 py-2">
                    {canManage ? (
                      <Button
                        variant="ghost"
                        size="sm"
                        onClick={() => edit(summary.supplier)}
                      >
                        设置规则
                      </Button>
                    ) : (
                      "—"
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          {!data?.supplier_summaries.length && (
            <p className="p-4 text-sm text-muted-foreground">
              {loading ? "正在汇总供应商补货量…" : "暂无相关供应商。"}
            </p>
          )}
        </div>
      </details>

      <section
        className="overflow-hidden rounded-xl border bg-card"
        aria-busy={loading}
      >
        <div className="flex min-h-[72px] flex-wrap items-center justify-between gap-2 border-b px-4 py-3 text-xs text-muted-foreground sm:min-h-12">
          <span>
            {brandLabel} · 库存快照 {data?.stock_date ?? "—"} · 日销{" "}
            {data?.sales_start ?? "—"} 至 {data?.sales_end ?? "—"}
          </span>
          <span role="status">
            {loading
              ? "正在计算补货建议…"
              : error
                ? "加载失败"
                : `共 ${number(data?.total ?? 0)} 项 · 按建议补货量降序`}
          </span>
        </div>
        <div className="h-[min(65vh,600px)] min-h-80 overflow-auto [scrollbar-gutter:stable]">
          <table className="w-full min-w-[1400px] table-fixed text-left text-xs">
            <thead className="sticky top-0 z-10 bg-muted text-muted-foreground">
              <tr>
                {[
                  "商品 / 供应商",
                  "可售库存 / 采购在途",
                  "近期净销 / 日均净销",
                  "预计可售天数",
                  "交期内可能缺货尺码",
                  "建议补货",
                  "供应商起订进度",
                  "尺码补货明细（配比估算）",
                ].map((label, index) => (
                  <th
                    key={label}
                    className={cn(
                      "px-3 py-3 font-medium",
                      index === 0 || index === 7 ? "w-56" : "w-40",
                      [1, 2, 3, 5].includes(index) && "text-right"
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
                        {item.supplier || "未填写供应商"} ·{" "}
                        {item.size_group || "未填尺码组"}
                      </p>
                      {canManage && item.supplier && (
                        <button
                          type="button"
                          className="mt-2 text-primary underline-offset-4 hover:underline focus-visible:outline-2 focus-visible:outline-ring"
                          onClick={() => edit(item.supplier)}
                        >
                          设置补货规则
                        </button>
                      )}
                    </td>
                    <td className="px-3 py-3 text-right tabular-nums">
                      <p className="text-sm font-semibold">
                        {number(item.available_quantity)}
                      </p>
                      <p className="mt-1 text-muted-foreground">
                        在途 {number(item.purchase_in_transit)}
                      </p>
                    </td>
                    <td className="px-3 py-3 text-right tabular-nums">
                      <p>
                        {number(item.net_sales)} /{" "}
                        {item.daily_sales === null
                          ? "—"
                          : number(item.daily_sales)}
                      </p>
                      <p className="mt-1 text-muted-foreground">
                        统计 {item.observation_days} 天 · 退回{" "}
                        {number(item.sales_returns)}
                      </p>
                    </td>
                    <td className="px-3 py-3 text-right tabular-nums">
                      <p className="text-sm font-semibold">
                        {item.stock_days === null
                          ? item.daily_sales !== null &&
                            Number(item.daily_sales) === 0
                            ? "无正净销"
                            : "待核对"
                          : `${number(item.stock_days)} 天`}
                      </p>
                      <p className="mt-1 text-muted-foreground">
                        交期{" "}
                        {item.lead_days === null
                          ? "未填"
                          : `${item.lead_days} 天`}
                      </p>
                    </td>
                    <td className="px-3 py-3 leading-6">
                      {item.pending_reasons.length ? (
                        "待完善后估算"
                      ) : item.size_details.some((size) => size.at_risk) ? (
                        <span className="font-medium text-amber-800 dark:text-amber-300">
                          {item.size_details
                            .filter((size) => size.at_risk)
                            .map((size) => size.name)
                            .join("、")}
                        </span>
                      ) : (
                        "暂无"
                      )}
                    </td>
                    <td className="px-3 py-3 text-right tabular-nums">
                      <p className="text-base font-semibold">
                        {item.suggested_quantity === null
                          ? "—"
                          : `${number(item.suggested_quantity)} 双`}
                      </p>
                      {item.cover_days !== null && (
                        <p className="mt-1 text-muted-foreground">
                          到货后备货 {item.cover_days} 天
                        </p>
                      )}
                    </td>
                    <td className="px-3 py-3 leading-6">
                      {item.supplier_summary ? (
                        <>
                          <MinimumLabel summary={item.supplier_summary} />
                          <p className="mt-1 text-muted-foreground">
                            供应商合计{" "}
                            {number(item.supplier_summary.suggested_quantity)}{" "}
                            双
                          </p>
                        </>
                      ) : (
                        "—"
                      )}
                    </td>
                    <td className="px-3 py-3 leading-5">
                      {item.pending_reasons.length ? (
                        <p className="text-amber-800 dark:text-amber-300">
                          {item.pending_reasons.join("；")}
                        </p>
                      ) : (
                        <details>
                          <summary className="cursor-pointer font-medium">
                            查看 {item.size_details.length} 个尺码
                          </summary>
                          <div className="mt-2 space-y-2">
                            {item.size_details.map((size) => (
                              <div key={size.name} className="border-l-2 pl-2">
                                <p>
                                  <span className="font-medium">
                                    {size.name}
                                  </span>{" "}
                                  · 建议 {number(size.suggested_quantity)} 双
                                </p>
                                <p className="text-muted-foreground">
                                  库存 {number(size.available_quantity)} / 在途{" "}
                                  {number(size.purchase_in_transit)} / 配比{" "}
                                  {size.ratio}
                                </p>
                                <p
                                  className={
                                    size.at_risk
                                      ? "text-amber-800 dark:text-amber-300"
                                      : "text-muted-foreground"
                                  }
                                >
                                  {size.stock_days === null
                                    ? "无分配需求"
                                    : `预计可售 ${number(size.stock_days)} 天`}
                                  {size.at_risk && " · 交期内可能缺货"}
                                </p>
                              </div>
                            ))}
                          </div>
                        </details>
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
                  : filters.status === "suggested"
                    ? "暂无有效补货建议，可查看待完善商品并填写规则"
                    : "当前筛选下没有相关商品"}
              </p>
            </div>
          )}
        </div>
        <footer className="flex flex-wrap items-center justify-between gap-3 border-t px-4 py-3 text-xs text-muted-foreground">
          <span>分码需求为配比估算；建议仅供采购核对，不自动生成采购单。</span>
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
      <details className="rounded-lg border bg-card px-4 py-3 text-xs">
        <summary className="cursor-pointer font-medium text-muted-foreground">
          数据来源与计算口径
        </summary>
        <div className="mt-2 space-y-1 leading-6 text-muted-foreground">
          {(data ?? result?.data)?.source_issues.map((notice) => (
            <p key={notice}>{notice}</p>
          ))}
          {(data ?? result?.data)?.unmatched_stock_rows ? (
            <p>
              全品牌库存中有{" "}
              {number((data ?? result?.data)?.unmatched_stock_rows ?? 0)}{" "}
              组编码无法唯一匹配，未计入建议，请核对商品档案。
            </p>
          ) : null}
          <p>
            事实缓存最长 2 分钟，手动刷新立即重新查询；规则每次读取最新保存值。
          </p>
        </div>
      </details>
      {editingSupplier && (
        <ReplenishmentRuleDialog
          key={`${filters.brand}:${editingSupplier}`}
          brand={filters.brand}
          brandLabel={brandLabel}
          supplier={editingSupplier}
          onClose={() => setEditingSupplier(null)}
          onSaved={() => {
            setEditingSupplier(null)
            setRevision((value) => value + 1)
          }}
        />
      )}
    </div>
  )
}
