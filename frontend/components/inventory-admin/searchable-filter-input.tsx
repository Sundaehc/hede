"use client"

import { useEffect, useMemo, useRef, useState } from "react"
import { Search, X } from "lucide-react"

export type SearchableFilterOption = {
  value: string
  label: string
  keywords?: string
}

type SearchableFilterInputProps = {
  value: string
  options: SearchableFilterOption[]
  onChange: (value: string) => void
  onSubmit?: () => void
  placeholder?: string
  emptyText?: string
  className?: string
}

type SearchableMultiFilterInputProps = {
  values: string[]
  options: SearchableFilterOption[]
  onChange: (values: string[]) => void
  onSubmit?: () => void
  placeholder?: string
  emptyText?: string
  className?: string
}

export function SearchableFilterInput({
  value,
  options,
  onChange,
  onSubmit,
  placeholder = "输入关键词搜索",
  emptyText = "没有匹配项",
  className = "",
}: SearchableFilterInputProps) {
  const rootRef = useRef<HTMLDivElement>(null)
  const [open, setOpen] = useState(false)
  const searchTerm = value.trim().toLowerCase()
  const visibleOptions = useMemo(() => (
    (searchTerm
      ? options.filter((option) => `${option.label} ${option.value} ${option.keywords || ""}`.toLowerCase().includes(searchTerm))
      : options
    ).slice(0, 80)
  ), [options, searchTerm])

  useEffect(() => {
    const handlePointerDown = (event: MouseEvent) => {
      if (!rootRef.current?.contains(event.target as Node)) {
        setOpen(false)
      }
    }
    document.addEventListener("mousedown", handlePointerDown)
    return () => document.removeEventListener("mousedown", handlePointerDown)
  }, [])

  const selectValue = (nextValue: string) => {
    onChange(nextValue)
    setOpen(false)
  }

  return (
    <div ref={rootRef} className="relative">
      <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
      <input
        value={value}
        role="combobox"
        aria-expanded={open}
        aria-autocomplete="list"
        onFocus={() => setOpen(true)}
        onChange={(event) => {
          onChange(event.target.value)
          setOpen(true)
        }}
        onKeyDown={(event) => {
          if (event.key === "Enter") {
            event.preventDefault()
            if (visibleOptions.length === 1) {
              selectValue(visibleOptions[0].value)
            } else {
              setOpen(false)
              onSubmit?.()
            }
          }
          if (event.key === "Escape") {
            setOpen(false)
          }
        }}
        placeholder={placeholder}
        className={`flex h-9 w-full rounded-lg border border-input bg-card py-2 pl-9 pr-9 text-sm shadow-xs outline-none transition-colors placeholder:text-muted-foreground focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/35 ${className}`}
      />
      {value ? (
        <button
          type="button"
          aria-label="清空"
          onClick={() => selectValue("")}
          className="absolute right-2 top-1/2 inline-flex h-6 w-6 -translate-y-1/2 cursor-pointer items-center justify-center rounded-md text-muted-foreground hover:bg-muted hover:text-foreground"
        >
          <X className="h-3.5 w-3.5" />
        </button>
      ) : null}
      {open ? (
        <div className="absolute z-50 mt-1 max-h-72 w-full overflow-auto rounded-lg border border-border bg-popover p-1 text-sm shadow-lg">
          {visibleOptions.length === 0 ? (
            <div className="px-3 py-2 text-muted-foreground">{emptyText}</div>
          ) : visibleOptions.map((option) => (
            <button
              key={`${option.value}-${option.label}`}
              type="button"
              onMouseDown={(event) => event.preventDefault()}
              onClick={() => selectValue(option.value)}
              className={`flex w-full cursor-pointer items-center rounded-md px-3 py-2 text-left hover:bg-muted ${option.value === value ? "bg-muted text-foreground" : "text-foreground"}`}
            >
              <span className="min-w-0 truncate">{option.label}</span>
            </button>
          ))}
          {visibleOptions.length === 80 ? (
            <div className="border-t border-border px-3 py-2 text-xs text-muted-foreground">结果较多，请继续输入缩小范围</div>
          ) : null}
        </div>
      ) : null}
    </div>
  )
}

