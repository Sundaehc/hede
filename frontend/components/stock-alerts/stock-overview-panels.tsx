import {
  CalendarDays,
  ChartNoAxesColumn,
  CheckCircle2,
  ChevronDown,
  ChevronRight,
  Database,
  Info,
  TriangleAlert,
} from "lucide-react"
import { Button } from "@/components/ui/button"
import type {
  InventoryBucket,
  OverviewResponse,
  OverviewWeek,
} from "@/lib/stock-overview"
import { cn } from "@/lib/utils"

export const overviewPanel =
  "min-w-0 overflow-hidden rounded-xl border border-border/80 bg-card text-card-foreground"
export const overviewWarning = "text-amber-800 dark:text-amber-300"

const number = new Intl.NumberFormat("zh-CN", { maximumFractionDigits: 1 })
const percent = new Intl.NumberFormat("zh-CN", {
  maximumFractionDigits: 1,
  style: "percent",
})
export const formatOverview = (
  value: number | null | undefined,
  suffix = ""
) => (value == null ? "—" : number.format(value) + suffix)

const buckets: Record<
  InventoryBucket["key"],
  { name: string; color: string; definition: string }
> = {
  selling: {
    name: "正常销售",
    color: "bg-emerald-600 dark:bg-emerald-400",
    definition: "近 7 天和 30 天非清仓净销均为正，且没有处理建议或待核对问题。",
  },
  next_season: {
    name: "跨季待售",
    color: "bg-chart-2",
    definition: "已设置再次开售日，当前还未到开售时间。",
  },
  size_imbalance: {
    name: "尺码不均衡",
    color: "bg-chart-3",
    definition: "核心尺码需补货，同时其他尺码仍有库存。",
  },
  clearance: {
    name: "待清货",
    color: "bg-destructive",
    definition:
      "已生成清货建议。此处统计该款色全部可售库存，实际处理量以清单为准。",
  },
  watch: {
    name: "继续观察",
    color: "bg-chart-1",
    definition: "暂未归到其他类别，仍需观察销售和库存变化。",
  },
  review: {
    name: "数据待核对",
    color: "bg-amber-500 dark:bg-amber-400",
    definition: "库存、日销或档案资料需要核实。此处只统计可售合计为正的款色。",
  },
}
const statuses = Object.values(buckets)
const sectionTitle = "flex min-w-0 items-center gap-2 text-sm font-semibold"
const muted = "text-xs text-muted-foreground"
const numeric = "text-right tabular-nums"

function shareLabel(units: number, total: number | null) {
  if (!total || !units) return "0%"
  const share = units / total
  return share < 0.001
    ? "<0.1%"
    : share > 0.999 && share < 1
      ? ">99.9%"
      : percent.format(share)
}

