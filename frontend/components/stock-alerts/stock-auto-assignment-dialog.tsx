"use client"

import { useEffect, useState } from "react"
import { Button } from "@/components/ui/button"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogTitle,
} from "@/components/ui/dialog"
import { Input } from "@/components/ui/input"
import { Select } from "@/components/ui/select"
import {
  getStockAutoAssignment,
  getStockAlertAssignees,
  saveStockAutoAssignment,
} from "@/lib/api"
import {
  alertKindLabels,
  type StockTaskKind,
  type TaskAssignee,
} from "@/lib/stock-alert-tasks"
import type { AutoAssignmentRule } from "@/lib/stock-portfolio"

const kinds = ["zero", "slow", "replenish", "clearance"] as const
const defaults = { zero: 2, slow: 5, replenish: 0, clearance: 1 }
const emptyRule = (kind: StockTaskKind): AutoAssignmentRule => ({
  kind,
  assignee_id: 0,
  enabled: false,
  due_days: defaults[kind],
  version: 0,
})

export function StockAutoAssignmentDialog({
  brand,
  onClose,
}: {
  brand: string
  onClose: () => void
}) {
  const [rules, setRules] = useState<AutoAssignmentRule[] | null>(null)
  const [people, setPeople] = useState<TaskAssignee[]>([])
  const [kind, setKind] = useState<StockTaskKind>("zero")
  const [drafts, setDrafts] = useState<
    Partial<Record<StockTaskKind, AutoAssignmentRule>>
  >({})
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState("")
  const [notice, setNotice] = useState("")
  useEffect(() => {
    const controller = new AbortController()
    Promise.all([
      getStockAutoAssignment(brand, controller.signal),
      getStockAlertAssignees(controller.signal),
    ])
      .then(([result, owners]) => {
        if (!controller.signal.aborted) {
          setRules(result.items)
          setPeople(owners.items)
        }
      })
      .catch((error: unknown) => {
        if (!controller.signal.aborted)
          setError(error instanceof Error ? error.message : "无法加载规则")
      })
    return () => controller.abort()
  }, [brand])
  const current = rules?.find((entry) => entry.kind === kind) ?? emptyRule(kind)
  const draft = drafts[kind] ?? current
  const patch = (values: Partial<AutoAssignmentRule>) =>
    setDrafts((previous) => ({ ...previous, [kind]: { ...draft, ...values } }))
  return (
    <Dialog
      open
      onOpenChange={(open) => {
        if (!open && !busy) onClose()
      }}
    >
      <DialogContent>
        <DialogTitle>自动派办</DialogTitle>
        <DialogDescription>
          按当前品牌和预警类型设置。库存和日销就绪后，派给已配置的负责人。相同问题仍在时，沿用已有记录；提醒合并在「我的待办」。
        </DialogDescription>
        {error && (
          <p role="alert" className="text-sm text-destructive">
            {error}
          </p>
        )}
        {notice && (
          <p role="status" className="text-sm text-muted-foreground">
            {notice}
          </p>
        )}
        {!rules && !error && (
          <p role="status" className="text-sm text-muted-foreground">
            正在读取自动派办规则…
          </p>
        )}
        {rules && (
          <form
            className="grid gap-3"
            onSubmit={async (event) => {
              event.preventDefault()
              if (busy || !draft.assignee_id) return
              setBusy(true)
              setError("")
              setNotice("")
              try {
                const response = await saveStockAutoAssignment(brand, draft)
                setRules((previous) => [
                  ...(previous ?? []).filter((entry) => entry.kind !== kind),
                  response.item,
                ])
                setDrafts((previous) => ({
                  ...previous,
                  [kind]: response.item,
                }))
                setNotice(response.message)
              } catch (error) {
                setError(error instanceof Error ? error.message : "保存失败")
              } finally {
                setBusy(false)
              }
            }}
          >
            <label className="grid gap-1 text-sm">
              预警类型
              <Select
                value={kind}
                disabled={busy}
                onChange={(event) => {
                  setKind(event.target.value as StockTaskKind)
                  setNotice("")
                  setError("")
                }}
              >
                {kinds.map((item) => (
                  <option key={item} value={item}>
                    {alertKindLabels[item]}
                  </option>
                ))}
              </Select>
            </label>
            <label className="grid gap-1 text-sm">
              负责人
              <Select
                value={draft.assignee_id}
                disabled={busy}
                onChange={(event) =>
                  patch({ assignee_id: Number(event.target.value) })
                }
              >
                <option value={0}>请选择</option>
                {draft.assignee_id > 0 &&
                  !people.some((person) => person.id === draft.assignee_id) && (
                    <option value={draft.assignee_id}>原负责人不可用</option>
                  )}
                {people.map((person) => (
                  <option key={person.id} value={person.id}>
                    {person.name}
                  </option>
                ))}
              </Select>
            </label>
            <label className="grid gap-1 text-sm">
              默认处理期限（天）
              <Input
                type="number"
                min={0}
                max={90}
                required
                value={draft.due_days}
                disabled={busy}
                onChange={(event) =>
                  patch({ due_days: Number(event.target.value) })
                }
              />
            </label>
            <label className="flex items-center gap-2 text-sm">
              <input
                type="checkbox"
                checked={draft.enabled}
                disabled={busy}
                onChange={(event) => patch({ enabled: event.target.checked })}
              />
              启用此项自动派办
            </label>
            <Button type="submit" disabled={busy || !draft.assignee_id}>
              保存规则
            </Button>
          </form>
        )}
      </DialogContent>
    </Dialog>
  )
}
