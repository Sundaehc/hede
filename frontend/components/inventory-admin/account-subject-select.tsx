"use client"

import { useId, useRef, useState, type KeyboardEvent } from "react"
import { BookOpenText, Check, ChevronDown, Search, X } from "lucide-react"
import { Popover } from "radix-ui"

import type { InventoryAccountSubject } from "@/lib/api"
import { cn } from "@/lib/utils"

type AccountSubjectSelectProps = {
  id: string
  value: string
  subjects: InventoryAccountSubject[]
  onValueChange: (value: string) => void
  disabled?: boolean
}

const CATEGORIES = ["收入类", "支出类"] as const

export function AccountSubjectSelect({
  id,
  value,
  subjects,
  onValueChange,
  disabled = false,
}: AccountSubjectSelectProps) {
  const listId = useId()
  const triggerRef = useRef<HTMLButtonElement>(null)
  const inputRef = useRef<HTMLInputElement>(null)
  const listRef = useRef<HTMLDivElement>(null)
  const [open, setOpen] = useState(false)
  const [query, setQuery] = useState("")
  const [activeName, setActiveName] = useState("")
  const [portalContainer, setPortalContainer] = useState<HTMLElement>()
  const selected = subjects.find((subject) => subject.name === value)
  const searchTerm = query.trim().toLocaleLowerCase()
  const groups = CATEGORIES.map((category) => ({
    category,
    subjects: subjects.filter(
      (subject) =>
        (subject.category || "收入类") === category &&
        (!searchTerm || `${subject.name} ${category}`.toLocaleLowerCase().includes(searchTerm))
    ),
  })).filter((group) => group.subjects.length > 0)
  const visibleSubjects = groups.flatMap((group) => group.subjects)
  const activeSubject =
    visibleSubjects.find((subject) => subject.name === activeName) ||
    visibleSubjects.find((subject) => subject.name === value) ||
    visibleSubjects[0]

  function changeOpen(nextOpen: boolean) {
    if (nextOpen && disabled) return
    if (nextOpen) {
      setPortalContainer(triggerRef.current?.closest<HTMLElement>('[role="dialog"]') || undefined)
      setQuery("")
      setActiveName(value)
    }
    setOpen(nextOpen)
  }

  function selectSubject(name: string) {
    onValueChange(name)
    setOpen(false)
  }

  function navigateOptions(event: KeyboardEvent<HTMLInputElement>) {
    if (event.nativeEvent.isComposing) return
    if (event.key === "Enter") {
      event.preventDefault()
      if (activeSubject) selectSubject(activeSubject.name)
    } else if (event.key === "ArrowDown" || event.key === "ArrowUp") {
      event.preventDefault()
      const currentIndex = visibleSubjects.findIndex((subject) => subject.id === activeSubject?.id)
      const nextIndex = currentIndex + (event.key === "ArrowDown" ? 1 : -1)
      const next = visibleSubjects[Math.max(0, Math.min(visibleSubjects.length - 1, nextIndex))]
      if (!next) return
      setActiveName(next.name)
      listRef.current?.querySelector<HTMLElement>(`[data-subject-id="${next.id}"]`)?.scrollIntoView?.({ block: "nearest" })
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
          <BookOpenText aria-hidden="true" className="size-4 shrink-0 text-muted-foreground" />
          <span className={cn("min-w-0 flex-1 truncate", !value && "text-muted-foreground")}>
            {value || "请选择科目"}
          </span>
          {selected ? (
            <span className="shrink-0 rounded bg-muted px-1.5 py-0.5 text-[11px] text-muted-foreground">
              {selected.category || "收入类"}
            </span>
          ) : null}
          <ChevronDown aria-hidden="true" className={cn("size-3.5 shrink-0 text-muted-foreground transition-transform", open && "rotate-180")} />
        </button>
      </Popover.Trigger>
      <Popover.Portal container={portalContainer}>
        <Popover.Content
          aria-label="选择费用科目"
          align="start"
          sideOffset={6}
          collisionPadding={12}
          onOpenAutoFocus={(event) => {
            event.preventDefault()
            inputRef.current?.focus()
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
          className="z-[150] flex max-h-[min(22rem,var(--radix-popover-content-available-height))] w-[var(--radix-popover-trigger-width)] max-w-[calc(100vw-1.5rem)] flex-col overflow-hidden rounded-xl border border-border/80 bg-popover text-popover-foreground shadow-xl shadow-black/10 outline-none"
        >
          <div className="relative shrink-0 border-b border-border/70">
            <Search aria-hidden="true" className="pointer-events-none absolute top-3 left-3 size-4 text-muted-foreground" />
            <input
              ref={inputRef}
              role="combobox"
              aria-label="搜索科目"
              aria-autocomplete="list"
              aria-expanded={open}
              aria-controls={listId}
              aria-activedescendant={activeSubject ? `${listId}-${activeSubject.id}` : undefined}
              value={query}
              onChange={(event) => {
                setQuery(event.target.value)
                setActiveName("")
                listRef.current?.scrollTo?.({ top: 0 })
              }}
              onKeyDown={navigateOptions}
              placeholder="搜索科目名称或分类"
              autoComplete="off"
              className="h-10 w-full min-w-0 bg-transparent pr-9 pl-9 text-sm outline-none placeholder:text-muted-foreground"
            />
            {query ? (
              <button
                type="button"
                aria-label="清空科目搜索"
                onClick={() => {
                  setQuery("")
                  setActiveName(value)
                  inputRef.current?.focus()
                }}
                className="absolute top-2 right-2 flex size-6 cursor-pointer items-center justify-center rounded-md text-muted-foreground hover:bg-muted hover:text-foreground focus-visible:outline-2 focus-visible:outline-ring"
              >
                <X aria-hidden="true" className="size-3.5" />
              </button>
            ) : null}
          </div>
          <div ref={listRef} id={listId} role="listbox" aria-label="费用科目" className="min-h-0 flex-1 overflow-y-auto overscroll-contain p-1">
            {groups.length === 0 ? (
              <div role="status" className="px-3 py-7 text-center text-sm text-muted-foreground">
                {subjects.length === 0 ? "暂无可选科目，请先在科目管理中添加" : "没有匹配的科目，请更换关键词"}
              </div>
            ) : groups.map((group) => (
              <div key={group.category} role="group" aria-label={group.category}>
                <div className="flex items-center justify-between rounded-md bg-muted px-2.5 py-1.5 text-[11px] font-medium text-muted-foreground">
                  <span>{group.category}</span>
                  <span className="tabular-nums">{group.subjects.length}</span>
                </div>
                {group.subjects.map((subject) => (
                  <button
                    key={subject.id}
                    id={`${listId}-${subject.id}`}
                    data-subject-id={subject.id}
                    type="button"
                    role="option"
                    tabIndex={-1}
                    aria-selected={subject.name === value}
                    onMouseDown={(event) => event.preventDefault()}
                    onPointerMove={() => setActiveName(subject.name)}
                    onClick={() => selectSubject(subject.name)}
                    className={cn(
                      "my-0.5 flex min-h-8 w-full cursor-pointer items-center gap-2 rounded-md px-2.5 py-1.5 text-left text-sm transition-colors hover:bg-accent focus-visible:outline-2 focus-visible:outline-ring",
                      activeSubject?.id === subject.id && "bg-accent",
                      subject.name === value && "font-medium text-primary"
                    )}
                  >
                    <span className="min-w-0 flex-1 break-words">{subject.name}</span>
                    {subject.name === value ? <Check aria-hidden="true" className="size-4 shrink-0" /> : null}
                  </button>
                ))}
              </div>
            ))}
          </div>
          <div className="flex shrink-0 items-center justify-between gap-3 border-t border-border/70 bg-muted/20 px-3 py-2 text-[11px] text-muted-foreground">
            <span aria-live="polite">共 {visibleSubjects.length} 个科目</span>
            <span>↑↓ 选择 · 回车确认</span>
          </div>
        </Popover.Content>
      </Popover.Portal>
    </Popover.Root>
  )
}
