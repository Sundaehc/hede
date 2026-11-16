"use client"

import { useCallback, useState } from "react"
import { useSearchParams } from "next/navigation"
import {
  Archive,
  ChevronLeft,
  ChevronRight,
  ClipboardCheck,
  RefreshCw,
  Search,
} from "lucide-react"
import { useAuth } from "@/components/auth/auth-provider"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Select } from "@/components/ui/select"
import { getStockAlertOptions, getStockAlertTasks } from "@/lib/api"
import {
  alertKindLabels,
  type TaskFilters,
} from "@/lib/stock-alert-tasks"
import { useSessionQueryState } from "@/lib/session-query-state"
import { STOCK_TASK_RESOURCES, useStockModuleOptions, useStockModuleQuery } from "@/lib/stock-module-query"
import { cn } from "@/lib/utils"
import { StockAlertTaskDialog, TaskStatusBadge } from "./task-dialog"
import { useTaskRefresh } from "./use-task-refresh"
import {
  BatchSelectionBar,
  SelectionCheckbox,
  useBatchSelection,
} from "./batch-selection"
import { BatchTaskDialog } from "./batch-task-dialog"
import type { StockAlertTask } from "@/lib/stock-alert-tasks"

const defaults: TaskFilters = {
  scope: "mine",
  status: "open",
  brand: "",
  kind: "",
  query: "",
  page: 1,
}
const tabs = [
  { value: "open", label: "未完成" },
  { value: "overdue", label: "已超期" },
  { value: "completed", label: "已完成" },
  { value: "all", label: "全部状态" },
] as const

export function StockAlertTasksPage() {
  const { hasPermission } = useAuth()
  const searchParams = useSearchParams()
  const reminderEntry = searchParams.get("view") === "mine-open"
  if (!hasPermission("product.view"))
    return (
      <p className="p-6 text-sm text-muted-foreground">
        你没有查看预警待办的权限。
      </p>
    )
  return (
    <StockAlertTasksContent
      key={reminderEntry ? "reminders" : "saved"}
      reminderEntry={reminderEntry}
    />
  )
}

