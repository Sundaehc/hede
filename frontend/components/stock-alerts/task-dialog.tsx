"use client"

import { useEffect, useState } from "react"
import { CheckCheck, ClipboardList, LoaderCircle } from "lucide-react"
import { useAuth } from "@/components/auth/auth-provider"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Select } from "@/components/ui/select"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import {
  createOverviewTask,
  createStockAlertTask,
  getStockAlertAssignees,
  getStockAlertTask,
  getStockAlertTaskEvents,
  updateStockAlertTask,
} from "@/lib/api"
import type { StockAlertItem, StockAlertKind } from "@/lib/stock-alerts"
import type { OverviewItem } from "@/lib/stock-overview"
import {
  alertKindLabels,
  beijingDate,
  taskDateTime,
  taskStatusLabels,
  type StockAlertTask,
  type StockAlertTaskSummary,
  type TaskAssignee,
  type TaskEventsResponse,
  type TaskUpdate,
} from "@/lib/stock-alert-tasks"
import { cn } from "@/lib/utils"

const textAreaClass =
  "min-h-24 w-full resize-y rounded-lg border border-input bg-background px-3 py-2 text-sm outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:opacity-70"
const errorMessage = (cause: unknown) =>
  cause instanceof Error ? cause.message : "保存失败，请重试"

function useAssignees(enabled: boolean) {
  const [state, setState] = useState<{
    items: TaskAssignee[]
    error: string | null
  } | null>(null)
  useEffect(() => {
    if (!enabled) return
    const controller = new AbortController()
    getStockAlertAssignees(controller.signal)
      .then((result) => {
        if (!controller.signal.aborted)
          setState({ items: result.items, error: null })
      })
      .catch((cause) => {
        if (!controller.signal.aborted)
          setState({ items: [], error: errorMessage(cause) })
      })
    return () => controller.abort()
  }, [enabled])
  return state
}

export function TaskStatusBadge({ task }: { task: StockAlertTaskSummary }) {
  return (
    <span
      className={cn(
        "inline-flex rounded-full border px-2 py-0.5 text-xs font-medium",
        task.overdue
          ? "border-destructive/25 bg-destructive/5 text-destructive"
          : task.status === "completed"
            ? "border-emerald-600/20 bg-emerald-600/5 text-emerald-700 dark:text-emerald-400"
            : "border-border bg-muted/50 text-foreground"
      )}
    >
      {task.overdue ? "已超期 · " : ""}
      {taskStatusLabels[task.status]}
    </span>
  )
}

