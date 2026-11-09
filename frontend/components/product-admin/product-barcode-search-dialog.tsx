"use client"

import { useEffect, useRef, useState } from "react"
import { Check, Copy, Download, LoaderCircle, Search, X } from "lucide-react"

import { Button } from "@/components/ui/button"
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "@/components/ui/dialog"
import { Label } from "@/components/ui/label"
import { downloadProductBarcodes, listProductBarcodes, type ProductBarcodeResponse } from "@/lib/api"
import type { ProductArchiveBrand } from "@/lib/brands"
import { useCrossTabRefresh } from "@/lib/use-cross-tab-refresh"

const PAGE_SIZE = 50

export function ProductBarcodeSearchDialog({
  brand,
  brands,
  initialQuery = "",
  canExport = false,
  onClose,
}: {
  brand: string
  brands: ProductArchiveBrand[]
  initialQuery?: string
  canExport?: boolean
  onClose: () => void
}) {
  const [query, setQuery] = useState(initialQuery)
  const [submittedQuery, setSubmittedQuery] = useState(initialQuery.trim())
  const [page, setPage] = useState(1)
  const [reload, setReload] = useState(0)
  const [data, setData] = useState<ProductBarcodeResponse | null>(null)
  const [loading, setLoading] = useState(Boolean(initialQuery.trim()))
  const [error, setError] = useState("")
  const [copyStatus, setCopyStatus] = useState("")
  const [copiedKey, setCopiedKey] = useState("")
  const [exporting, setExporting] = useState(false)
  const [exportError, setExportError] = useState("")
  const [exportStatus, setExportStatus] = useState("")
  const exportController = useRef<AbortController | null>(null)
  const brandLabel = brands.find((item) => item.key === brand)?.label || brand
  const totalPages = Math.max(1, Math.ceil((data?.total ?? 0) / PAGE_SIZE))

  useCrossTabRefresh(["products", "reference-data"], () => setReload((value) => value + 1), exporting)

  useEffect(() => () => { exportController.current?.abort() }, [brand, submittedQuery])

  useEffect(() => {
    if (!submittedQuery) return
    const controller = new AbortController()
    async function load() {
      setLoading(true)
      setError("")
      setData(null)
      setCopiedKey("")
      setCopyStatus("")
      setExportError("")
      setExportStatus("")
      try {
        const result = await listProductBarcodes({ brand, query: submittedQuery, page, pageSize: PAGE_SIZE }, controller.signal)
        if (!controller.signal.aborted) setData(result)
      } catch (error) {
        if (!controller.signal.aborted) setError(error instanceof Error ? error.message : "条码查询失败，请重试")
      } finally {
        if (!controller.signal.aborted) setLoading(false)
      }
    }
    void load()
    return () => controller.abort()
  }, [brand, submittedQuery, page, reload])

  const exportResults = async () => {
    if (!canExport || loading || !data?.total || exportController.current) return
    const controller = new AbortController()
    exportController.current = controller
    setExporting(true)
    setExportError("")
    setExportStatus("")
    try {
      await downloadProductBarcodes({ brand, query: submittedQuery }, controller.signal)
      if (!controller.signal.aborted) setExportStatus("已导出当前查询的全部条码结果")
    } catch (error) {
      if (!controller.signal.aborted) setExportError(error instanceof Error ? error.message : "导出失败，请重试")
    } finally {
      if (exportController.current === controller) {
        exportController.current = null
        setExporting(false)
      }
    }
  }

  const copyBarcode = async (barcode: string, key: string) => {
    try {
      await navigator.clipboard.writeText(barcode)
      setCopiedKey(key)
      setCopyStatus("已复制条码 " + barcode)
    } catch {
      setCopyStatus("复制失败，请选中完整条码手动复制。")
    }
  }

  return (
    <Dialog open onOpenChange={(open) => { if (!open) onClose() }}>
      <DialogContent className="flex max-h-[90svh] w-[calc(100%-1.5rem)] max-w-5xl flex-col gap-0 overflow-hidden p-0">
        <DialogHeader className="shrink-0 border-b border-border px-4 py-4 sm:px-5">
          <div className="flex items-start justify-between gap-3">
            <div className="space-y-1.5">
              <DialogTitle>条码搜索</DialogTitle>
              <DialogDescription className="text-xs leading-5">
                在{brand === "all" ? "全部品牌" : brandLabel}中按货号或原始货号搜索，按商品档案的条码构成逻辑和尺码条码展开。
              </DialogDescription>
            </div>
            <Button type="button" variant="ghost" size="icon-sm" aria-label="关闭条码搜索" onClick={onClose} className="shrink-0">
              <X className="size-4" />
            </Button>
          </div>
        </DialogHeader>
        <form
          className="flex shrink-0 flex-col gap-2 border-b border-border bg-muted/20 px-4 py-3 sm:flex-row sm:items-end sm:px-5"
          onSubmit={(event) => {
            event.preventDefault()
            if (!query.trim() || exporting) return
            setSubmittedQuery(query.trim())
            setPage(1)
            setReload((value) => value + 1)
          }}
        >
          <div className="min-w-0 flex-1 space-y-1.5">
            <Label htmlFor="product-barcode-query" className="text-xs">货号 / 原始货号</Label>
            <textarea
              id="product-barcode-query"
              autoFocus
              rows={1}
              value={query}
              maxLength={2000}
              placeholder="输入货号，多个用逗号或换行分隔"
              onChange={(event) => setQuery(event.target.value)}
              onKeyDown={(event) => {
                if (event.key === "Enter" && !event.shiftKey && !event.nativeEvent.isComposing) {
                  event.preventDefault()
                  event.currentTarget.form?.requestSubmit()
                }
              }}
              className="block min-h-9 w-full min-w-0 resize-y rounded-md border border-input bg-background px-3 py-2 text-sm outline-none placeholder:text-muted-foreground focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/35"
            />
          </div>
          <div className="flex shrink-0 gap-2">
            <Button type="submit" size="sm" disabled={!query.trim() || loading || exporting} className="h-9 flex-1 gap-1.5 sm:flex-none">
              {loading ? <LoaderCircle className="size-3.5 animate-spin" /> : <Search className="size-3.5" />}
              {loading ? "查询中…" : "查询条码"}
            </Button>
            {canExport && <Button type="button" variant="outline" size="sm" disabled={loading || !data?.total || exporting} onClick={() => void exportResults()} title="导出当前已查询条件下的全部结果" className="h-9 flex-1 gap-1.5 sm:flex-none">
              {exporting ? <LoaderCircle className="size-3.5 animate-spin" /> : <Download className="size-3.5" />}
              {exporting ? "导出中…" : "导出 Excel"}
            </Button>}
          </div>
        </form>
        {exportError && <p role="alert" className="shrink-0 border-b border-border bg-destructive/5 px-4 py-2 text-xs text-destructive sm:px-5">{exportError}</p>}
        <div className="min-h-0 overflow-auto" aria-busy={loading}>
          {error ? (
            <div role="alert" className="space-y-3 px-5 py-8 text-sm">
              <p className="text-destructive">{error}</p>
              <Button type="button" variant="outline" size="sm" onClick={() => setReload((value) => value + 1)}>重新查询</Button>
            </div>
          ) : loading ? (
            <p role="status" className="px-5 py-14 text-center text-sm text-muted-foreground">正在查询商品条码…</p>
          ) : !data ? (
            <p className="px-5 py-14 text-center text-sm text-muted-foreground">输入货号，查看各尺码的完整条码</p>
          ) : data.total === 0 ? (
            <p className="px-5 py-14 text-center text-sm text-muted-foreground">未找到匹配的商品，请检查货号或切换品牌后重试。</p>
          ) : (
            <table className="w-full min-w-[820px] text-sm" aria-label="商品条码查询结果">
              <thead className="sticky top-0 z-10 bg-background">
                <tr className="table-head-row text-xs">
                  {["品牌", "货号 / 条码构成逻辑", "品名", "颜色", "尺码", "完整条码", "操作"].map((label) => <th key={label} className="px-3 py-2.5 text-left font-medium whitespace-nowrap">{label}</th>)}
                </tr>
              </thead>
              <tbody className="divide-y divide-border">
                {data.items.map((item, index) => {
                  const key = `${item.brand}:${item.id}:${index}`
                  return (
                    <tr key={key} className="table-row align-top">
                      <td className="px-3 py-3 text-xs whitespace-nowrap">{brands.find((option) => option.key === item.brand)?.label || item.brand}</td>
                      <td className="px-3 py-3">
                        <p className="font-medium whitespace-nowrap">{item.sku || item.original_sku || "—"}</p>
                        <p className="mt-1 text-[11px] whitespace-nowrap text-muted-foreground">{item.barcode_build_rule || "未设置构成逻辑"}</p>
                      </td>
                      <td className="max-w-40 px-3 py-3 text-xs">{item.product_name || "—"}</td>
                      <td className="px-3 py-3 text-xs whitespace-nowrap">{[item.color, item.color_code].filter(Boolean).join(" · ") || "—"}</td>
                      <td className="px-3 py-3 whitespace-nowrap">{item.size_name || "—"}</td>
                      <td className="px-3 py-3">
                        {item.barcode ? <span className="font-mono text-sm whitespace-nowrap select-all">{item.barcode}</span> : <span className="text-xs text-amber-700 dark:text-amber-400">{item.issue || "无法生成条码"}</span>}
                      </td>
                      <td className="px-3 py-2">
                        {item.barcode && <Button type="button" variant="ghost" size="icon-sm" aria-label={`复制条码 ${item.barcode}`} onClick={() => void copyBarcode(item.barcode!, key)}>
                          {copiedKey === key ? <Check className="size-3.5 text-emerald-600" /> : <Copy className="size-3.5" />}
                        </Button>}
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          )}
        </div>
        <div className="flex shrink-0 flex-wrap items-center justify-between gap-2 border-t border-border px-4 py-3 text-xs text-muted-foreground sm:px-5">
          <span role="status" aria-live="polite">{exporting ? "正在导出当前查询的全部结果…" : exportStatus || copyStatus || (data ? `共 ${data.total} 条结果 · 每页 ${PAGE_SIZE} 条` : "完整条码使用尺码组中的条码值生成")}</span>
          <div className="flex items-center gap-2">
            <Button type="button" variant="outline" size="sm" className="h-8" disabled={loading || page <= 1} onClick={() => setPage((value) => value - 1)}>上一页</Button>
            <span className="tabular-nums">{page} / {totalPages}</span>
            <Button type="button" variant="outline" size="sm" className="h-8" disabled={loading || !data || page >= totalPages} onClick={() => setPage((value) => value + 1)}>下一页</Button>
          </div>
        </div>
      </DialogContent>
    </Dialog>
  )
}
