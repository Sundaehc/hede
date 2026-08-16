"use client"

import Link from "next/link"
import { useEffect, useState } from "react"
import {
  ArrowRight,
  ArrowUpRight,
  ChevronRight,
  CircleAlert,
  Database,
  Factory,
  History,
  LoaderCircle,
  PackageSearch,
  Search,
  Sparkles,
  Table2,
  Trash2,
  Warehouse,
  X,
} from "lucide-react"

import { Button } from "@/components/ui/button"
import {
  ApiError,
  clearAiQueryHistory,
  listAiQueryHistory,
  runAiQuery,
} from "@/lib/api"
import type { AiQueryColumn, AiQueryResponse } from "@/lib/types"

const MAX_HISTORY_ITEMS = 8
const AI_QUERY_TIMEOUT_MS = 150_000
const HIDDEN_CONDITION_LABELS = new Set(["查询模式", "数据范围"])

const EXAMPLE_QUESTIONS = [
  {
    label: "货品经营",
    question: "查询千百度女鞋 QC153883D54 近7天销量和库存",
    icon: PackageSearch,
  },
  {
    label: "库存风险",
    question: "查询千百度女鞋近7天无销量的缺货风险商品",
    icon: Warehouse,
  },
  {
    label: "工厂渠道",
    question: "查询2026年各工厂传统、直播、清仓销量",
    icon: Factory,
  },
]

const numberFormatter = new Intl.NumberFormat("zh-CN")

function formatCell(value: unknown, column: AiQueryColumn) {
  if (value === null || value === undefined || value === "") return "暂无数据"
  if (column.type === "number" && typeof value === "number")
    return numberFormatter.format(value)
  if (typeof value === "number") return numberFormatter.format(value)
  if (typeof value === "object") {
    try {
      return JSON.stringify(value)
    } catch {
      return String(value)
    }
  }
  return String(value)
}

function metricTone(tone: string | undefined) {
  return (
    {
      slate: "bg-slate-500/10 text-slate-700 dark:text-slate-300",
      blue: "bg-blue-500/10 text-blue-700 dark:text-blue-300",
      violet: "bg-violet-500/10 text-violet-700 dark:text-violet-300",
      orange: "bg-orange-500/10 text-orange-700 dark:text-orange-300",
      emerald: "bg-emerald-500/10 text-emerald-700 dark:text-emerald-300",
    }[tone || "slate"] || "bg-muted text-muted-foreground"
  )
}

function metricGridColumns(count: number) {
  if (count >= 4) return "sm:grid-cols-2 xl:grid-cols-4"
  if (count === 3) return "sm:grid-cols-3"
  if (count === 2) return "sm:grid-cols-2"
  return "grid-cols-1"
}

function errorMessage(error: unknown) {
  if (
    error instanceof DOMException &&
    (error.name === "AbortError" || error.name === "TimeoutError")
  ) {
    return "查询耗时过长，请缩小查询范围后重试"
  }
  if (error instanceof ApiError) {
    if (
      error.status >= 500 &&
      (!error.message || error.message === "Internal Server Error")
    ) {
      return "查询服务暂时不可用，请稍后重试"
    }
    return error.message || `请求失败（${error.status}）`
  }
  if (error instanceof Error) return error.message
  return "查询失败，请稍后重试"
}

