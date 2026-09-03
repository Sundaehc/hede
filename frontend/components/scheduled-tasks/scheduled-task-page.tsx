"use client"

import { useCallback, useEffect, useState } from "react"
import {
  Activity,
  CheckCircle2,
  ChevronDown,
  ChevronRight,
  CircleAlert,
  Clock3,
  Copy,
  Loader2,
  RefreshCw,
  Search,
  ServerCog,
} from "lucide-react"

import { useAuth } from "@/components/auth/auth-provider"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Select } from "@/components/ui/select"
import {
  ApiError,
  listScheduledTaskBusinessStatuses,
  listScheduledTaskHistory,
  listScheduledTaskRuns,
} from "@/lib/api"
import type {
  ScheduledTaskBusinessStatus,
  ScheduledTaskBusinessStatusItem,
  ScheduledTaskRunItem,
  ScheduledTaskRunStatus,
  ScheduledTaskRunSummary,
} from "@/lib/types"
import { cn } from "@/lib/utils"

const PAGE_SIZE = 50

const TASK_LABELS: Record<string, string> = {
  HedeImportJstDaily: "聚水潭日销导入",
  HedeImportVipDaily: "唯品商品日报导入",
  HedeImportVipDailySalesReport: "唯品日销导入",
  HedeImportDewuOrders: "得物订单导入",
  HedeImportJstFullStock: "聚水潭全量库存导入",
  Hede_JST_Stock_Sync: "聚水潭尺码库存同步",
  HedeImportPriceDaily: "商品物价信息更新",
  hede_import_gj_merged_product_info_daily: "管家婆商品信息更新",
  HedeImportProductsDaily: "商品信息档案更新",
  HedeImportSmileyFineTableDaily: "笑脸精细表导入",
  "Hede Fine Table Snapshot Daily": "精细表每日快照",
  "Hede Fine Table Export Daily": "精细表日报导出",
  HedeImportProductGoodsDetailSnapshotsDaily: "货品表每日快照",
  HedeImportProductGoodsOrdersDaily: "货品表订单数据导入",
  HedeDatabaseMaintenance: "数据库日常维护",
  HedeDataGovernanceAudit: "数据库治理检查",
}

const RUN_STATUS_OPTIONS = [
  { value: "all", label: "全部状态" },
  { value: "success", label: "成功" },
  { value: "failed", label: "失败" },
  { value: "running", label: "执行中" },
]

const BUSINESS_STATUS_OPTIONS = [
  ...RUN_STATUS_OPTIONS,
  { value: "skipped", label: "已跳过" },
]

