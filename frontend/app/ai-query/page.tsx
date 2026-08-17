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
  Link2,
  LoaderCircle,
  MessageSquarePlus,
  Search,
  TableProperties,
  Trash2,
  X,
} from "lucide-react"

import { ConfirmDialog } from "@/components/confirm-dialog"
import { useAuth } from "@/components/auth/auth-provider"
import { Button } from "@/components/ui/button"
import {
  getAiQueryFineTableHref,
  getAiQueryPrimaryHref,
  getAiQuerySuggestionHref,
} from "@/lib/ai-query-navigation"
import {
  ApiError,
  clearAiQueryHistory,
  listAiQueryHistory,
  runAiQuery,
} from "@/lib/api"
import { hasProductGoodsDepartmentAccess } from "@/lib/product-goods-access"
import type {
  AiQueryColumn,
  AiQueryContext,
  AiQueryResponse,
} from "@/lib/types"

const MAX_HISTORY_ITEMS = 8
const AI_QUERY_TIMEOUT_MS = 190_000
const AI_QUERY_DRAFT_STORAGE_KEY = "hede.ai-query.draft"
const AI_QUERY_CONTEXT_STORAGE_KEY = "hede.ai-query.context.v1"
const HIDDEN_CONDITION_LABELS = new Set(["查询模式", "数据范围"])

const numberFormatter = new Intl.NumberFormat("zh-CN")

function formatSizeQuantities(value: unknown) {
  let parsed = value
  if (typeof value === "string" && value.trim().startsWith("{")) {
    try {
      parsed = JSON.parse(value)
    } catch {
      return null
    }
  }
  if (!parsed || Array.isArray(parsed) || typeof parsed !== "object") {
    return null
  }
  const entries = Object.entries(parsed as Record<string, unknown>).sort(
    ([left], [right]) =>
      left.localeCompare(right, "zh-CN", { numeric: true })
  )
  if (!entries.length) return "暂无数据"
  return entries
    .map(([size, quantity]) => `${size}: ${String(quantity ?? 0)}`)
    .join("，")
}

function readAiQueryDraft() {
  if (typeof window === "undefined") return ""
  try {
    return window.localStorage.getItem(AI_QUERY_DRAFT_STORAGE_KEY) ?? ""
  } catch {
    return ""
  }
}

function readAiQueryContext(storageKey: string): AiQueryContext | null {
  if (typeof window === "undefined") return null
  try {
    const rawValue = window.sessionStorage.getItem(storageKey)
    if (!rawValue) return null
    const value = JSON.parse(rawValue) as Partial<AiQueryContext>
    if (!Array.isArray(value.questions) || value.questions.length === 0) {
      return null
    }
    return {
      questions: value.questions
        .filter((item): item is string => typeof item === "string")
        .slice(-4),
      brand: typeof value.brand === "string" ? value.brand : null,
      product_codes: Array.isArray(value.product_codes)
        ? value.product_codes
            .filter((item): item is string => typeof item === "string")
            .slice(0, 50)
        : [],
      year: typeof value.year === "number" ? value.year : null,
      intent: typeof value.intent === "string" ? value.intent : null,
      used_previous: Boolean(value.used_previous),
    }
  } catch {
    return null
  }
}