export function CreateStockAlertTaskDialog({
  item,
  kind,
  brandLabel,
  onClose,
  onCreated,
  recommendation,
}: {
  item: Pick<
    StockAlertItem,
    "id" | "brand" | "sku" | "product_name" | "color" | "available_quantity"
  > &
    Partial<Pick<StockAlertItem, "listed_days" | "sell_through_rate">>
  kind: StockAlertKind | "replenish" | "clearance"
  recommendation?: OverviewItem
  brandLabel: string
  onClose: () => void
  onCreated: (task: StockAlertTask) => void
}) {
  const { user } = useAuth()
  const assignees = useAssignees(true)
  const [assigneeId, setAssigneeId] = useState(String(user?.id ?? ""))
  const [dueDate, setDueDate] = useState(
    recommendation?.due_date ?? beijingDate(3)
  )
  const [measures, setMeasures] = useState(recommendation?.reason ?? "")
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const validAssignee = assignees?.items.some(
    (person) => String(person.id) === assigneeId
  )
  return (
    <Dialog
      open
      onOpenChange={(open) => {
        if (!open && !saving) onClose()
      }}
    >
      <DialogContent className="max-h-[90svh] overflow-y-auto sm:max-w-xl">
        <DialogHeader>
          <DialogTitle>分配预警待办</DialogTitle>
          <DialogDescription>
            指定负责人和期限，后续在“存 / 预警待办”记录措施与处理结果。
          </DialogDescription>
        </DialogHeader>
        <form
          className="space-y-5"
          onSubmit={async (event) => {
            event.preventDefault()
            if (saving || !validAssignee) return
            setSaving(true)
            setError(null)
            try {
              const details = {
                brand: item.brand,
                product_id: item.id,
                assignee_id: Number(assigneeId),
                due_date: dueDate,
                measures,
              }
              const response = recommendation?.signature
                ? await createOverviewTask({
                    ...details,
                    kind,
                    signature: recommendation.signature,
                  })
                : kind === "zero" || kind === "slow"
                  ? await createStockAlertTask({ ...details, kind })
                  : (() => {
                      throw new Error("建议已变化，请刷新后重试")
                    })()
              onCreated(response.item)
            } catch (cause) {
              setError(errorMessage(cause))
            } finally {
              setSaving(false)
            }
          }}
        >
          <div className="rounded-xl border bg-muted/30 p-4 text-sm">
            <p className="text-xs text-muted-foreground">
              {brandLabel} · {alertKindLabels[kind]}
            </p>
            <p className="mt-2 font-mono font-semibold break-all">{item.sku}</p>
            <p className="mt-1 text-muted-foreground">
              {[item.product_name, item.color].filter(Boolean).join(" · ")}
            </p>
            <p className="mt-3 text-xs leading-5 text-muted-foreground">
              可售库存 {item.available_quantity} 双 ·{" "}
              {recommendation
                ? `${recommendation.reason}${recommendation.quantity !== null ? ` · 建议 ${recommendation.quantity} 双` : ""}`
                : `上市 ${item.listed_days ?? "—"} 天${kind === "slow" ? ` · 参考售罄率 ${item.sell_through_rate ?? "—"}%` : " · 上市后无销售"}`}
            </p>
          </div>
          <div className="grid gap-4 sm:grid-cols-2">
            <label className="space-y-2 text-sm">
              <span>负责人</span>
              <Select
                aria-label="负责人"
                required
                disabled={saving || !assignees}
                value={validAssignee ? assigneeId : ""}
                onChange={(event) => setAssigneeId(event.target.value)}
              >
                <option value="">
                  {assignees ? "请选择负责人" : "加载负责人…"}
                </option>
                {assignees?.items.map((person) => (
                  <option key={person.id} value={person.id}>
                    {person.name} · {person.department}
                  </option>
                ))}
              </Select>
            </label>
            <label className="space-y-2 text-sm">
              <span>处理期限（北京时间）</span>
              <Input
                aria-label="处理期限"
                type="date"
                min={beijingDate()}
                max={
                  kind === "clearance"
                    ? (recommendation?.due_date ?? undefined)
                    : undefined
                }
                required
                value={dueDate}
                disabled={saving}
                onChange={(event) => setDueDate(event.target.value)}
              />
            </label>
          </div>
          <label className="block space-y-2 text-sm">
            <span>处理措施（可稍后填写）</span>
            <textarea
              aria-label="处理措施"
              className={textAreaClass}
              maxLength={2000}
              value={measures}
              disabled={saving}
              placeholder="例如：核查上架情况、协调调拨或安排促销"
              onChange={(event) => setMeasures(event.target.value)}
            />
          </label>
          <p className="text-xs leading-5 text-muted-foreground">
            同一商品的同类预警只能有一条未完成待办。超过期限后持续站内提醒，完成后停止提醒。
          </p>
          {(error || assignees?.error) && (
            <p role="alert" className="text-sm text-destructive">
              {error || assignees?.error}
            </p>
          )}
          <DialogFooter>
            <Button
              type="button"
              variant="outline"
              disabled={saving}
              onClick={onClose}
            >
              取消
            </Button>
            <Button type="submit" disabled={saving || !validAssignee}>
              {saving ? "分配中…" : "确认分配"}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}

export function StockAlertTaskDialog({
  id,
  onClose,
}: {
  id: number
  onClose: () => void
}) {
  const [result, setResult] = useState<{
    item: StockAlertTask | null
    error: string | null
  } | null>(null)
  const [revision, setRevision] = useState(0)
  const [savedVersion, setSavedVersion] = useState<number | null>(null)
  useEffect(() => {
    const controller = new AbortController()
    getStockAlertTask(id, controller.signal)
      .then((response) => {
        if (!controller.signal.aborted)
          setResult({ item: response.item, error: null })
      })
      .catch((cause) => {
        if (!controller.signal.aborted)
          setResult({ item: null, error: errorMessage(cause) })
      })
    return () => controller.abort()
  }, [id, revision])
  if (!result?.item)
    return (
      <Dialog
        open
        onOpenChange={(open) => {
          if (!open) onClose()
        }}
      >
        <DialogContent>
          <DialogHeader>
            <DialogTitle>预警待办 #{id}</DialogTitle>
            <DialogDescription>加载处理内容与分配信息。</DialogDescription>
          </DialogHeader>
          {result?.error ? (
            <div className="space-y-3">
              <p role="alert" className="text-sm text-destructive">
                {result.error}
              </p>
              <Button
                variant="outline"
                onClick={() => setRevision((value) => value + 1)}
              >
                重试
              </Button>
            </div>
          ) : (
            <p
              role="status"
              className="flex items-center gap-2 py-8 text-sm text-muted-foreground"
            >
              <LoaderCircle className="size-4 animate-spin" />
              正在加载待办…
            </p>
          )}
        </DialogContent>
      </Dialog>
    )
  return (
    <TaskEditor
      key={`${id}:${result.item.version}`}
      item={result.item}
      saved={savedVersion === result.item.version}
      onClose={onClose}
      onSaved={(item) => {
        setResult({ item, error: null })
        setSavedVersion(item.version)
      }}
    />
  )
}

function TaskEditor({
  item,
  saved,
  onClose,
  onSaved,
}: {
  item: StockAlertTask
  saved: boolean
  onClose: () => void
  onSaved: (task: StockAlertTask) => void
}) {
  const { user, hasPermission } = useAuth()
  const manager = hasPermission("product.manage")
  const editable =
    item.status !== "completed" && (manager || user?.id === item.assignee_id)
  const assignees = useAssignees(manager && editable)
  const [assigneeId, setAssigneeId] = useState(String(item.assignee_id))
  const [dueDate, setDueDate] = useState(item.due_date)
  const [status, setStatus] = useState(item.status)
  const [measures, setMeasures] = useState(item.measures)
  const [result, setResult] = useState(item.result)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)
  return (
    <Dialog
      open
      onOpenChange={(open) => {
        if (!open && !saving) onClose()
      }}
    >
      <DialogContent className="max-h-[90svh] overflow-y-auto sm:max-w-2xl">
        <DialogHeader>
          <DialogTitle className="flex flex-wrap items-center gap-3">
            预警待办 #{item.id}
            <TaskStatusBadge task={item} />
          </DialogTitle>
          <DialogDescription>
            {alertKindLabels[item.kind]} · 创建于{" "}
            {taskDateTime(item.created_at)} · 完成后保留全部处理记录
          </DialogDescription>
        </DialogHeader>
        <form
          className="space-y-5"
          onSubmit={async (event) => {
            event.preventDefault()
            if (saving || !editable) return
            const completed =
              (
                (event.nativeEvent as SubmitEvent)
                  .submitter as HTMLButtonElement | null
              )?.value === "completed"
            if (completed && (!measures.trim() || !result.trim())) {
              setError("完成前请填写处理措施和处理结果")
              return
            }
            const payload: TaskUpdate = {
              version: item.version,
              status: completed ? "completed" : status,
              measures,
              result,
            }
            if (manager && Number(assigneeId) !== item.assignee_id)
              payload.assignee_id = Number(assigneeId)
            if (manager && dueDate !== item.due_date) payload.due_date = dueDate
            setSaving(true)
            setError(null)
            try {
              const response = await updateStockAlertTask(item.id, payload)
              onSaved(response.item)
            } catch (cause) {
              setError(errorMessage(cause))
            } finally {
              setSaving(false)
            }
          }}
        >
          <div className="rounded-xl border bg-muted/25 p-4">
            <p className="font-mono text-sm font-semibold break-all">
              {item.sku}
            </p>
            <p className="mt-1 text-sm text-muted-foreground">
              {[item.product_name, item.color].filter(Boolean).join(" · ") ||
                "—"}
            </p>
            <details className="mt-3 text-xs leading-6 text-muted-foreground">
              <summary className="cursor-pointer">查看创建时的预警依据</summary>
              <p>
                库存快照 {item.snapshot.stock_date ?? "—"} · 日销截止{" "}
                {item.snapshot.sales_end ?? "—"}
              </p>
              {item.snapshot.reason ? (
                <>
                  <p>{item.snapshot.reason}</p>
                  <p>
                    可售库存 {item.snapshot.available_quantity} 双 · 建议处理{" "}
                    {item.snapshot.quantity ?? "—"} 双
                    {item.snapshot.channel ? ` · ${item.snapshot.channel}` : ""}
                  </p>
                  {item.snapshot.sizes?.length ? (
                    <p>
                      建议尺码：
                      {item.snapshot.sizes
                        .map((size) => `${size.name}码 ${size.quantity}双`)
                        .join("、")}
                    </p>
                  ) : null}
                </>
              ) : (
                <>
                  <p>
                    可售库存 {item.snapshot.available_quantity} 双 · 上市{" "}
                    {item.snapshot.listed_days ?? "—"} 天
                  </p>
                  <p>
                    上市满 {item.snapshot.rule_age_days} 天
                    {item.kind === "slow"
                      ? ` · 参考售罄率 ${item.snapshot.sell_through_rate ?? "—"}%，低于 ${item.snapshot.rule_rate}%`
                      : " · 上市后无销售"}
                  </p>
                </>
              )}
              <p>
                此处保留创建时的数据，当前情况请回库存经营总览或预警清单核对。
              </p>
            </details>
          </div>
          {item.overdue && (
            <p className="rounded-lg border border-destructive/20 bg-destructive/5 px-3 py-2 text-sm text-destructive">
              已超过处理期限 {item.due_date}，完成前将持续提醒负责人。
            </p>
          )}
          <div className="grid gap-4 sm:grid-cols-3">
            <label className="space-y-2 text-sm">
              <span>负责人</span>
              {manager && editable ? (
                <Select
                  aria-label="负责人"
                  value={assigneeId}
                  disabled={saving || !assignees || !!assignees.error}
                  onChange={(event) => setAssigneeId(event.target.value)}
                >
                  {!assignees?.items.some(
                    (person) => person.id === item.assignee_id
                  ) && (
                    <option value={item.assignee_id}>
                      {item.assignee_name}（原负责人）
                    </option>
                  )}
                  {assignees?.items.map((person) => (
                    <option key={person.id} value={person.id}>
                      {person.name} · {person.department}
                    </option>
                  ))}
                </Select>
              ) : (
                <p className="py-1.5 font-medium">{item.assignee_name}</p>
              )}
            </label>
            <label className="space-y-2 text-sm">
              <span>处理期限</span>
              {manager && editable ? (
                <Input
                  aria-label="处理期限"
                  type="date"
                  required
                  min={
                    item.due_date < beijingDate()
                      ? item.due_date
                      : beijingDate()
                  }
                  value={dueDate}
                  disabled={saving}
                  onChange={(event) => setDueDate(event.target.value)}
                />
              ) : (
                <p className="py-1.5 font-medium tabular-nums">
                  {item.due_date}
                </p>
              )}
            </label>
            <label className="space-y-2 text-sm">
              <span>处理状态</span>
              {editable ? (
                <Select
                  aria-label="处理状态"
                  value={status}
                  disabled={saving}
                  onChange={(event) =>
                    setStatus(event.target.value as StockAlertTask["status"])
                  }
                >
                  <option value="pending">待处理</option>
                  <option value="processing">处理中</option>
                </Select>
              ) : (
                <p className="py-1.5 font-medium">
                  {taskStatusLabels[item.status]}
                </p>
              )}
            </label>
          </div>
          <label className="block space-y-2 text-sm">
            <span>处理措施</span>
            <textarea
              aria-label="处理措施"
              className={textAreaClass}
              maxLength={2000}
              value={measures}
              disabled={saving || !editable}
              placeholder="记录核查、调拨、促销等实际措施"
              onChange={(event) => setMeasures(event.target.value)}
            />
          </label>
          <label className="block space-y-2 text-sm">
            <span>处理结果</span>
            <textarea
              aria-label="处理结果"
              className={textAreaClass}
              maxLength={2000}
              value={result}
              disabled={saving || !editable}
              placeholder="记录处理结果，完成待办前必填"
              onChange={(event) => setResult(event.target.value)}
            />
          </label>
          {!editable && item.status !== "completed" && (
            <p className="text-xs text-muted-foreground">
              此待办由负责人或有商品管理权限的账户处理。
            </p>
          )}
          {item.completed_at && (
            <p className="flex items-center gap-2 text-sm text-emerald-700 dark:text-emerald-400">
              <CheckCheck className="size-4" />
              已于 {taskDateTime(item.completed_at)} 完成，已停止提醒。
            </p>
          )}
          {(error || assignees?.error) && (
            <p role="alert" className="text-sm text-destructive">
              {error || assignees?.error}
            </p>
          )}
          {saved && (
            <p role="status" className="text-sm text-muted-foreground">
              处理记录已保存
            </p>
          )}
          <DialogFooter>
            <Button
              type="button"
              variant="outline"
              disabled={saving}
              onClick={onClose}
            >
              关闭
            </Button>
            {editable && (
              <>
                <Button type="submit" variant="outline" disabled={saving}>
                  {saving ? "保存中…" : "保存进度"}
                </Button>
                <Button type="submit" value="completed" disabled={saving}>
                  <CheckCheck className="size-4" />
                  完成待办
                </Button>
              </>
            )}
          </DialogFooter>
        </form>
        <TaskHistory key={item.version} taskId={item.id} />
      </DialogContent>
    </Dialog>
  )
}