function shanghaiDateInputValue() {
  const parts = new Intl.DateTimeFormat("en-US", {
    timeZone: "Asia/Shanghai",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).formatToParts(new Date())
  const values = Object.fromEntries(
    parts.map((part) => [part.type, part.value])
  )
  return `${values.year}-${values.month}-${values.day}`
}

function getErrorMessage(error: unknown) {
  if (error instanceof ApiError) return error.message
  if (error instanceof Error) return error.message
  return "加载失败，请稍后重试"
}

function formatDateTime(value: string | null) {
  if (!value) return "-"
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return value
  return new Intl.DateTimeFormat("zh-CN", {
    timeZone: "Asia/Shanghai",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    hour12: false,
  }).format(date)
}

function formatDuration(value: number | null) {
  if (value === null) return "-"
  if (value < 1000) return `${value} ms`
  const seconds = Math.floor(value / 1000)
  if (seconds < 60) return `${seconds} 秒`
  const minutes = Math.floor(seconds / 60)
  const remainingSeconds = seconds % 60
  if (minutes < 60) return `${minutes} 分 ${remainingSeconds} 秒`
  const hours = Math.floor(minutes / 60)
  return `${hours} 小时 ${minutes % 60} 分`
}

function taskLabel(taskName: string) {
  return TASK_LABELS[taskName] || taskName
}

function StatusBadge({ status }: { status: ScheduledTaskBusinessStatus }) {
  const label = {
    success: "成功",
    failed: "失败",
    running: "执行中",
    skipped: "已跳过",
  }[status]
  return (
    <span
      className={cn(
        "inline-flex h-6 items-center rounded-md border px-2 text-xs font-medium",
        status === "success" &&
          "border-emerald-200 bg-emerald-50 text-emerald-700 dark:border-emerald-900 dark:bg-emerald-950/50 dark:text-emerald-300",
        status === "failed" &&
          "border-red-200 bg-red-50 text-red-700 dark:border-red-900 dark:bg-red-950/50 dark:text-red-300",
        status === "running" &&
          "border-blue-200 bg-blue-50 text-blue-700 dark:border-blue-900 dark:bg-blue-950/50 dark:text-blue-300",
        status === "skipped" && "border-border bg-muted text-muted-foreground"
      )}
    >
      {status === "running" ? (
        <Loader2 className="mr-1 size-3 animate-spin" />
      ) : null}
      {label}
    </span>
  )
}

async function copyText(value: string) {
  await navigator.clipboard.writeText(value)
}

function CopyableText({ value }: { value: string | null }) {
  if (!value) return <span className="text-muted-foreground">-</span>
  return (
    <span className="group/copy flex min-w-0 items-start gap-1.5">
      <span className="min-w-0 text-xs leading-5 break-all" title={value}>
        {value}
      </span>
      <button
        type="button"
        title="复制"
        aria-label="复制"
        className="mt-0.5 shrink-0 cursor-pointer rounded p-1 text-muted-foreground opacity-0 transition-opacity group-hover/copy:opacity-100 hover:bg-muted hover:text-foreground focus:opacity-100"
        onClick={() => void copyText(value)}
      >
        <Copy className="size-3" />
      </button>
    </span>
  )
}

function RunHistory({
  items,
  loading,
}: {
  items: ScheduledTaskRunItem[]
  loading: boolean
}) {
  if (loading) {
    return (
      <div className="flex h-24 items-center justify-center text-sm text-muted-foreground">
        <Loader2 className="mr-2 size-4 animate-spin" />
        加载运行历史
      </div>
    )
  }
  if (!items.length) {
    return (
      <div className="py-8 text-center text-sm text-muted-foreground">
        暂无运行历史
      </div>
    )
  }
  return (
    <div className="space-y-2 px-4 py-3">
      <div className="text-xs font-medium text-muted-foreground">
        最近 {items.length} 次执行
      </div>
      <div className="overflow-hidden rounded-md border border-border bg-background">
        {items.map((item) => (
          <div
            key={item.id}
            className="grid gap-2 border-t border-border px-3 py-2 text-xs first:border-t-0 md:grid-cols-[88px_150px_100px_minmax(0,1fr)]"
          >
            <StatusBadge status={item.status} />
            <span className="text-muted-foreground tabular-nums">
              {formatDateTime(item.started_at)}
            </span>
            <span className="text-muted-foreground tabular-nums">
              {formatDuration(item.duration_ms)}
            </span>
            <span
              className={cn(
                "break-words",
                item.error_summary
                  ? "text-red-600 dark:text-red-300"
                  : "text-muted-foreground"
              )}
            >
              {item.error_summary || "执行完成"}
            </span>
          </div>
        ))}
      </div>
    </div>
  )
}

export function ScheduledTaskPage() {
  const { user } = useAuth()
  const canAccess =
    user?.role_code === "super_admin" || user?.department_code === "开发部"
  const [today] = useState(shanghaiDateInputValue)
  const [mode, setMode] = useState<"runs" | "business">("runs")
  const [selectedDate, setSelectedDate] = useState(today)
  const [status, setStatus] = useState("all")
  const [queryInput, setQueryInput] = useState("")
  const [query, setQuery] = useState("")
  const [latestOnly, setLatestOnly] = useState(true)
  const [page, setPage] = useState(1)
  const [runItems, setRunItems] = useState<ScheduledTaskRunItem[]>([])
  const [businessItems, setBusinessItems] = useState<
    ScheduledTaskBusinessStatusItem[]
  >([])
  const [summary, setSummary] = useState<ScheduledTaskRunSummary>({
    total: 0,
    success: 0,
    failed: 0,
    running: 0,
    task_count: 0,
    latest_started_at: null,
  })
  const [businessSummary, setBusinessSummary] = useState({
    total: 0,
    success: 0,
    failed: 0,
    running: 0,
    skipped: 0,
  })
  const [total, setTotal] = useState(0)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState("")
  const [expandedRunId, setExpandedRunId] = useState<number | null>(null)
  const [historyByTask, setHistoryByTask] = useState<
    Record<string, ScheduledTaskRunItem[]>
  >({})
  const [historyLoadingTask, setHistoryLoadingTask] = useState<string | null>(
    null
  )

  const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE))
  const statusOptions =
    mode === "runs" ? RUN_STATUS_OPTIONS : BUSINESS_STATUS_OPTIONS

  const loadData = useCallback(async () => {
    if (!canAccess) return
    setLoading(true)
    setError("")
    try {
      if (mode === "runs") {
        const response = await listScheduledTaskRuns({
          runDate: selectedDate,
          status,
          query,
          latestOnly,
          page,
          pageSize: PAGE_SIZE,
        })
        setRunItems(response.items)
        setBusinessItems([])
        setSummary(response.summary)
        setTotal(response.total)
      } else {
        const response = await listScheduledTaskBusinessStatuses({
          businessDate: selectedDate,
          status,
          query,
          page,
          pageSize: PAGE_SIZE,
        })
        setBusinessItems(response.items)
        setRunItems([])
        setTotal(response.total)
        setBusinessSummary(response.summary)
      }
    } catch (loadError) {
      setRunItems([])
      setBusinessItems([])
      setTotal(0)
      setError(getErrorMessage(loadError))
    } finally {
      setLoading(false)
    }
  }, [canAccess, latestOnly, mode, page, query, selectedDate, status])

  useEffect(() => {
    void Promise.resolve().then(loadData)
  }, [loadData])

  useEffect(() => {
    if (mode !== "runs" || !runItems.some((item) => item.status === "running"))
      return
    const timer = window.setInterval(() => void loadData(), 30_000)
    return () => window.clearInterval(timer)
  }, [loadData, mode, runItems])

  const switchMode = (nextMode: "runs" | "business") => {
    if (nextMode === mode) return
    setMode(nextMode)
    setStatus("all")
    setPage(1)
    setExpandedRunId(null)
  }

  const summaryItems =
    mode === "runs"
      ? [
          {
            label: "涉及任务",
            value: summary.task_count,
            icon: ServerCog,
            tone: "text-foreground",
          },
          {
            label: "成功",
            value: summary.success,
            icon: CheckCircle2,
            tone: "text-emerald-600",
          },
          {
            label: "失败",
            value: summary.failed,
            icon: CircleAlert,
            tone: "text-red-600",
          },
          {
            label: "执行中",
            value: summary.running,
            icon: Loader2,
            tone: "text-blue-600",
          },
          {
            label: "执行总次数",
            value: summary.total,
            icon: Clock3,
            tone: "text-foreground",
          },
        ]
      : [
          {
            label: "数据任务",
            value: businessSummary.total,
            icon: ServerCog,
            tone: "text-foreground",
          },
          {
            label: "成功",
            value: businessSummary.success,
            icon: CheckCircle2,
            tone: "text-emerald-600",
          },
          {
            label: "失败",
            value: businessSummary.failed,
            icon: CircleAlert,
            tone: "text-red-600",
          },
          {
            label: "执行中",
            value: businessSummary.running,
            icon: Loader2,
            tone: "text-blue-600",
          },
          {
            label: "已跳过",
            value: businessSummary.skipped,
            icon: Clock3,
            tone: "text-muted-foreground",
          },
        ]

  const toggleRunHistory = async (item: ScheduledTaskRunItem) => {
    if (expandedRunId === item.id) {
      setExpandedRunId(null)
      return
    }
    setExpandedRunId(item.id)
    if (historyByTask[item.task_name]) return
    setHistoryLoadingTask(item.task_name)
    try {
      const response = await listScheduledTaskHistory(item.task_name)
      setHistoryByTask((current) => ({
        ...current,
        [item.task_name]: response.items,
      }))
    } catch (historyError) {
      setError(getErrorMessage(historyError))
    } finally {
      setHistoryLoadingTask(null)
    }
  }

  if (!canAccess) {
    return (
      <div className="app-page">
        <div className="app-content py-12 text-sm text-muted-foreground">
          暂无访问权限
        </div>
      </div>
    )
  }

  return (
    <div className="app-page">
      <div className="app-content-wide gap-4">
        <header className="flex flex-wrap items-center justify-between gap-3 rounded-lg border border-border bg-card px-5 py-4 shadow-xs">
          <div>
            <div className="flex items-center gap-2">
              <Activity className="size-5 text-primary" />
              <h1 className="text-xl font-semibold">定时任务执行情况</h1>
            </div>
            <p className="mt-1 text-sm text-muted-foreground">
              查看任务执行结果、重试记录与数据业务日期状态
            </p>
          </div>
          <Button
            type="button"
            variant="outline"
            className="cursor-pointer gap-2"
            disabled={loading}
            onClick={() => void loadData()}
          >
            <RefreshCw className={cn("size-4", loading && "animate-spin")} />
            刷新
          </Button>
        </header>

        <div className="grid overflow-hidden rounded-lg border border-border bg-card shadow-xs sm:grid-cols-2 xl:grid-cols-5">
          {summaryItems.map((item, index) => (
            <div
              key={item.label}
              className={cn(
                "flex min-h-20 items-center gap-3 px-4 py-3",
                index > 0 && "border-t border-border sm:border-t-0 sm:border-l",
                index === 2 && "sm:border-t xl:border-t-0"
              )}
            >
              <item.icon
                className={cn(
                  "size-4",
                  item.tone,
                  item.label === "执行中" &&
                    summary.running > 0 &&
                    "animate-spin"
                )}
              />
              <div>
                <div className="text-xs text-muted-foreground">
                  {item.label}
                </div>
                <div className="mt-1 text-xl font-semibold tabular-nums">
                  {item.value}
                </div>
              </div>
            </div>
          ))}
        </div>

        <section className="overflow-hidden rounded-lg border border-border bg-card shadow-xs">
          <div className="flex flex-wrap items-center justify-between gap-3 border-b border-border p-3">
            <div className="flex rounded-md bg-muted p-1">
              <button
                type="button"
                onClick={() => switchMode("runs")}
                className={cn(
                  "h-8 cursor-pointer rounded px-3 text-sm transition-colors",
                  mode === "runs"
                    ? "bg-background font-medium text-foreground shadow-xs"
                    : "text-muted-foreground hover:text-foreground"
                )}
              >
                执行记录
              </button>
              <button
                type="button"
                onClick={() => switchMode("business")}
                className={cn(
                  "h-8 cursor-pointer rounded px-3 text-sm transition-colors",
                  mode === "business"
                    ? "bg-background font-medium text-foreground shadow-xs"
                    : "text-muted-foreground hover:text-foreground"
                )}
              >
                业务日期状态
              </button>
            </div>
            <div className="text-xs text-muted-foreground">
              {mode === "runs" && summary.latest_started_at
                ? `最近启动 ${formatDateTime(summary.latest_started_at)}`
                : `共 ${total} 条`}
            </div>
          </div>

          <form
            className="flex flex-wrap items-center gap-2 border-b border-border px-3 py-3"
            onSubmit={(event) => {
              event.preventDefault()
              setPage(1)
              setQuery(queryInput.trim())
            }}
          >
            <Input
              type="date"
              aria-label={mode === "runs" ? "执行日期" : "业务日期"}
              max={today}
              value={selectedDate}
              onChange={(event) => {
                setSelectedDate(event.target.value)
                setPage(1)
              }}
              className="w-40 cursor-pointer"
            />
            <Select
              aria-label="状态筛选"
              value={status}
              onChange={(event) => {
                setStatus(event.target.value)
                setPage(1)
              }}
              className="w-32 cursor-pointer"
            >
              {statusOptions.map((option) => (
                <option key={option.value} value={option.value}>
                  {option.label}
                </option>
              ))}
            </Select>
            {mode === "runs" ? (
              <Select
                aria-label="执行记录范围"
                value={latestOnly ? "latest" : "all"}
                onChange={(event) => {
                  setLatestOnly(event.target.value === "latest")
                  setPage(1)
                  setExpandedRunId(null)
                }}
                className="w-40 cursor-pointer"
              >
                <option value="latest">每个任务最新一次</option>
                <option value="all">全部执行记录</option>
              </Select>
            ) : null}
            <div className="relative min-w-56 flex-1 lg:max-w-md">
              <Search className="pointer-events-none absolute top-1/2 left-3 size-4 -translate-y-1/2 text-muted-foreground" />
              <Input
                value={queryInput}
                onChange={(event) => setQueryInput(event.target.value)}
                placeholder="搜索任务名称、日志或结果"
                className="pl-9"
              />
            </div>
            <Button type="submit" className="cursor-pointer">
              搜索
            </Button>
          </form>

          {error ? (
            <div className="m-3 flex items-start gap-2 rounded-md border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700 dark:border-red-900 dark:bg-red-950/50 dark:text-red-300">
              <CircleAlert className="mt-0.5 size-4 shrink-0" />
              {error}
            </div>
          ) : null}

          <div className="relative min-h-[420px] overflow-auto">
            {loading && (runItems.length > 0 || businessItems.length > 0) ? (
              <div className="absolute inset-0 z-20 flex items-center justify-center bg-card/70 backdrop-blur-[1px]">
                <div className="flex items-center gap-2 rounded-md border border-border bg-card px-3 py-2 text-sm text-muted-foreground shadow-sm">
                  <Loader2 className="size-4 animate-spin" />
                  加载中
                </div>
              </div>
            ) : null}

            {mode === "runs" ? (
              <table className="w-full min-w-[1180px] table-fixed text-sm">
                <thead className="sticky top-0 z-10 bg-muted text-left text-xs text-muted-foreground">
                  <tr>
                    <th className="w-12 px-3 py-3" />
                    <th className="w-72 px-3 py-3 font-medium">任务</th>
                    <th className="w-24 px-3 py-3 font-medium">状态</th>
                    <th className="w-40 px-3 py-3 font-medium">开始时间</th>
                    <th className="w-40 px-3 py-3 font-medium">结束时间</th>
                    <th className="w-28 px-3 py-3 font-medium">耗时</th>
                    <th className="w-28 px-3 py-3 font-medium">主机</th>
                    <th className="px-3 py-3 font-medium">执行结果</th>
                  </tr>
                </thead>
                <tbody>
                  {loading && runItems.length === 0 ? (
                    <tr>
                      <td
                        colSpan={8}
                        className="h-64 text-center text-muted-foreground"
                      >
                        <Loader2 className="mr-2 inline size-4 animate-spin" />
                        加载中
                      </td>
                    </tr>
                  ) : runItems.length ? (
                    runItems.map((item) => {
                      const expanded = expandedRunId === item.id
                      return (
                        <FragmentRunRow
                          key={item.id}
                          item={item}
                          expanded={expanded}
                          onToggle={() => void toggleRunHistory(item)}
                          history={historyByTask[item.task_name] || []}
                          historyLoading={historyLoadingTask === item.task_name}
                        />
                      )
                    })
                  ) : (
                    <tr>
                      <td
                        colSpan={8}
                        className="h-64 text-center text-muted-foreground"
                      >
                        该日期暂无任务执行记录
                      </td>
                    </tr>
                  )}
                </tbody>
              </table>
            ) : (
              <table className="w-full min-w-[1120px] table-fixed text-sm">
                <thead className="sticky top-0 z-10 bg-muted text-left text-xs text-muted-foreground">
                  <tr>
                    <th className="w-64 px-4 py-3 font-medium">任务</th>
                    <th className="w-24 px-3 py-3 font-medium">状态</th>
                    <th className="w-20 px-3 py-3 font-medium">尝试次数</th>
                    <th className="w-40 px-3 py-3 font-medium">最后启动</th>
                    <th className="w-40 px-3 py-3 font-medium">完成时间</th>
                    <th className="w-72 px-3 py-3 font-medium">数据源</th>
                    <th className="px-3 py-3 font-medium">处理结果</th>
                  </tr>
                </thead>
                <tbody>
                  {loading && businessItems.length === 0 ? (
                    <tr>
                      <td
                        colSpan={7}
                        className="h-64 text-center text-muted-foreground"
                      >
                        <Loader2 className="mr-2 inline size-4 animate-spin" />
                        加载中
                      </td>
                    </tr>
                  ) : businessItems.length ? (
                    businessItems.map((item) => (
                      <tr
                        key={item.id}
                        className="border-t border-border align-top hover:bg-muted/25"
                      >
                        <td className="px-4 py-3">
                          <div className="font-medium">
                            {taskLabel(item.task_name)}
                          </div>
                          {TASK_LABELS[item.task_name] ? (
                            <div
                              className="mt-1 truncate font-mono text-[11px] text-muted-foreground"
                              title={item.task_name}
                            >
                              {item.task_name}
                            </div>
                          ) : null}
                        </td>
                        <td className="px-3 py-3">
                          <StatusBadge status={item.status} />
                        </td>
                        <td className="px-3 py-3 tabular-nums">
                          {item.attempts}
                        </td>
                        <td className="px-3 py-3 text-muted-foreground tabular-nums">
                          {formatDateTime(item.last_started_at)}
                        </td>
                        <td className="px-3 py-3 text-muted-foreground tabular-nums">
                          {formatDateTime(item.finished_at)}
                        </td>
                        <td className="px-3 py-3">
                          <CopyableText value={item.source_path} />
                        </td>
                        <td
                          className={cn(
                            "px-3 py-3 text-xs leading-5",
                            item.status === "failed"
                              ? "text-red-600 dark:text-red-300"
                              : "text-muted-foreground"
                          )}
                        >
                          <span className="break-words">
                            {item.message || "-"}
                          </span>
                        </td>
                      </tr>
                    ))
                  ) : (
                    <tr>
                      <td
                        colSpan={7}
                        className="h-64 text-center text-muted-foreground"
                      >
                        该业务日期暂无数据处理状态
                      </td>
                    </tr>
                  )}
                </tbody>
              </table>
            )}
          </div>

          <div className="flex flex-wrap items-center justify-between gap-3 border-t border-border px-4 py-3 text-sm">
            <span className="text-muted-foreground">
              共 {total} 条，第 {page} / {totalPages} 页
            </span>
            <div className="flex items-center gap-2">
              <Button
                type="button"
                variant="outline"
                size="sm"
                className="cursor-pointer"
                disabled={page <= 1 || loading}
                onClick={() => setPage((value) => Math.max(1, value - 1))}
              >
                上一页
              </Button>
              <Button
                type="button"
                variant="outline"
                size="sm"
                className="cursor-pointer"
                disabled={page >= totalPages || loading}
                onClick={() =>
                  setPage((value) => Math.min(totalPages, value + 1))
                }
              >
                下一页
              </Button>
            </div>
          </div>
        </section>
      </div>
    </div>
  )
}

