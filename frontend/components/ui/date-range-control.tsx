"use client"

import { useState } from "react"
import { CalendarDays, ChevronDown, ChevronLeft, ChevronRight } from "lucide-react"

import { cn } from "@/lib/utils"

type Period = "day" | "week" | "month" | "custom"

type DateRangeControlProps = {
  start: string
  end: string
  onStartChange: (value: string) => void
  onEndChange: (value: string) => void
  label?: string
  hideLabel?: boolean
  className?: string
  disabled?: boolean
  maxDate?: string
}

function parseDate(value: string): Date | null {
  if (!/^\d{4}-\d{2}-\d{2}$/.test(value)) return null
  const [year, month, day] = value.split("-").map(Number)
  const date = new Date(year, month - 1, day)
  return date.getFullYear() === year && date.getMonth() === month - 1 && date.getDate() === day ? date : null
}

function formatDate(date: Date) {
  return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, "0")}-${String(date.getDate()).padStart(2, "0")}`
}

function addDays(date: Date, count: number) {
  const result = new Date(date)
  result.setDate(result.getDate() + count)
  return result
}

function periodFor(start: string, end: string, maxDate?: string): Period {
  const first = parseDate(start)
  const last = parseDate(end)
  if (!first || !last || first > last) return "custom"
  if (start === end) return "day"
  const limit = parseDate(maxDate || "")
  if (first.getDay() === 1 && formatDate(limit && addDays(first, 6) > limit ? limit : addDays(first, 6)) === end) return "week"
  if (first.getDate() === 1 && formatDate(limit && new Date(first.getFullYear(), first.getMonth() + 1, 0) > limit
    ? limit : new Date(first.getFullYear(), first.getMonth() + 1, 0)) === end) return "month"
  return "custom"
}

export function DateRangeControl({ start, end, onStartChange, onEndChange, label = "日期范围", hideLabel = false, className, disabled, maxDate }: DateRangeControlProps) {
  const [customOpen, setCustomOpen] = useState(false)
  const today = new Date()
  today.setHours(0, 0, 0, 0)
  const configuredMax = parseDate(maxDate || "")
  const max = configuredMax && configuredMax < today ? configuredMax : today
  const maxValue = formatDate(max)
  const period = periodFor(start, end, maxValue)

  const setRange = (first: Date, last: Date) => {
    if (first > max) return
    onStartChange(formatDate(first))
    onEndChange(formatDate(last > max ? max : last))
  }

  const changeStart = (value: string) => {
    if (value && (!parseDate(value) || value > maxValue || (end && value > end))) return
    onStartChange(value)
  }

  const changeEnd = (value: string) => {
    if (value && (!parseDate(value) || value > maxValue || (start && value < start))) return
    onEndChange(value)
  }

  const choosePeriod = (next: Period) => {
    if (next === "custom") {
      setCustomOpen((open) => !open)
      return
    }
    setCustomOpen(false)
    const selectedEnd = parseDate(end)
    const anchor = selectedEnd && selectedEnd < max ? selectedEnd : max
    if (next === "day") setRange(anchor, anchor)
    if (next === "week") {
      const monday = addDays(anchor, -((anchor.getDay() + 6) % 7))
      setRange(monday, addDays(monday, 6))
    }
    if (next === "month") setRange(new Date(anchor.getFullYear(), anchor.getMonth(), 1), new Date(anchor.getFullYear(), anchor.getMonth() + 1, 0))
  }

  const shift = (direction: number) => {
    const first = parseDate(start)
    const last = parseDate(end)
    if (!first || !last || first > last) return
    let nextStart: Date
    let nextEnd: Date
    if (period === "month") {
      nextStart = new Date(first.getFullYear(), first.getMonth() + direction, 1)
      nextEnd = new Date(nextStart.getFullYear(), nextStart.getMonth() + 1, 0)
    } else if (period === "week") {
      nextStart = addDays(first, direction * 7)
      nextEnd = addDays(nextStart, 6)
    } else {
      const days = period === "day" ? 1 : Math.round((last.getTime() - first.getTime()) / 86400000) + 1
      nextStart = addDays(first, days * direction)
      nextEnd = addDays(last, days * direction)
    }
    setRange(nextStart, nextEnd)
  }

  const canNext = (() => {
    const last = parseDate(end)
    if (!last || last > max) return false
    const first = parseDate(start)
    if (period === "month" && first) return new Date(first.getFullYear(), first.getMonth() + 1, 1) <= max
    if (period === "week" && first) return addDays(first, 7) <= max
    const days = period === "day" ? 1 : period === "week" ? 7 : first ? Math.round((last.getTime() - first.getTime()) / 86400000) + 1 : 0
    return addDays(last, days) <= max
  })()

  return (
    <div className={cn("min-w-0 space-y-1.5", className)}>
      {!hideLabel ? <span className="block text-xs font-medium text-muted-foreground">{label}</span> : null}
      <div className="flex flex-wrap items-center gap-1.5">
        <div className="inline-flex h-9 shrink-0 items-center rounded-lg border border-input bg-card p-0.5 shadow-xs" role="group" aria-label="日期周期">
          {([ ["day", "日"], ["week", "周"], ["month", "月"], ["custom", "自定义"] ] as const).map(([value, text]) => (
            <button
              key={value}
              type="button"
              disabled={disabled}
              aria-pressed={customOpen ? value === "custom" : Boolean(start && end) && period === value}
              onClick={() => choosePeriod(value)}
              className={cn(
                "h-full cursor-pointer rounded-md px-2.5 text-xs text-muted-foreground transition-colors hover:bg-muted hover:text-foreground focus-visible:outline-2 focus-visible:outline-ring disabled:cursor-not-allowed disabled:opacity-50",
                (customOpen ? value === "custom" : Boolean(start && end) && period === value) && "bg-primary text-primary-foreground shadow-xs hover:bg-primary/90 hover:text-primary-foreground"
              )}
            >
              {text}
            </button>
          ))}
        </div>
        <button
          type="button"
          disabled={disabled}
          aria-label={`${label}：${start || "未选择"}至${end || "未选择"}，点击选择日期`}
          aria-expanded={customOpen}
          onClick={() => setCustomOpen((open) => !open)}
          className={cn(
            "inline-flex h-9 max-w-full min-w-0 cursor-pointer items-center gap-2 rounded-lg border border-input bg-card px-3 text-xs text-foreground shadow-xs transition-colors hover:border-ring/60 hover:bg-muted/40 focus-visible:outline-2 focus-visible:outline-ring disabled:cursor-not-allowed disabled:opacity-50",
            customOpen && "border-ring/60 bg-muted/40"
          )}
        >
          <CalendarDays className="size-4 shrink-0 text-muted-foreground" aria-hidden="true" />
          <span className="truncate whitespace-nowrap tabular-nums">{start || "未选择"} <span className="px-0.5 text-muted-foreground">—</span> {end || "未选择"}</span>
          <ChevronDown className={cn("size-3.5 shrink-0 text-muted-foreground transition-transform", customOpen && "rotate-180")} aria-hidden="true" />
        </button>
        <div className="inline-flex h-9 shrink-0 items-center rounded-lg border border-input bg-card p-0.5 shadow-xs" role="group" aria-label="切换日期周期">
          <button type="button" aria-label="上一周期" title="上一周期" disabled={disabled || !start || !end || start > end} onClick={() => shift(-1)} className="flex h-7 w-7 cursor-pointer items-center justify-center rounded-md text-muted-foreground transition-colors hover:bg-muted hover:text-foreground focus-visible:outline-2 focus-visible:outline-ring disabled:cursor-not-allowed disabled:opacity-40"><ChevronLeft className="size-4" /></button>
          <button type="button" aria-label="下一周期" title="下一周期" disabled={disabled || !start || !end || start > end || !canNext} onClick={() => shift(1)} className="flex h-7 w-7 cursor-pointer items-center justify-center rounded-md text-muted-foreground transition-colors hover:bg-muted hover:text-foreground focus-visible:outline-2 focus-visible:outline-ring disabled:cursor-not-allowed disabled:opacity-40"><ChevronRight className="size-4" /></button>
        </div>
      </div>
      {customOpen && (
        <div className="flex max-w-full flex-wrap items-end gap-3 rounded-lg border border-border bg-muted/25 p-3 shadow-xs">
          <label className="grid min-w-0 gap-1.5 text-xs font-medium text-muted-foreground">开始日期
            <input aria-label={`${label}开始日期`} type="date" value={start} max={end && end < maxValue ? end : maxValue} disabled={disabled} onChange={(event) => changeStart(event.target.value)} className="h-9 min-w-0 cursor-pointer rounded-lg border border-input bg-card px-2 text-sm font-normal tabular-nums text-foreground focus-visible:outline-2 focus-visible:outline-ring disabled:cursor-not-allowed disabled:opacity-50" />
          </label>
          <label className="grid min-w-0 gap-1.5 text-xs font-medium text-muted-foreground">结束日期
            <input aria-label={`${label}结束日期`} type="date" value={end} min={start || undefined} max={maxValue} disabled={disabled} onChange={(event) => changeEnd(event.target.value)} className="h-9 min-w-0 cursor-pointer rounded-lg border border-input bg-card px-2 text-sm font-normal tabular-nums text-foreground focus-visible:outline-2 focus-visible:outline-ring disabled:cursor-not-allowed disabled:opacity-50" />
          </label>
          <button type="button" onClick={() => setCustomOpen(false)} className="h-9 cursor-pointer rounded-lg bg-primary px-4 text-xs font-medium text-primary-foreground transition-colors hover:bg-primary/90 focus-visible:outline-2 focus-visible:outline-ring">完成</button>
        </div>
      )}
    </div>
  )
}
