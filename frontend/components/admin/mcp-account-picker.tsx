"use client"

import { useEffect, useId, useRef, useState } from "react"
import {
  Check,
  ChevronDown,
  ChevronLeft,
  ChevronRight,
  Loader2,
  Search,
  UserRound,
  X,
} from "lucide-react"

import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import {
  listMcpCandidates,
  type McpCandidate,
  type McpPage,
} from "@/lib/mcp-tokens"
import { cn } from "@/lib/utils"

type McpAccountPickerProps = {
  value: McpCandidate | null
  onChange: (account: McpCandidate) => void
  disabled?: boolean
}

export function McpAccountPicker({
  value,
  onChange,
  disabled = false,
}: McpAccountPickerProps) {
  const identity = useId()
  const triggerRef = useRef<HTMLButtonElement>(null)
  const searchRef = useRef<HTMLInputElement>(null)
  const resultsRef = useRef<HTMLDivElement>(null)
  const [open, setOpen] = useState(false)
  const [query, setQuery] = useState("")
  const [page, setPage] = useState(1)
  const [retry, setRetry] = useState(0)
  const [result, setResult] = useState<McpPage<McpCandidate> | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState("")

  useEffect(() => {
    if (!open) return
    searchRef.current?.focus()
  }, [open])

  useEffect(() => {
    if (!open) return
    let cancelled = false
    const timer = setTimeout(
      () => {
        void listMcpCandidates(query.trim(), page)
          .then((response) => {
            if (!cancelled) setResult(response)
          })
          .catch((failure: unknown) => {
            if (!cancelled)
              setError(
                failure instanceof Error
                  ? failure.message
                  : "账号加载失败，请重试"
              )
          })
          .finally(() => {
            if (!cancelled) setLoading(false)
          })
      },
      query ? 250 : 0
    )
    return () => {
      cancelled = true
      clearTimeout(timer)
    }
  }, [open, query, page, retry])

  function changeQuery(next: string) {
    if (next === query) return
    setQuery(next)
    setPage(1)
    setLoading(true)
    setError("")
  }

  function changePage(next: number) {
    setPage(next)
    setLoading(true)
    setError("")
  }

  function close() {
    setOpen(false)
    triggerRef.current?.focus()
  }

  const totalPages = Math.max(
    1,
    Math.ceil((result?.total ?? 0) / (result?.page_size || 30))
  )

  return (
    <div className="min-w-0 space-y-2">
      <div className="flex items-center justify-between gap-2">
        <label
          id={`${identity}-label`}
          htmlFor={`${identity}-trigger`}
          className="text-sm font-medium"
        >
          中台账号
        </label>
        {value ? (
          <span className="flex items-center gap-1 text-xs text-primary">
            <Check aria-hidden="true" className="size-3" />
            已选择
          </span>
        ) : null}
      </div>
      <div
        className={cn(
          "overflow-hidden rounded-xl border bg-card transition-colors",
          open ? "border-ring/60 shadow-xs" : "border-input"
        )}
      >
        <button
          id={`${identity}-trigger`}
          ref={triggerRef}
          type="button"
          aria-labelledby={`${identity}-label`}
          aria-describedby={`${identity}-selection`}
          aria-expanded={open}
          aria-controls={open ? `${identity}-panel` : undefined}
          disabled={disabled}
          onClick={() => {
            if (open) close()
            else {
              setLoading(true)
              setError("")
              setOpen(true)
            }
          }}
          className="flex min-h-14 w-full cursor-pointer items-center gap-3 p-3 text-left transition-colors outline-none hover:bg-muted/40 focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-inset disabled:cursor-not-allowed disabled:opacity-50"
        >
          <span
            aria-hidden="true"
            className={cn(
              "flex size-9 shrink-0 items-center justify-center rounded-lg",
              value
                ? "bg-primary/10 text-primary"
                : "bg-muted text-muted-foreground"
            )}
          >
            {value ? (
              <span className="text-sm font-semibold">
                {(value.display_name || value.username).slice(0, 1)}
              </span>
            ) : (
              <UserRound className="size-4" />
            )}
          </span>
          <span id={`${identity}-selection`} className="min-w-0 flex-1">
            <span className="block truncate text-sm font-medium">
              {value ? value.display_name || value.username : "请选择账号"}
            </span>
            <span className="mt-0.5 block truncate text-xs text-muted-foreground">
              {value ? value.username : "按姓名或用户名搜索"}
            </span>
          </span>
          {value ? (
            <span className="max-w-24 truncate rounded-md bg-muted px-2 py-1 text-xs text-muted-foreground">
              {value.department_code || "未分配部门"}
            </span>
          ) : null}
          <ChevronDown
            aria-hidden="true"
            className={cn(
              "size-4 shrink-0 text-muted-foreground transition-transform",
              open && "rotate-180"
            )}
          />
        </button>
        {open ? (
          <div
            id={`${identity}-panel`}
            role="region"
            aria-label="选择中台账号"
            className="border-t border-border"
            onKeyDown={(event) => {
              if (event.key === "Escape") {
                event.preventDefault()
                event.stopPropagation()
                close()
              }
            }}
          >
            <div className="p-2">
              <div className="relative">
                <Search
                  aria-hidden="true"
                  className="pointer-events-none absolute top-2.5 left-3 size-4 text-muted-foreground"
                />
                <Input
                  ref={searchRef}
                  aria-label="搜索中台账号"
                  placeholder="输入姓名或用户名…"
                  autoComplete="off"
                  value={query}
                  maxLength={100}
                  disabled={disabled}
                  onChange={(event) => changeQuery(event.target.value)}
                  onKeyDown={(event) => {
                    if (event.key === "Enter") event.preventDefault()
                    if (event.key === "ArrowDown") {
                      event.preventDefault()
                      resultsRef.current
                        ?.querySelector<HTMLInputElement>(
                          'input[type="radio"]:not(:disabled)'
                        )
                        ?.focus()
                    }
                  }}
                  className="border-transparent bg-muted/60 pr-10 pl-9 shadow-none"
                />
                {query ? (
                  <Button
                    type="button"
                    size="icon-sm"
                    variant="ghost"
                    aria-label="清空账号搜索"
                    disabled={disabled}
                    className="absolute top-1 right-1"
                    onClick={() => {
                      changeQuery("")
                      searchRef.current?.focus()
                    }}
                  >
                    <X aria-hidden="true" className="size-3.5" />
                  </Button>
                ) : null}
              </div>
            </div>
            {loading ? (
              <div
                role="status"
                className="flex h-32 items-center justify-center gap-2 text-sm text-muted-foreground"
              >
                <Loader2 aria-hidden="true" className="size-4 animate-spin" />
                正在加载账号…
              </div>
            ) : error ? (
              <div className="space-y-3 px-4 py-6 text-center">
                <p role="alert" className="text-sm text-destructive">
                  {error}
                </p>
                <Button
                  type="button"
                  size="sm"
                  variant="outline"
                  disabled={disabled}
                  onClick={() => {
                    setError("")
                    setLoading(true)
                    setRetry((previous) => previous + 1)
                  }}
                >
                  重新加载账号
                </Button>
              </div>
            ) : result?.items.length ? (
              <div
                ref={resultsRef}
                role="radiogroup"
                aria-label="可选中台账号"
                className="max-h-52 space-y-1 overflow-y-auto overscroll-contain px-2 pb-2"
              >
                {result.items.map((account) => {
                  const selected = account.id === value?.id
                  const unavailable = disabled || !account.profiles.length
                  return (
                    <label
                      key={account.id}
                      className={cn(
                        "relative flex min-h-14 cursor-pointer items-center gap-3 rounded-lg px-3 py-2 transition-colors hover:bg-muted/60 has-focus-visible:ring-2 has-focus-visible:ring-ring has-focus-visible:ring-inset",
                        selected && "bg-primary/5",
                        unavailable && "cursor-not-allowed opacity-50"
                      )}
                    >
                      <input
                        type="radio"
                        name={`${identity}-account`}
                        value={account.id}
                        aria-label={`${account.username} · ${account.display_name} · ${account.department_code}`}
                        checked={selected}
                        disabled={unavailable}
                        onChange={() => {
                          onChange(account)
                          close()
                        }}
                        className="sr-only"
                      />
                      <span
                        aria-hidden="true"
                        className={cn(
                          "flex size-8 shrink-0 items-center justify-center rounded-full text-xs font-medium",
                          selected
                            ? "bg-primary/10 text-primary"
                            : "bg-muted text-muted-foreground"
                        )}
                      >
                        {(account.display_name || account.username).slice(0, 1)}
                      </span>
                      <span className="min-w-0 flex-1">
                        <span className="block truncate text-sm font-medium">
                          {account.display_name || account.username}
                        </span>
                        <span className="block truncate text-xs text-muted-foreground">
                          {account.username}
                          {!account.profiles.length ? " · 暂无查询范围" : ""}
                        </span>
                      </span>
                      <span className="max-w-24 truncate rounded-md bg-muted/70 px-2 py-1 text-xs text-muted-foreground">
                        {account.department_code || "未分配部门"}
                      </span>
                      <span
                        aria-hidden="true"
                        className={cn(
                          "flex size-4 shrink-0 items-center justify-center rounded-full border",
                          selected
                            ? "border-primary bg-primary text-primary-foreground"
                            : "border-input"
                        )}
                      >
                        {selected ? <Check className="size-3" /> : null}
                      </span>
                    </label>
                  )
                })}
              </div>
            ) : (
              <div className="space-y-1 px-4 py-7 text-center">
                <UserRound
                  aria-hidden="true"
                  className="mx-auto mb-2 size-5 text-muted-foreground"
                />
                <p role="status" className="text-sm font-medium">
                  {query.trim() ? "没有找到匹配账号" : "暂无可选账号"}
                </p>
                <p className="text-xs text-muted-foreground">
                  {query.trim()
                    ? "换个姓名或用户名试试"
                    : "请先确认账号已启用并具备商品查看权限"}
                </p>
              </div>
            )}
            {!loading && !error && result ? (
              <div className="flex min-h-10 flex-wrap items-center justify-between gap-2 border-t border-border bg-muted/20 px-3 py-2 text-xs text-muted-foreground">
                <span>共 {result.total} 个账号</span>
                {totalPages > 1 ? (
                  <div className="flex items-center gap-2">
                    <Button
                      type="button"
                      size="icon-xs"
                      variant="ghost"
                      aria-label="上一页账号"
                      disabled={disabled || page <= 1}
                      onClick={() => changePage(page - 1)}
                    >
                      <ChevronLeft aria-hidden="true" className="size-3.5" />
                    </Button>
                    <span className="tabular-nums">
                      {page} / {totalPages}
                    </span>
                    <Button
                      type="button"
                      size="icon-xs"
                      variant="ghost"
                      aria-label="下一页账号"
                      disabled={disabled || page >= totalPages}
                      onClick={() => changePage(page + 1)}
                    >
                      <ChevronRight aria-hidden="true" className="size-3.5" />
                    </Button>
                  </div>
                ) : null}
              </div>
            ) : null}
          </div>
        ) : null}
      </div>
    </div>
  )
}
