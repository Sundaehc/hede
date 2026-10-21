"use client"

import { useId, useMemo, useRef, useState, type KeyboardEvent } from "react"
import { Check, ChevronDown, Ruler, Search, X } from "lucide-react"
import { Popover } from "radix-ui"

import type { SizeGroup } from "@/lib/types"
import { cn } from "@/lib/utils"

type SizeGroupSelectProps = {
  id: string
  value: string
  groups: SizeGroup[]
  onValueChange: (value: string) => void
  disabled?: boolean
}

export function SizeGroupSelect({ id, value, groups, onValueChange, disabled = false }: SizeGroupSelectProps) {
  const listId = useId()
  const triggerRef = useRef<HTMLButtonElement>(null)
  const inputRef = useRef<HTMLInputElement>(null)
  const listRef = useRef<HTMLDivElement>(null)
  const [open, setOpen] = useState(false)
  const [query, setQuery] = useState("")
  const [activeValue, setActiveValue] = useState<string | null>(null)
  const [portalContainer, setPortalContainer] = useState<HTMLElement>()
  const selected = groups.find((group) => group.name === value)
  const searchTerm = query.trim().toLocaleLowerCase()
  const options = useMemo(() => {
    const terms = searchTerm.split(/\s+/).filter(Boolean)
    const matching = groups.filter((group) => {
      const keywords = `${group.name} ${group.items.map((item) => item.size_name).join(" ")}`.toLocaleLowerCase()
      return terms.every((term) => keywords.includes(term))
    }).map((group) => ({ value: group.name, label: group.name, sizeCount: group.items.length }))
    return searchTerm ? matching : [{ value: "", label: "未选择尺码段", sizeCount: null }, ...matching]
  }, [groups, searchTerm])
  const activeIndex = Math.max(0, options.findIndex((option) => option.value === (activeValue ?? value)))
  const activeOption = options[activeIndex]

  function changeOpen(nextOpen: boolean) {
    if (nextOpen && disabled) return
    if (nextOpen) {
      setPortalContainer(triggerRef.current?.closest<HTMLElement>('[role="dialog"]') || undefined)
      setQuery("")
      setActiveValue(value)
    }
    setOpen(nextOpen)
  }

  function selectValue(nextValue: string) {
    if (nextValue !== value) onValueChange(nextValue)
    setOpen(false)
  }

  function scrollToOption(index: number) {
    listRef.current?.querySelector<HTMLElement>(`[data-option-index="${index}"]`)?.scrollIntoView?.({ block: "nearest" })
  }

  function navigateOptions(event: KeyboardEvent<HTMLInputElement>) {
    if (event.nativeEvent.isComposing) return
    if (event.key === "Enter") {
      event.preventDefault()
      if (activeOption) selectValue(activeOption.value)
    } else if (["ArrowDown", "ArrowUp", "Home", "End"].includes(event.key)) {
      event.preventDefault()
      const nextIndex = event.key === "Home" ? 0
        : event.key === "End" ? options.length - 1
        : Math.max(0, Math.min(options.length - 1, activeIndex + (event.key === "ArrowDown" ? 1 : -1)))
      const next = options[nextIndex]
      if (!next) return
      setActiveValue(next.value)
      scrollToOption(nextIndex)
    }
  }

  return (
    <Popover.Root open={open} onOpenChange={changeOpen}>
      <Popover.Trigger asChild>
        <button
          ref={triggerRef}
          id={id}
          type="button"
          disabled={disabled}
          onKeyDown={(event) => {
            if (event.key === "ArrowDown" || event.key === "ArrowUp") {
              event.preventDefault()
              changeOpen(true)
            }
          }}
          className="flex h-9 w-full min-w-0 cursor-pointer items-center gap-2 rounded-lg border border-input bg-card px-3 text-left text-sm shadow-xs outline-none transition-colors hover:border-ring/55 hover:bg-accent/30 focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/35 disabled:cursor-not-allowed disabled:opacity-60 data-[state=open]:border-ring data-[state=open]:ring-3 data-[state=open]:ring-ring/20"
        >
          <Ruler aria-hidden="true" className="size-4 shrink-0 text-muted-foreground" />
          <span className={cn("min-w-0 flex-1 truncate", !value && "text-muted-foreground")} title={value || undefined}>
            {value || "未选择尺码段"}
          </span>
          {selected ? <span className="shrink-0 rounded bg-muted px-1.5 py-0.5 text-[11px] tabular-nums text-muted-foreground">{selected.items.length} 码</span> : null}
          <ChevronDown aria-hidden="true" className={cn("size-3.5 shrink-0 text-muted-foreground transition-transform motion-reduce:transition-none", open && "rotate-180")} />
        </button>
      </Popover.Trigger>
      <Popover.Portal container={portalContainer}>
        <Popover.Content
          aria-label="选择尺码段"
          align="start"
          sideOffset={5}
          collisionPadding={12}
          onOpenAutoFocus={(event) => {
            event.preventDefault()
            inputRef.current?.focus()
            scrollToOption(activeIndex)
          }}
          onEscapeKeyDown={(event) => {
            event.preventDefault()
            event.stopPropagation()
            setOpen(false)
          }}
          onKeyDown={(event) => {
            if (event.key === "Escape") {
              event.preventDefault()
              event.stopPropagation()
              setOpen(false)
            }
          }}
          className="z-[150] flex max-h-[min(20rem,var(--radix-popover-content-available-height))] w-[var(--radix-popover-trigger-width)] max-w-[calc(100vw-1.5rem)] flex-col overflow-hidden rounded-xl border border-border/80 bg-popover text-popover-foreground shadow-xl shadow-black/10 outline-none"
        >
          <div className="relative shrink-0 border-b border-border/70">
            <Search aria-hidden="true" className="pointer-events-none absolute top-3 left-3 size-3.5 text-muted-foreground" />
            <input
              ref={inputRef}
              role="combobox"
              aria-label="搜索尺码段"
              aria-autocomplete="list"
              aria-expanded={open}
              aria-controls={listId}
              aria-activedescendant={activeOption ? `${listId}-${activeIndex}` : undefined}
              value={query}
              onChange={(event) => {
                setQuery(event.target.value)
                setActiveValue(null)
                listRef.current?.scrollTo?.({ top: 0 })
              }}
              onKeyDown={navigateOptions}
              placeholder="搜索名称或尺码，如 220"
              autoComplete="off"
              className="h-10 w-full min-w-0 bg-transparent pr-9 pl-9 text-sm outline-none placeholder:text-muted-foreground"
            />
            {query ? (
              <button
                type="button"
                aria-label="清空尺码段搜索"
                onClick={() => {
                  setQuery("")
                  setActiveValue(value)
                  inputRef.current?.focus()
                }}
                className="absolute top-2 right-2 flex size-6 cursor-pointer items-center justify-center rounded-md text-muted-foreground hover:bg-muted hover:text-foreground focus-visible:outline-2 focus-visible:outline-ring"
              >
                <X aria-hidden="true" className="size-3.5" />
              </button>
            ) : null}
          </div>
          <div ref={listRef} id={listId} role="listbox" aria-label="尺码段选项" className="min-h-0 flex-1 overflow-y-auto overscroll-contain p-1">
            {options.map((option, index) => (
              <button
                key={option.value}
                id={`${listId}-${index}`}
                data-option-index={index}
                type="button"
                role="option"
                tabIndex={-1}
                aria-label={option.sizeCount === null ? option.label : `${option.label} ${option.sizeCount} 码`}
                aria-selected={option.value === value}
                onMouseDown={(event) => event.preventDefault()}
                onPointerMove={() => setActiveValue(option.value)}
                onClick={() => selectValue(option.value)}
                className={cn(
                  "my-0.5 flex min-h-9 w-full cursor-pointer items-center gap-2 rounded-md px-2.5 py-2 text-left text-sm transition-colors hover:bg-accent focus-visible:outline-2 focus-visible:outline-ring motion-reduce:transition-none",
                  activeIndex === index && "bg-accent",
                  option.value === value && "font-medium text-primary",
                  !option.value && "text-muted-foreground"
                )}
              >
                <span className="flex size-4 shrink-0 items-center justify-center">{option.value === value ? <Check aria-hidden="true" className="size-3.5" /> : null}</span>
                <span className="min-w-0 flex-1 break-words">{option.label}</span>
                {option.sizeCount !== null ? <span className="shrink-0 text-[11px] font-normal tabular-nums text-muted-foreground">{option.sizeCount} 码</span> : null}
              </button>
            ))}
            {options.length === 0 || groups.length === 0 ? (
              <div role="status" className="px-3 py-5 text-center text-xs leading-5 text-muted-foreground">
                {groups.length === 0 ? "暂无可选尺码段，请先在尺码组管理中维护" : "没有匹配的尺码段，请更换关键词"}
              </div>
            ) : null}
          </div>
          <div className="flex shrink-0 items-center justify-between gap-3 border-t border-border/70 bg-muted/20 px-3 py-1.5 text-[11px] text-muted-foreground">
            <span aria-live="polite">共 {options.filter((option) => option.value).length} 个尺码段</span>
            <span>↑↓ 选择 · 回车确认</span>
          </div>
        </Popover.Content>
      </Popover.Portal>
    </Popover.Root>
  )
}