function InventoryDistribution({
  inventory,
  canReview,
  onReview,
}: {
  inventory: OverviewResponse["inventory"]
  canReview: boolean
  onReview: () => void
}) {
  const hasStock = inventory.buckets.some(({ units }) => units > 0)
  return (
    <div className="min-w-0 px-4 py-4 sm:px-5">
      <div className="flex flex-wrap items-center justify-between gap-x-2 gap-y-1">
        <div className="flex items-baseline gap-2">
          <h3 className={sectionTitle}>库存分布</h3>
          <span className={muted}>按可售双数</span>
        </div>
        {canReview && (
          <Button
            variant="ghost"
            size="sm"
            onClick={onReview}
            className={cn("gap-1 px-2 shadow-none", overviewWarning)}
          >
            <TriangleAlert aria-hidden="true" /> 查看待核对建议{" "}
            <ChevronRight aria-hidden="true" />
          </Button>
        )}
      </div>
      {inventory.buckets.length ? (
        <>
          <div
            className="mt-3 flex h-2.5 overflow-hidden rounded-full bg-muted"
            aria-hidden="true"
          >
            {hasStock &&
              inventory.buckets
                .filter(({ units }) => units > 0)
                .map(({ key, units }) => (
                  <span
                    key={key}
                    className={buckets[key].color}
                    style={{ flex: units }}
                  />
                ))}
          </div>
          <ul className="mt-3 grid grid-cols-2 gap-x-3 gap-y-1 @min-[54rem]/inventory:grid-cols-3">
            {inventory.buckets.map(({ key, units, styles }) => (
              <li
                key={key}
                className="min-w-0 border-b border-border/65 px-0.5 py-2.5"
              >
                <div className="flex items-start justify-between gap-1.5">
                  <span className="flex min-w-0 items-start gap-1.5 text-xs font-medium">
                    <span
                      className={cn(
                        "mt-1.5 size-1.5 shrink-0 rounded-full",
                        buckets[key].color
                      )}
                      aria-hidden="true"
                    />
                    <span>{buckets[key].name}</span>
                  </span>
                  <span
                    className={cn(
                      "shrink-0 text-xs tabular-nums",
                      key === "review" && units > 0
                        ? overviewWarning
                        : "text-muted-foreground"
                    )}
                  >
                    {shareLabel(units, inventory.available)}
                  </span>
                </div>
                <p className="mt-1 flex flex-wrap items-baseline gap-x-1.5 text-xs text-muted-foreground tabular-nums">
                  <span
                    className={cn(
                      "font-mono text-base font-semibold wrap-anywhere",
                      units > 0 && "text-foreground"
                    )}
                  >
                    {formatOverview(units)}
                  </span>
                  <span>双</span>
                  <span>· {formatOverview(styles, " 款色")}</span>
                </p>
              </li>
            ))}
          </ul>
          <details className="group mt-2.5">
            <summary className="inline-flex min-h-7 cursor-pointer list-none items-center gap-1.5 rounded-sm text-xs text-muted-foreground underline-offset-4 hover:text-foreground hover:underline focus-visible:outline-2 focus-visible:outline-offset-2 [&::-webkit-details-marker]:hidden">
              <Info className="size-3.5" aria-hidden="true" /> 查看分类口径
              <ChevronDown
                className="size-3.5 group-open:rotate-180"
                aria-hidden="true"
              />
            </summary>
            <p className="mt-1 text-xs leading-relaxed text-muted-foreground">
              每个款色只归入一类。负库存可在待核对建议中查看。
            </p>
            <dl className="mt-2 grid gap-3 rounded-lg bg-muted/45 p-3 text-xs sm:grid-cols-2">
              {statuses.map(({ name, definition }) => (
                <div key={name}>
                  <dt className="font-medium">{name}</dt>
                  <dd className="mt-1 leading-relaxed text-muted-foreground">
                    {definition}
                  </dd>
                </div>
              ))}
            </dl>
          </details>
        </>
      ) : (
        <p className="mt-3 text-sm text-muted-foreground">暂无库存分布数据。</p>
      )}
    </div>
  )
}

