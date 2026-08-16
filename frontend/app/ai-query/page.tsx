"use client"

import Link from "next/link"
import { useEffect, useState } from "react"
import {
  ArrowUp,
  ArrowUpRight,
  ChevronRight,
  CircleAlert,
  Clock3,
  Database,
  History,
  LoaderCircle,
  Search,
  Trash2,
  X,
} from "lucide-react"

import { ConfirmDialog } from "@/components/confirm-dialog"
import { Button } from "@/components/ui/button"
import {
  getAiQueryPrimaryHref,
  getAiQuerySuggestionHref,
} from "@/lib/ai-query-navigation"
import {
  ApiError,
  clearAiQueryHistory,
  listAiQueryHistory,
  runAiQuery,
} from "@/lib/api"
import type { AiQueryColumn, AiQueryResponse } from "@/lib/types"

const MAX_HISTORY_ITEMS = 8
const AI_QUERY_TIMEOUT_MS = 150_000
const AI_QUERY_DRAFT_STORAGE_KEY = "hede.ai-query.draft"
const HIDDEN_CONDITION_LABELS = new Set(["查询模式", "数据范围"])

const numberFormatter = new Intl.NumberFormat("zh-CN")

function readAiQueryDraft() {
  if (typeof window === "undefined") return ""
  try {
    return window.localStorage.getItem(AI_QUERY_DRAFT_STORAGE_KEY) ?? ""
  } catch {
    return ""
  }
}

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

