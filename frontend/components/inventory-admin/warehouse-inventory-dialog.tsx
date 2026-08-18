"use client"

import { useEffect, useMemo, useState } from "react"
import { ArrowLeft, Eye, LoaderCircle, Search, X } from "lucide-react"

import { ApiError, getWarehouseInventory, listWarehouseInventoryMovements, type WarehouseInventoryItem, type WarehouseInventoryMovementItem, type WarehouseItem } from "@/lib/api"
import { Button } from "@/components/ui/button"
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Select } from "@/components/ui/select"

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
}: {
  warehouse: WarehouseItem | null
  open: boolean
  onOpenChange: (open: boolean) => void
}) {
  const defaultRange = useMemo(defaultDateRange, [])
  const [dateStart, setDateStart] = useState(defaultRange.start)
  const [dateEnd, setDateEnd] = useState(defaultRange.end)
  const [productCode, setProductCode] = useState("")
  const [filters, setFilters] = useState<SubmittedFilters | null>(null)
  const [items, setItems] = useState<WarehouseInventoryItem[]>([])
  const [total, setTotal] = useState(0)
  const [totals, setTotals] = useState({ beginning_qty: "0", inbound_qty: "0", outbound_qty: "0", ending_qty: "0" })
  const [page, setPage] = useState(1)
  const [pageSize, setPageSize] = useState(PAGE_SIZES[0])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState("")
  const [selectedItem, setSelectedItem] = useState<WarehouseInventoryItem | null>(null)
  const [movementItems, setMovementItems] = useState<WarehouseInventoryMovementItem[]>([])
  const [movementTotal, setMovementTotal] = useState(0)
  const [movementPage, setMovementPage] = useState(1)
  const [movementLoading, setMovementLoading] = useState(false)
  const [movementError, setMovementError] = useState("")

  useEffect(() => {
    if (!open || !warehouse) return
    const range = defaultDateRange()
    setDateStart(range.start)
    setDateEnd(range.end)
    setProductCode("")
    setFilters({ date_start: range.start, date_end: range.end })
    setPage(1)
    setSelectedItem(null)
    setError("")
  }, [open, warehouse?.id])

  useEffect(() => {
    if (!open || !warehouse || !filters || selectedItem) return
    const warehouseId = warehouse.id
    let cancelled = false
    async function loadInventory() {
      setLoading(true)
      setError("")
      try {
        const response = await getWarehouseInventory(warehouseId, {
          ...filters,
          page,
          pageSize,
        })
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
    return () => { cancelled = true }
  }, [filters, open, page, pageSize, selectedItem, warehouse])

  useEffect(() => {
    if (!open || !warehouse || !filters || !selectedItem) return
    const warehouseId = warehouse.id
    const inventoryItem = selectedItem
    let cancelled = false
    async function loadMovements() {
      setMovementLoading(true)
      setMovementError("")
      try {
        const response = await listWarehouseInventoryMovements(warehouseId, {
          ...filters,
          product_code: inventoryItem.product_code || undefined,
          color_name: inventoryItem.color_name || undefined,
          color_spec: inventoryItem.color_spec || undefined,
          page: movementPage,
          pageSize: 50,
        })
        if (cancelled) return
        setMovementItems(response.items)
        setMovementTotal(response.total)
      } catch (loadError) {
        if (cancelled) return
        setMovementItems([])
        setMovementTotal(0)
        setMovementError(getErrorMessage(loadError))
      } finally {
        if (!cancelled) setMovementLoading(false)
      }
    }
    void loadMovements()
    return () => { cancelled = true }
  }, [filters, movementPage, open, selectedItem, warehouse])

  const totalPages = Math.max(1, Math.ceil(total / pageSize))
  const movementPages = Math.max(1, Math.ceil(movementTotal / 50))

  const submitSearch = () => {
    setSelectedItem(null)
    setPage(1)
    setFilters({
      date_start: dateStart || undefined,
      date_end: dateEnd || undefined,
      product_code: productCode.trim() || undefined,
    })
  }

  const clearSearch = () => {
    setDateStart("")
    setDateEnd("")
    setProductCode("")
    setSelectedItem(null)
    setPage(1)
    setFilters({})
  }

  const openMovements = (item: WarehouseInventoryItem) => {
    setSelectedItem(item)
    setMovementPage(1)
    setMovementItems([])
    setMovementTotal(0)
  }

  const showFilters = !selectedItem

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="flex max-h-[88vh] max-w-[min(96vw,1440px)] flex-col overflow-hidden">
        <DialogHeader>
          <div className="flex min-w-0 items-center justify-between gap-3 pr-8">
            <div className="min-w-0">
              <DialogTitle className="truncate">{selectedItem ? "库存明细" : "仓库库存"}</DialogTitle>
              <p className="mt-1 text-sm text-muted-foreground">{warehouse?.name || "-"}{selectedItem?.product_code ? ` · ${selectedItem.product_code}` : ""}</p>
            </div>
            {selectedItem && (
              <Button variant="outline" size="sm" className="shrink-0 cursor-pointer" onClick={() => setSelectedItem(null)}>
                <ArrowLeft className="size-4" />
                <span className="ml-1.5">返回汇总</span>
              </Button>
            )}
          </div>
        </DialogHeader>

        <div className="min-h-0 space-y-4 overflow-y-auto py-1 pr-1">
          {showFilters && (
            <div className="rounded-lg border border-border bg-muted/20 p-3">
              <div className="flex flex-wrap items-end gap-3">
                <div className="space-y-1.5">
                  <Label className="text-xs text-muted-foreground">期间</Label>
                  <div className="grid grid-cols-[minmax(8.75rem,1fr)_auto_minmax(8.75rem,1fr)] items-center gap-2">
                    <input type="date" value={dateStart} max={dateEnd || undefined} onChange={(event) => setDateStart(event.target.value)} className="h-9 min-w-0 rounded-lg border border-input bg-card px-3 py-2 text-sm shadow-xs outline-none focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/35" />
                    <span className="text-xs text-muted-foreground">至</span>
                    <input type="date" value={dateEnd} min={dateStart || undefined} onChange={(event) => setDateEnd(event.target.value)} className="h-9 min-w-0 rounded-lg border border-input bg-card px-3 py-2 text-sm shadow-xs outline-none focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/35" />
                  </div>
                </div>
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
                  ["期末库存", totals.ending_qty, "text-foreground"],
                ].map(([label, value, className]) => (
                  <div key={label} className="rounded-lg border border-border bg-card px-3 py-2.5">
                    <p className="text-xs text-muted-foreground">{label}</p>
                    <p className={`mt-1 text-lg font-semibold tabular-nums ${className}`}>{value}</p>
                  </div>
                ))}
              </div>
              {error && <div className="rounded-lg border border-destructive/30 bg-destructive/5 px-3 py-2 text-sm text-destructive">{error}</div>}
              <div className="flex flex-wrap items-center justify-between gap-2 text-sm text-muted-foreground">
                <span>共 {total} 条 · 当前 {rangeLabel(page, pageSize, total)} 条</span>
                <div className="flex items-center gap-2"><span>每页</span><Select value={String(pageSize)} onChange={(event) => { setPageSize(Number(event.target.value)); setPage(1) }} className="w-24">{PAGE_SIZES.map((size) => <option key={size} value={String(size)}>{size} 条</option>)}</Select></div>
              </div>
              <div className="max-h-[44vh] overflow-auto rounded-lg border border-border">
                <table className="min-w-[980px] w-full text-sm">
                  <thead className="sticky top-0 z-20 [&_th]:border-b [&_th]:border-border [&_th]:bg-muted"><tr className="table-head-row"><th className="px-3 py-2.5 text-left font-medium">商品货号</th><th className="px-3 py-2.5 text-left font-medium">商品名称</th><th className="px-3 py-2.5 text-left font-medium">颜色</th><th className="px-3 py-2.5 text-right font-medium">期初库存</th><th className="px-3 py-2.5 text-right font-medium">本期入库</th><th className="px-3 py-2.5 text-right font-medium">本期出库</th><th className="px-3 py-2.5 text-right font-medium">期末库存</th><th className="w-18 px-3 py-2.5 text-center font-medium">明细</th></tr></thead>
                  <tbody className="divide-y divide-border">
                    {loading && <tr><td colSpan={8} className="px-3 py-12 text-center text-muted-foreground"><LoaderCircle className="mr-2 inline size-4 animate-spin" />加载中...</td></tr>}
                    {!loading && items.length === 0 && <tr><td colSpan={8} className="px-3 py-12 text-center text-muted-foreground">该期间暂无影响此仓库库存的单据明细</td></tr>}
                    {!loading && items.map((item, index) => <tr key={`${item.product_code}-${item.color_name}-${item.color_spec}-${index}`} className="table-row"><td className="px-3 py-2.5 font-mono text-xs">{item.product_code || "-"}</td><td className="px-3 py-2.5">{item.product_name || "-"}</td><td className="max-w-48 px-3 py-2.5"><span className="block truncate" title={item.color_name || item.color_spec || ""}>{item.color_name || item.color_spec || "-"}</span></td><td className="px-3 py-2.5 text-right tabular-nums">{item.beginning_qty}</td><td className="px-3 py-2.5 text-right tabular-nums text-emerald-700">{item.inbound_qty}</td><td className="px-3 py-2.5 text-right tabular-nums text-rose-700">{item.outbound_qty}</td><td className="px-3 py-2.5 text-right font-medium tabular-nums">{item.ending_qty}</td><td className="px-3 py-2.5 text-center"><Button variant="ghost" size="icon-sm" className="cursor-pointer" title="查看库存明细" aria-label="查看库存明细" onClick={() => openMovements(item)}><Eye className="size-4" /></Button></td></tr>)}
                  </tbody>
                </table>
              </div>
              {totalPages > 1 && <div className="flex items-center justify-center gap-2"><Button size="sm" variant="outline" className="cursor-pointer" disabled={page <= 1 || loading} onClick={() => setPage((value) => Math.max(value - 1, 1))}>上一页</Button><span className="text-sm tabular-nums text-muted-foreground">{page} / {totalPages}</span><Button size="sm" variant="outline" className="cursor-pointer" disabled={page >= totalPages || loading} onClick={() => setPage((value) => Math.min(value + 1, totalPages))}>下一页</Button></div>}
            </>
          )}

          {selectedItem && (
            <>
              <div className="grid gap-2 sm:grid-cols-4">
                {[["期初", selectedItem.beginning_qty], ["入库", selectedItem.inbound_qty], ["出库", selectedItem.outbound_qty], ["期末", selectedItem.ending_qty]].map(([label, value]) => <div key={label} className="rounded-lg border border-border bg-muted/20 px-3 py-2"><span className="text-xs text-muted-foreground">{label}</span><span className="ml-2 font-semibold tabular-nums">{value}</span></div>)}
              </div>
              {movementError && <div className="rounded-lg border border-destructive/30 bg-destructive/5 px-3 py-2 text-sm text-destructive">{movementError}</div>}
              <div className="flex items-center justify-between text-sm text-muted-foreground"><span>库存流水 {movementTotal} 条</span><span>{filters?.date_start || "最早"} 至 {filters?.date_end || "当前"}</span></div>
              <div className="max-h-[50vh] overflow-auto rounded-lg border border-border">
                <table className="min-w-[1180px] w-full text-sm"><thead className="sticky top-0 z-20 [&_th]:border-b [&_th]:border-border [&_th]:bg-muted"><tr className="table-head-row"><th className="px-3 py-2.5 text-left font-medium">日期</th><th className="px-3 py-2.5 text-left font-medium">单据编号</th><th className="px-3 py-2.5 text-left font-medium">单据类型</th><th className="px-3 py-2.5 text-left font-medium">商品名称</th><th className="px-3 py-2.5 text-left font-medium">颜色</th><th className="px-3 py-2.5 text-right font-medium">入库</th><th className="px-3 py-2.5 text-right font-medium">出库</th><th className="px-3 py-2.5 text-right font-medium">变动</th><th className="px-3 py-2.5 text-left font-medium">摘要</th><th className="px-3 py-2.5 text-left font-medium">经手人</th></tr></thead><tbody className="divide-y divide-border">{movementLoading && <tr><td colSpan={10} className="px-3 py-12 text-center text-muted-foreground"><LoaderCircle className="mr-2 inline size-4 animate-spin" />加载中...</td></tr>}{!movementLoading && movementItems.length === 0 && <tr><td colSpan={10} className="px-3 py-12 text-center text-muted-foreground">暂无库存流水</td></tr>}{!movementLoading && movementItems.map((item) => <tr key={item.detail_id} className="table-row"><td className="whitespace-nowrap px-3 py-2.5 tabular-nums">{item.date || "-"}</td><td className="whitespace-nowrap px-3 py-2.5 font-mono text-xs">{item.document_number || item.document_id}</td><td className="whitespace-nowrap px-3 py-2.5">{item.document_type || "-"}</td><td className="px-3 py-2.5">{item.product_name || "-"}</td><td className="max-w-40 px-3 py-2.5"><span className="block truncate" title={item.color_name || item.color_spec || ""}>{item.color_name || item.color_spec || "-"}</span></td><td className="px-3 py-2.5 text-right tabular-nums text-emerald-700">{item.inbound_qty}</td><td className="px-3 py-2.5 text-right tabular-nums text-rose-700">{item.outbound_qty}</td><td className="px-3 py-2.5 text-right font-medium tabular-nums">{item.change_qty}</td><td className="max-w-56 px-3 py-2.5"><span className="block truncate" title={item.summary || ""}>{item.summary || "-"}</span></td><td className="px-3 py-2.5">{item.handler || "-"}</td></tr>)}</tbody></table>
              </div>
              {movementPages > 1 && <div className="flex items-center justify-center gap-2"><Button size="sm" variant="outline" className="cursor-pointer" disabled={movementPage <= 1 || movementLoading} onClick={() => setMovementPage((value) => Math.max(value - 1, 1))}>上一页</Button><span className="text-sm tabular-nums text-muted-foreground">{movementPage} / {movementPages}</span><Button size="sm" variant="outline" className="cursor-pointer" disabled={movementPage >= movementPages || movementLoading} onClick={() => setMovementPage((value) => Math.min(value + 1, movementPages))}>下一页</Button></div>}
            </>
          )}
        </div>
      </DialogContent>
    </Dialog>
  )
}
