"use client"

import type { MouseEvent } from "react"
import { ChevronDown, ChevronUp } from "lucide-react"

import { cn } from "@/lib/utils"

type SortableColumnLabelProps = {
  label: string
  sortRule?: {
    direction: "asc" | "desc"
    index: number
    total: number
  }
  onClick: (event: MouseEvent<HTMLButtonElement>) => void
}

export function SortableColumnLabel({
  label,
  sortRule,
  onClick,
}: SortableColumnLabelProps) {
  const active = Boolean(sortRule)
  const multiple = (sortRule?.total ?? 0) > 1
  const currentState = sortRule
    ? `当前${sortRule.direction === "asc" ? "升序" : "降序"}${multiple ? `，第 ${sortRule.index} 优先级` : ""}`
    : "未排序"
  const nextAction =
    !sortRule || multiple
      ? "点击按此列降序"
      : sortRule.direction === "desc"
        ? "点击切换升序"
        : "点击取消排序"

  return (
    <button
      type="button"
      onClick={onClick}
      aria-pressed={active}
      aria-label={`${label}：${currentState}；${nextAction}`}
      title={`${label}：${currentState}；${nextAction}；按住上档键点击可追加或切换多列排序`}
      className={cn(
        "group/sort -mx-1.5 -my-1 inline-flex h-6 max-w-full min-w-0 cursor-pointer items-center gap-1 rounded-md border px-1.5 text-left transition-colors focus-visible:ring-2 focus-visible:ring-ring/50 focus-visible:outline-none",
        active
          ? "border-primary/15 bg-primary/8 font-semibold text-foreground hover:bg-primary/12"
          : "border-transparent text-muted-foreground hover:bg-muted-foreground/8 hover:text-foreground"
      )}
    >
      <span className="truncate">{label}</span>
      <span aria-hidden="true" className="relative h-4 w-3 shrink-0">
        <ChevronUp
          strokeWidth={2.5}
          className={cn(
            "absolute -top-0.5 left-0 size-3 transition-colors",
            sortRule?.direction === "asc"
              ? "text-primary"
              : active
                ? "text-muted-foreground/25"
                : "text-muted-foreground/45 group-hover/sort:text-muted-foreground/80"
          )}
        />
        <ChevronDown
          strokeWidth={2.5}
          className={cn(
            "absolute -bottom-0.5 left-0 size-3 transition-colors",
            sortRule?.direction === "desc"
              ? "text-primary"
              : active
                ? "text-muted-foreground/25"
                : "text-muted-foreground/45 group-hover/sort:text-muted-foreground/80"
          )}
        />
      </span>
      {multiple && sortRule ? (
        <span
          aria-hidden="true"
          className="flex size-3.5 shrink-0 items-center justify-center rounded-sm border border-primary/15 bg-card text-[9px] leading-none text-primary tabular-nums"
        >
          {sortRule.index}
        </span>
      ) : null}
    </button>
  )
}
