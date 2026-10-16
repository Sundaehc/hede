"use client"

import {
  useMemo,
  useRef,
  useState,
  type ComponentProps,
  type KeyboardEvent,
  type ReactElement,
} from "react"
import { CalendarDays, ChevronLeft, ChevronRight } from "lucide-react"
import { Popover } from "radix-ui"

import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { cn } from "@/lib/utils"

type DatePickerProps = Omit<
  ComponentProps<"input">,
  "type" | "value" | "defaultValue" | "onChange" | "min" | "max"
> & {
  value: string
  onValueChange: (value: string) => void
  min?: string
  max?: string
  availableDates?: string[]
  trigger?: ReactElement
  wrapperClassName?: string
}

const WEEKDAYS = ["一", "二", "三", "四", "五", "六", "日"]

function dateValue(date: Date) {
  return (
    String(date.getFullYear()).padStart(4, "0") +
    "-" +
    String(date.getMonth() + 1).padStart(2, "0") +
    "-" +
    String(date.getDate()).padStart(2, "0")
  )
}

function parseDate(value: string | undefined) {
  if (!value || !/^\d{4}-\d{2}-\d{2}$/.test(value)) return null
  const [year, month, day] = value.split("-").map(Number)
  const date = new Date(year, month - 1, day, 12)
  date.setFullYear(year)
  return dateValue(date) === value ? date : null
}

function addDays(date: Date, days: number) {
  const result = new Date(date)
  result.setDate(result.getDate() + days)
  return result
}

function shiftMonth(date: Date, months: number) {
  const first = new Date(date.getFullYear(), date.getMonth() + months, 1, 12)
  first.setDate(
    Math.min(
      date.getDate(),
      new Date(first.getFullYear(), first.getMonth() + 1, 0).getDate()
    )
  )
  return first
}

function dateLabel(date: Date) {
  return (
    date.getFullYear() +
    "年" +
    (date.getMonth() + 1) +
    "月" +
    date.getDate() +
    "日"
  )
}

