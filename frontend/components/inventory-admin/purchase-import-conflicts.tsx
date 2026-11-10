"use client"

import { useId, useState, type Dispatch, type SetStateAction } from "react"

import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Select } from "@/components/ui/select"
import type {
  InventoryTemplateConflict,
  PurchaseImportPayload,
} from "@/lib/api"

type Decisions = NonNullable<PurchaseImportPayload["decisions"]>
type Action = Decisions[string]["action"]
type BulkAction = Action | "clear"

const ACTION_LABELS: Record<BulkAction, string> = {
  overwrite: "覆盖已有单据",
  new: "另增单据",
  skip: "取消导入",
  clear: "清空处理方式",
}

export function PurchaseImportConflicts({
  conflicts,
  decisions,
  onDecisionsChange,
  disabled = false,
}: {
  conflicts: InventoryTemplateConflict[]
  decisions: Decisions
  onDecisionsChange: Dispatch<SetStateAction<Decisions>>
  disabled?: boolean
}) {
  const id = useId()
  const [selectedKeys, setSelectedKeys] = useState<Set<string>>(() => new Set())
  const [bulkAction, setBulkAction] = useState<BulkAction | "">("")
  const [feedback, setFeedback] = useState("")
  let selectedCount = 0
  let pendingCount = 0
  let summaryCount = 0
  for (const conflict of conflicts) {
    if (selectedKeys.has(conflict.key)) selectedCount++
    const decision = decisions[conflict.key]
    if (!decision?.action) pendingCount++
    if (
      decision?.action === "new" &&
      (!decision.new_summary?.trim() ||
        decision.new_summary.trim() === conflict.summary)
    )
      summaryCount++
  }
  const allSelected = selectedCount === conflicts.length

  function applyBulkAction() {
    if (disabled || !bulkAction || selectedCount === 0) return
    const targets = conflicts.filter(
      (conflict) =>
        selectedKeys.has(conflict.key) &&
        (bulkAction !== "overwrite" || conflict.can_merge)
    )
    onDecisionsChange((previous) => {
      const next = { ...previous }
      for (const conflict of targets) {
        if (bulkAction === "clear") delete next[conflict.key]
        else
          next[conflict.key] = {
            action: bulkAction,
            new_summary: previous[conflict.key]?.new_summary ?? "",
          }
      }
      return next
    })
    const excluded = selectedCount - targets.length
    setFeedback(
      `已为 ${targets.length} 张单据${bulkAction === "clear" ? "清空处理方式" : `设置“${ACTION_LABELS[bulkAction]}”`}。${excluded > 0 ? `${excluded} 张不支持覆盖，已保留原处理方式。` : ""}`
    )
  }

  return (
    <section aria-label="采购单重复处理" className="space-y-3">
      <div className="sticky top-0 z-10 space-y-3 rounded-lg border border-border bg-card p-3 shadow-xs">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <h3 className="text-sm font-semibold">重复单据处理</h3>
          <p className="text-xs text-muted-foreground">
            待选择 {pendingCount} 张
            {summaryCount > 0 ? ` · 待补摘要 ${summaryCount} 张` : ""}
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-x-3 gap-y-2 text-xs">
          <label className="inline-flex cursor-pointer items-center gap-2">
            <input
              type="checkbox"
              aria-label="全选重复单据"
              checked={allSelected}
              ref={(element) => {
                if (element)
                  element.indeterminate = selectedCount > 0 && !allSelected
              }}
              disabled={disabled}
              onChange={(event) => {
                setSelectedKeys(
                  event.target.checked
                    ? new Set(conflicts.map((conflict) => conflict.key))
                    : new Set()
                )
                setFeedback("")
              }}
              className="size-4 cursor-pointer rounded border border-input accent-primary focus-visible:outline-2 focus-visible:outline-ring disabled:cursor-not-allowed"
            />
            全选
          </label>
          <Button
            type="button"
            variant="ghost"
            size="xs"
            disabled={disabled || pendingCount === 0}
            onClick={() => {
              setSelectedKeys(
                new Set(
                  conflicts
                    .filter((conflict) => !decisions[conflict.key]?.action)
                    .map((conflict) => conflict.key)
                )
              )
              setFeedback("")
            }}
          >
            仅选未处理
          </Button>
          <span className="text-muted-foreground">
            已选{" "}
            <span className="font-medium text-foreground tabular-nums">
              {selectedCount}
            </span>{" "}
            / {conflicts.length} 张
          </span>
        </div>
        <div className="flex flex-wrap items-end gap-2">
          <div className="min-w-0 grow basis-48 space-y-1.5">
            <Label
              htmlFor={`${id}-bulk-action`}
              className="text-xs text-muted-foreground"
            >
              批量处理方式
            </Label>
            <Select
              id={`${id}-bulk-action`}
              value={bulkAction}
              disabled={disabled}
              onChange={(event) => {
                setBulkAction(event.target.value as BulkAction | "")
                setFeedback("")
              }}
            >
              <option value="">请选择批量处理方式</option>
              <option value="overwrite">覆盖已有单据（仅可覆盖项）</option>
              <option value="new">另增单据（逐单填写新摘要）</option>
              <option value="skip">取消导入</option>
              <option value="clear">清空处理方式</option>
            </Select>
          </div>
          <Button
            type="button"
            className="h-9"
            disabled={disabled || !bulkAction || selectedCount === 0}
            onClick={applyBulkAction}
          >
            应用到已选
          </Button>
        </div>
        <p className="text-xs leading-5 text-muted-foreground">
          仅设置已选重复单据，确认导入后生效。覆盖会替换原明细并保留编号；另增需逐单填写不同的新摘要。
        </p>
        {feedback && (
          <p aria-live="polite" className="text-xs leading-5">
            {feedback}
          </p>
        )}
      </div>
      <ul aria-label="重复采购单" className="divide-y divide-border">
        {conflicts.map((conflict, index) => {
          const decision = decisions[conflict.key]
          const rowId = `${id}-${index}`
          return (
            <li key={conflict.key} className="space-y-2 py-3 first:pt-0">
              <label className="flex cursor-pointer items-start gap-2.5 text-sm font-medium">
                <input
                  type="checkbox"
                  aria-label={`选择第 ${index + 1} 张重复单据`}
                  checked={selectedKeys.has(conflict.key)}
                  disabled={disabled}
                  onChange={(event) => {
                    const checked = event.target.checked
                    setSelectedKeys((previous) => {
                      const next = new Set(previous)
                      if (checked) next.add(conflict.key)
                      else next.delete(conflict.key)
                      return next
                    })
                    setFeedback("")
                  }}
                  className="mt-0.5 size-4 shrink-0 cursor-pointer rounded border border-input accent-primary focus-visible:outline-2 focus-visible:outline-ring disabled:cursor-not-allowed"
                />
                <span>
                  {conflict.date} · {conflict.document_type}
                </span>
              </label>
              <p className="text-xs leading-5 break-words text-muted-foreground">
                摘要：{conflict.summary}；
                {conflict.existing_number
                  ? `已有单据：${conflict.existing_number}`
                  : "与本次导入的其他单据匹配字段相同"}
              </p>
              <Label htmlFor={`${rowId}-action`} className="sr-only">
                第 {index + 1} 张单据的处理方式
              </Label>
              <Select
                id={`${rowId}-action`}
                disabled={disabled}
                value={decision?.action ?? ""}
                onChange={(event) => {
                  const action = event.target.value as Action | ""
                  onDecisionsChange((previous) => {
                    const next = { ...previous }
                    if (!action) delete next[conflict.key]
                    else
                      next[conflict.key] = {
                        action,
                        new_summary: previous[conflict.key]?.new_summary ?? "",
                      }
                    return next
                  })
                  setFeedback("")
                }}
              >
                <option value="">请选择处理方式</option>
                {conflict.can_merge && (
                  <option value="overwrite">
                    覆盖已有单据（替换原明细，保留编号）
                  </option>
                )}
                <option value="new">另增一张单据（修改摘要）</option>
                <option value="skip">取消该单据（其他单据继续导入）</option>
              </Select>
              {decision?.action === "new" && (
                <>
                  <Label htmlFor={`${rowId}-summary`} className="sr-only">
                    第 {index + 1} 张单据的新摘要
                  </Label>
                  <Input
                    id={`${rowId}-summary`}
                    disabled={disabled}
                    value={decision.new_summary ?? ""}
                    placeholder="请输入不同于原摘要的新摘要"
                    onChange={(event) => {
                      const newSummary = event.target.value
                      onDecisionsChange((previous) => ({
                        ...previous,
                        [conflict.key]: {
                          action: "new",
                          new_summary: newSummary,
                        },
                      }))
                    }}
                  />
                </>
              )}
            </li>
          )
        })}
      </ul>
    </section>
  )
}