function RecentSales({
  inventory,
}: {
  inventory: OverviewResponse["inventory"]
}) {
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
    <div className="min-w-0 border-t border-border/80 px-4 py-4 sm:px-5 @min-[48rem]/inventory:border-t-0 @min-[48rem]/inventory:border-l">
      <h3 className={sectionTitle}>
        <ChartNoAxesColumn
          className="size-4 shrink-0 text-muted-foreground"
          aria-hidden="true"
        />{" "}
        近期销售
      </h3>
      <table className="mt-2 w-full text-xs sm:text-sm">
        <caption className="sr-only">近期销售（单位：双）</caption>
        <thead className="text-xs text-muted-foreground">
          <tr className="border-b border-border/80">
            <th scope="col" className="py-2 text-left font-medium">
              净销（双）
            </th>
            <th scope="col" className="py-2 pl-1.5 text-right font-medium">
              近 7 天
            </th>
            <th scope="col" className="py-2 pl-1.5 text-right font-medium">
              近 30 天
            </th>
          </tr>
        </thead>
        <tbody className="divide-y divide-border/70">
          {rows.map(([label, recent, monthly], index) => (
            <tr key={label} className={index === 2 ? "bg-muted/45" : undefined}>
              <th
                scope="row"
                className={cn(
                  "py-2.5 text-left",
                  index === 2
                    ? "rounded-l-md pl-2 font-semibold"
                    : "font-medium text-muted-foreground"
                )}
              >
                {label}
              </th>
              <td
                className={cn(
                  numeric,
                  "py-2.5 pl-1.5 font-mono",
                  index === 2 && "font-semibold"
                )}
              >
                {formatOverview(recent)}
              </td>
              <td
                className={cn(
                  numeric,
                  "py-2.5 pl-1.5 font-mono",
                  index === 2 && "rounded-r-md pr-2 font-semibold"
                )}
              >
                {formatOverview(monthly)}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

export function InventoryPanel({
  data,
  onReview,
}: {
  data: OverviewResponse
  onReview: () => void
}) {
  const { inventory, sources } = data
  return (
    <section
      id="overview-inventory"
      aria-labelledby="overview-inventory-title"
      className={cn(overviewPanel, "@container/inventory scroll-mt-6")}
    >
      <header className="flex flex-wrap items-center justify-between gap-x-3 gap-y-2 border-b border-border/80 px-4 py-2.5 sm:px-5">
        <h2 id="overview-inventory-title" className="sr-only">
          整盘库存
        </h2>
        <div
          className="flex flex-wrap items-center gap-x-4 gap-y-0.5 text-xs text-muted-foreground tabular-nums"
          title="数据日期（北京时间）"
        >
          <span className="inline-flex items-center gap-1.5">
            <Database className="size-3.5 shrink-0" aria-hidden="true" />
            库存快照：{sources.stock_date ?? "待同步"}
          </span>
          <span>日销截至：{sources.sales_end ?? "待同步"}</span>
        </div>
        <span
          className={cn(
            "inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-xs font-medium",
            sources.aligned
              ? "bg-emerald-500/10 text-emerald-800 dark:text-emerald-300"
              : cn("bg-amber-500/10", overviewWarning)
          )}
        >
          {sources.aligned ? (
            <CheckCircle2 className="size-3.5" aria-hidden="true" />
          ) : (
            <TriangleAlert className="size-3.5" aria-hidden="true" />
          )}
          {sources.aligned ? "日期已对齐" : "数据待同步"}
        </span>
      </header>
      <div className="grid grid-cols-2 border-b border-border/80 @min-[37rem]/inventory:grid-cols-[1.35fr_1fr_1fr]">
        <div className="col-span-2 min-w-0 border-b border-border/80 bg-primary/[0.055] px-4 py-4 sm:px-5 @min-[37rem]/inventory:col-span-1 @min-[37rem]/inventory:border-r @min-[37rem]/inventory:border-b-0">
          <h3 className="text-xs font-medium text-muted-foreground">
            整盘可售库存
          </h3>
          <p className="mt-1 flex flex-wrap items-baseline gap-x-1.5">
            <strong className="font-mono text-[clamp(2rem,4.2cqw,3rem)] leading-none font-semibold tracking-tight wrap-anywhere tabular-nums">
              {formatOverview(inventory.available)}
            </strong>
            {inventory.available != null && <span className={muted}>双</span>}
          </p>
          <p className="mt-2 text-xs leading-5 text-muted-foreground">
            已匹配且可售合计为正的款色
          </p>
        </div>
        <div className="min-w-0 border-r border-border/80 px-4 py-4 sm:px-5">
          <h3 className={muted}>预计覆盖天数</h3>
          <p className="mt-1 flex flex-wrap items-baseline gap-x-1.5">
            <strong className="font-mono text-[clamp(1.55rem,3.4cqw,2.2rem)] leading-none font-semibold tracking-tight wrap-anywhere tabular-nums">
              {formatOverview(inventory.coverage_days)}
            </strong>
            {inventory.coverage_days != null && (
              <span className={muted}>天</span>
            )}
          </p>
          <p className="mt-2 text-xs leading-5 text-muted-foreground">
            {inventory.coverage_days == null
              ? "库存或近销数据不完整"
              : "按近 30 天总净销估算"}
          </p>
        </div>
        <div className="min-w-0 px-4 py-4 sm:px-5">
          <h3 className={muted}>近 30 天总净销</h3>
          <p className="mt-1 flex flex-wrap items-baseline gap-x-1.5">
            <strong className="font-mono text-[clamp(1.55rem,3.4cqw,2.2rem)] leading-none font-semibold tracking-tight wrap-anywhere tabular-nums">
              {formatOverview(inventory.total_30)}
            </strong>
            {inventory.total_30 != null && <span className={muted}>双</span>}
          </p>
          <p className="mt-2 text-xs leading-5 text-muted-foreground">
            聚水潭与唯品合并日销
          </p>
        </div>
      </div>
      {!sources.aligned && (
        <p
          className={cn(
            "flex items-start gap-2 border-b border-amber-500/20 bg-amber-500/5 px-4 py-2.5 text-xs leading-5 sm:px-5",
            overviewWarning
          )}
        >
          <TriangleAlert
            className="mt-0.5 size-3.5 shrink-0"
            aria-hidden="true"
          />
          库存或日销有延迟，可查看当前数据，暂不生成可分配建议。
        </p>
      )}
      <div className="grid @min-[48rem]/inventory:grid-cols-[minmax(0,1.55fr)_minmax(0,1fr)]">
        <InventoryDistribution
          inventory={inventory}
          canReview={data.counts.review > 0}
          onReview={onReview}
        />
        <RecentSales inventory={inventory} />
      </div>
      {sources.unmatched_stock_rows > 0 && (
        <p className="border-t px-4 py-2.5 text-xs text-muted-foreground sm:px-5">
          全品牌 {formatOverview(sources.unmatched_stock_rows)} 组库存编码未匹配
        </p>
      )}
    </section>
  )
}

export function InventoryPanelLoading() {
  return (
    <section
      id="overview-inventory"
      aria-label="整盘库存"
      aria-busy="true"
      className={cn(overviewPanel, "@container/inventory")}
    >
      <div className="border-b px-4 py-3.5 sm:px-5">
        <p role="status" className="text-sm text-muted-foreground">
          正在汇总库存和处理建议…
        </p>
      </div>
      <div
        aria-hidden="true"
        className="grid grid-cols-2 divide-x border-b motion-safe:animate-pulse @min-[37rem]/inventory:grid-cols-3"
      >
        {[0, 1, 2].map((index) => (
          <div
            key={index}
            className={cn(
              "space-y-2 p-4 sm:p-5",
              index === 0 &&
                "col-span-2 border-b @min-[37rem]/inventory:col-span-1 @min-[37rem]/inventory:border-b-0"
            )}
          >
            <div className="h-3 w-24 rounded bg-muted" />
            <div className="h-8 w-2/3 rounded bg-muted" />
            <div className="h-3 w-3/4 rounded bg-muted" />
          </div>
        ))}
      </div>
      <div
        aria-hidden="true"
        className="space-y-3 p-4 motion-safe:animate-pulse sm:p-5"
      >
        <div className="h-4 w-24 rounded bg-muted" />
        <div className="h-2.5 w-full rounded bg-muted" />
        <div className="grid grid-cols-2 gap-3 @min-[48rem]/inventory:grid-cols-3">
          {[0, 1, 2, 3, 4, 5].map((i) => (
            <div key={i} className="h-9 rounded bg-muted" />
          ))}
        </div>
      </div>
    </section>
  )
}

export function WeeklyPanel({
  week,
  error,
  retry,
  onClearance,
}: {
  week: OverviewWeek | null
  error: string | null
  retry: () => void
  onClearance: (first: string) => void
}) {
  return (
    <section
      id="overview-week"
      aria-labelledby="stock-overview-week"
      aria-busy={!week && !error}
      className={cn(overviewPanel, "@container/week scroll-mt-6")}
    >
      <header className="border-b border-border/80 px-4 py-3.5 sm:px-5">
        <h2
          id="stock-overview-week"
          className="flex items-center gap-2 text-base font-semibold"
        >
          <CalendarDays
            className="size-4 shrink-0 text-muted-foreground"
            aria-hidden="true"
          />{" "}
          上周复盘
        </h2>
        {week && (
          <div className="mt-1 flex flex-wrap items-center justify-between gap-2">
            <p className="text-xs text-muted-foreground tabular-nums">
              {week.start} 至 {week.end}
            </p>
            <Button
              size="sm"
              variant="outline"
              onClick={() => onClearance(week.start)}
            >
              清货明细
            </Button>
          </div>
        )}
      </header>
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
          <dl className="grid grid-cols-3 divide-x border-b pb-3">
            {(
              [
                ["新增待办", week.created, ""],
                ["已完成", week.completed, ""],
                [
                  "到期未完成",
                  week.overdue,
                  week.overdue > 0 ? overviewWarning : "",
                ],
              ] as const
            ).map(([label, value, tone]) => (
              <div key={label} className="min-w-0 px-2 py-1 first:pl-0 sm:px-4">
                <dt
                  className={cn(
                    "text-xs leading-4",
                    tone || "text-muted-foreground"
                  )}
                  title={label === "到期未完成" ? "截至上周末" : undefined}
                >
                  {label}
                </dt>
                <dd
                  className={cn(
                    "mt-1 flex flex-wrap items-baseline gap-1 font-mono text-lg leading-tight font-semibold wrap-anywhere tabular-nums",
                    tone
                  )}
                >
                  {formatOverview(value)}{" "}
                  <span className="font-sans text-xs font-normal text-muted-foreground">
                    项
                  </span>
                </dd>
              </div>
            ))}
          </dl>
          <div>
            <h3 className="border-b py-2.5 text-sm font-semibold">处理成效</h3>
            <dl className="divide-y divide-border/65 text-xs">
              {(
                [
                  ["处理款净销", week.net_sales],
                  ["处理款尺码库存变化", week.stock_change],
                  ["清货款清仓净销", week.clearance_net_sales],
                ] as const
              ).map(([label, value]) => (
                <div
                  key={label}
                  className="flex flex-wrap items-baseline justify-between gap-x-2 gap-y-1 py-2.5"
                >
                  <dt className="text-muted-foreground">{label}</dt>
                  <dd className="font-mono font-medium tabular-nums">
                    {formatOverview(value, " 双")}
                  </dd>
                </div>
              ))}
              <div className="flex flex-wrap items-baseline justify-between gap-x-2 gap-y-1 py-2.5">
                <dt className="text-muted-foreground">财务已确认回收</dt>
                <dd className="font-mono font-medium tabular-nums">
                  {week.recovery_amount == null
                    ? "—"
                    : `${week.recovery_amount} 元`}
                  {week.recovery_covered != null &&
                    week.clearance_products != null && (
                      <span className="ml-1 text-muted-foreground">
                        （{week.recovery_covered}/{week.clearance_products} 款）
                      </span>
                    )}
                </dd>
              </div>
            </dl>
          </div>
          <p className="text-xs text-muted-foreground">
            观察上周已完成待办的 {formatOverview(week.completed_styles)}{" "}
            个款色。
          </p>
          <details className="group">
            <summary className="inline-flex min-h-7 cursor-pointer list-none items-center gap-1.5 rounded-sm text-xs text-muted-foreground underline-offset-4 hover:text-foreground hover:underline focus-visible:outline-2 focus-visible:outline-offset-2 [&::-webkit-details-marker]:hidden">
              <Info className="size-3.5" aria-hidden="true" /> 查看复盘口径{" "}
              <ChevronDown
                className="size-3.5 group-open:rotate-180"
                aria-hidden="true"
              />
            </summary>
            <p className="mt-1 text-xs leading-5 text-muted-foreground">
              库存取尺码历史快照，缺记录时显示「—」。回收金额以财务录入的结算凭证为准。
            </p>
          </details>
        </div>
      ) : (
        <div className="space-y-3 p-4 sm:px-5">
          <p className="text-sm text-muted-foreground" role="status">
            正在读取上周记录…
          </p>
          <div
            aria-hidden="true"
            className="grid grid-cols-3 gap-1.5 motion-safe:animate-pulse"
          >
            {[0, 1, 2].map((i) => (
              <div key={i} className="h-14 rounded-lg bg-muted" />
            ))}
          </div>
        </div>
      )}
    </section>
  )
}