function TaskHistory({ taskId }: { taskId: number }) {
  const [page, setPage] = useState(1)
  const [revision, setRevision] = useState(0)
  const [result, setResult] = useState<{
    key: string
    data: TaskEventsResponse | null
    error: string | null
  } | null>(null)
  const key = `${page}:${revision}`
  const data = result?.key === key ? result.data : null
  useEffect(() => {
    const controller = new AbortController()
    getStockAlertTaskEvents(taskId, page, controller.signal)
      .then((data) => {
        if (!controller.signal.aborted) setResult({ key, data, error: null })
      })
      .catch((cause) => {
        if (!controller.signal.aborted)
          setResult({ key, data: null, error: errorMessage(cause) })
      })
    return () => controller.abort()
  }, [taskId, page, key])
  return (
    <section className="space-y-3 border-t pt-4" aria-label="处理历史">
      <h3 className="flex items-center gap-2 text-sm font-semibold">
        <ClipboardList className="size-4 text-muted-foreground" />
        处理历史
      </h3>
      {result?.key === key && result.error ? (
        <div className="flex items-center justify-between text-sm">
          <p role="alert" className="text-destructive">
            处理历史加载失败
          </p>
          <Button
            size="sm"
            variant="outline"
            onClick={() => setRevision((value) => value + 1)}
          >
            重试
          </Button>
        </div>
      ) : !data ? (
        <p role="status" className="text-xs text-muted-foreground">
          加载历史…
        </p>
      ) : (
        <>
          <ol className="space-y-3">
            {data.items.map((event) => (
              <li
                key={event.id}
                className="rounded-lg border bg-muted/20 p-3 text-xs leading-6"
              >
                <p className="flex flex-wrap items-center justify-between gap-2">
                  <span className="font-medium">
                    {event.actor_name} ·{" "}
                    {event.action === "created"
                      ? "创建并分配"
                      : event.action === "completed"
                        ? "完成待办"
                        : "更新处理"}
                  </span>
                  <time className="text-muted-foreground">
                    {taskDateTime(event.created_at)}
                  </time>
                </p>
                <div className="mt-1 break-words whitespace-pre-wrap text-muted-foreground">
                  {event.changes.assignee_name !== undefined && (
                    <p>负责人：{event.changes.assignee_name}</p>
                  )}
                  {event.changes.due_date !== undefined && (
                    <p>处理期限：{event.changes.due_date}</p>
                  )}
                  {event.changes.status && (
                    <p>状态：{taskStatusLabels[event.changes.status]}</p>
                  )}
                  {event.changes.measures !== undefined && (
                    <p>措施：{event.changes.measures || "未填写"}</p>
                  )}
                  {event.changes.result !== undefined && (
                    <p>结果：{event.changes.result || "未填写"}</p>
                  )}
                </div>
              </li>
            ))}
          </ol>
          {data.total > data.page_size && (
            <div className="flex justify-end gap-3">
              <Button
                size="sm"
                variant="outline"
                disabled={page <= 1}
                onClick={() => setPage((value) => value - 1)}
              >
                较新记录
              </Button>
              <span className="py-1 text-xs text-muted-foreground">
                {page} / {Math.ceil(data.total / data.page_size)}
              </span>
              <Button
                size="sm"
                variant="outline"
                disabled={page * data.page_size >= data.total}
                onClick={() => setPage((value) => value + 1)}
              >
                更早记录
              </Button>
            </div>
          )}
        </>
      )}
    </section>
  )
}