function StockAlertTasksContent({ reminderEntry }: { reminderEntry: boolean }) {
  const { user, hasPermission } = useAuth()
  const manager = hasPermission("product.manage")
  const selection = useBatchSelection<StockAlertTask>()
  const [batch, setBatch] = useState<{
    mode: "assign" | "process"
    items: StockAlertTask[]
  } | null>(null)
  const [storedFilters, setStoredFilters] = useSessionQueryState<TaskFilters>(
    "stock-alert-tasks:filters",
    defaults
  )
  // A reminder link always lands on unfinished work, even if the saved view was completed.
  const [leftReminderView, setLeftReminderView] = useState(false)
  const filters = reminderEntry && !leftReminderView ? defaults : storedFilters
  const setFilters = (next: TaskFilters) => {
    if (
      JSON.stringify({ ...filters, page: 1 }) !==
      JSON.stringify({ ...next, page: 1 })
    )
      selection.clear()
    setLeftReminderView(true)
    setStoredFilters(next)
  }
  const [draft, setDraft] = useState({
    brand: filters.brand,
    kind: filters.kind,
    query: filters.query,
  })
  const options = useStockModuleOptions(getStockAlertOptions)
  const brands = options.data?.brands ?? []
  const optionsError = Boolean(options.error)
  const [revision, setRevision] = useState(0)
  const [taskId, setTaskId] = useState<number | null>(null)
  const key = JSON.stringify(filters)
  const { data, error, loading, refreshing } = useStockModuleQuery({
    group: "stock-tasks", queryKey: key, revision, resources: STOCK_TASK_RESOURCES,
    ttl: 15_000, retention: 60_000,
    load: (signal) => getStockAlertTasks(JSON.parse(key) as TaskFilters, signal),
  })
  const selectable =
    data?.items.filter(
      (item) =>
        item.status !== "completed" &&
        (manager || user?.id === item.assignee_id)
    ) ?? []
  const selectedOnPage = selectable.filter((item) =>
    selection.selected.has(item.id)
  ).length
  const refresh = useCallback(() => setRevision((value) => value + 1), [setRevision])
  useTaskRefresh(refresh)
  const page = data?.page ?? filters.page
  const pages = Math.max(
    1,
    Math.ceil((data?.total ?? 0) / (data?.page_size ?? 25))
  )
  const brandName = (brand: string) =>
    brands.find((item) => item.value === brand)?.label ?? brand
  return (
    <div className="space-y-5 p-4 sm:p-6">
      <header className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <p className="mb-2 flex items-center gap-1.5 text-xs text-muted-foreground">
            <Archive className="size-3.5" aria-hidden="true" />存 / 预警处理
          </p>
          <h1 className="text-xl font-semibold tracking-tight">预警待办</h1>
          <p className="mt-2 text-sm text-muted-foreground">
            分配、跟进、记录结果。超期持续提醒，处理完成后归档。
          </p>
        </div>
        <Button variant="outline" disabled={refreshing} onClick={refresh}>
          <RefreshCw
            className={cn("size-4", refreshing && "animate-spin")}
            aria-hidden="true"
          />
          刷新
        </Button>
      </header>
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div
          className="flex rounded-xl border bg-card p-1"
          aria-label="待办范围"
        >
          {(
            [
              { value: "mine", label: "我的待办" },
              { value: "all", label: "全部待办" },
            ] as const
          ).map((scope) => (
            <Button
              key={scope.value}
              size="sm"
              variant={filters.scope === scope.value ? "secondary" : "ghost"}
              aria-pressed={filters.scope === scope.value}
              onClick={() =>
                setFilters({ ...filters, scope: scope.value, page: 1 })
              }
            >
              {scope.label}
            </Button>
          ))}
        </div>
      </div>
      <form
        className="flex flex-wrap items-end gap-3 rounded-xl border bg-card p-4"
        onSubmit={(event) => {
          event.preventDefault()
          setFilters({
            ...filters,
            ...draft,
            query: draft.query.trim(),
            page: 1,
          })
        }}
      >
        <label className="w-40 space-y-1.5 text-xs text-muted-foreground">
          <span>品牌</span>
          <Select
            aria-label="品牌"
            value={draft.brand}
            onChange={(event) =>
              setDraft((current) => ({ ...current, brand: event.target.value }))
            }
          >
            <option value="">全部品牌</option>
            {brands.map((brand) => (
              <option key={brand.value} value={brand.value}>
                {brand.label}
              </option>
            ))}
          </Select>
        </label>
        <label className="w-44 space-y-1.5 text-xs text-muted-foreground">
          <span>预警类型</span>
          <Select
            aria-label="预警类型"
            value={draft.kind}
            onChange={(event) =>
              setDraft((current) => ({
                ...current,
                kind: event.target.value as TaskFilters["kind"],
              }))
            }
          >
            <option value="">全部类型</option>
            <option value="zero">新品零动销</option>
            <option value="slow">低售罄、滞销</option>
          </Select>
        </label>
        <label className="min-w-44 flex-1 space-y-1.5 text-xs text-muted-foreground">
          <span>搜索待办</span>
          <Input
            aria-label="搜索待办"
            maxLength={200}
            placeholder="货号、原始货号、品名、颜色或负责人"
            value={draft.query}
            onChange={(event) =>
              setDraft((current) => ({ ...current, query: event.target.value }))
            }
          />
        </label>
        <Button type="submit">
          <Search className="size-4" aria-hidden="true" />
          查询
        </Button>
        <Button
          type="button"
          variant="ghost"
          onClick={() => {
            setDraft({ brand: "", kind: "", query: "" })
            setFilters(defaults)
          }}
        >
          重置
        </Button>
      </form>
      {optionsError && (
        <p role="alert" className="text-sm text-destructive">
          品牌选项加载失败，重新进入页面可重试。
        </p>
      )}
      {error && (
        <div
          role="alert"
          className="flex flex-wrap items-center justify-between gap-3 rounded-lg border border-destructive/25 p-3 text-sm text-destructive"
        >
          <span>
            {error}
            {data ? "；当前仍显示上次加载的记录。" : ""}
          </span>
          <Button variant="outline" size="sm" onClick={refresh}>
            重试
          </Button>
        </div>
      )}
      <section
        className="overflow-hidden rounded-xl border bg-card"
        aria-label="预警待办列表"
        aria-busy={refreshing}
      >
        <div className="flex flex-wrap items-center justify-between gap-3 border-b px-4 py-3">
          <div className="flex flex-wrap gap-1" aria-label="处理状态筛选">
            {tabs.map((tab) => (
              <Button
                key={tab.value}
                variant={filters.status === tab.value ? "secondary" : "ghost"}
                size="sm"
                aria-pressed={filters.status === tab.value}
                onClick={() =>
                  setFilters({ ...filters, status: tab.value, page: 1 })
                }
                className={
                  tab.value === "overdue" && (data?.counts.overdue ?? 0) > 0
                    ? "text-destructive"
                    : undefined
                }
              >
                {tab.label}
                <span className="ml-1 text-muted-foreground tabular-nums">
                  {data
                    ? tab.value === "all"
                      ? data.counts.open + data.counts.completed
                      : data.counts[tab.value]
                    : "—"}
                </span>
              </Button>
            ))}
          </div>
          <span role="status" className="text-xs text-muted-foreground">
            {refreshing ? "正在更新…" : `共 ${data?.total ?? 0} 项 · 期限优先`}
          </span>
        </div>
        <BatchSelectionBar
          count={selection.selected.size}
          error={selection.error}
          onClear={selection.clear}
        >
          {manager && (
            <Button
              size="sm"
              variant="outline"
              disabled={!selection.selected.size}
              onClick={() =>
                setBatch({
                  mode: "assign",
                  items: Array.from(selection.selected.values()),
                })
              }
            >
              批量调整分配
            </Button>
          )}
          <Button
            size="sm"
            disabled={!selection.selected.size}
            onClick={() =>
              setBatch({
                mode: "process",
                items: Array.from(selection.selected.values()),
              })
            }
          >
            批量处理
          </Button>
        </BatchSelectionBar>
        <div className="h-[min(65vh,620px)] min-h-80 overflow-auto [scrollbar-gutter:stable]">
          <table className="w-full min-w-[960px] table-fixed text-left text-xs">
            <thead className="sticky top-0 z-10 bg-muted text-muted-foreground">
              <tr>
                <th className="w-12 px-4 py-3">
                  <SelectionCheckbox
                    label="选择本页可处理待办"
                    checked={
                      selectable.length > 0 &&
                      selectedOnPage === selectable.length
                    }
                    mixed={
                      selectedOnPage > 0 && selectedOnPage < selectable.length
                    }
                    disabled={loading || !selectable.length}
                    onChange={(checked) =>
                      selection.select(selectable, checked)
                    }
                  />
                </th>
                {[
                  "商品 / 品牌",
                  "预警类型",
                  "负责人",
                  "处理期限",
                  "状态",
                  "措施 / 结果",
                  "操作",
                ].map((label, index) => (
                  <th
                    key={label}
                    className={cn(
                      "px-4 py-3 font-medium",
                      index === 0 || index === 5 ? "w-56" : "w-32"
                    )}
                  >
                    {label}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody className="divide-y">
              {data?.items.map((item) => (
                <tr key={item.id} className="align-top hover:bg-muted/30">
                  <td className="px-4 py-4">
                    <SelectionCheckbox
                      label={`选择 ${item.sku}（#${item.id}）`}
                      checked={selection.selected.has(item.id)}
                      disabled={
                        (item.status === "completed" ||
                          (!manager && user?.id !== item.assignee_id)) &&
                        !selection.selected.has(item.id)
                      }
                      onChange={(checked) => selection.select([item], checked)}
                    />
                  </td>
                  <td className="px-4 py-4">
                    <p className="font-mono font-semibold break-all">
                      {item.sku}
                    </p>
                    <p className="mt-1 text-muted-foreground">
                      {[item.product_name, item.color]
                        .filter(Boolean)
                        .join(" · ")}
                    </p>
                    <p className="mt-1 text-muted-foreground">
                      {brandName(item.brand)} · #{item.id}
                    </p>
                  </td>
                  <td className="px-4 py-4">{alertKindLabels[item.kind]}</td>
                  <td className="px-4 py-4 font-medium">
                    {item.assignee_name}
                  </td>
                  <td
                    className={cn(
                      "px-4 py-4 tabular-nums",
                      item.overdue && "font-medium text-destructive"
                    )}
                  >
                    {item.due_date}
                    <p className="mt-1 text-muted-foreground">北京时间</p>
                  </td>
                  <td className="px-4 py-4">
                    <TaskStatusBadge task={item} />
                  </td>
                  <td className="px-4 py-4 leading-5">
                    <p className="line-clamp-2 break-words">
                      {item.measures || "尚未填写措施"}
                    </p>
                    <p className="mt-1 line-clamp-2 break-words text-muted-foreground">
                      {item.result || "尚未填写结果"}
                    </p>
                  </td>
                  <td className="px-4 py-4">
                    <Button
                      size="sm"
                      variant="outline"
                      onClick={() => setTaskId(item.id)}
                    >
                      查看 / 处理
                    </Button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          {(!data || !data.items.length) && (
            <div className="flex h-56 flex-col items-center justify-center gap-3 px-6 text-center text-sm text-muted-foreground">
              <ClipboardCheck
                className="size-8 opacity-50"
                aria-hidden="true"
              />
              <p>
                {loading
                  ? "正在加载预警待办…"
                  : error
                    ? "暂时无法读取待办，请重试"
                    : "当前筛选下没有待办"}
              </p>
              {!loading && !error && (
                <p className="text-xs">
                  在新品零动销或低售罄预警清单中点击“分配待办”创建。
                </p>
              )}
            </div>
          )}
        </div>
        <footer className="flex flex-wrap items-center justify-between gap-3 border-t px-4 py-3 text-xs text-muted-foreground">
          <span>商品退出预警后，处理记录仍会保留。</span>
          <div className="flex items-center gap-3">
            <Button
              size="icon-sm"
              variant="outline"
              aria-label="上一页"
              disabled={refreshing || page <= 1}
              onClick={() => setFilters({ ...filters, page: page - 1 })}
            >
              <ChevronLeft className="size-4" />
            </Button>
            <span className="tabular-nums">
              {page} / {pages}
            </span>
            <Button
              size="icon-sm"
              variant="outline"
              aria-label="下一页"
              disabled={refreshing || page >= pages}
              onClick={() => setFilters({ ...filters, page: page + 1 })}
            >
              <ChevronRight className="size-4" />
            </Button>
          </div>
        </footer>
      </section>
      {taskId !== null && (
        <StockAlertTaskDialog
          key={taskId}
          id={taskId}
          onClose={() => setTaskId(null)}
        />
      )}
      {batch && (
        <BatchTaskDialog
          mode={batch.mode}
          items={batch.items}
          onClose={() => setBatch(null)}
          onApplied={(report) => {
            selection.remove(report.succeeded)
            refresh()
          }}
        />
      )}
    </div>
  )
}