function metricAccent(tone: string | undefined) {
  return (
    {
      slate: "bg-slate-400",
      blue: "bg-blue-500",
      violet: "bg-violet-500",
      orange: "bg-orange-500",
      emerald: "bg-emerald-500",
    }[tone || "slate"] || "bg-muted-foreground"
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
  const [question, setQuestion] = useState(readAiQueryDraft)
  const [response, setResponse] = useState<AiQueryResponse | null>(null)
  const [history, setHistory] = useState<string[]>([])
  const [historyLoading, setHistoryLoading] = useState(true)
  const [historyClearing, setHistoryClearing] = useState(false)
  const [historyClearConfirmOpen, setHistoryClearConfirmOpen] = useState(false)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState("")

  useEffect(() => {
    try {
      if (question) {
        window.localStorage.setItem(AI_QUERY_DRAFT_STORAGE_KEY, question)
      } else {
        window.localStorage.removeItem(AI_QUERY_DRAFT_STORAGE_KEY)
      }
    } catch {
      return
    }
  }, [question])

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
      setQuestion("")
    } catch (requestError) {
      setResponse(null)
      setError(errorMessage(requestError))
    } finally {
      setLoading(false)
    }
  }

  async function clearHistory() {
    if (historyClearing) return
    setHistoryClearConfirmOpen(false)
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
      <div className="app-content-wide min-h-[calc(100svh-2rem)] sm:min-h-[calc(100svh-3rem)]">
        <div className="mx-auto flex min-h-0 w-full max-w-[1640px] flex-1 flex-col gap-5">
          <div className="grid min-h-0 min-w-0 flex-1 items-stretch gap-6 xl:grid-cols-[minmax(0,1fr)_248px]">
            <main className="flex min-h-0 min-w-0 flex-col gap-5">
              {error ? (
                <div
                  className="flex items-start gap-3 border-y border-destructive/25 bg-destructive/6 px-1 py-3 text-sm text-destructive"
                  role="alert"
                >
                  <CircleAlert className="mt-0.5 size-4 shrink-0" />
                  <span className="leading-5">{error}</span>
                </div>
              ) : null}

              {loading ? (
                <section
                  className="flex min-h-48 flex-1 items-center border-y border-border/80 py-10"
                  aria-live="polite"
                  aria-busy="true"
                >
                  <div className="mx-auto flex max-w-xl flex-col items-center px-6 text-center">
                    <LoaderCircle className="size-5 animate-spin text-foreground/70" />
                    <p className="mt-3 text-sm font-medium">正在读取数据</p>
                    <p className="mt-1 max-w-full truncate text-xs text-muted-foreground">
                      {question}
                    </p>
                    <div
                      className="mt-6 grid w-full grid-cols-3 gap-2"
                      aria-hidden="true"
                    >
                      <span className="h-12 animate-pulse rounded-md bg-muted/70" />
                      <span className="h-12 animate-pulse rounded-md bg-muted/50 [animation-delay:120ms]" />
                      <span className="h-12 animate-pulse rounded-md bg-muted/35 [animation-delay:240ms]" />
                    </div>
                  </div>
                </section>
              ) : null}

              {!response && !loading && !error ? (
                <section
                  className="flex min-h-48 flex-1 items-center justify-center px-6 py-12"
                  aria-label="等待查询"
                >
                  <div className="w-full max-w-md text-center">
                    <div className="mx-auto flex size-12 items-center justify-center rounded-full border border-dashed border-border bg-muted/20 text-muted-foreground">
                      <Search className="size-5" />
                    </div>
                    <p className="mt-4 text-sm font-medium text-foreground/80">
                      等待查询
                    </p>
                    <p className="mt-1 text-xs text-muted-foreground">
                      查询结果将在这里展开
                    </p>
                    <div
                      className="mx-auto mt-7 grid max-w-xs grid-cols-[0.8fr_1.2fr_0.65fr] gap-2 opacity-55"
                      aria-hidden="true"
                    >
                      <span className="h-px bg-border" />
                      <span className="h-px bg-border" />
                      <span className="h-px bg-border" />
                    </div>
                  </div>
                </section>
              ) : null}

              {response && !loading ? (
                <section className="min-w-0 border-t border-border/80 pt-5">
                  <div className="flex flex-wrap items-start justify-between gap-4 px-1">
                    <div className="min-w-0 flex-1">
                      <div className="flex items-center gap-2.5">
                        <span
                          className="h-5 w-1 rounded-full bg-foreground"
                          aria-hidden="true"
                        />
                        <h2 className="text-lg font-semibold">
                          {response.title}
                        </h2>
                      </div>
                      <p className="mt-2 max-w-5xl pl-3.5 text-sm leading-6 text-foreground/75">
                        {response.summary}
                      </p>
                    </div>
                  </div>

                  {visibleConditions.length > 0 ||
                    response.data_as_of.length > 0 ? (
                    <div className="mt-3 flex flex-wrap gap-x-4 gap-y-2 px-1 pl-4 text-xs text-muted-foreground">
                      {visibleConditions.map((item) => (
                        <span
                          key={`${item.label}-${item.value}`}
                          className="inline-flex items-center gap-1.5"
                        >
                          <span className="size-1 rounded-full bg-muted-foreground/60" />
                          {item.label}：
                          <span className="font-medium text-foreground">
                            {item.value}
                          </span>
                        </span>
                      ))}
                      {response.data_as_of.map((item) => (
                        <span
                          key={`${item.label}-${item.value}`}
                          className="inline-flex items-center gap-1.5 text-blue-700 dark:text-blue-300"
                        >
                          <span className="size-1 rounded-full bg-blue-500" />
                          {item.label}：
                          <span className="font-medium">{item.value}</span>
                        </span>
                      ))}
                    </div>
                  ) : null}

                  {response.metrics.length > 0 ? (
                    <div
                      className={`mt-5 grid gap-px overflow-hidden rounded-lg border border-border bg-border ${metricGridColumns(response.metrics.length)}`}
                    >
                      {response.metrics.map((item) => (
                        <div
                          key={item.label}
                          className="bg-background px-4 py-4 sm:px-5"
                        >
                          <div className="flex items-center gap-2 text-xs text-muted-foreground">
                            <span
                              className={`size-1.5 rounded-full ${metricAccent(item.tone)}`}
                            />
                            {item.label}
                          </div>
                          <p className="mt-2 text-2xl font-semibold text-foreground tabular-nums">
                            {item.value}
                          </p>
                          {item.hint ? (
                            <p className="mt-1.5 text-xs text-muted-foreground">
                              {item.hint}
                            </p>
                          ) : null}
                        </div>
                      ))}
                    </div>
                  ) : null}

                  {response.needs_clarification ? (
                    <div className="mt-5 flex items-start gap-3 rounded-lg border border-amber-500/25 bg-amber-500/8 px-4 py-3 text-sm leading-6 text-foreground/80">
                      <CircleAlert className="mt-1 size-4 shrink-0 text-amber-600" />
                      {response.summary}
                    </div>
                  ) : null}

                  <div className="mt-5 overflow-hidden rounded-lg border border-border bg-background shadow-[0_10px_30px_-28px_rgb(15_23_42_/_0.7)]">
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
                                className="border-b border-border/65 transition-colors last:border-0 hover:bg-muted/30"
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
                      <div className="flex min-h-32 items-center justify-center px-5 py-8 text-sm text-muted-foreground">
                        没有符合条件的数据
                      </div>
                    ) : null}
                  </div>

                  {response.generated_sql ? (
                    <details className="group mt-3 rounded-lg border border-border/80 bg-muted/10">
                      <summary className="flex cursor-pointer list-none items-center gap-2 px-4 py-3 text-xs font-medium text-muted-foreground transition-colors hover:text-foreground">
                        <ChevronRight className="size-3.5 transition-transform group-open:rotate-90" />
                        <Database className="size-3.5" />
                        执行 SQL
                      </summary>
                      <div className="px-4 pb-4">
                        <pre className="max-h-64 overflow-auto border-t border-border/80 pt-3 text-xs leading-5 whitespace-pre-wrap text-foreground">
                          {response.generated_sql}
                        </pre>
                      </div>
                    </details>
                  ) : null}

                  {response.suggestions.length > 0 || response.link ? (
                    <div className="mt-4 flex flex-wrap items-center justify-end gap-2">
                      {response.suggestions.slice(0, 3).map((item) => {
                        const href = getAiQuerySuggestionHref(response, item)
                        return href ? (
                          <Button
                            key={item}
                            type="button"
                            variant="outline"
                            size="sm"
                            asChild
                          >
                            <Link href={href} title={item}>
                              <span className="max-w-48 truncate">{item}</span>
                            </Link>
                          </Button>
                        ) : (
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
                        )
                      })}
                      {response.link ? (
                        <Button type="button" size="sm" asChild>
                          <Link
                            href={
                              getAiQueryPrimaryHref(response) ??
                              response.link.href
                            }
                          >
                            {response.link.label}
                            <ArrowUpRight className="size-3.5" />
                          </Link>
                        </Button>
                      ) : null}
                    </div>
                  ) : null}
                </section>
              ) : null}

              <section className="sticky bottom-4 z-20 mt-auto overflow-hidden rounded-4xl border border-border/90 bg-card shadow-[0_18px_46px_-28px_rgb(15_23_42_/_0.65)] transition-[border-color,box-shadow] focus-within:border-foreground/25 focus-within:shadow-[0_20px_52px_-28px_rgb(15_23_42_/_0.75)]">
                <form
                  className="relative"
                  onSubmit={(event) => {
                    event.preventDefault()
                    void submit()
                  }}
                >
                  <div className="flex min-h-[96px] items-start gap-3 px-4 pt-4 pr-14 pb-3 sm:px-5 sm:pt-4 sm:pr-16">
                    <Search className="mt-1 size-[18px] shrink-0 text-muted-foreground" />
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
                      className="block min-h-[64px] min-w-0 flex-1 resize-none bg-transparent pb-2 text-[15px] leading-7 outline-none placeholder:text-muted-foreground/55"
                      aria-label="自然语言查询问题"
                    />
                    {question ? (
                      <Button
                        type="button"
                        variant="ghost"
                        size="icon-sm"
                        className="shrink-0"
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
                    size="icon"
                    disabled={!question.trim() || loading}
                    className="absolute right-3 bottom-3 size-9 shrink-0 cursor-pointer rounded-full disabled:cursor-not-allowed sm:right-4"
                    title={loading ? "查询中" : "提交查询"}
                    aria-label={loading ? "查询中" : "提交查询"}
                  >
                    {loading ? (
                      <LoaderCircle className="size-4 animate-spin" />
                    ) : (
                      <ArrowUp className="size-4" />
                    )}
                  </Button>
                </form>
              </section>
            </main>

            <aside className="min-w-0 xl:sticky xl:top-5 xl:self-start">
              <div className="border-t border-border/80 pt-4 xl:border-t-0 xl:border-l xl:pt-0 xl:pl-5">
                <div className="flex h-9 items-center justify-between">
                  <div className="flex items-center gap-2 text-sm font-semibold">
                    <History className="size-4 text-muted-foreground" />
                    最近查询
                  </div>
                  {history.length > 0 ? (
                    <Button
                      type="button"
                      variant="ghost"
                      size="icon-sm"
                      onClick={() => setHistoryClearConfirmOpen(true)}
                      disabled={historyClearing}
                      title="清空最近查询"
                      aria-label="清空最近查询"
                    >
                      <Trash2 className="size-3.5" />
                    </Button>
                  ) : null}
                </div>

                {historyLoading ? (
                  <div className="space-y-2 py-3" aria-label="正在加载最近查询">
                    <div className="h-10 animate-pulse rounded-md bg-muted/55" />
                    <div className="h-10 animate-pulse rounded-md bg-muted/35" />
                  </div>
                ) : history.length > 0 ? (
                  <div className="mt-1 grid gap-1 sm:grid-cols-2 xl:grid-cols-1">
                    {history.map((item) => (
                      <button
                        key={item}
                        type="button"
                        className="group flex w-full cursor-pointer items-start gap-2.5 rounded-md px-2 py-2.5 text-left transition-colors hover:bg-muted/55 disabled:cursor-not-allowed disabled:opacity-60"
                        onClick={() => void submit(item)}
                        disabled={loading}
                        title={item}
                      >
                        <Clock3 className="mt-0.5 size-3.5 shrink-0 text-muted-foreground" />
                        <span className="line-clamp-2 min-w-0 flex-1 text-xs leading-5 text-foreground/75 group-hover:text-foreground">
                          {item}
                        </span>
                        <ChevronRight className="mt-0.5 size-3.5 shrink-0 text-muted-foreground opacity-0 transition-[opacity,transform] group-hover:translate-x-0.5 group-hover:opacity-100" />
                      </button>
                    ))}
                  </div>
                ) : (
                  <p className="py-5 text-xs text-muted-foreground">
                    暂无最近查询
                  </p>
                )}
              </div>
            </aside>
          </div>
        </div>
      </div>
      <ConfirmDialog
        open={historyClearConfirmOpen}
        title="确认删除聊天记录"
        description="确定删除当前账户的全部最近查询记录吗？删除后无法恢复。"
        confirmLabel={historyClearing ? "删除中..." : "删除"}
        variant="destructive"
        onConfirm={() => void clearHistory()}
        onCancel={() => setHistoryClearConfirmOpen(false)}
      />
    </div>
  )
}
