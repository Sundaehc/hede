"use client"

import { useEffect, useRef, useState } from "react"
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
  createOverviewTasks,
  createStockAlertTasks,
  getStockAlertAssignees,
  updateStockAlertTasks,
} from "@/lib/api"
import {
  alertKindLabels,
  beijingDate,
  type StockAlertTask,
  type TaskAssignee,
  type TaskBatchResult,
  type TaskBatchUpdate,
} from "@/lib/stock-alert-tasks"
import type { OverviewItem } from "@/lib/stock-overview"
import type { StockAlertItem, StockAlertKind } from "@/lib/stock-alerts"
import { StockProductPhoto } from "./stock-product-photo"

export type OverviewBatchItem = Omit<
  OverviewItem,
  "id" | "kind" | "signature"
> & {
  id: string
  productId: number
  kind: keyof typeof alertKindLabels
  signature: string
}

type Props = { onClose: () => void } & (
  | {
      mode: "overview"
      items: OverviewBatchItem[]
      brand: string
      onApplied: (result: TaskBatchResult<string>) => void
    }
  | ({ onApplied: (result: TaskBatchResult) => void } & (
      | {
          mode: "create"
          items: StockAlertItem[]
          brand: string
          kind: StockAlertKind
        }
      | { mode: "assign" | "process"; items: StockAlertTask[] }
    ))
)
const textAreaClass =
  "min-h-24 w-full resize-y rounded-lg border border-input bg-background px-3 py-2 text-sm outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:opacity-60"