function FragmentRunRow({
  item,
  expanded,
  onToggle,
  history,
  historyLoading,
}: {
  item: ScheduledTaskRunItem
  expanded: boolean
  onToggle: () => void
  history: ScheduledTaskRunItem[]
  historyLoading: boolean
}) {
  return (
    <>
      <tr className="border-t border-border align-top hover:bg-muted/25">
        <td className="px-3 py-3">
          <button
            type="button"
            onClick={onToggle}
            className="cursor-pointer rounded p-1 text-muted-foreground hover:bg-muted hover:text-foreground"
            title={expanded ? "收起运行历史" : "查看运行历史"}
            aria-label={expanded ? "收起运行历史" : "查看运行历史"}
          >
            {expanded ? (
              <ChevronDown className="size-4" />
            ) : (
              <ChevronRight className="size-4" />
            )}
          </button>
        </td>
        <td className="px-3 py-3">
          <div className="font-medium">{taskLabel(item.task_name)}</div>
          {TASK_LABELS[item.task_name] ? (
            <div
              className="mt-1 truncate font-mono text-[11px] text-muted-foreground"
              title={item.task_name}
            >
              {item.task_name}
            </div>
          ) : null}
        </td>
        <td className="px-3 py-3">
          <StatusBadge status={item.status as ScheduledTaskRunStatus} />
        </td>
        <td className="px-3 py-3 text-muted-foreground tabular-nums">
          {formatDateTime(item.started_at)}
        </td>
        <td className="px-3 py-3 text-muted-foreground tabular-nums">
          {formatDateTime(item.finished_at)}
        </td>
        <td className="px-3 py-3 tabular-nums">
          {formatDuration(item.duration_ms)}
        </td>
        <td className="px-3 py-3 text-muted-foreground">
          {item.host_name || "-"}
        </td>
        <td className="px-3 py-3">
          <div
            className={cn(
              "text-xs leading-5 break-words",
              item.error_summary
                ? "text-red-600 dark:text-red-300"
                : "text-muted-foreground"
            )}
          >
            {item.error_summary ||
              (item.status === "running"
                ? "任务正在执行"
                : `退出码 ${item.exit_code ?? 0}`)}
          </div>
          {item.log_path ? (
            <div className="mt-1">
              <CopyableText value={item.log_path} />
            </div>
          ) : null}
        </td>
      </tr>
      {expanded ? (
        <tr className="border-t border-border bg-muted/20">
          <td colSpan={8}>
            <RunHistory items={history} loading={historyLoading} />
          </td>
        </tr>
      ) : null}
    </>
  )
}
