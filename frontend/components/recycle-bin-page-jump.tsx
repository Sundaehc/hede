"use client"

import { useId, useState } from "react"
import { ArrowRight, ChevronLeft, ChevronRight } from "lucide-react"

import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"

type RecycleBinPageJumpProps = {
  page: number
  totalPages: number
  disabled?: boolean
  onPageChange: (page: number) => void
}

export function RecycleBinPagination({ page, totalPages, disabled = false, onPageChange }: RecycleBinPageJumpProps) {
  return (
    <nav aria-label="回收站分页" className="flex max-w-full flex-wrap items-center justify-end gap-x-3 gap-y-2">
      <div className="inline-flex h-9 shrink-0 items-center gap-1 rounded-lg border border-border/60 bg-muted/40 p-0.5">
        <Button
          type="button"
          size="sm"
          variant="ghost"
          aria-label="上一页"
          disabled={page <= 1 || disabled}
          onClick={() => onPageChange(Math.max(1, page - 1))}
          className="h-8 gap-1 rounded-md px-2 text-xs text-muted-foreground shadow-none hover:bg-background hover:text-foreground disabled:opacity-35 sm:px-2.5"
        >
          <ChevronLeft className="size-3.5" aria-hidden="true" />
          <span className="hidden sm:inline">上一页</span>
        </Button>
        <span
          role="status"
          aria-label="回收站当前页码"
          aria-live="polite"
          aria-atomic="true"
          className="min-w-16 px-2 text-center text-xs font-semibold whitespace-nowrap tabular-nums text-foreground"
        >
          {page} / {totalPages}
        </span>
        <Button
          type="button"
          size="sm"
          variant="ghost"
          aria-label="下一页"
          disabled={page >= totalPages || disabled}
          onClick={() => onPageChange(Math.min(totalPages, page + 1))}
          className="h-8 gap-1 rounded-md px-2 text-xs text-muted-foreground shadow-none hover:bg-background hover:text-foreground disabled:opacity-35 sm:px-2.5"
        >
          <span className="hidden sm:inline">下一页</span>
          <ChevronRight className="size-3.5" aria-hidden="true" />
        </Button>
      </div>
      <span aria-hidden="true" className="hidden h-5 w-px bg-border/70 sm:block" />
      <RecycleBinPageJump page={page} totalPages={totalPages} disabled={disabled} onPageChange={onPageChange} />
    </nav>
  )
}

export function RecycleBinPageJump({ page, totalPages, disabled = false, onPageChange }: RecycleBinPageJumpProps) {
  const inputId = useId()
  const [pageInput, setPageInput] = useState({ page, value: String(page) })
  if (pageInput.page !== page) {
    setPageInput({ page, value: String(page) })
  }
  const targetPage = Number(pageInput.value)
  const isTargetPageValid = Number.isInteger(targetPage) && targetPage >= 1 && targetPage <= totalPages

  return (
    <form
      aria-label="回收站页码跳转"
      className="flex shrink-0 items-center gap-2 text-xs text-muted-foreground"
      onSubmit={(event) => {
        event.preventDefault()
        if (!isTargetPageValid || disabled) return
        onPageChange(targetPage)
      }}
    >
      <Label htmlFor={inputId} className="shrink-0 text-xs font-normal text-muted-foreground">跳至</Label>
      <div className="relative">
        <Input
          id={inputId}
          aria-label="回收站跳转页码"
          aria-invalid={pageInput.value !== "" && !isTargetPageValid}
          type="number"
          inputMode="numeric"
          min={1}
          max={totalPages}
          step={1}
          required
          value={pageInput.value}
          onChange={(event) => setPageInput({ page, value: event.target.value })}
          disabled={disabled}
          className="h-8 w-20 appearance-none rounded-md border-border/80 pl-2 pr-6 text-center text-xs tabular-nums shadow-none [appearance:textfield] [&::-webkit-inner-spin-button]:appearance-none [&::-webkit-outer-spin-button]:appearance-none"
        />
        <span aria-hidden="true" className="pointer-events-none absolute inset-y-0 right-2.5 flex items-center text-xs text-muted-foreground">页</span>
      </div>
      <Button type="submit" size="sm" variant="secondary" disabled={!isTargetPageValid || disabled} className="h-8 gap-1.5 rounded-md bg-primary/10 px-3 text-xs text-primary shadow-none hover:bg-primary/15">
        跳转
        <ArrowRight className="size-3.5" aria-hidden="true" />
      </Button>
    </form>
  )
}
