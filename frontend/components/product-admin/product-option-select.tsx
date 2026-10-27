"use client"

import { useId, useMemo, useRef, useState, type KeyboardEvent } from "react"
import { Check, ChevronDown, Search, X } from "lucide-react"
import { Popover } from "radix-ui"

import { Input } from "@/components/ui/input"
import { cn } from "@/lib/utils"

export type ProductSelectOption = {
  value: string
  label: string
  description?: string
  keywords?: string
}

type ProductOptionSelectProps = {
  id: string
  label: string
  value: string
  options: ProductSelectOption[]
  onValueChange: (value: string) => void
  disabled?: boolean
  isLoading?: boolean
  allowCustomValue?: boolean
  placeholder?: string
  emptyText?: string
}

const MAX_VISIBLE_OPTIONS = 80

export function ProductOptionSelect({
  id,
  label,
  value,
  options,
  onValueChange,
  disabled = false,
  isLoading = false,
  allowCustomValue = false,
  placeholder = "搜索并选择",
  emptyText = "没有匹配的选项",
}: ProductOptionSelectProps) {
  const listId = useId()
  const rootRef = useRef<HTMLDivElement>(null)
  const inputRef = useRef<HTMLInputElement>(null)
  const listRef = useRef<HTMLDivElement>(null)
  const [open, setOpen] = useState(false)
  const [query, setQuery] = useState("")
  const [activeValue, setActiveValue] = useState<string | null>(null)
  const [portalContainer, setPortalContainer] = useState<HTMLElement>()
  const selected = options.find((option) => option.value === value)
  const displayValue = selected
    ? [selected.label, selected.description].filter(Boolean).join(" - ")
    : value
  const matchingOptions = useMemo(() => {
    const terms = query.trim().toLocaleLowerCase().split(/\s+/).filter(Boolean)
    const unique = new Map<string, ProductSelectOption>()
    if (!terms.length && value && selected) unique.set(value, selected)
    for (const option of options) {
      const keywords =
        `${option.label} ${option.description || ""} ${option.keywords || ""}`.toLocaleLowerCase()
      if (
        terms.every((term) => keywords.includes(term)) &&
        !unique.has(option.value)
      ) {
        unique.set(option.value, option)
      }
    }
    return Array.from(unique.values())
  }, [options, query, selected, value])
  const visibleOptions = matchingOptions.slice(0, MAX_VISIBLE_OPTIONS)
  const activeIndex = Math.max(
    0,
    visibleOptions.findIndex(
      (option) => option.value === (activeValue ?? value)
    )
  )
  const activeOption = visibleOptions[activeIndex]
  const isDisabled = disabled || isLoading

  function changeOpen(nextOpen: boolean) {
    if (nextOpen && isDisabled) return
    if (nextOpen) {
      setPortalContainer(
        rootRef.current?.closest<HTMLElement>('[data-slot="dialog-content"]') ||
          undefined
      )
      setQuery("")
      setActiveValue(value)
    }
    setOpen(nextOpen)
  }

  function selectValue(nextValue: string) {
    if (nextValue !== value) onValueChange(nextValue)
    setOpen(false)
    setQuery("")
  }

  function navigateOptions(event: KeyboardEvent<HTMLInputElement>) {
    if (event.nativeEvent.isComposing) return
    if (event.key === "Escape" && open) {
      event.preventDefault()
      event.stopPropagation()
      changeOpen(false)
    } else if (event.key === "Enter" && open) {
      event.preventDefault()
      if (activeOption) selectValue(activeOption.value)
    } else if (
      ["ArrowDown", "ArrowUp", "Home", "End"].includes(event.key) &&
      (open || event.key.startsWith("Arrow"))
    ) {
      event.preventDefault()
      if (!open) {
        changeOpen(true)
        return
      }
      const nextIndex =
        event.key === "Home"
          ? 0
          : event.key === "End"
            ? visibleOptions.length - 1
            : Math.max(
                0,
                Math.min(
                  visibleOptions.length - 1,
                  activeIndex + (event.key === "ArrowDown" ? 1 : -1)
                )
              )
      const next = visibleOptions[nextIndex]
      if (!next) return
      setActiveValue(next.value)
      listRef.current
        ?.querySelector<HTMLElement>(`[data-option-index="${nextIndex}"]`)
        ?.scrollIntoView?.({ block: "nearest" })
    } else if (event.key === "Tab" && open) {
      changeOpen(false)
    }
  }

  return (
    <Popover.Root open={open && !isDisabled} onOpenChange={changeOpen}>
      <Popover.Anchor asChild>
        <div ref={rootRef} className="relative min-w-0">
          <Search
            aria-hidden="true"
            className="pointer-events-none absolute top-1/2 left-2.5 size-3.5 -translate-y-1/2 text-muted-foreground"
          />
          <Input
            ref={inputRef}
            id={id}
            role="combobox"
            aria-expanded={open && !isDisabled}
            aria-controls={open ? listId : undefined}
            aria-autocomplete="list"
            aria-activedescendant={
              open && activeOption ? `${listId}-${activeIndex}` : undefined
            }
            value={open && !isDisabled ? query : displayValue}
            placeholder={isLoading ? `${label}加载中...` : placeholder}
            disabled={isDisabled}
            autoComplete="off"
            spellCheck={false}
            onFocus={() => changeOpen(true)}
            onClick={() => {
              if (!open) changeOpen(true)
            }}
            onChange={(event) => {
              setQuery(event.target.value)
              setActiveValue(null)
              setOpen(true)
              listRef.current?.scrollTo?.({ top: 0 })
              if (allowCustomValue) onValueChange(event.target.value)
            }}
            onKeyDown={navigateOptions}
            className={cn(
              "min-w-0 pr-14 pl-8",
              open && "border-ring ring-3 ring-ring/20"
            )}
          />
          <div className="absolute top-1/2 right-1.5 flex -translate-y-1/2 items-center gap-0.5">
            {value && !isDisabled ? (
              <button
                type="button"
                aria-label={`清空${label}`}
                onMouseDown={(event) => event.preventDefault()}
                onClick={() => selectValue("")}
                className="flex size-5 cursor-pointer items-center justify-center rounded text-muted-foreground hover:bg-muted hover:text-foreground focus-visible:outline-2 focus-visible:outline-ring"
              >
                <X aria-hidden="true" className="size-3" />
              </button>
            ) : null}
            <button
              type="button"
              aria-label={`${open ? "收起" : "展开"}${label}选项`}
              disabled={isDisabled}
              tabIndex={-1}
              onMouseDown={(event) => event.preventDefault()}
              onClick={() => {
                if (open) changeOpen(false)
                else {
                  inputRef.current?.focus()
                  changeOpen(true)
                }
              }}
              className="flex size-5 cursor-pointer items-center justify-center rounded text-muted-foreground hover:bg-muted hover:text-foreground disabled:cursor-not-allowed disabled:opacity-50"
            >
              <ChevronDown
                aria-hidden="true"
                className={cn(
                  "size-3.5 transition-transform motion-reduce:transition-none",
                  open && "rotate-180"
                )}
              />
            </button>
          </div>
        </div>
      </Popover.Anchor>
      <Popover.Portal container={portalContainer}>
        <Popover.Content
          aria-label={`选择${label}`}
          align="start"
          sideOffset={5}
          collisionPadding={12}
          onOpenAutoFocus={(event) => {
            event.preventDefault()
            requestAnimationFrame(() =>
              listRef.current
                ?.querySelector<HTMLElement>('[aria-selected="true"]')
                ?.scrollIntoView?.({ block: "nearest" })
            )
          }}
          onCloseAutoFocus={(event) => event.preventDefault()}
          onInteractOutside={(event) => {
            if (rootRef.current?.contains(event.target as Node))
              event.preventDefault()
          }}
          onEscapeKeyDown={(event) => {
            event.preventDefault()
            event.stopPropagation()
            changeOpen(false)
            inputRef.current?.focus()
          }}
          className="z-[150] flex max-h-[min(18rem,var(--radix-popover-content-available-height))] w-[var(--radix-popover-trigger-width)] max-w-[calc(100vw-1.5rem)] flex-col overflow-hidden rounded-xl border border-border/80 bg-popover text-popover-foreground shadow-xl shadow-black/10 outline-none"
        >
          <div
            ref={listRef}
            id={listId}
            role="listbox"
            aria-label={`${label}选项`}
            className="min-h-0 flex-1 overflow-y-auto overscroll-contain p-1"
          >
            {visibleOptions.map((option, index) => (
              <button
                key={option.value}
                id={`${listId}-${index}`}
                data-option-index={index}
                type="button"
                role="option"
                aria-label={[option.label, option.description]
                  .filter(Boolean)
                  .join(" ")}
                aria-selected={option.value === value}
                tabIndex={-1}
                onMouseDown={(event) => event.preventDefault()}
                onPointerMove={() => setActiveValue(option.value)}
                onClick={() => selectValue(option.value)}
                className={cn(
                  "my-0.5 flex min-h-8 w-full cursor-pointer items-center gap-2 rounded-md px-2.5 py-1.5 text-left text-sm transition-colors hover:bg-accent motion-reduce:transition-none",
                  activeIndex === index && "bg-accent",
                  option.value === value && "font-medium text-primary"
                )}
              >
                <span className="min-w-0 flex-1 break-words">
                  {option.label}
                  {option.description ? (
                    <span className="ml-2 text-xs font-normal text-muted-foreground">
                      {option.description}
                    </span>
                  ) : null}
                </span>
                {option.value === value ? (
                  <Check aria-hidden="true" className="size-3.5 shrink-0" />
                ) : null}
              </button>
            ))}
            {visibleOptions.length === 0 ? (
              <div
                role="status"
                className="px-3 py-5 text-center text-xs leading-5 text-muted-foreground"
              >
                {emptyText}
              </div>
            ) : null}
          </div>
          <div className="flex shrink-0 items-center justify-between gap-2 border-t border-border/70 bg-muted/20 px-3 py-1.5 text-[11px] text-muted-foreground">
            <span aria-live="polite">
              {matchingOptions.length > MAX_VISIBLE_OPTIONS
                ? `显示前 ${MAX_VISIBLE_OPTIONS} 项，请搜索`
                : `共 ${matchingOptions.length} 项`}
            </span>
            <span className="shrink-0">↑↓ 选择 · 回车确认</span>
          </div>
        </Popover.Content>
      </Popover.Portal>
    </Popover.Root>
  )
}
