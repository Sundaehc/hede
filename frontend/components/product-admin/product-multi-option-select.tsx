"use client"

import { useId, useMemo, useRef, useState, type KeyboardEvent } from "react"
import { Check, ChevronDown, Search, X } from "lucide-react"
import { Popover } from "radix-ui"

import type { ProductSelectOption } from "@/components/product-admin/product-option-select"
import { cn } from "@/lib/utils"

type Props = {
  id: string
  label: string
  values: string[]
  query: string
  options: ProductSelectOption[]
  onValuesChange: (values: string[]) => void
  onQueryChange: (query: string) => void
  onSubmit: (values: string[]) => void
  placeholder: string
}

const MAX_VISIBLE_OPTIONS = 80

export function ProductMultiOptionSelect({ id, label, values, query, options, onValuesChange, onQueryChange, onSubmit, placeholder }: Props) {
  const listId = useId()
  const rootRef = useRef<HTMLDivElement>(null)
  const inputRef = useRef<HTMLInputElement>(null)
  const listRef = useRef<HTMLDivElement>(null)
  const [open, setOpen] = useState(false)
  const [activeValue, setActiveValue] = useState<string | null>(null)
  const valueSet = useMemo(() => new Set(values), [values])
  const matchingOptions = useMemo(() => {
    const terms = query.trim().toLocaleLowerCase().split(/\s+/).filter(Boolean)
    return options.filter((option) => {
      const text = `${option.label} ${option.description ?? ""} ${option.keywords ?? ""}`.toLocaleLowerCase()
      return terms.every((term) => text.includes(term))
    })
  }, [options, query])
  const visibleOptions = matchingOptions.slice(0, MAX_VISIBLE_OPTIONS)
  const activeIndex = visibleOptions.findIndex((option) => option.value === activeValue)
  const activeOption = visibleOptions[activeIndex]

  function toggleValue(value: string) {
    onValuesChange(valueSet.has(value) ? values.filter((item) => item !== value) : [...values, value])
    onQueryChange("")
    setActiveValue(null)
    inputRef.current?.focus()
  }

  function navigateOptions(event: KeyboardEvent<HTMLInputElement>) {
    if (event.nativeEvent.isComposing) return
    if (event.key === "Enter") {
      event.preventDefault()
      event.stopPropagation()
      if (open && activeOption) {
        toggleValue(activeOption.value)
        return
      }
      const next = [...new Set([...values, query.trim()].filter(Boolean))]
      onValuesChange(next)
      onQueryChange("")
      setOpen(false)
      onSubmit(next)
    } else if (event.key === "Escape") {
      event.preventDefault()
      event.stopPropagation()
      setOpen(false)
    } else if (["ArrowDown", "ArrowUp", "Home", "End"].includes(event.key) && (open || event.key.startsWith("Arrow"))) {
      event.preventDefault()
      setOpen(true)
      const nextIndex = event.key === "Home" ? 0 : event.key === "End" ? visibleOptions.length - 1
        : activeIndex < 0 ? (event.key === "ArrowDown" ? 0 : visibleOptions.length - 1)
          : Math.max(0, Math.min(visibleOptions.length - 1, activeIndex + (event.key === "ArrowDown" ? 1 : -1)))
      setActiveValue(visibleOptions[nextIndex]?.value ?? null)
      listRef.current?.querySelector<HTMLElement>(`[data-option-index="${nextIndex}"]`)?.scrollIntoView?.({ block: "nearest" })
    } else if (event.key === "Backspace" && !query && values.length) {
      onValuesChange(values.slice(0, -1))
    } else if (event.key === "Tab") {
      setOpen(false)
    }
  }

  return (
    <Popover.Root open={open} onOpenChange={setOpen}>
      <Popover.Anchor asChild>
        <div ref={rootRef} className={cn("relative flex min-h-8 min-w-0 flex-wrap items-center gap-1 rounded-md border border-input bg-background py-1 pr-14 pl-8 text-sm shadow-none", open && "border-ring ring-3 ring-ring/20")}>
          <Search aria-hidden="true" className="pointer-events-none absolute top-2.5 left-2.5 size-3.5 text-muted-foreground" />
          {values.map((value) => (
            <span key={value} className="inline-flex max-w-full items-center gap-1 rounded bg-primary/10 px-1.5 py-0.5 text-xs text-foreground">
              <span className="truncate" title={value}>{value}</span>
              <button type="button" aria-label={`移除${label}：${value}`} onMouseDown={(event) => event.preventDefault()} onClick={() => onValuesChange(values.filter((item) => item !== value))} className="flex size-4 shrink-0 cursor-pointer items-center justify-center rounded hover:bg-primary/15 focus-visible:outline-2 focus-visible:outline-ring">
                <X aria-hidden="true" className="size-3" />
              </button>
            </span>
          ))}
          <input
            ref={inputRef}
            id={id}
            role="combobox"
            aria-expanded={open}
            aria-controls={open ? listId : undefined}
            aria-autocomplete="list"
            aria-activedescendant={open && activeOption ? `${listId}-${activeIndex}` : undefined}
            value={query}
            placeholder={values.length ? "继续搜索添加" : placeholder}
            autoComplete="off"
            spellCheck={false}
            onFocus={() => { setActiveValue(null); setOpen(true) }}
            onClick={() => setOpen(true)}
            onChange={(event) => { onQueryChange(event.target.value); setActiveValue(null); setOpen(true); listRef.current?.scrollTo?.({ top: 0 }) }}
            onKeyDown={navigateOptions}
            className="h-5 w-20 min-w-16 flex-1 bg-transparent text-sm outline-none placeholder:text-muted-foreground"
          />
          <div className="absolute top-1 right-1.5 flex items-center gap-0.5">
            {(values.length > 0 || query) && (
              <button type="button" aria-label={`清空${label}`} onMouseDown={(event) => event.preventDefault()} onClick={() => { onValuesChange([]); onQueryChange(""); setActiveValue(null) }} className="flex size-5 cursor-pointer items-center justify-center rounded text-muted-foreground hover:bg-muted hover:text-foreground focus-visible:outline-2 focus-visible:outline-ring">
                <X aria-hidden="true" className="size-3" />
              </button>
            )}
            <button type="button" aria-label={`${open ? "收起" : "展开"}${label}选项`} tabIndex={-1} onMouseDown={(event) => event.preventDefault()} onClick={() => { if (open) setOpen(false); else { inputRef.current?.focus(); setOpen(true) } }} className="flex size-5 cursor-pointer items-center justify-center rounded text-muted-foreground hover:bg-muted hover:text-foreground">
              <ChevronDown aria-hidden="true" className={cn("size-3.5 transition-transform motion-reduce:transition-none", open && "rotate-180")} />
            </button>
          </div>
        </div>
      </Popover.Anchor>
      <Popover.Portal>
        <Popover.Content
          aria-label={`选择${label}`}
          align="start"
          sideOffset={5}
          collisionPadding={12}
          onOpenAutoFocus={(event) => event.preventDefault()}
          onCloseAutoFocus={(event) => event.preventDefault()}
          onInteractOutside={(event) => { if (rootRef.current?.contains(event.target as Node)) event.preventDefault() }}
          onEscapeKeyDown={(event) => { event.preventDefault(); event.stopPropagation(); setOpen(false); inputRef.current?.focus() }}
          className="z-[150] flex max-h-[min(18rem,var(--radix-popover-content-available-height))] w-[var(--radix-popover-trigger-width)] max-w-[calc(100vw-1.5rem)] flex-col overflow-hidden rounded-xl border border-border/80 bg-popover text-popover-foreground shadow-xl outline-none"
        >
          <div ref={listRef} id={listId} role="listbox" aria-label={`${label}选项`} aria-multiselectable="true" className="min-h-0 flex-1 overflow-y-auto overscroll-contain p-1">
            {visibleOptions.map((option, index) => (
              <button key={option.value} id={`${listId}-${index}`} data-option-index={index} type="button" role="option" aria-label={option.label} aria-selected={valueSet.has(option.value)} tabIndex={-1} onMouseDown={(event) => event.preventDefault()} onClick={() => toggleValue(option.value)} className={cn("my-0.5 flex min-h-8 w-full cursor-pointer items-center gap-2 rounded-md px-2.5 py-1.5 text-left text-sm hover:bg-accent", activeIndex === index && "bg-accent", valueSet.has(option.value) && "font-medium text-primary")}>
                <span aria-hidden="true" className={cn("flex size-3.5 shrink-0 items-center justify-center rounded-sm border", valueSet.has(option.value) ? "border-primary bg-primary text-primary-foreground" : "border-input")}>
                  {valueSet.has(option.value) && <Check className="size-3" />}
                </span>
                <span className="min-w-0 flex-1 break-words">{option.label}</span>
              </button>
            ))}
            {!visibleOptions.length && <p role="status" className="px-3 py-5 text-center text-xs text-muted-foreground">没有匹配的选项，可按回车搜索关键词</p>}
          </div>
          <div className="flex shrink-0 items-center justify-between gap-2 border-t border-border/70 bg-muted/20 px-3 py-1.5 text-[11px] text-muted-foreground">
            <span aria-live="polite">已选 {values.length} 项 · {matchingOptions.length > MAX_VISIBLE_OPTIONS ? `显示前 ${MAX_VISIBLE_OPTIONS} 项，请搜索` : `共 ${matchingOptions.length} 项`}</span>
            <span className="shrink-0">可多选</span>
          </div>
        </Popover.Content>
      </Popover.Portal>
    </Popover.Root>
  )
}