export function BatchTaskDialog(props: Props) {
  const assigning = props.mode !== "process"
  const creating = props.mode === "create" || props.mode === "overview"
  const latestDue =
    props.mode === "overview"
      ? props.items.reduce<string | undefined>((limit, item) => {
          if (item.kind !== "clearance" || !item.due_date) return limit
          return !limit || item.due_date < limit ? item.due_date : limit
        }, undefined)
      : undefined
  const title = creating
    ? "批量分配待办"
    : assigning
      ? "批量调整分配"
      : "批量处理待办"
  const [assignees, setAssignees] = useState<TaskAssignee[]>([])
  const [assigneeError, setAssigneeError] = useState<string | null>(null)
  const [assigneeId, setAssigneeId] = useState("")
  const [dueDate, setDueDate] = useState(() => {
    if (!creating) return ""
    const suggested = beijingDate(3)
    return latestDue && latestDue < suggested ? latestDue : suggested
  })
  const [status, setStatus] = useState<"processing" | "completed">("processing")
  const [measures, setMeasures] = useState("")
  const [result, setResult] = useState("")
  const [writeMeasures, setWriteMeasures] = useState(creating)
  const [writeResult, setWriteResult] = useState(false)
  const [saving, setSaving] = useState(false)
  const savingRef = useRef(false)
  const [error, setError] = useState<string | null>(null)
  const [report, setReport] = useState<TaskBatchResult<string | number> | null>(
    null
  )
  useEffect(() => {
    if (!assigning) return
    const controller = new AbortController()
    getStockAlertAssignees(controller.signal)
      .then((response) => {
        if (!controller.signal.aborted) setAssignees(response.items)
      })
      .catch((cause: unknown) => {
        if (!controller.signal.aborted)
          setAssigneeError(
            cause instanceof Error
              ? cause.message
              : "负责人加载失败，请关闭后重试"
          )
      })
    return () => controller.abort()
  }, [assigning])
  return (
    <Dialog
      open
      onOpenChange={(open) => {
        if (!open && !savingRef.current) props.onClose()
      }}
    >
      <DialogContent className="max-h-[90svh] overflow-y-auto sm:max-w-2xl">
        <DialogHeader>
          <DialogTitle>{title}</DialogTitle>
          <DialogDescription>
            本次共 {props.items.length} 项，包含跨页选择。
            {assigning
              ? "为所选商品统一指定负责人和期限。"
              : "统一更新所选待办；未勾选的内容保留原值。"}
          </DialogDescription>
        </DialogHeader>
        <form
          className="space-y-5"
          onSubmit={async (event) => {
            event.preventDefault()
            if (savingRef.current || report) return
            setError(null)
            if (props.mode === "assign" && !assigneeId && !dueDate) {
              setError("请选择负责人或填写新的处理期限")
              return
            }
            if (
              props.mode === "process" &&
              status === "completed" &&
              ((writeMeasures && !measures.trim()) ||
                (writeResult && !result.trim()))
            ) {
              setError("完成时统一填写的处理措施和处理结果不能为空")
              return
            }
            savingRef.current = true
            setSaving(true)
            try {
              if (props.mode === "overview") {
                const response = await createOverviewTasks({
                  brand: props.brand,
                  items: props.items.map(({ productId, kind, signature }) => ({
                    product_id: productId,
                    kind,
                    signature,
                  })),
                  assignee_id: Number(assigneeId),
                  due_date: dueDate,
                  measures,
                })
                setReport(response)
                props.onApplied(response)
                return
              }
              let response: TaskBatchResult
              if (props.mode === "create") {
                response = await createStockAlertTasks({
                  brand: props.brand,
                  kind: props.kind,
                  product_ids: props.items.map((item) => item.id),
                  assignee_id: Number(assigneeId),
                  due_date: dueDate,
                  measures,
                })
              } else {
                const changes: TaskBatchUpdate["changes"] = {}
                if (props.mode === "assign") {
                  if (assigneeId) changes.assignee_id = Number(assigneeId)
                  if (dueDate) changes.due_date = dueDate
                } else {
                  changes.status = status
                  if (writeMeasures) changes.measures = measures
                  if (writeResult) changes.result = result
                }
                response = await updateStockAlertTasks({
                  items: props.items.map(({ id, version }) => ({
                    id,
                    version,
                  })),
                  changes,
                })
              }
              setReport(response)
              props.onApplied(response)
            } catch (cause) {
              setError(
                cause instanceof Error ? cause.message : "批量操作失败，请重试"
              )
            } finally {
              savingRef.current = false
              setSaving(false)
            }
          }}
        >
          <details className="rounded-xl border bg-muted/20 px-4 py-3 text-sm">
            <summary className="cursor-pointer font-medium">
              查看所选 {props.items.length} 项
            </summary>
            <ul className="mt-2 max-h-36 space-y-1 overflow-y-auto text-xs text-muted-foreground">
              {props.items.map((item) => (
                <li
                  key={item.id}
                  className="flex items-center gap-2 break-words"
                >
                  <StockProductPhoto item={item} />
                  <span className="min-w-0">
                    #{"productId" in item ? item.productId : item.id} ·{" "}
                    {item.sku}
                    {"productId" in item && ` · ${alertKindLabels[item.kind]}`}
                    {"assignee_name" in item && ` · ${item.assignee_name}`}
                  </span>
                </li>
              ))}
            </ul>
          </details>
          {!report && (
            <>
              {assigning ? (
                <div className="grid gap-4 sm:grid-cols-2">
                  <label className="space-y-2 text-sm">
                    <span>
                      统一负责人
                      {props.mode === "assign" ? "（留空保留原值）" : ""}
                    </span>
                    <Select
                      aria-label="统一负责人"
                      required={creating}
                      value={assigneeId}
                      disabled={saving || !assignees.length}
                      onChange={(event) => setAssigneeId(event.target.value)}
                    >
                      <option value="">
                        {props.mode === "assign"
                          ? "保留原负责人"
                          : "请选择负责人"}
                      </option>
                      {assignees.map((person) => (
                        <option key={person.id} value={person.id}>
                          {person.name} · {person.department}
                        </option>
                      ))}
                    </Select>
                  </label>
                  <label className="space-y-2 text-sm">
                    <span>
                      统一处理期限
                      {props.mode === "assign" ? "（留空保留原值）" : ""}
                    </span>
                    <Input
                      aria-label="统一处理期限"
                      type="date"
                      min={beijingDate()}
                      max={latestDue}
                      required={creating}
                      value={dueDate}
                      disabled={saving}
                      onChange={(event) => setDueDate(event.target.value)}
                    />
                    {latestDue && (
                      <span className="block text-xs text-muted-foreground">
                        清货项最晚 {latestDue} 处理
                      </span>
                    )}
                  </label>
                </div>
              ) : (
                <label className="block space-y-2 text-sm">
                  <span>统一处理状态</span>
                  <Select
                    aria-label="统一处理状态"
                    disabled={saving}
                    value={status}
                    onChange={(event) =>
                      setStatus(event.target.value as typeof status)
                    }
                  >
                    <option value="processing">标记为处理中</option>
                    <option value="completed">完成待办并停止提醒</option>
                  </Select>
                </label>
              )}
              {props.mode !== "assign" && (
                <div className="block space-y-2 text-sm">
                  <span className="flex items-center gap-2">
                    统一处理措施
                    {props.mode === "process" && (
                      <label className="ml-auto flex items-center gap-2 text-xs text-muted-foreground">
                        <input
                          type="checkbox"
                          aria-label="填写统一处理措施"
                          checked={writeMeasures}
                          disabled={saving}
                          onChange={(event) =>
                            setWriteMeasures(event.target.checked)
                          }
                          className="size-4 accent-primary"
                        />
                        统一填写
                      </label>
                    )}
                  </span>
                  <textarea
                    aria-label="统一处理措施"
                    className={textAreaClass}
                    maxLength={2000}
                    disabled={saving || !writeMeasures}
                    value={measures}
                    onChange={(event) => {
                      setMeasures(event.target.value)
                      setError(null)
                    }}
                    placeholder={
                      props.mode === "process"
                        ? "勾选后覆盖所选待办的措施；未勾选保留原值"
                        : "可稍后由负责人填写"
                    }
                  />
                </div>
              )}
              {props.mode === "process" && (
                <div className="block space-y-2 text-sm">
                  <span className="flex items-center gap-2">
                    统一处理结果
                    <label className="ml-auto flex items-center gap-2 text-xs text-muted-foreground">
                      <input
                        type="checkbox"
                        aria-label="填写统一处理结果"
                        checked={writeResult}
                        disabled={saving}
                        onChange={(event) =>
                          setWriteResult(event.target.checked)
                        }
                        className="size-4 accent-primary"
                      />
                      统一填写
                    </label>
                  </span>
                  <textarea
                    aria-label="统一处理结果"
                    className={textAreaClass}
                    maxLength={2000}
                    disabled={saving || !writeResult}
                    value={result}
                    onChange={(event) => {
                      setResult(event.target.value)
                      setError(null)
                    }}
                    placeholder="勾选后覆盖所选待办的结果；完成时每项均须有措施和结果"
                  />
                </div>
              )}
              <p className="text-xs leading-5 text-muted-foreground">
                每项独立检查权限、版本和当前状态；成功项保存，失败项列出原因并保留选择。每项均保留处理历史。
              </p>
            </>
          )}
          {(error || assigneeError) && (
            <p role="alert" className="text-sm text-destructive">
              {error || assigneeError}
            </p>
          )}
          {report && (
            <div className="space-y-3 rounded-xl border p-4">
              <p role="status" className="text-sm font-medium">
                操作完成：成功 {report.succeeded.length} 项，失败{" "}
                {report.failed.length} 项
              </p>
              {report.failed.length > 0 && (
                <div className="max-h-60 overflow-auto">
                  <ul className="space-y-2 text-xs text-destructive">
                    {report.failed.map((item) => (
                      <li key={item.id} className="break-words">
                        {item.label}
                        {typeof item.id === "number"
                          ? `（#${item.id}）`
                          : ` · ${alertKindLabels[item.id.split("/")[1] as keyof typeof alertKindLabels]}`}
                        ：{item.reason}
                      </li>
                    ))}
                  </ul>
                </div>
              )}
            </div>
          )}
          <DialogFooter>
            <Button
              type="button"
              variant="outline"
              disabled={saving}
              onClick={props.onClose}
            >
              {report ? "关闭" : "取消"}
            </Button>
            {!report && (
              <Button
                type="submit"
                disabled={
                  saving || (creating && (!assigneeId || !assignees.length))
                }
              >
                {saving
                  ? "正在处理…"
                  : props.mode === "process" && status === "completed"
                    ? `确认完成 ${props.items.length} 项`
                    : `确认操作 ${props.items.length} 项`}
              </Button>
            )}
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}
