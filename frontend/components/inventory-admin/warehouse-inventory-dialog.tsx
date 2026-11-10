"use client"

import { useEffect, useRef, useState } from "react"
import { ArrowLeft, ChevronRight, Download, Eye, LoaderCircle, Search, X } from "lucide-react"

import { ApiError, downloadWarehouseEndingInventory, getWarehouseInventory, listWarehouseInventoryMovements, type WarehouseInventoryItem, type WarehouseInventoryMovementItem, type WarehouseInventoryMovementResponse, type WarehouseItem } from "@/lib/api"
import { Button } from "@/components/ui/button"
import { DateRangeControl } from "@/components/ui/date-range-control"
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Select } from "@/components/ui/select"
import { useCrossTabRefresh } from "@/lib/use-cross-tab-refresh"

const PAGE_SIZES = [20, 50, 100]

type SubmittedFilters = {
  date_start?: string
  date_end?: string
  product_code?: string
}

function getErrorMessage(error: unknown) {
  if (error instanceof ApiError) return error.message || `请求失败（${error.status}）`
  if (error instanceof Error) return error.message
  return "发生未知错误"
}

function defaultDateRange() {
  const now = new Date()
  const year = now.getFullYear()
  const month = String(now.getMonth() + 1).padStart(2, "0")
  const day = String(now.getDate()).padStart(2, "0")
  return {
    start: `${year}-${month}-01`,
    end: `${year}-${month}-${day}`,
  }
}

function rangeLabel(page: number, pageSize: number, total: number) {
  if (!total) return "0"
  return `${(page - 1) * pageSize + 1}-${Math.min(page * pageSize, total)}`
}

