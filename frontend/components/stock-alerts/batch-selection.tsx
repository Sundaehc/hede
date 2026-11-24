"use client"

import { useState, type ReactNode } from "react"
import { Button } from "@/components/ui/button"

export const BATCH_LIMIT = 500

export function useBatchSelection<T extends { id: string | number }>() {
  const [selected, setSelected] = useState<Map<T["id"], T>>(() => new Map())
  const [error, setError] = useState<string | null>(null)
  const clear = () => {
    setSelected(new Map())
    setError(null)
  }
  const select = (items: T[], checked: boolean) => {
    const additions = items.filter((item) => !selected.has(item.id)).length
    if (checked && selected.size + additions > BATCH_LIMIT) {
      setError(`每批最多选择 ${BATCH_LIMIT} 项，请分批操作`)
      return
    }
    setError(null)
    setSelected((current) => {
      const next = new Map(current)
      items.forEach((item) => {
        if (checked) next.set(item.id, item)
        else next.delete(item.id)
      })
      return next
    })
  }
  const remove = (ids: T["id"][]) =>
    setSelected((current) => {
      const next = new Map(current)
      ids.forEach((id) => next.delete(id))
      return next
    })
  return { selected, error, select, clear, remove }
}

export function SelectionCheckbox({
  label,
  checked,
  mixed = false,
  disabled = false,
  onChange,
}: {
  label: string
  checked: boolean
  mixed?: boolean
  disabled?: boolean
  onChange: (checked: boolean) => void
}) {
  return (
    <input
      type="checkbox"
      aria-label={label}
      aria-checked={mixed ? "mixed" : checked}
      checked={checked}
      ref={(node) => {
        if (node) node.indeterminate = mixed
      }}
      disabled={disabled}
      className="size-4 cursor-pointer rounded border-input accent-primary disabled:cursor-not-allowed disabled:opacity-40"
      onChange={(event) => onChange(event.target.checked)}
    />
  )
}

export function BatchSelectionBar({
  count,
  error,
  onClear,
  children,
}: {
  count: number
  error: string | null
  onClear: () => void
  children: ReactNode
}) {
  return (
    <div className="flex flex-wrap items-center gap-3 border-b bg-muted/20 px-4 py-3">
      <span className="text-sm font-medium" role="status">
        已选 {count} 项
      </span>
      <span className="text-xs text-muted-foreground">
        支持跨页选择 · 每批最多 {BATCH_LIMIT} 项
      </span>
      <div className="flex flex-wrap items-center gap-2 sm:ml-auto">
        {children}
        <Button size="sm" variant="ghost" disabled={!count} onClick={onClear}>
          清空选择
        </Button>
      </div>
      {error && (
        <p role="alert" className="w-full text-xs text-destructive">
          {error}
        </p>
      )}
    </div>
  )
}