export function SearchableMultiFilterInput({
  values,
  options,
  onChange,
  onSubmit,
  placeholder = "输入关键词搜索",
  emptyText = "没有匹配项",
  className = "",
}: SearchableMultiFilterInputProps) {
  const rootRef = useRef<HTMLDivElement>(null)
  const [open, setOpen] = useState(false)
  const [searchTerm, setSearchTerm] = useState("")
  const normalizedSearchTerm = searchTerm.trim().toLowerCase()
  const selectedValues = useMemo(() => new Set(values), [values])
  const selectedOptions = useMemo(() => (
    values.map((value) => options.find((option) => option.value === value) ?? { value, label: value })
  ), [options, values])
  const visibleOptions = useMemo(() => (
    (normalizedSearchTerm
      ? options.filter((option) => `${option.label} ${option.value} ${option.keywords || ""}`.toLowerCase().includes(normalizedSearchTerm))
      : options
    ).filter((option) => !selectedValues.has(option.value)).slice(0, 80)
  ), [normalizedSearchTerm, options, selectedValues])

  useEffect(() => {
    const handlePointerDown = (event: MouseEvent) => {
      if (!rootRef.current?.contains(event.target as Node)) setOpen(false)
    }
    document.addEventListener("mousedown", handlePointerDown)
    return () => document.removeEventListener("mousedown", handlePointerDown)
  }, [])

  const addValue = (value: string) => {
    if (!selectedValues.has(value)) onChange([...values, value])
    setSearchTerm("")
    setOpen(true)
  }

  const removeValue = (value: string) => {
    onChange(values.filter((selectedValue) => selectedValue !== value))
  }

  return (
    <div ref={rootRef} className="relative">
      <div className={`flex min-h-9 w-full flex-wrap items-center gap-1 rounded-lg border border-input bg-card py-1 pl-2 pr-2 shadow-xs transition-colors focus-within:border-ring focus-within:ring-3 focus-within:ring-ring/35 ${className}`}>
        {selectedOptions.map((option) => (
          <span key={option.value} className="inline-flex max-w-full items-center gap-1 rounded-md bg-muted px-1.5 py-0.5 text-xs text-foreground">
            <span className="max-w-32 truncate">{option.label}</span>
            <button type="button" aria-label={`移除 ${option.label}`} onClick={() => removeValue(option.value)} className="inline-flex h-4 w-4 shrink-0 cursor-pointer items-center justify-center rounded-sm text-muted-foreground hover:bg-background hover:text-foreground">
              <X className="h-3 w-3" />
            </button>
          </span>
        ))}
        <div className="flex min-w-24 flex-1 items-center">
          <Search className="pointer-events-none ml-1 mr-1.5 h-4 w-4 shrink-0 text-muted-foreground" />
          <input
            value={searchTerm}
            role="combobox"
            aria-expanded={open}
            aria-autocomplete="list"
            onFocus={() => setOpen(true)}
            onChange={(event) => {
              setSearchTerm(event.target.value)
              setOpen(true)
            }}
            onKeyDown={(event) => {
              if (event.key === "Enter") {
                event.preventDefault()
                if (visibleOptions.length === 1) addValue(visibleOptions[0].value)
                else {
                  setOpen(false)
                  onSubmit?.()
                }
              }
              if (event.key === "Backspace" && !searchTerm && values.length > 0) removeValue(values[values.length - 1])
              if (event.key === "Escape") setOpen(false)
            }}
            placeholder={values.length ? "继续添加仓库" : placeholder}
            className="h-7 min-w-0 flex-1 bg-transparent text-sm outline-none placeholder:text-muted-foreground"
          />
        </div>
        {values.length ? (
          <button type="button" aria-label="清空已选仓库" onClick={() => onChange([])} className="inline-flex h-6 w-6 shrink-0 cursor-pointer items-center justify-center rounded-md text-muted-foreground hover:bg-muted hover:text-foreground">
            <X className="h-3.5 w-3.5" />
          </button>
        ) : null}
      </div>
      {open ? (
        <div className="absolute z-50 mt-1 max-h-72 w-full overflow-auto rounded-lg border border-border bg-popover p-1 text-sm shadow-lg">
          {visibleOptions.length === 0 ? (
            <div className="px-3 py-2 text-muted-foreground">{emptyText}</div>
          ) : visibleOptions.map((option) => (
            <button
              key={`${option.value}-${option.label}`}
              type="button"
              onMouseDown={(event) => event.preventDefault()}
              onClick={() => addValue(option.value)}
              className="flex w-full cursor-pointer items-center rounded-md px-3 py-2 text-left text-foreground hover:bg-muted"
            >
              <span className="min-w-0 truncate">{option.label}</span>
            </button>
          ))}
          {visibleOptions.length === 80 ? (
            <div className="border-t border-border px-3 py-2 text-xs text-muted-foreground">结果较多，请继续输入缩小范围</div>
          ) : null}
        </div>
      ) : null}
    </div>
  )
}
