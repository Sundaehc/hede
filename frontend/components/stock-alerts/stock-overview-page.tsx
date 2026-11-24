"use client"

import { useEffect, useRef, useState } from "react"
import dynamic from "next/dynamic"
import Link from "next/link"
import {
  Archive,
  ArrowRight,
  Box,
  CheckCircle2,
  CalendarDays,
  ChevronDown,
  ChevronLeft,
  ChevronRight,
  ClipboardList,
  Database,
  Info,
  ListPlus,
  RefreshCw,
  Search,
  SlidersHorizontal,
  TriangleAlert,
  X,
} from "lucide-react"
import { useAuth } from "@/components/auth/auth-provider"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Select } from "@/components/ui/select"
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
  InventoryBucket,
  OverviewFilters,
  OverviewItem,
  OverviewResponse,
  OverviewWeek,
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

const BatchTaskDialog = dynamic(() =>
  import("./batch-task-dialog").then((module) => module.BatchTaskDialog)
)
const recommendationKey = ({ id, kind }: OverviewItem) => `${id}/${kind}`

const defaults: OverviewFilters = {
  brand: "cbanner_womens",
  kind: "all",
  query: "",
  page: 1,
}
const labels = { ...alertKindLabels, review: "数据待核对" }
const bucketLabels: Record<InventoryBucket["key"], [string, string]> = {
  selling: ["正常销售", "bg-emerald-600 dark:bg-emerald-400"],
  next_season: ["跨季待售", "bg-chart-2"],
  size_imbalance: ["尺码不均衡", "bg-chart-3"],
  clearance: ["待清货", "bg-destructive"],
  watch: ["继续观察", "bg-chart-1"],
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
const warning = "text-amber-800 dark:text-amber-300"

const bucketDefinitions: Record<InventoryBucket["key"], string> = {
  selling: "近 7 天和 30 天非清仓净销均为正，且没有触发处理建议或待核对问题。",
  next_season: "设置了再次开售日，当前还未到开售时间。",
  size_imbalance: "核心尺码需补货，同时其他非核心尺码仍有库存。",
  clearance:
    "已生成清货建议。这里统计该款色全部可售库存，实际处理量以清单为准。",
  watch: "未归到其他类别，仍需观察近期销售和库存变化。",
  review:
    "库存或日销不可用，或存在需要核实的资料问题。仅统计可售合计为正的款色。",
}

function shareLabel(units: number, total: number | null) {
  if (!total || !units) return "0%"
  const share = units / total
  return share < 0.001
    ? "<0.1%"
    : share > 0.999 && share < 1
      ? ">99.9%"
      : percent.format(share)
}

function InventoryPanel({
  data,
  onReview,
}: {
  data: OverviewResponse
  onReview: () => void
}) {
  const { inventory, sources } = data
  const rows = [
    ["非清仓净销", inventory.regular_7, inventory.regular_30],
    ["清仓净销", inventory.clearance_7, inventory.clearance_30],
    [
      "总净销",
      inventory.regular_7 == null || inventory.clearance_7 == null
        ? null
        : inventory.regular_7 + inventory.clearance_7,
      inventory.total_30,
    ],
  ] as const
  return (
    <section
      aria-label="整盘库存"
      className={cn(panel, "@container/inventory")}
    >
      <div className="grid @min-[49rem]/inventory:grid-cols-[minmax(0,2fr)_minmax(0,3fr)]">
        <div className="border-b bg-primary/[0.06] px-5 py-5 sm:px-6 sm:py-6 @min-[49rem]/inventory:border-r @min-[49rem]/inventory:border-b-0">
          <h2 className="flex items-center gap-2 text-sm font-medium text-muted-foreground">
            <Box className="size-4 shrink-0 text-primary" aria-hidden="true" />
            整盘可售库存
          </h2>
          <p className="mt-2 flex flex-wrap items-baseline gap-x-2">
            <strong className="text-[clamp(2.1rem,6cqw,3.5rem)] leading-none font-semibold tracking-tight wrap-anywhere tabular-nums">
              {fmt(inventory.available)}
            </strong>
            {inventory.available != null && (
              <span className="text-sm text-muted-foreground">双</span>
            )}
          </p>
          <p className="mt-3 flex flex-wrap items-baseline gap-x-2 text-xs leading-5 text-muted-foreground">
            <span>预计可覆盖</span>
            <strong className="font-semibold text-foreground tabular-nums">
              {fmt(inventory.coverage_days, " 天")}
            </strong>
            <span>
              {inventory.coverage_days == null
                ? "暂缺完整库存或近销数据"
                : "按近 30 天总净销估算"}
            </span>
          </p>
        </div>
        <div className="min-w-0 px-5 py-4 sm:px-6">
          <h3 className="text-sm font-semibold">近期销售</h3>
          <table className="mt-1 w-full text-xs tabular-nums sm:text-sm">
            <caption className="sr-only">近期销售（单位：双）</caption>
            <thead className="text-muted-foreground">
              <tr className="border-b">
                <th scope="col" className="py-1.5 text-left font-normal">
                  净销（双）
                </th>
                <th scope="col" className="py-1.5 pl-2 text-right font-normal">
                  近 7 天
                </th>
                <th scope="col" className="py-1.5 pl-2 text-right font-normal">
                  近 30 天
                </th>
              </tr>
            </thead>
            <tbody className="divide-y divide-border/65">
              {rows.map(([label, recent, monthly]) => (
                <tr
                  key={label}
                  className={label === "总净销" ? "font-semibold" : undefined}
                >
                  <th scope="row" className="py-1.5 text-left font-medium">
                    {label}
                  </th>
                  <td className="py-1.5 pl-2 text-right wrap-anywhere">
                    {fmt(recent)}
                  </td>
                  <td className="py-1.5 pl-2 text-right wrap-anywhere">
                    {fmt(monthly)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
      <div className="border-t px-4 py-4 sm:px-6">
        <div className="flex flex-wrap items-center justify-between gap-x-4 gap-y-1.5">
          <div className="flex flex-wrap items-baseline gap-x-2 gap-y-0.5">
            <h3 className="text-base font-semibold tracking-tight">库存分布</h3>
            <span className="text-xs text-muted-foreground">按双数统计</span>
          </div>
          {data.counts.review > 0 && (
            <Button
              variant="outline"
              type="button"
              size="sm"
              onClick={onReview}
              className={cn("shadow-none", warning)}
            >
              <TriangleAlert aria-hidden="true" /> 查看待核对建议
              <ChevronRight aria-hidden="true" />
            </Button>
          )}
        </div>
        {inventory.buckets.length ? (
          <>
            <div
              className="mt-3 flex h-2.5 gap-px overflow-hidden rounded-full bg-muted"
              aria-hidden="true"
            >
              {inventory.buckets
                .filter(({ units }) => units > 0)
                .map(({ key, units }) => (
                  <span
                    key={key}
                    className={bucketLabels[key][1]}
                    style={{ flexGrow: units, flexBasis: 0 }}
                  />
                ))}
            </div>
            <ul className="mt-3 grid grid-cols-2 gap-px overflow-hidden rounded-lg border border-border/80 bg-border @min-[31rem]/inventory:grid-cols-3 @min-[68rem]/inventory:grid-cols-6">
              {inventory.buckets.map(({ key, units, styles }) => (
                <li
                  key={key}
                  className={cn(
                    "min-w-0 bg-card px-3 py-2.5 text-xs",
                    key === "review" &&
                      units > 0 &&
                      "bg-linear-to-b from-amber-500/5 to-amber-500/5"
                  )}
                >
                  <p className="flex flex-wrap items-center justify-between gap-x-2 gap-y-1">
                    <span className="flex items-center gap-1.5 font-medium">
                      <span
                        className={cn(
                          "size-1.5 shrink-0 rounded-full",
                          bucketLabels[key][1]
                        )}
                        aria-hidden="true"
                      />
                      {bucketLabels[key][0]}
                    </span>
                    <span
                      className={cn(
                        "tabular-nums",
                        key === "review" && units > 0
                          ? warning
                          : "text-muted-foreground"
                      )}
                    >
                      {shareLabel(units, inventory.available)}
                    </span>
                  </p>
                  <p className="mt-1.5 flex flex-wrap items-baseline gap-x-1.5 tabular-nums">
                    <strong
                      className={cn(
                        "text-base leading-5 font-semibold wrap-anywhere",
                        !units && "text-muted-foreground"
                      )}
                    >
                      {fmt(units)}
                    </strong>
                    <span className="text-muted-foreground">双</span>
                    <span className="text-muted-foreground">
                      · {fmt(styles, " 款色")}
                    </span>
                  </p>
                </li>
              ))}
            </ul>
            <details className="group mt-2.5 text-xs">
              <summary className="inline-flex min-h-7 cursor-pointer list-none items-center gap-1.5 rounded-sm text-muted-foreground underline-offset-4 hover:text-foreground hover:underline focus-visible:outline-2 focus-visible:outline-offset-2 [&::-webkit-details-marker]:hidden">
                <Info className="size-3.5" aria-hidden="true" />
                查看分类口径
                <ChevronDown
                  className="size-3.5 group-open:rotate-180"
                  aria-hidden="true"
                />
              </summary>
              <p className="mt-1 leading-5 text-muted-foreground">
                仅统计可售库存合计为正的款色，每个款色归入一类。负库存可在下方待核对建议中查看。
              </p>
              <dl className="mt-2 grid gap-3 rounded-lg bg-muted/40 p-3 @min-[34rem]/inventory:grid-cols-2 @min-[54rem]/inventory:grid-cols-3">
                {(Object.keys(bucketLabels) as InventoryBucket["key"][]).map(
                  (key) => (
                    <div key={key}>
                      <dt className="font-semibold">{bucketLabels[key][0]}</dt>
                      <dd className="mt-1 leading-5 text-muted-foreground">
                        {bucketDefinitions[key]}
                      </dd>
                    </div>
                  )
                )}
              </dl>
            </details>
          </>
        ) : (
          <p className="mt-2 text-sm text-muted-foreground">
            暂无库存分布数据。
          </p>
        )}
      </div>
      <div className="flex flex-wrap items-center gap-x-4 gap-y-1 border-t bg-muted/30 px-4 py-2.5 text-xs leading-5 text-muted-foreground sm:px-6">
        <p className="inline-flex items-center gap-1.5">
          <Database className="size-3.5 shrink-0" aria-hidden="true" />
          数据日期（北京时间）
        </p>
        <p className="flex flex-wrap gap-x-3 tabular-nums">
          <span>库存快照：{sources.stock_date ?? "待同步"}</span>
          <span>日销截至：{sources.sales_end ?? "待同步"}</span>
        </p>
        {sources.aligned && (
          <span className="inline-flex items-center gap-1 text-emerald-700 dark:text-emerald-400">
            <CheckCircle2 className="size-3.5" aria-hidden="true" /> 日期已对齐
          </span>
        )}
        {sources.unmatched_stock_rows > 0 && (
          <span>
            全部品牌有 {fmt(sources.unmatched_stock_rows)}{" "}
            个库存编码组未能唯一匹配
          </span>
        )}
      </div>
      {!sources.aligned && (
        <p
          className={cn(
            "flex items-start gap-2 border-t border-amber-500/20 bg-amber-500/5 px-4 py-2.5 text-xs leading-5 font-medium sm:px-6",
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

export function StockOverviewPage() {
  const { hasPermission } = useAuth()
  const manager = hasPermission("product.manage")
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
  const [policyOpen, setPolicyOpen] = useState(false)
  const [detail, setDetail] = useState<OverviewItem | null>(null)
  const [assignment, setAssignment] = useState<OverviewItem | null>(null)
  const [taskId, setTaskId] = useState<number | null>(null)
  const [notice, setNotice] = useState("")
  const force = useRef(false)
  const queueHeading = useRef<HTMLHeadingElement>(null)
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
  const clearQuery = () => {
    setQuery("")
    if (filters.query) setFilters({ ...filters, query: "", page: 1 })
  }
  return (
    <div className="@container/overview mx-auto max-w-[1600px] space-y-4 px-3 py-4 sm:space-y-5 sm:px-5 sm:py-5 lg:px-6">
      <header className="flex flex-wrap items-end justify-between gap-x-5 gap-y-3.5">
        <div className="min-w-0">
          <p className="mb-1.5 flex flex-wrap items-center gap-x-2 gap-y-1 text-xs text-muted-foreground">
            <Archive className="size-3.5 shrink-0" aria-hidden="true" /> 存 /
            经营分析
            {summary && (
              <span className="border-l pl-2 tabular-nums">
                业务日 <time dateTime={summary.today}>{summary.today}</time>
              </span>
            )}
          </p>
          <h1 className="text-2xl font-semibold tracking-tight sm:text-[1.75rem]">
            库存经营总览
          </h1>
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
              disabled={!data || refreshing}
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
        <InventoryPanel
          data={summary}
          onReview={() => {
            selectKind("review")
            queueHeading.current?.focus()
          }}
        />
      ) : (
        loading && (
          <div className={cn(panel, "p-5")}>
            <div
              aria-hidden="true"
              className="mb-4 grid max-w-lg grid-cols-2 items-end gap-4 motion-safe:animate-pulse"
            >
              <div className="h-12 rounded-lg bg-muted" />
              <div className="h-7 rounded-lg bg-muted" />
            </div>
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
          aria-busy={loading || refreshing}
        >
          <div className="flex flex-wrap items-center justify-between gap-x-3 gap-y-2 px-4 py-4 sm:px-5">
            <div className="min-w-0">
              <h2
                id="stock-overview-queue"
                ref={queueHeading}
                tabIndex={-1}
                className="flex scroll-mt-16 items-center gap-2 rounded-sm text-base font-semibold tracking-tight focus-visible:outline-2 focus-visible:outline-offset-2"
              >
                <ClipboardList
                  className="size-4 shrink-0 text-muted-foreground"
                  aria-hidden="true"
                />
                今日优先处理
              </h2>
              {summary ? (
                <p className="mt-1 flex flex-wrap items-baseline gap-x-3 text-xs text-muted-foreground tabular-nums">
                  <span>
                    待分配{" "}
                    <strong className="font-semibold text-foreground">
                      {fmt(summary.assignable)}
                    </strong>{" "}
                    条
                  </span>
                  <span>
                    已有待办{" "}
                    <strong className="font-semibold text-foreground">
                      {fmt(summary.in_progress)}
                    </strong>{" "}
                    条
                  </span>
                </p>
              ) : (
                <p className="mt-1 text-xs text-muted-foreground">
                  按处理类型、期限和影响数量排序
                </p>
              )}
            </div>
            <Button asChild variant="outline" size="sm" className="shadow-none">
              <Link href="/stock-alerts/tasks">
                预警待办 <ArrowRight aria-hidden="true" />
              </Link>
            </Button>
          </div>
          <div className="space-y-2.5 border-y bg-muted/25 px-4 py-3 sm:px-5">
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
              className="flex max-w-lg items-center gap-2"
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
              <p className="text-xs leading-5 wrap-anywhere text-muted-foreground">
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
                          <span
                            className={cn(
                              "rounded border px-1.5 py-0.5 text-xs font-medium",
                              decisionTone[item.kind]
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
                        "flex min-w-0 flex-wrap items-center gap-2 @min-[34rem]/queue:max-w-44 @min-[34rem]/queue:justify-end @min-[34rem]/queue:pl-0",
                        manager &&
                          (selectable.length > 0 || selection.selected.size > 0)
                          ? "pl-[5.5rem]"
                          : "pl-[3.75rem]"
                      )}
                    >
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
                    setFilters({ ...filters, kind: "all", query: "", page: 1 })
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
