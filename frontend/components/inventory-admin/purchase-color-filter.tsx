"use client"

import { useState } from "react"
import { Filter, Search } from "lucide-react"
import { Popover } from "radix-ui"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import type { PurchaseColorOption } from "@/lib/api"
import { cn } from "@/lib/utils"

export function PurchaseColorFilter({ options, values, disabled, onApply }: {
  options: PurchaseColorOption[]
  values: string[]
  disabled: boolean
  onApply: (values: string[]) => void
}) {
  const [open, setOpen] = useState(false)
  const [query, setQuery] = useState("")
  const [selected, setSelected] = useState<Set<string>>(new Set())
  const search = query.trim().toLowerCase()
  const matching = options.filter(({ value }) => value.toLowerCase().includes(search))
  const allMatchingSelected = matching.length > 0 && matching.every(({ value }) => selected.has(value))
  const active = values.length > 0

  function toggle(values: string[], checked: boolean) {
    setSelected((current) => {
      const next = new Set(current)
      for (const value of values) {
        if (checked) next.add(value)
        else next.delete(value)
      }
      return next
    })
  }

  function apply() {
    if (!selected.size) return
    onApply(options.every(({ value }) => selected.has(value)) ? [] : [...selected])
    setOpen(false)
  }

  return (
    <Popover.Root open={open} onOpenChange={(next) => {
      if (next) {
        setQuery("")
        setSelected(new Set(active ? values : options.map(({ value }) => value)))
      }
      setOpen(next)
    }}>
      <Popover.Trigger asChild>
        <button type="button" disabled={disabled} aria-label={active ? "颜色已筛选" : "筛选颜色"}
          aria-pressed={active} title="筛选颜色"
          className={cn("inline-flex size-5 shrink-0 cursor-pointer items-center justify-center rounded-[5px] border disabled:cursor-default disabled:opacity-50",
            active ? "border-primary bg-primary text-primary-foreground" : "border-transparent text-muted-foreground/70 hover:border-border hover:bg-muted hover:text-foreground")}>
          <Filter className={cn("size-3", active && "fill-current")} aria-hidden="true" />
        </button>
      </Popover.Trigger>
      <Popover.Portal>
        <Popover.Content aria-label="颜色筛选" align="start" sideOffset={6} collisionPadding={8}
          className="z-[90] w-64 max-w-[calc(100vw-1rem)] rounded-lg border border-border bg-popover p-2.5 text-sm text-popover-foreground shadow-lg">
          <div className="mb-2 flex items-center justify-between px-0.5">
            <span className="font-medium">筛选颜色</span>
            <span className="text-xs text-muted-foreground">{options.length} 个筛选项</span>
          </div>
          <div className="relative">
            <Search className="pointer-events-none absolute left-2.5 top-2.5 size-3 text-muted-foreground" aria-hidden="true" />
            <Input aria-label="搜索颜色筛选项" placeholder="搜索筛选项" className="h-8 pl-7 text-xs"
              value={query} onChange={(event) => setQuery(event.target.value)}
              onKeyDown={(event) => {
                if (event.key === "Enter" && !event.nativeEvent.isComposing) {
                  event.preventDefault()
                  apply()
                }
              }} />
          </div>
          <label className="mt-2 flex cursor-pointer items-center gap-2 border-b px-1.5 py-2 text-xs">
            <input type="checkbox" checked={allMatchingSelected} disabled={!matching.length}
              onChange={(event) => toggle(matching.map(({ value }) => value), event.target.checked)} />
            {search ? "全选匹配项" : "全选"}
          </label>
          <div className="max-h-56 overflow-y-auto py-1">
            {matching.map(({ value, count }) => (
              <label key={value} className="flex cursor-pointer items-center gap-2 rounded px-1.5 py-1.5 text-xs hover:bg-muted">
                <input type="checkbox" checked={selected.has(value)} onChange={(event) => toggle([value], event.target.checked)} />
                <span className="min-w-0 flex-1 break-words">{value === "-" ? "（空白）" : value}</span>
                <span className="text-muted-foreground">{count.toLocaleString("zh-CN")}</span>
              </label>
            ))}
            {!matching.length && <p className="px-1 py-4 text-center text-xs text-muted-foreground">没有匹配的筛选项</p>}
          </div>
          <div className="flex items-center justify-between gap-2 border-t pt-2">
            <Button variant="ghost" size="sm" disabled={!active} onClick={() => { onApply([]); setOpen(false) }}>清除筛选</Button>
            <div className="flex gap-1.5">
              <Popover.Close asChild><Button variant="outline" size="sm">取消</Button></Popover.Close>
              <Button size="sm" disabled={!selected.size} onClick={apply}>确定</Button>
            </div>
          </div>
        </Popover.Content>
      </Popover.Portal>
    </Popover.Root>
  )
}
