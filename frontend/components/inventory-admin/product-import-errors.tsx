"use client"

import { useRef, useState } from "react"
import { Check, ChevronLeft, ChevronRight, CircleAlert, Copy } from "lucide-react"

import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert"
import { Button } from "@/components/ui/button"
import { copyTextareaText } from "@/lib/copy-textarea"
import type { ProductImportValidation } from "@/lib/product-import-validation"
import { PRODUCT_ARCHIVE_BRANDS } from "@/lib/brands"

const PAGE_SIZE = 50

export function ProductImportErrors({ validation, message, brands }: {
  validation: ProductImportValidation
  message: string
  brands?: ReadonlyArray<{ value: string; label: string }>
}) {
  const [page, setPage] = useState(1)
  const [copyState, setCopyState] = useState<"idle" | "copying" | "copied" | "failed">("idle")
  const copyContainerRef = useRef<HTMLDivElement>(null)
  const pages = Math.max(1, Math.ceil(validation.errors.length / PAGE_SIZE))
  const currentPage = Math.min(page, pages)
  const start = (currentPage - 1) * PAGE_SIZE
  const brandLabels = new Map<string, string>(PRODUCT_ARCHIVE_BRANDS.map((item) => [item.key, item.label]))
  brandLabels.set("ns", "NS")
  brandLabels.set("eblan_womens", "伊伴女鞋")
  for (const item of brands ?? []) brandLabels.set(item.value, item.label)
  const brandLabel = (brand: string) => brandLabels.get(brand) || brand

  async function handleCopy() {
    if (!copyContainerRef.current || copyState === "copying") return
    setCopyState("copying")
    const previousFocus = document.activeElement as HTMLElement | null
    const textarea = document.createElement("textarea")
    const cell = (value: unknown) => String(value ?? "").replace(/[\t\r\n]+/g, " ")
    textarea.value = [
      ["Excel 行号", "商品编码", "品牌", "单据摘要", "错误原因"].join("\t"),
      ...validation.errors.map((row) => [row.row_number, row.product_code, brandLabel(row.brand), row.summary, row.reason].map(cell).join("\t")),
    ].join("\n")
    textarea.readOnly = true
    textarea.style.position = "fixed"
    textarea.style.opacity = "0"
    copyContainerRef.current.appendChild(textarea)
    try {
      setCopyState(await copyTextareaText(textarea) ? "copied" : "failed")
    } finally {
      textarea.remove()
      if (previousFocus?.isConnected) previousFocus.focus({ preventScroll: true })
    }
  }

  return (
    <Alert className="min-w-0 rounded-xl border-destructive/25 bg-destructive/[0.035] p-4 dark:bg-destructive/5">
      <div className="flex items-start gap-3">
        <span className="flex size-8 shrink-0 items-center justify-center rounded-lg bg-destructive/10 text-destructive">
          <CircleAlert className="size-4" aria-hidden="true" />
        </span>
        <div className="min-w-0 flex-1 pt-0.5">
          <AlertTitle className="mb-0 text-sm font-semibold leading-5 text-foreground">商品资料校验未通过</AlertTitle>
          <AlertDescription className="mt-1 text-xs leading-5 break-words">{message}</AlertDescription>
        </div>
      </div>
      <div ref={copyContainerRef} className="mt-3 min-w-0 space-y-3 sm:ml-11">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <p className="text-xs text-muted-foreground">完整错误清单 · 共 <span className="font-medium text-foreground tabular-nums">{validation.total}</span> 条</p>
          <Button type="button" variant="outline" size="sm" onClick={handleCopy} disabled={copyState === "copying"} className="h-8 gap-1.5 bg-background text-xs">
            {copyState === "copied" ? <Check aria-hidden="true" /> : <Copy aria-hidden="true" />}
            {copyState === "copied" ? "已复制全部错误" : copyState === "copying" ? "复制中…" : "复制全部错误"}
          </Button>
        </div>
        <div role="region" aria-label="商品资料错误明细" tabIndex={0} className="max-h-64 overflow-auto overscroll-contain rounded-lg border border-destructive/15 bg-background">
          <table className="w-full min-w-[620px] text-left text-xs leading-5">
            <thead className="sticky top-0 bg-muted text-muted-foreground">
              <tr>{["Excel 行号", "商品编码", "品牌", "单据摘要", "错误原因"].map((label) => <th key={label} scope="col" className="px-3 py-2 font-medium whitespace-nowrap">{label}</th>)}</tr>
            </thead>
            <tbody>
              {validation.errors.slice(start, start + PAGE_SIZE).map((row, index) => (
                <tr key={start + index} className="border-t border-border/60 align-top text-foreground">
                  <td className="px-3 py-2 tabular-nums whitespace-nowrap">{row.row_number ?? "—"}</td>
                  <td className="max-w-52 px-3 py-2 font-mono break-all select-all">{row.product_code || "（未填写）"}</td>
                  <td className="px-3 py-2 whitespace-nowrap">{brandLabel(row.brand)}</td>
                  <td className="min-w-28 max-w-48 px-3 py-2 break-words">{row.summary || "—"}</td>
                  <td className="min-w-48 px-3 py-2 break-words">{row.reason}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <div className="flex flex-wrap items-center justify-between gap-2 text-xs text-muted-foreground">
          <p role="status" aria-live="polite">{copyState === "failed" ? "复制失败，请选中清单内容手动复制。" : `第 ${start + 1}–${Math.min(start + PAGE_SIZE, validation.total)} 条，共 ${validation.total} 条`}</p>
          {pages > 1 && <div className="flex items-center gap-2">
            <Button type="button" variant="outline" size="icon" className="size-7" aria-label="上一页错误" disabled={currentPage === 1} onClick={() => setPage(currentPage - 1)}><ChevronLeft className="size-3.5" /></Button>
            <span className="tabular-nums">{currentPage} / {pages}</span>
            <Button type="button" variant="outline" size="icon" className="size-7" aria-label="下一页错误" disabled={currentPage === pages} onClick={() => setPage(currentPage + 1)}><ChevronRight className="size-3.5" /></Button>
          </div>}
        </div>
      </div>
    </Alert>
  )
}