export function DatePicker({
  value,
  onValueChange,
  min,
  max,
  availableDates,
  trigger,
  disabled,
  readOnly,
  className,
  wrapperClassName,
  onClick,
  onKeyDown,
  ...props
}: DatePickerProps) {
  const rootRef = useRef<HTMLDivElement>(null)
  const contentRef = useRef<HTMLDivElement>(null)
  const [open, setOpen] = useState(false)
  const [portalContainer, setPortalContainer] = useState<
    HTMLElement | undefined
  >()
  const [viewMonth, setViewMonth] = useState(
    () => parseDate(value) || new Date()
  )
  const [focusedDate, setFocusedDate] = useState(value || dateValue(new Date()))
  const today = dateValue(new Date())
  const allowedDates = useMemo(
    () =>
      availableDates
        ? [...new Set(availableDates.filter((day) => parseDate(day)))].sort()
        : undefined,
    [availableDates]
  )
  const allowedSet = useMemo(
    () => (allowedDates ? new Set(allowedDates) : undefined),
    [allowedDates]
  )
  const minimum =
    [parseDate(min) ? min : "", allowedDates?.[0] || ""].sort().at(-1) || ""
  const maximum =
    [parseDate(max) ? max : "", allowedDates?.at(-1) || ""]
      .filter(Boolean)
      .sort()[0] || ""
  const isDisabled = Boolean(disabled || readOnly)
  const label = props["aria-label"] || "选择日期"
  const isAllowed = (day: string) =>
    Boolean(
      parseDate(day) &&
      (!minimum || day >= minimum) &&
      (!maximum || day <= maximum) &&
      (!allowedSet || allowedSet.has(day))
    )

  function focusDay(day: string) {
    requestAnimationFrame(() => {
      const target = contentRef.current?.querySelector<HTMLButtonElement>(
        '[data-date="' + day + '"]:not(:disabled)'
      )
      if (target) target.focus()
      else contentRef.current?.focus()
    })
  }

  function openCalendar(nextOpen: boolean) {
    if (nextOpen && isDisabled) return
    if (nextOpen) {
      let anchor = parseDate(value) || parseDate(today)!
      if (minimum && dateValue(anchor) < minimum) anchor = parseDate(minimum)!
      if (maximum && dateValue(anchor) > maximum) anchor = parseDate(maximum)!
      const preferred = isAllowed(dateValue(anchor))
        ? dateValue(anchor)
        : allowedDates?.find((day) => isAllowed(day)) || dateValue(anchor)
      setViewMonth(parseDate(preferred)!)
      setFocusedDate(preferred)
      setPortalContainer(
        rootRef.current?.closest<HTMLElement>('[role="dialog"]') || undefined
      )
    }
    setOpen(nextOpen)
  }

  function chooseDate(day: string) {
    if (isDisabled || (day && !isAllowed(day)) || (!day && props.required))
      return
    onValueChange(day)
    setOpen(false)
  }

  function changeMonth(next: Date) {
    let nextMonth = next
    if (minimum && dateValue(next).slice(0, 7) < minimum.slice(0, 7))
      nextMonth = parseDate(minimum)!
    if (maximum && dateValue(nextMonth).slice(0, 7) > maximum.slice(0, 7))
      nextMonth = parseDate(maximum)!
    setViewMonth(nextMonth)
    const firstDay = new Date(
      nextMonth.getFullYear(),
      nextMonth.getMonth(),
      1,
      12
    )
    const preferred = Array.from({ length: 31 }, (_, index) =>
      dateValue(addDays(firstDay, index))
    ).find(
      (day) =>
        day.slice(0, 7) === dateValue(firstDay).slice(0, 7) && isAllowed(day)
    )
    setFocusedDate(preferred || dateValue(firstDay))
  }

  function handleDayKeyDown(
    event: KeyboardEvent<HTMLButtonElement>,
    date: Date
  ) {
    const weekday = (date.getDay() + 6) % 7
    const offsets: Record<string, number> = {
      ArrowLeft: -1,
      ArrowRight: 1,
      ArrowUp: -7,
      ArrowDown: 7,
      Home: -weekday,
      End: 6 - weekday,
    }
    let next: Date
    if (event.key in offsets) next = addDays(date, offsets[event.key])
    else if (event.key === "PageUp" || event.key === "PageDown")
      next = shiftMonth(
        date,
        (event.key === "PageUp" ? -1 : 1) * (event.shiftKey ? 12 : 1)
      )
    else return
    event.preventDefault()
    event.stopPropagation()
    let nextValue = dateValue(next)
    if (minimum && nextValue < minimum) nextValue = minimum
    if (maximum && nextValue > maximum) nextValue = maximum
    if (!isAllowed(nextValue) && allowedDates) {
      const direction = next >= date ? 1 : -1
      nextValue =
        direction > 0
          ? allowedDates.find((day) => day >= nextValue && isAllowed(day)) || ""
          : [...allowedDates]
              .reverse()
              .find((day) => day <= nextValue && isAllowed(day)) || ""
    }
    if (!isAllowed(nextValue)) return
    setViewMonth(parseDate(nextValue)!)
    setFocusedDate(nextValue)
    focusDay(nextValue)
  }

  const year = viewMonth.getFullYear()
  const month = viewMonth.getMonth()
  const first = new Date(year, month, 1, 12)
  const gridStart = addDays(first, -((first.getDay() + 6) % 7))
  const days = Array.from({ length: 42 }, (_, index) =>
    addDays(gridStart, index)
  )
  const tabbableDate =
    days.find(
      (day) => dateValue(day) === focusedDate && isAllowed(focusedDate)
    ) ||
    days.find((day) => day.getMonth() === month && isAllowed(dateValue(day))) ||
    days.find((day) => isAllowed(dateValue(day)))
  const firstYear = minimum ? Number(minimum.slice(0, 4)) : Math.min(1900, year)
  const lastYear = maximum
    ? Number(maximum.slice(0, 4))
    : Math.max(new Date().getFullYear() + 10, year)
  const years = Array.from(
    { length: Math.max(0, lastYear - firstYear + 1) },
    (_, index) => firstYear + index
  )
  const hasDates =
    (!minimum || !maximum || minimum <= maximum) &&
    (!allowedDates || allowedDates.some(isAllowed))
  const canPrevious =
    hasDates && (!minimum || dateValue(new Date(year, month, 0, 12)) >= minimum)
  const canNext =
    hasDates &&
    (!maximum || dateValue(new Date(year, month + 1, 1, 12)) <= maximum)

  return (
    <Popover.Root open={open} onOpenChange={openCalendar}>
      <div
        ref={rootRef}
        className={cn(
          "relative min-w-0",
          !trigger && "w-full",
          wrapperClassName
        )}
      >
        {trigger ? (
          <Popover.Trigger asChild disabled={isDisabled}>
            {trigger}
          </Popover.Trigger>
        ) : (
          <Popover.Anchor asChild>
            <div className="relative">
              <Input
                {...props}
                type="date"
                value={value}
                min={min}
                max={max}
                disabled={disabled}
                readOnly={readOnly}
                aria-haspopup="dialog"
                aria-expanded={open}
                onChange={(event) => {
                  if (!event.target.value || isAllowed(event.target.value))
                    onValueChange(event.target.value)
                }}
                onClick={(event) => {
                  onClick?.(event)
                  if (!event.defaultPrevented) {
                    event.preventDefault()
                    openCalendar(true)
                  }
                }}
                onKeyDown={(event) => {
                  onKeyDown?.(event)
                  if (
                    !event.defaultPrevented &&
                    ["Enter", " ", "ArrowDown"].includes(event.key)
                  ) {
                    event.preventDefault()
                    event.stopPropagation()
                    openCalendar(true)
                  }
                }}
                className={cn(
                  "tabular-nums [&::-webkit-calendar-picker-indicator]:hidden",
                  className,
                  "pr-10"
                )}
              />
              <Popover.Trigger asChild>
                <button
                  type="button"
                  aria-label={"打开" + label + "日历"}
                  disabled={isDisabled}
                  className="absolute inset-y-1 right-1 flex w-8 cursor-pointer items-center justify-center rounded-md text-muted-foreground transition-colors hover:bg-muted hover:text-foreground focus-visible:outline-2 focus-visible:outline-ring disabled:cursor-not-allowed disabled:opacity-40"
                >
                  <CalendarDays className="size-4" aria-hidden="true" />
                </button>
              </Popover.Trigger>
            </div>
          </Popover.Anchor>
        )}
      </div>
      <Popover.Portal container={portalContainer}>
        <Popover.Content
          ref={contentRef}
          aria-label={label + "日历"}
          align="start"
          sideOffset={8}
          collisionPadding={12}
          onKeyDown={(event) => {
            if (event.key === "Escape") {
              event.preventDefault()
              event.stopPropagation()
              setOpen(false)
            }
          }}
          onOpenAutoFocus={(event) => {
            event.preventDefault()
            focusDay(focusedDate)
          }}
          className="z-[150] w-[min(20rem,calc(100vw-1.5rem))] overflow-hidden rounded-2xl border border-border/80 bg-popover text-popover-foreground shadow-xl shadow-black/10 outline-none data-[state=open]:animate-in data-[state=open]:fade-in-0 data-[state=open]:zoom-in-95 motion-reduce:animate-none"
        >
          <div className="flex items-center justify-between gap-3 border-b border-border/60 bg-muted/30 px-4 py-3">
            <div className="flex items-center gap-1">
              <select
                aria-label="选择年份"
                value={year}
                onChange={(event) =>
                  changeMonth(
                    new Date(Number(event.target.value), month, 1, 12)
                  )
                }
                className="h-8 cursor-pointer rounded-md bg-transparent px-1 text-sm font-semibold outline-none hover:bg-muted focus-visible:ring-2 focus-visible:ring-ring"
              >
                {years.map((item) => (
                  <option key={item} value={item}>
                    {item}年
                  </option>
                ))}
              </select>
              <select
                aria-label="选择月份"
                value={month}
                onChange={(event) =>
                  changeMonth(new Date(year, Number(event.target.value), 1, 12))
                }
                className="h-8 cursor-pointer rounded-md bg-transparent px-1 text-sm font-semibold outline-none hover:bg-muted focus-visible:ring-2 focus-visible:ring-ring"
              >
                {Array.from({ length: 12 }, (_, index) => (
                  <option
                    key={index}
                    value={index}
                    disabled={Boolean(
                      (minimum &&
                        year === Number(minimum.slice(0, 4)) &&
                        index < Number(minimum.slice(5, 7)) - 1) ||
                      (maximum &&
                        year === Number(maximum.slice(0, 4)) &&
                        index > Number(maximum.slice(5, 7)) - 1)
                    )}
                  >
                    {index + 1}月
                  </option>
                ))}
              </select>
            </div>
            <div className="flex items-center gap-1">
              <Button
                type="button"
                variant="ghost"
                size="icon-sm"
                aria-label="上个月"
                disabled={!canPrevious}
                onClick={() => changeMonth(new Date(year, month - 1, 1, 12))}
                className="shadow-none"
              >
                <ChevronLeft className="size-4" />
              </Button>
              <Button
                type="button"
                variant="ghost"
                size="icon-sm"
                aria-label="下个月"
                disabled={!canNext}
                onClick={() => changeMonth(new Date(year, month + 1, 1, 12))}
                className="shadow-none"
              >
                <ChevronRight className="size-4" />
              </Button>
            </div>
          </div>
          <div className="p-3">
            <table
              role="grid"
              aria-label={year + "年" + (month + 1) + "月"}
              className="w-full table-fixed border-separate border-spacing-1"
            >
              <thead>
                <tr>
                  {WEEKDAYS.map((day, index) => (
                    <th
                      key={day}
                      scope="col"
                      className={cn(
                        "h-7 text-center text-[11px] font-medium text-muted-foreground",
                        index > 4 && "text-muted-foreground/65"
                      )}
                    >
                      {day}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {Array.from({ length: 6 }, (_, rowIndex) => (
                  <tr key={rowIndex}>
                    {days.slice(rowIndex * 7, rowIndex * 7 + 7).map((day) => {
                      const dayValue = dateValue(day)
                      const selected = value === dayValue
                      const isToday = today === dayValue
                      const inactive = !isAllowed(dayValue)
                      return (
                        <td
                          key={dayValue}
                          role="gridcell"
                          aria-selected={selected}
                          className="p-0"
                        >
                          <button
                            type="button"
                            data-date={dayValue}
                            aria-label={dateLabel(day)}
                            aria-current={isToday ? "date" : undefined}
                            disabled={inactive}
                            tabIndex={
                              !inactive &&
                              tabbableDate &&
                              dateValue(tabbableDate) === dayValue
                                ? 0
                                : -1
                            }
                            onFocus={() => setFocusedDate(dayValue)}
                            onClick={() => chooseDate(dayValue)}
                            onKeyDown={(event) => handleDayKeyDown(event, day)}
                            className={cn(
                              "relative flex h-9 w-full cursor-pointer items-center justify-center rounded-lg text-xs font-medium tabular-nums transition-colors outline-none hover:bg-accent focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-1 disabled:cursor-not-allowed disabled:opacity-25",
                              day.getMonth() !== month &&
                                "text-muted-foreground/50",
                              isToday &&
                                !selected &&
                                "bg-primary/5 font-semibold text-primary ring-1 ring-primary/25 ring-inset",
                              selected &&
                                "bg-primary font-semibold text-primary-foreground shadow-sm hover:bg-primary/90"
                            )}
                          >
                            {day.getDate()}
                            {isToday && (
                              <span
                                aria-hidden="true"
                                className={cn(
                                  "absolute bottom-1 h-0.5 w-0.5 rounded-full bg-primary",
                                  selected && "bg-primary-foreground"
                                )}
                              />
                            )}
                          </button>
                        </td>
                      )
                    })}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <div className="flex items-center justify-between gap-3 border-t border-border/60 bg-muted/20 px-4 py-2.5">
            <Button
              type="button"
              variant="ghost"
              size="sm"
              disabled={!value || props.required}
              onClick={() => chooseDate("")}
              className="h-8 px-2 text-xs text-muted-foreground shadow-none"
            >
              清除
            </Button>
            <span className="text-[11px] text-muted-foreground">
              {hasDates ? value || "请选择日期" : "暂无可选日期"}
            </span>
            <Button
              type="button"
              variant="secondary"
              size="sm"
              disabled={!isAllowed(today)}
              onClick={() => chooseDate(today)}
              className="h-8 px-3 text-xs shadow-none"
            >
              今天
            </Button>
          </div>
        </Popover.Content>
      </Popover.Portal>
    </Popover.Root>
  )
}