function formatCell(value: unknown, column: AiQueryColumn) {
  if (value === null || value === undefined || value === "") return "暂无数据"
  if (/尺码.*数量|size.*quantit/i.test(`${column.key} ${column.label}`)) {
    const formatted = formatSizeQuantities(value)
    if (formatted) return formatted
  }
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

function resultColumnWidth(column: AiQueryColumn) {
  if (column.type === "number") return 112
  if (column.type === "date") return 144
  if (/尺码.*数量|size.*quantit/i.test(`${column.key} ${column.label}`)) {
    return 240
  }
  if (
    /摘要|名称|说明|备注|地址|内容|message|description|summary|detail/i.test(
      `${column.key} ${column.label}`
    )
  ) {
    return 288
  }
  return 160
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
  const { hasPermission, user } = useAuth()
  const [question, setQuestion] = useState(readAiQueryDraft)
  const [response, setResponse] = useState<AiQueryResponse | null>(null)
  const [queryContext, setQueryContext] = useState<AiQueryContext | null>(null)
  const [history, setHistory] = useState<string[]>([])
  const [historyLoading, setHistoryLoading] = useState(true)
  const [historyClearing, setHistoryClearing] = useState(false)
  const [historyClearConfirmOpen, setHistoryClearConfirmOpen] = useState(false)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState("")
  const [hydratedContextStorageKey, setHydratedContextStorageKey] = useState<
    string | null
  >(null)
  const contextStorageKey = user?.id
    ? `${AI_QUERY_CONTEXT_STORAGE_KEY}.${user.id}`
    : null

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
    if (!contextStorageKey) {
      setHydratedContextStorageKey(null)
      setQueryContext(null)
      return
    }
    setQueryContext(readAiQueryContext(contextStorageKey))
    setHydratedContextStorageKey(contextStorageKey)
  }, [contextStorageKey])

  useEffect(() => {
    if (
      !contextStorageKey ||
      hydratedContextStorageKey !== contextStorageKey
    ) {
      return
    }
    try {
      if (queryContext) {
        window.sessionStorage.setItem(
          contextStorageKey,
          JSON.stringify(queryContext)
        )
      } else {
        window.sessionStorage.removeItem(contextStorageKey)
      }
    } catch {
      return
    }
  }, [contextStorageKey, hydratedContextStorageKey, queryContext])

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

  async function submit(
    nextQuestion = question,
    nextContext: AiQueryContext | null = queryContext
  ) {
    const value = nextQuestion.trim()
    if (!value || loading) return
    setQuestion(value)
    setLoading(true)
    setError("")
    try {
      const result = await runAiQuery(value, nextContext, {
        signal: AbortSignal.timeout(AI_QUERY_TIMEOUT_MS),
      })
      setResponse(result)
      setQueryContext(result.context ?? null)
      setHistory((current) =>
        [value, ...current.filter((item) => item !== value)].slice(
          0,
          MAX_HISTORY_ITEMS
        )
      )
      setQuestion("")
    } catch (requestError) {
      setError(errorMessage(requestError))
    } finally {
      setLoading(false)
    }
  }

  function startNewQuery() {
    setQueryContext(null)
    setResponse(null)
    setError("")
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
  const contextQuestion = queryContext?.questions.length
    ? queryContext.questions[queryContext.questions.length - 1]
    : ""
  const isEntryState = !response && !loading
  const resultColumnWidths =
    response?.columns.map((column) => resultColumnWidth(column)) ?? []
  const resultTableMinWidth = Math.max(
    720,
    resultColumnWidths.reduce((total, width) => total + width, 0)
  )
  const canOpenProductArchive = hasPermission("product.view")
  const canOpenFineTable = hasPermission("fine_table.view")
  const canOpenProductGoods =
    hasPermission("product.view") && hasProductGoodsDepartmentAccess(user)
  const resultFineTableHref =
    response && canOpenFineTable ? getAiQueryFineTableHref(response) : null
  const resultPrimaryHref = response ? getAiQueryPrimaryHref(response) : null
  const canOpenResultHref = (href: string) => {
    const pathname = new URL(href, "http://localhost").pathname
    if (["/product-goods", "/factory-channel-dashboard"].includes(pathname)) {
      return canOpenProductGoods
    }
    if (pathname === "/products") return canOpenProductArchive
    if (pathname === "/fine-table") return canOpenFineTable
    return true
  }
  const visibleResultSuggestions =
    response?.suggestions.filter((item) => {
      const href = getAiQuerySuggestionHref(response, item)
      return !href || canOpenResultHref(href)
    }) ?? []
  const showPrimaryResultLink = Boolean(
    response?.link &&
      resultPrimaryHref &&
      canOpenResultHref(resultPrimaryHref)
  )
  const visibleConditions =
    response?.conditions.filter(
      (item) => !HIDDEN_CONDITION_LABELS.has(item.label)
    ) ?? []

  return (
    <div className="app-page">
      <div className="app-content-wide min-h-[calc(100svh-2rem)] sm:min-h-[calc(100svh-3rem)]">
        <div className="mx-auto flex min-h-0 w-full max-w-[1640px] flex-1 flex-col gap-5">
          <div className="grid min-h-0 min-w-0 flex-1 items-stretch gap-6 xl:grid-cols-[minmax(0,1fr)_248px]">
            <main
              className={`flex min-h-0 min-w-0 flex-col gap-5 ${isEntryState ? "justify-center pb-[8vh]" : ""}`}
            >
              {error ? (
                <div
                  className="animate-in fade-in-0 slide-in-from-top-1 mx-auto flex w-full max-w-4xl items-start gap-3 rounded-lg border border-destructive/25 bg-card/95 p-3.5 shadow-[0_16px_36px_-30px_rgb(127_29_29_/_0.75)] duration-200"
                  role="alert"
                  aria-live="assertive"
                >
                  <span className="flex size-8 shrink-0 items-center justify-center rounded-md bg-destructive/10 text-destructive">
                    <CircleAlert className="size-4" />
                  </span>
                  <div className="min-w-0 flex-1 pt-0.5">
                    <p className="text-sm font-medium text-foreground">
                      查询未完成
                    </p>
                    <p className="mt-1 text-sm leading-5 text-muted-foreground">
                      {error}
                    </p>
                  </div>
                  <Button
                    type="button"
                    variant="ghost"
                    size="icon-sm"
                    className="-mt-0.5 -mr-0.5 shrink-0 cursor-pointer text-muted-foreground hover:text-foreground"
                    onClick={() => setError("")}
                    title="关闭提示"
                    aria-label="关闭提示"
                  >
                    <X className="size-3.5" />
                  </Button>
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
                  className="flex items-center justify-center px-6 pt-6"
                  aria-label="等待查询"
                >
                  <div className="flex size-11 items-center justify-center rounded-full border border-dashed border-border bg-muted/15 text-muted-foreground">
                    <Search className="size-[18px]" />
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
                        <table
                          className="w-full table-fixed border-collapse text-sm"
                          style={{ minWidth: resultTableMinWidth }}
                        >
                          <colgroup>
                            {response.columns.map((column, index) => (
                              <col
                                key={column.key}
                                style={{ width: resultColumnWidths[index] }}
                              />
                            ))}
                          </colgroup>
                          <thead className="sticky top-0 z-10 border-b border-border bg-muted/95 text-left text-xs text-muted-foreground backdrop-blur">
                            <tr>
                              {response.columns.map((column) => (
                                <th
                                  key={column.key}
                                  className={`overflow-hidden px-4 py-3 font-medium whitespace-nowrap ${column.type === "number" ? "text-right" : "text-left"}`}
                                >
                                  <span className="block truncate">
                                    {column.label}
                                  </span>
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
                                    className={`overflow-hidden px-4 py-3 align-top whitespace-nowrap text-foreground ${column.type === "number" ? "text-right tabular-nums" : "text-left"}`}
                                    title={formatCell(row[column.key], column)}
                                  >
                                    <span className="block truncate">
                                      {formatCell(row[column.key], column)}
                                    </span>
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

                  {visibleResultSuggestions.length > 0 ||
                  resultFineTableHref ||
                  showPrimaryResultLink ? (
                    <div className="mt-4 flex flex-wrap items-center justify-end gap-2">
                      {visibleResultSuggestions.slice(0, 3).map((item) => {
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
                      {resultFineTableHref ? (
                        <Button type="button" variant="outline" size="sm" asChild>
                          <Link href={resultFineTableHref}>
                            <TableProperties className="size-3.5" />
                            打开精细表
                          </Link>
                        </Button>
                      ) : null}
                      {showPrimaryResultLink && response.link && resultPrimaryHref ? (
                        <Button type="button" size="sm" asChild>
                          <Link href={resultPrimaryHref}>
                            {response.link.label}
                            <ArrowUpRight className="size-3.5" />
                          </Link>
                        </Button>
                      ) : null}
                    </div>
                  ) : null}
                </section>
              ) : null}

              <section
                className={`${isEntryState ? "mx-auto w-full max-w-4xl" : "sticky bottom-0 mt-auto"} z-20 overflow-hidden rounded-4xl border border-border/90 bg-card shadow-[0_18px_46px_-28px_rgb(15_23_42_/_0.65)] transition-[border-color,box-shadow] focus-within:border-foreground/25 focus-within:shadow-[0_20px_52px_-28px_rgb(15_23_42_/_0.75)]`}
              >
                {queryContext && contextQuestion ? (
                  <div className="flex min-w-0 items-center gap-2 border-b border-border/70 bg-muted/20 px-4 py-2 sm:px-5">
                    <Link2 className="size-3.5 shrink-0 text-blue-600 dark:text-blue-400" />
                    <span className="shrink-0 text-xs font-medium text-foreground/80">
                      连续追问
                    </span>
                    <span
                      className="min-w-0 flex-1 truncate text-xs text-muted-foreground"
                      title={contextQuestion}
                    >
                      {contextQuestion}
                    </span>
                    <Button
                      type="button"
                      variant="ghost"
                      size="icon-sm"
                      className="shrink-0 cursor-pointer"
                      onClick={startNewQuery}
                      disabled={loading}
                      title="结束连续追问并开始新查询"
                      aria-label="结束连续追问并开始新查询"
                    >
                      <MessageSquarePlus className="size-3.5" />
                    </Button>
                  </div>
                ) : null}
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
                      onChange={(event) => {
                        setQuestion(event.target.value)
                        if (error) setError("")
                      }}
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
                        onClick={() => {
                          startNewQuery()
                          void submit(item, null)
                        }}
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