export function WarehouseInventoryDialog({
  warehouse,
  open,
  onOpenChange,
  initialDateRange,
  canExport = false,
}: {
  warehouse: WarehouseItem | null
  open: boolean
  onOpenChange: (open: boolean) => void
  initialDateRange?: { start: string; end: string }
  canExport?: boolean
}) {
  const [defaultRange] = useState(() => initialDateRange ?? defaultDateRange())
  const [dateStart, setDateStart] = useState(defaultRange.start)
  const [dateEnd, setDateEnd] = useState(defaultRange.end)
  const [productCode, setProductCode] = useState("")
  const [filters, setFilters] = useState<SubmittedFilters>(() => ({ date_start: defaultRange.start, date_end: defaultRange.end }))
  const [items, setItems] = useState<WarehouseInventoryItem[]>([])
  const [total, setTotal] = useState(0)
  const [totals, setTotals] = useState({ beginning_qty: "0", inbound_qty: "0", outbound_qty: "0", ending_qty: "0" })
  const [page, setPage] = useState(1)
  const [pageSize, setPageSize] = useState(PAGE_SIZES[0])
  const [endingOnly, setEndingOnly] = useState(false)
  const [displayMode, setDisplayMode] = useState<"goods" | "barcode">("goods")
  const barcodeMode = displayMode === "barcode"
  const [inventoryRevision, setInventoryRevision] = useState(0)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState("")
  const [exporting, setExporting] = useState(false)
  const [exportError, setExportError] = useState("")
  const [exportStatus, setExportStatus] = useState("")
  const exportController = useRef<AbortController | null>(null)
  const [selectedItem, setSelectedItem] = useState<WarehouseInventoryItem | null>(null)
  const [movementItems, setMovementItems] = useState<WarehouseInventoryMovementItem[]>([])
  const [movementTotal, setMovementTotal] = useState(0)
  const [movementTotals, setMovementTotals] = useState<WarehouseInventoryMovementResponse["totals"] | null>(null)
  const [movementPage, setMovementPage] = useState(1)
  const [movementLoading, setMovementLoading] = useState(false)
  const [movementError, setMovementError] = useState("")
  const warehouseId = warehouse?.id

  useEffect(() => () => { exportController.current?.abort() }, [open, warehouseId, filters, endingOnly, selectedItem, canExport, displayMode])

  useCrossTabRefresh(["inventory", "products", "reference-data"], () => setInventoryRevision((value) => value + 1), !open)

  useEffect(() => {
    if (!open || warehouseId === undefined) return
    const requestedWarehouseId = warehouseId
    const controller = new AbortController()
    let cancelled = false
    async function loadInventory() {
      setLoading(true)
      setError("")
      try {
        const response = await getWarehouseInventory(requestedWarehouseId, {
          ...filters,
          ...(barcodeMode ? { display_mode: "barcode" as const } : {}),
          ending_nonzero: endingOnly,
          page,
          pageSize,
        }, controller.signal)
        if (cancelled) return
        setItems(response.items)
        setTotal(response.total)
        setTotals(response.totals)
      } catch (loadError) {
        if (cancelled) return
        setItems([])
        setTotal(0)
        setTotals({ beginning_qty: "0", inbound_qty: "0", outbound_qty: "0", ending_qty: "0" })
        setError(getErrorMessage(loadError))
      } finally {
        if (!cancelled) setLoading(false)
      }
    }
    void loadInventory()
    return () => { cancelled = true; controller.abort() }
  }, [barcodeMode, endingOnly, filters, inventoryRevision, open, page, pageSize, warehouseId])

  useEffect(() => {
    if (!open || warehouseId === undefined || !selectedItem) return
    const requestedWarehouseId = warehouseId
    const controller = new AbortController()
    const inventoryItem = selectedItem
    let cancelled = false
    async function loadMovements() {
      setMovementLoading(true)
      setMovementError("")
      setMovementTotals(null)
      try {
        const response = await listWarehouseInventoryMovements(requestedWarehouseId, {
          ...filters,
          product_code: inventoryItem.product_code,
          product_name: inventoryItem.product_name,
          color_name: inventoryItem.color_name,
          color_spec: inventoryItem.color_spec,
          exact_match: true,
          ...(barcodeMode ? {
            display_mode: "barcode" as const,
            product_identity_id: inventoryItem.product_identity_id,
            inventory_size_key: inventoryItem.inventory_size_key,
            unallocated: inventoryItem.unallocated,
          } : {}),
          page: movementPage,
          pageSize: 50,
        }, controller.signal)
        if (cancelled) return
        setMovementItems(response.items)
        setMovementTotal(response.total)
        setMovementTotals(response.totals)
      } catch (loadError) {
        if (cancelled) return
        setMovementItems([])
        setMovementTotal(0)
        setMovementTotals(null)
        setMovementError(getErrorMessage(loadError))
      } finally {
        if (!cancelled) setMovementLoading(false)
      }
    }
    void loadMovements()
    return () => { cancelled = true; controller.abort() }
  }, [barcodeMode, filters, inventoryRevision, movementPage, open, selectedItem, warehouseId])

  const totalPages = Math.max(1, Math.ceil(total / pageSize))
  const movementPages = Math.max(1, Math.ceil(movementTotal / 50))

  const submitSearch = () => {
    setExportError("")
    setExportStatus("")
    setSelectedItem(null)
    setPage(1)
    setFilters({
      date_start: dateStart || undefined,
      date_end: dateEnd || undefined,
      product_code: productCode.trim() || undefined,
    })
  }

  const clearSearch = () => {
    setExportError("")
    setExportStatus("")
    setDateStart("")
    setDateEnd("")
    setProductCode("")
    setSelectedItem(null)
    setEndingOnly(false)
    setPage(1)
    setFilters({})
  }

  const openMovements = (item: WarehouseInventoryItem) => {
    setExportError("")
    setExportStatus("")
    setSelectedItem(item)
    setMovementPage(1)
    setMovementItems([])
    setMovementTotal(0)
    setMovementTotals(null)
  }

  const returnToInventory = () => {
    setSelectedItem(null)
    setInventoryRevision((value) => value + 1)
  }

  const showFilters = !selectedItem

  const exportEndingInventory = async () => {
    if (!open || !canExport || loading || error || !endingOnly || !total || warehouseId === undefined || exportController.current) return
    const controller = new AbortController()
    exportController.current = controller
    setExporting(true)
    setExportError("")
    setExportStatus("")
    try {
      await downloadWarehouseEndingInventory(warehouseId, { ...filters, ...(barcodeMode ? { display_mode: "barcode" as const } : {}) }, controller.signal)
      if (!controller.signal.aborted) setExportStatus("期末库存文件已生成，已开始下载")
    } catch (downloadError) {
      if (!controller.signal.aborted) setExportError(getErrorMessage(downloadError))
    } finally {
      if (exportController.current === controller) {
        exportController.current = null
        setExporting(false)
      }
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="flex max-h-[88vh] max-w-[min(96vw,1440px)] flex-col overflow-hidden">
        <DialogHeader>
          <div className="flex min-w-0 items-center justify-between gap-3 pr-8">
            <div className="min-w-0">
              <DialogTitle className="truncate">{selectedItem ? "库存明细" : endingOnly ? "期末库存商品" : "仓库库存"}</DialogTitle>
              <p className="mt-1 text-sm text-muted-foreground">{warehouse?.name || "-"}{selectedItem?.product_code ? ` · ${selectedItem.product_code}` : ""}</p>
              {selectedItem && barcodeMode && <p className="mt-1 text-xs text-muted-foreground break-all">商品编码：{selectedItem.barcode || "待维护"} · 尺码：{selectedItem.size_name || "未分配"}{selectedItem.barcode_issue ? ` · ${selectedItem.barcode_issue}` : ""}</p>}
            </div>
            {selectedItem && (
              <Button variant="outline" size="sm" className="shrink-0 cursor-pointer" onClick={returnToInventory}>
                <ArrowLeft className="size-4" />
                <span className="ml-1.5">返回汇总</span>
              </Button>
            )}
          </div>
        </DialogHeader>

        <div className="min-h-0 space-y-4 overflow-y-auto py-1 pr-1 [scrollbar-gutter:stable]">
          {showFilters && (
            <div className="rounded-lg border border-border bg-muted/20 p-3">
              <div className="flex flex-wrap items-end gap-3">
                <DateRangeControl label="期间" start={dateStart} end={dateEnd} onStartChange={setDateStart} onEndChange={setDateEnd} />
                <div className="space-y-1.5">
                  <Label className="text-xs text-muted-foreground">商品货号</Label>
                  <Input value={productCode} onChange={(event) => setProductCode(event.target.value)} onKeyDown={(event) => { if (event.key === "Enter") submitSearch() }} placeholder="输入商品货号" className="w-48" />
                </div>
                <Button size="sm" className="cursor-pointer" disabled={loading} onClick={submitSearch}>
                  <Search className="size-4" />
                  <span className="ml-1.5">查询</span>
                </Button>
                <Button variant="outline" size="sm" className="cursor-pointer" disabled={loading} onClick={clearSearch}>
                  <X className="size-4" />
                  <span className="ml-1.5">清空</span>
                </Button>
              </div>
            </div>
          )}

          {!selectedItem && (
            <>
              <div className="grid gap-2 sm:grid-cols-2 xl:grid-cols-4">
                {[
                  ["期初库存", totals.beginning_qty, "text-foreground"],
                  ["本期入库", totals.inbound_qty, "text-emerald-700"],
                  ["本期出库", totals.outbound_qty, "text-rose-700"],
                ].map(([label, value, className]) => (
                  <div key={label} className="rounded-lg border border-border bg-card px-3 py-2.5">
                    <p className="text-xs text-muted-foreground">{label}</p>
                    <p className={`mt-1 text-lg font-semibold tabular-nums ${className}`}>{loading || error ? "—" : value}</p>
                  </div>
                ))}
                <button
                  type="button"
                  aria-label="查看期末库存商品"
                  aria-pressed={endingOnly}
                  disabled={loading || Boolean(error)}
                  onClick={() => { setEndingOnly(true); setPage(1) }}
                  className={`cursor-pointer rounded-lg border px-3 py-2.5 text-left transition-colors outline-none hover:border-primary/50 hover:bg-muted/40 focus-visible:ring-2 focus-visible:ring-ring disabled:cursor-default disabled:opacity-60 ${endingOnly ? "border-primary/50 bg-primary/5" : "border-border bg-card"}`}
                >
                  <div className="flex items-center justify-between gap-2">
                    <p className="text-xs text-muted-foreground">期末库存</p>
                    <span className="flex items-center gap-0.5 text-xs text-primary">查看商品<ChevronRight className="size-3.5" /></span>
                  </div>
                  <p className="mt-1 text-lg font-semibold tabular-nums text-foreground">{loading || error ? "—" : totals.ending_qty}</p>
                </button>
              </div>
              {error && <div className="rounded-lg border border-destructive/30 bg-destructive/5 px-3 py-2 text-sm text-destructive">{error}</div>}
              {endingOnly && (
                <div className="flex flex-wrap items-center justify-between gap-2 rounded-lg border border-border bg-muted/20 px-3 py-2">
                  <div className="space-y-0.5">
                    <p className="text-sm font-medium">期末库存商品清单</p>
                    <p className="text-xs text-muted-foreground">截至 {filters.date_end || "当前"}，仅列期末非零商品（含负库存）；跨页期末合计与上方一致。</p>
                  </div>
                  <div className="flex flex-wrap items-center gap-2">
                    {canExport && <Button variant="outline" size="sm" disabled={loading || Boolean(error) || !total || exporting} onClick={() => void exportEndingInventory()} title="按已查询条件导出全部页的期末库存商品">
                      {exporting ? <LoaderCircle className="size-3.5 animate-spin" /> : <Download className="size-3.5" />}
                      {exporting ? "导出中…" : "导出 Excel"}
                    </Button>}
                    <Button variant="outline" size="sm" disabled={loading} onClick={() => { setEndingOnly(false); setPage(1); setExportError(""); setExportStatus("") }}>查看全部商品</Button>
                  </div>
                </div>
              )}
              {endingOnly && exportError && <p role="alert" className="rounded-lg border border-destructive/30 bg-destructive/5 px-3 py-2 text-sm text-destructive">导出失败：{exportError}</p>}
              {endingOnly && (exporting || exportStatus) && <p role="status" className="text-xs text-muted-foreground">{exporting ? "正在导出已查询条件下的全部期末库存商品…" : exportStatus}</p>}
              <div className="flex flex-wrap items-center justify-between gap-2 text-sm text-muted-foreground">
                <div className="flex flex-wrap items-center gap-3">
                  <div role="group" aria-label="库存展示方式" className="inline-flex gap-1 rounded-lg border border-border bg-muted/30 p-1">
                    {([["goods", "按货号"], ["barcode", "按编码"]] as const).map(([mode, label]) => (
                      <Button key={mode} type="button" size="sm" variant={displayMode === mode ? "default" : "ghost"} aria-pressed={displayMode === mode} disabled={loading} onClick={() => {
                        if (displayMode === mode) return
                        setDisplayMode(mode); setPage(1); setExportError(""); setExportStatus("")
                      }}>{label}</Button>
                    ))}
                  </div>
                  <span>共 {total} 条 · 当前 {rangeLabel(page, pageSize, total)} 条</span>
                </div>
                <div className="flex items-center gap-2"><span>每页</span><Select value={String(pageSize)} onChange={(event) => { setPageSize(Number(event.target.value)); setPage(1) }} className="w-24">{PAGE_SIZES.map((size) => <option key={size} value={String(size)}>{size} 条</option>)}</Select></div>
              </div>
              <div role="region" aria-label="仓库商品库存表" aria-busy={loading} className="h-[44vh] overflow-auto rounded-lg border border-border [scrollbar-gutter:stable]">
                <table className={`${barcodeMode ? "min-w-[1560px]" : "min-w-[980px]"} w-full table-fixed text-sm`}>
                  <colgroup>
                    {(barcodeMode ? [14, 12, 7, 17, 7, 6, 7, 6, 6, 6, 6, 6] : [18, 20, 14, 10, 10, 10, 10, 8]).map((width, index) => <col key={index} style={{ width: `${width}%` }} />)}
                  </colgroup>
                  <thead className="sticky top-0 z-20 [&_th]:border-b [&_th]:border-border [&_th]:bg-muted"><tr className="table-head-row">
                    {["商品货号", "商品名称", "颜色", ...(barcodeMode ? ["商品编码", "颜色条码", "尺码名称", "尺码条码"] : [])].map((label) => <th key={label} className="px-3 py-2.5 text-left font-medium">{label}</th>)}
                    {["期初库存", "本期入库", "本期出库", "期末库存"].map((label) => <th key={label} className="px-3 py-2.5 text-right font-medium">{label}</th>)}
                    <th className="px-3 py-2.5 text-center font-medium">明细</th>
                  </tr></thead>
                  <tbody className="divide-y divide-border">
                    {loading && <tr><td colSpan={barcodeMode ? 12 : 8} className="px-3 py-12 text-center text-muted-foreground"><LoaderCircle className="mr-2 inline size-4 animate-spin" />加载中...</td></tr>}
                    {!loading && !error && items.length === 0 && <tr><td colSpan={barcodeMode ? 12 : 8} className="px-3 py-12 text-center text-muted-foreground">{endingOnly ? "当前条件下没有期末库存非零的商品" : "该期间暂无影响此仓库库存的单据明细"}</td></tr>}
                    {!loading && items.map((item, index) => (
                      <tr key={`${item.product_code}-${item.color_name}-${item.color_spec}-${index}`} className="table-row">
                        <td className="px-3 py-2.5 font-mono text-xs"><span className="block truncate" title={item.product_code || ""}>{item.product_code || "-"}</span></td>
                        <td className="px-3 py-2.5"><span className="block truncate" title={item.product_name || ""}>{item.product_name || "-"}</span></td>
                        <td className="px-3 py-2.5"><span className="block truncate" title={item.color_name || item.color_spec || ""}>{item.color_name || item.color_spec || "-"}</span></td>
                        {barcodeMode && <>
                          <td className="px-3 py-2.5 font-mono text-xs"><span className="block truncate" title={item.barcode || ""}>{item.barcode || "-"}</span>{item.barcode_issue && <span className="mt-1 block text-xs text-amber-700 dark:text-amber-400">{item.barcode_issue}</span>}</td>
                          <td className="px-3 py-2.5 font-mono text-xs">{item.color_barcode || "-"}</td>
                          <td className="px-3 py-2.5">{item.size_name || "未分配"}</td>
                          <td className="px-3 py-2.5 font-mono text-xs">{item.size_barcode || "-"}</td>
                        </>}
                        <td className="px-3 py-2.5 text-right tabular-nums">{item.beginning_qty}</td>
                        <td className="px-3 py-2.5 text-right tabular-nums text-emerald-700">{item.inbound_qty}</td>
                        <td className="px-3 py-2.5 text-right tabular-nums text-rose-700">{item.outbound_qty}</td>
                        <td className="px-3 py-2.5 text-right font-medium tabular-nums">{item.ending_qty}</td>
                        <td className="px-3 py-2.5 text-center"><Button variant="ghost" size="icon-sm" className="cursor-pointer" title="查看库存明细" aria-label="查看库存明细" onClick={() => openMovements(item)}><Eye className="size-4" /></Button></td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              {totalPages > 1 && <div className="flex items-center justify-center gap-2"><Button size="sm" variant="outline" className="cursor-pointer" disabled={page <= 1 || loading} onClick={() => setPage((value) => Math.max(value - 1, 1))}>上一页</Button><span className="text-sm tabular-nums text-muted-foreground">{page} / {totalPages}</span><Button size="sm" variant="outline" className="cursor-pointer" disabled={page >= totalPages || loading} onClick={() => setPage((value) => Math.min(value + 1, totalPages))}>下一页</Button></div>}
            </>
          )}

          {selectedItem && (
            <>
              <div className="grid gap-2 sm:grid-cols-4">
                {[["期初", movementTotals?.beginning_qty], ["入库", movementTotals?.inbound_qty], ["出库", movementTotals?.outbound_qty], ["期末", movementTotals?.ending_qty]].map(([label, value]) => <div key={label} className="rounded-lg border border-border bg-muted/20 px-3 py-2"><span className="text-xs text-muted-foreground">{label}</span><span className="ml-2 font-semibold tabular-nums">{movementLoading ? "—" : value ?? "—"}</span></div>)}
              </div>
              {movementError && <div className="rounded-lg border border-destructive/30 bg-destructive/5 px-3 py-2 text-sm text-destructive">{movementError}</div>}
              <div className="flex items-center justify-between text-sm text-muted-foreground"><span>库存流水 {movementTotal} 条</span><span>{filters?.date_start || "最早"} 至 {filters?.date_end || "当前"}</span></div>
              <div role="region" aria-label="商品库存流水表" aria-busy={movementLoading} className="h-[50vh] overflow-auto rounded-lg border border-border [scrollbar-gutter:stable]">
                <table className="min-w-[1180px] w-full table-fixed text-sm">
                  <colgroup>
                    <col className="w-[10%]" /><col className="w-[17%]" /><col className="w-[10%]" /><col className="w-[14%]" /><col className="w-[8%]" />
                    <col className="w-[6%]" /><col className="w-[6%]" /><col className="w-[6%]" /><col className="w-[16%]" /><col className="w-[7%]" />
                  </colgroup>
                  <thead className="sticky top-0 z-20 [&_th]:border-b [&_th]:border-border [&_th]:bg-muted"><tr className="table-head-row"><th className="px-3 py-2.5 text-left font-medium">日期</th><th className="px-3 py-2.5 text-left font-medium">单据编号</th><th className="px-3 py-2.5 text-left font-medium">单据类型</th><th className="px-3 py-2.5 text-left font-medium">商品名称</th><th className="px-3 py-2.5 text-left font-medium">颜色</th><th className="px-3 py-2.5 text-right font-medium">入库</th><th className="px-3 py-2.5 text-right font-medium">出库</th><th className="px-3 py-2.5 text-right font-medium">变动</th><th className="px-3 py-2.5 text-left font-medium">摘要</th><th className="px-3 py-2.5 text-left font-medium">经手人</th></tr></thead>
                  <tbody className="divide-y divide-border">
                    {movementLoading && <tr><td colSpan={10} className="px-3 py-12 text-center text-muted-foreground"><LoaderCircle className="mr-2 inline size-4 animate-spin" />加载中...</td></tr>}
                    {!movementLoading && !movementError && movementItems.length === 0 && <tr><td colSpan={10} className="px-3 py-12 text-center text-muted-foreground">暂无库存流水</td></tr>}
                    {!movementLoading && movementItems.map((item) => (
                      <tr key={item.detail_id} className="table-row">
                        <td className="px-3 py-2.5 tabular-nums"><span className="block truncate" title={item.date || ""}>{item.date || "-"}</span></td>
                        <td className="px-3 py-2.5 font-mono text-xs"><span className="block truncate" title={item.document_number || String(item.document_id)}>{item.document_number || item.document_id}</span></td>
                        <td className="px-3 py-2.5"><span className="block truncate" title={item.document_type || ""}>{item.document_type || "-"}</span></td>
                        <td className="px-3 py-2.5"><span className="block truncate" title={item.product_name || ""}>{item.product_name || "-"}</span></td>
                        <td className="px-3 py-2.5"><span className="block truncate" title={item.color_name || item.color_spec || ""}>{item.color_name || item.color_spec || "-"}</span></td>
                        <td className="px-3 py-2.5 text-right tabular-nums text-emerald-700">{item.inbound_qty}</td>
                        <td className="px-3 py-2.5 text-right tabular-nums text-rose-700">{item.outbound_qty}</td>
                        <td className="px-3 py-2.5 text-right font-medium tabular-nums">{item.change_qty}</td>
                        <td className="px-3 py-2.5"><span className="block truncate" title={item.summary || ""}>{item.summary || "-"}</span></td>
                        <td className="px-3 py-2.5"><span className="block truncate" title={item.handler || ""}>{item.handler || "-"}</span></td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              {movementPages > 1 && <div className="flex items-center justify-center gap-2"><Button size="sm" variant="outline" className="cursor-pointer" disabled={movementPage <= 1 || movementLoading} onClick={() => setMovementPage((value) => Math.max(value - 1, 1))}>上一页</Button><span className="text-sm tabular-nums text-muted-foreground">{movementPage} / {movementPages}</span><Button size="sm" variant="outline" className="cursor-pointer" disabled={movementPage >= movementPages || movementLoading} onClick={() => setMovementPage((value) => Math.min(value + 1, movementPages))}>下一页</Button></div>}
            </>
          )}
        </div>
      </DialogContent>
    </Dialog>
  )
}