export default function AiQueryPage() {
  const [question, setQuestion] = useState("")
  const [response, setResponse] = useState<AiQueryResponse | null>(null)
  const [history, setHistory] = useState<string[]>([])
  const [historyLoading, setHistoryLoading] = useState(true)
  const [historyClearing, setHistoryClearing] = useState(false)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState("")

  useEffect(() => {
    let cancelled = false
    void listAiQueryHistory()
      .then((result) => {
        if (!cancelled) setHistory(result.items.slice(0, MAX_HISTORY_ITEMS))
      })
      .catch(() => {
        if (!cancelled) setHistory([])
      })
      .finally(() => {
        if (!cancelled) setHistoryLoading(false)
      })
    return () => {
      cancelled = true
    }
  }, [])

  async function submit(nextQuestion = question) {
    const value = nextQuestion.trim()
    if (!value || loading) return
    setQuestion(value)
    setLoading(true)
    setError("")
    try {
      const result = await runAiQuery(value, undefined, {
        signal: AbortSignal.timeout(AI_QUERY_TIMEOUT_MS),
      })
      setResponse(result)
      setHistory((current) =>
        [value, ...current.filter((item) => item !== value)].slice(
          0,
          MAX_HISTORY_ITEMS
        )
      )
    } catch (requestError) {
      setResponse(null)
      setError(errorMessage(requestError))
    } finally {
      setLoading(false)
    }
  }

  async function clearHistory() {
    if (historyClearing) return
    const previousHistory = history
    setHistory([])
    setHistoryClearing(true)
    try {
      await clearAiQueryHistory()
    } catch (requestError) {
      setHistory(previousHistory)
      setError(errorMessage(requestError))
    } finally {
      setHistoryClearing(false)
    }
  }

  const hasRows = Boolean(response?.rows.length && response.columns.length)
  const visibleConditions =
    response?.conditions.filter(
      (item) => !HIDDEN_CONDITION_LABELS.has(item.label)
    ) ?? []

  return (
    <div className="app-page">
      <div className="app-content-wide gap-4">
        <header className="flex flex-wrap items-center justify-between gap-3 rounded-lg border border-border bg-card/95 px-3 py-3 shadow-sm backdrop-blur sm:px-4">
          <div className="flex min-w-0 items-center gap-3">
            <div className="flex size-9 shrink-0 items-center justify-center rounded-lg bg-foreground text-background shadow-sm">
              <Sparkles className="size-[18px]" />
            </div>
            <div className="min-w-0">
              <h1 className="text-xl font-semibold">智能查询</h1>
              <p className="mt-0.5 truncate text-xs text-muted-foreground">
                企业业务数据工作台
              </p>
            </div>
          </div>
        </header>

        <div className="grid min-w-0 items-start gap-4 xl:grid-cols-[268px_minmax(0,1fr)]">
          <aside className="order-2 overflow-hidden rounded-lg border border-border bg-card/95 shadow-sm xl:sticky xl:top-6 xl:order-1">
            <div className="flex h-12 items-center justify-between border-b border-border px-4">
              <div className="flex items-center gap-2 text-sm font-semibold">
                <History className="size-4 text-muted-foreground" /> 最近查询
              </div>
              {history.length > 0 ? (
                <Button
                  type="button"
                  variant="ghost"
                  size="icon-sm"
                  onClick={() => void clearHistory()}
                  disabled={historyClearing}
                  title="清空最近查询"
                  aria-label="清空最近查询"
                >
                  <Trash2 className="size-3.5" />
                </Button>
              ) : null}
            </div>

            {historyLoading ? (
              <div className="flex min-h-32 items-center justify-center">
                <LoaderCircle className="size-4 animate-spin text-muted-foreground" />
              </div>
            ) : history.length > 0 ? (
              <div className="divide-y divide-border/70">
                {history.map((item, index) => (
                  <button
                    key={item}
                    type="button"
                    className="group flex w-full cursor-pointer items-start gap-2.5 px-4 py-3 text-left transition-colors hover:bg-muted/50 disabled:cursor-not-allowed disabled:opacity-60"
                    onClick={() => void submit(item)}
                    disabled={loading}
                    title={item}
                  >
                    <span className="mt-0.5 flex size-5 shrink-0 items-center justify-center rounded-md bg-muted text-[10px] font-semibold text-muted-foreground group-hover:bg-background">
                      {index + 1}
                    </span>
                    <span className="line-clamp-2 min-w-0 flex-1 text-xs leading-5 text-foreground/80">
                      {item}
                    </span>
                    <ArrowRight className="mt-1 size-3.5 shrink-0 text-muted-foreground opacity-0 transition-opacity group-hover:opacity-100" />
                  </button>
                ))}
              </div>
            ) : (
              <div className="flex min-h-32 flex-col items-center justify-center px-5 py-6 text-center">
                <Search className="size-5 text-muted-foreground/50" />
                <p className="mt-2 text-xs text-muted-foreground">
                  暂无最近查询
                </p>
              </div>
            )}
          </aside>

          <main className="order-1 min-w-0 space-y-4 xl:order-2">
            <section className="overflow-hidden rounded-lg border border-border bg-card/95 shadow-sm">
              <div className="flex h-12 items-center justify-between border-b border-border px-4 sm:px-5">
                <div className="flex items-center gap-2 text-sm font-semibold">
                  <Sparkles className="size-4 text-muted-foreground" /> 输入查询
                </div>
                <span className="text-xs text-muted-foreground tabular-nums">
                  {question.length}/500
                </span>
              </div>
              <form
                className="p-4 sm:p-5"
                onSubmit={(event) => {
                  event.preventDefault()
                  void submit()
                }}
              >
                <div className="overflow-hidden rounded-lg border border-input bg-background shadow-xs transition-[border-color,box-shadow] focus-within:border-ring focus-within:ring-3 focus-within:ring-ring/25">
                  <textarea
                    value={question}
                    onChange={(event) => setQuestion(event.target.value)}
                    onKeyDown={(event) => {
                      if (event.key === "Enter" && !event.shiftKey) {
                        event.preventDefault()
                        void submit()
                      }
                    }}
                    placeholder="例如：查询千百度女鞋 QC153883D54 近7天销量和库存"
                    className="block min-h-[104px] w-full resize-none bg-transparent px-4 py-3.5 text-sm leading-6 outline-none placeholder:text-muted-foreground/60"
                    maxLength={500}
                    aria-label="自然语言查询问题"
                  />
                  <div className="flex min-h-12 items-center justify-between gap-3 border-t border-border bg-muted/20 px-2.5 py-2">
                    <div>
                      {question ? (
                        <Button
                          type="button"
                          variant="ghost"
                          size="icon-sm"
                          onClick={() => setQuestion("")}
                          disabled={loading}
                          title="清空输入"
                          aria-label="清空输入"
                        >
                          <X className="size-3.5" />
                        </Button>
                      ) : null}
                    </div>
                    <Button
                      type="submit"
                      size="lg"
                      disabled={!question.trim() || loading}
                      className="min-w-24"
                    >
                      {loading ? (
                        <LoaderCircle className="size-4 animate-spin" />
                      ) : (
                        <Search className="size-4" />
                      )}
                      {loading ? "查询中" : "查询"}
                    </Button>
                  </div>
                </div>
              </form>
            </section>

            {error ? (
              <div
                className="flex items-start gap-3 rounded-lg border border-destructive/30 bg-destructive/8 px-4 py-3 text-sm text-destructive"
                role="alert"
              >
                <CircleAlert className="mt-0.5 size-4 shrink-0" />
                <span className="leading-5">{error}</span>
              </div>
            ) : null}

            {loading ? (
              <section
                className="flex min-h-48 items-center justify-center rounded-lg border border-border bg-card/95 shadow-sm"
                aria-live="polite"
                aria-busy="true"
              >
                <div className="flex flex-col items-center px-6 py-10 text-center">
                  <div className="flex size-10 items-center justify-center rounded-lg border border-border bg-background shadow-xs">
                    <LoaderCircle className="size-5 animate-spin text-muted-foreground" />
                  </div>
                  <p className="mt-3 text-sm font-medium">正在查询</p>
                  <p className="mt-1 max-w-md truncate text-xs text-muted-foreground">
                    {question}
                  </p>
                </div>
              </section>
            ) : null}

            {!response && !loading && !error ? (
              <section className="overflow-hidden rounded-lg border border-border bg-card/95 shadow-sm">
                <div className="flex h-12 items-center gap-2 border-b border-border px-4 text-sm font-semibold sm:px-5">
                  <Table2 className="size-4 text-muted-foreground" /> 推荐问题
                </div>
                <div className="grid lg:grid-cols-3">
                  {EXAMPLE_QUESTIONS.map((item, index) => {
                    const Icon = item.icon
                    return (
                      <button
                        key={item.question}
                        type="button"
                        className={`group flex min-h-20 cursor-pointer items-center gap-3 px-4 py-3.5 text-left transition-colors hover:bg-muted/45 sm:px-5 ${index > 0 ? "border-t border-border/70 lg:border-t-0 lg:border-l" : ""}`}
                        onClick={() => void submit(item.question)}
                      >
                        <span className="flex size-9 shrink-0 items-center justify-center rounded-lg border border-border bg-background text-muted-foreground shadow-xs transition-colors group-hover:text-foreground">
                          <Icon className="size-4" />
                        </span>
                        <span className="min-w-0 flex-1">
                          <span className="block text-xs font-medium text-muted-foreground">
                            {item.label}
                          </span>
                          <span className="mt-1 line-clamp-1 block text-sm text-foreground">
                            {item.question}
                          </span>
                        </span>
                        <ArrowUpRight className="size-4 shrink-0 text-muted-foreground transition-transform group-hover:translate-x-0.5 group-hover:-translate-y-0.5" />
                      </button>
                    )
                  })}
                </div>
              </section>
            ) : null}

            {response && !loading ? (
              <section className="overflow-hidden rounded-lg border border-border bg-card/95 shadow-sm">
                <div className="border-b border-border px-4 py-4 sm:px-5">
                  <div className="flex flex-wrap items-start justify-between gap-3">
                    <div className="min-w-0 flex-1">
                      <div className="flex flex-wrap items-center gap-2">
                        <h2 className="text-base font-semibold">
                          {response.title}
                        </h2>
                      </div>
                      <p className="mt-2 max-w-5xl text-sm leading-6 text-foreground/80">
                        {response.summary}
                      </p>
                    </div>
                  </div>

                  {visibleConditions.length > 0 ||
                  response.data_as_of.length > 0 ? (
                    <div className="mt-3 flex flex-wrap gap-1.5">
                      {visibleConditions.map((item) => (
                        <span
                          key={`${item.label}-${item.value}`}
                          className="rounded-md border border-border bg-muted/35 px-2.5 py-1 text-xs text-muted-foreground"
                        >
                          {item.label}：
                          <span className="font-medium text-foreground">
                            {item.value}
                          </span>
                        </span>
                      ))}
                      {response.data_as_of.map((item) => (
                        <span
                          key={`${item.label}-${item.value}`}
                          className="rounded-md border border-blue-500/20 bg-blue-500/6 px-2.5 py-1 text-xs text-blue-700 dark:text-blue-300"
                        >
                          {item.label}：
                          <span className="font-medium">{item.value}</span>
                        </span>
                      ))}
                    </div>
                  ) : null}
                </div>

                {response.metrics.length > 0 ? (
                  <div
                    className={`grid gap-px border-b border-border bg-border ${metricGridColumns(response.metrics.length)}`}
                  >
                    {response.metrics.map((item) => (
                      <div
                        key={item.label}
                        className="bg-card px-4 py-3.5 sm:px-5"
                      >
                        <p className="text-xs text-muted-foreground">
                          {item.label}
                        </p>
                        <p
                          className={`mt-2 inline-flex min-w-10 rounded-md px-2 py-1 text-xl font-semibold tabular-nums ${metricTone(item.tone)}`}
                        >
                          {item.value}
                        </p>
                        {item.hint ? (
                          <p className="mt-2 text-xs text-muted-foreground">
                            {item.hint}
                          </p>
                        ) : null}
                      </div>
                    ))}
                  </div>
                ) : null}

                {response.generated_sql ? (
                  <details className="group border-b border-border bg-muted/15">
                    <summary className="flex cursor-pointer list-none items-center gap-2 px-4 py-3 text-xs font-medium text-muted-foreground transition-colors hover:text-foreground sm:px-5">
                      <ChevronRight className="size-3.5 transition-transform group-open:rotate-90" />
                      <Database className="size-3.5" />
                      执行 SQL
                    </summary>
                    <div className="px-4 pb-4 sm:px-5">
                      <pre className="max-h-64 overflow-auto rounded-lg border border-border bg-background p-3 text-xs leading-5 whitespace-pre-wrap text-foreground">
                        {response.generated_sql}
                      </pre>
                    </div>
                  </details>
                ) : null}

                {response.needs_clarification ? (
                  <div className="m-4 flex items-start gap-3 rounded-lg border border-amber-500/25 bg-amber-500/8 px-4 py-3 text-sm leading-6 text-foreground/80 sm:m-5">
                    <CircleAlert className="mt-1 size-4 shrink-0 text-amber-600" />
                    {response.summary}
                  </div>
                ) : null}

                {hasRows ? (
                  <div className="max-h-[min(60vh,560px)] overflow-auto">
                    <table className="min-w-full border-collapse text-sm">
                      <thead className="sticky top-0 z-10 border-b border-border bg-muted/95 text-left text-xs text-muted-foreground backdrop-blur">
                        <tr>
                          {response.columns.map((column) => (
                            <th
                              key={column.key}
                              className="px-4 py-3 font-medium whitespace-nowrap"
                            >
                              {column.label}
                            </th>
                          ))}
                        </tr>
                      </thead>
                      <tbody>
                        {response.rows.map((row, index) => (
                          <tr
                            key={`${response.query_id}-${index}`}
                            className="border-b border-border/70 transition-colors last:border-0 hover:bg-muted/35"
                          >
                            {response.columns.map((column) => (
                              <td
                                key={column.key}
                                className="max-w-72 px-4 py-3 align-top whitespace-nowrap text-foreground"
                                title={formatCell(row[column.key], column)}
                              >
                                {formatCell(row[column.key], column)}
                              </td>
                            ))}
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                ) : !response.needs_clarification ? (
                  <div className="flex min-h-32 items-center justify-center border-b border-border px-5 py-8 text-sm text-muted-foreground">
                    没有符合条件的数据
                  </div>
                ) : null}

                {response.suggestions.length > 0 || response.link ? (
                  <div className="flex flex-wrap items-center justify-end gap-2 border-t border-border px-4 py-3 sm:px-5">
                    {response.suggestions.slice(0, 3).map((item) => (
                      <Button
                        key={item}
                        type="button"
                        variant="outline"
                        size="sm"
                        onClick={() => void submit(item)}
                        title={item}
                      >
                        <span className="max-w-48 truncate">{item}</span>
                      </Button>
                    ))}
                    {response.link ? (
                      <Button type="button" size="sm" asChild>
                        <Link href={response.link.href}>
                          {response.link.label}
                          <ArrowUpRight className="size-3.5" />
                        </Link>
                      </Button>
                    ) : null}
                  </div>
                ) : null}
              </section>
            ) : null}
          </main>
        </div>
      </div>
    </div>
  )
}
