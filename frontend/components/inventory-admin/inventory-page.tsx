"use client"

import { useCallback, useEffect, useRef, useState } from "react"
import { Plus, Download, Upload, Trash2, Edit, Search, X, RefreshCw, List } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Select } from "@/components/ui/select"
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import {
  Pagination,
  PaginationContent,
  PaginationEllipsis,
  PaginationItem,
  PaginationLink,
  PaginationNext,
  PaginationPrevious,
} from "@/components/ui/pagination"
import { Alert, AlertDescription } from "@/components/ui/alert"
import { ConfirmDialog, MessageDialog } from "@/components/confirm-dialog"
import { InventoryDetailPanel } from "@/components/inventory-admin/inventory-detail-panel"
import { EndingInventoryTab } from "@/components/inventory-admin/ending-inventory-tab"
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs"
import {
  listInventory,
  createInventoryRecord,
  updateInventoryRecord,
  deleteInventoryRecord,
  batchDeleteInventory,
  importInventory,
  exportInventory,
  listSuppliers,
  listWarehouses,
  ApiError,
  type InventoryRecord,
  type SupplierItem,
  type WarehouseItem,
} from "@/lib/api"

const PAGE_SIZES = [10, 50, 100]

const DOCUMENT_TYPES = ["工厂进货单", "工厂退货单", "报溢单"]

const EMPTY_FORM: Record<string, string> = {
  date: "",
  supplier: "",
  total_count: "",
  amount: "",
  warehouse: "",
  document_type: "",
  summary: "",
}

function getErrorMessage(error: unknown) {
  if (error instanceof ApiError) return error.message || `请求失败（${error.status}）`
  if (error instanceof Error) return error.message
  return "发生未知错误"
}

function buildPageRange(current: number, total: number): (number | "ellipsis")[] {
  if (total <= 7) return Array.from({ length: total }, (_, i) => i + 1)
  const pages: (number | "ellipsis")[] = [1]
  if (current > 3) pages.push("ellipsis")
  const start = Math.max(2, current - 1)
  const end = Math.min(total - 1, current + 1)
  for (let i = start; i <= end; i++) pages.push(i)
  if (current < total - 2) pages.push("ellipsis")
  pages.push(total)
  return pages
}

export function InventoryPage() {
  const [searchDateStart, setSearchDateStart] = useState("")
  const [searchDateEnd, setSearchDateEnd] = useState("")
  const [searchSupplier, setSearchSupplier] = useState("")
  const [searchWarehouse, setSearchWarehouse] = useState("")
  const [searchDocumentType, setSearchDocumentType] = useState("")
  const [submittedFilters, setSubmittedFilters] = useState<Record<string, string>>({})

  const [supplierOptions, setSupplierOptions] = useState<SupplierItem[]>([])
  const [warehouseOptions, setWarehouseOptions] = useState<WarehouseItem[]>([])
  const [page, setPage] = useState(1)
  const [pageSize, setPageSize] = useState(PAGE_SIZES[0])
  const [reloadToken, setReloadToken] = useState(0)
  const [items, setItems] = useState<InventoryRecord[]>([])
  const [total, setTotal] = useState(0)
  const [isLoading, setIsLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const [selectedIds, setSelectedIds] = useState<Set<number>>(() => new Set())
  const [deleteTarget, setDeleteTarget] = useState<InventoryRecord | null>(null)
  const [isDeleting, setIsDeleting] = useState(false)
  const [batchDeleteOpen, setBatchDeleteOpen] = useState(false)
  const [isBatchDeleting, setIsBatchDeleting] = useState(false)
  const [messageOpen, setMessageOpen] = useState(false)
  const [messageContent, setMessageContent] = useState({ title: "", description: "" })

  const [formOpen, setFormOpen] = useState(false)
  const [formMode, setFormMode] = useState<"create" | "edit">("create")
  const [formData, setFormData] = useState<Record<string, string>>({ ...EMPTY_FORM })
  const [editingId, setEditingId] = useState<number | null>(null)
  const [isSaving, setIsSaving] = useState(false)

  const [detailDocumentId, setDetailDocumentId] = useState<number | null>(null)
  const [activeTab, setActiveTab] = useState("records")

  const fileInputRef = useRef<HTMLInputElement>(null)
  const [isImporting, setIsImporting] = useState(false)

  useEffect(() => {
    async function loadOptions() {
      try {
        const [suppliersRes, warehousesRes] = await Promise.all([listSuppliers(), listWarehouses()])
        setSupplierOptions(suppliersRes.items)
        setWarehouseOptions(warehousesRes.items)
      } catch { /* ignore */ }
    }
    void loadOptions()
  }, [])

  useEffect(() => {
    let cancelled = false
    async function load() {
      setIsLoading(true)
      setError(null)
      try {
        const response = await listInventory({
          date_start: submittedFilters.date_start || undefined,
          date_end: submittedFilters.date_end || undefined,
          supplier: submittedFilters.supplier || undefined,
          warehouse: submittedFilters.warehouse || undefined,
          document_type: submittedFilters.document_type || undefined,
          page,
          pageSize,
        })
        if (cancelled) return
        setItems(response.items)
        setTotal(response.total)
      } catch (e) {
        if (cancelled) return
        setItems([])
        setTotal(0)
        setError(getErrorMessage(e))
      } finally {
        if (!cancelled) setIsLoading(false)
      }
    }
    void load()
    return () => { cancelled = true }
  }, [page, pageSize, reloadToken, submittedFilters])

  useEffect(() => { setSelectedIds(new Set()) }, [page, submittedFilters])

  const showMessage = useCallback((title: string, description: string) => {
    setMessageContent({ title, description })
    setMessageOpen(true)
  }, [])

  const openCreate = () => {
    setFormMode("create")
    setFormData({ ...EMPTY_FORM })
    setEditingId(null)
    setFormOpen(true)
  }

  const openEdit = (item: InventoryRecord) => {
    setFormMode("edit")
    setEditingId(item.id)
    setFormData({
      date: item.date || "",
      supplier: item.supplier || "",
      total_count: item.total_count || "",
      amount: item.amount || "",
      warehouse: item.warehouse || "",
      document_type: item.document_type || "",
      summary: item.summary || "",
    })
    setFormOpen(true)
  }

  const handleSave = async () => {
    setIsSaving(true)
    try {
      if (formMode === "create") {
        await createInventoryRecord(formData)
      } else if (editingId !== null) {
        await updateInventoryRecord(editingId, formData)
      }
      setFormOpen(false)
      setReloadToken((t) => t + 1)
    } catch (e) {
      showMessage("保存失败", getErrorMessage(e))
    } finally {
      setIsSaving(false)
    }
  }

  const handleDeleteConfirm = async () => {
    if (!deleteTarget) return
    setIsDeleting(true)
    try {
      await deleteInventoryRecord(deleteTarget.id)
      setSelectedIds((prev) => { const next = new Set(prev); next.delete(deleteTarget.id); return next })
      setReloadToken((t) => t + 1)
    } catch (e) {
      showMessage("删除失败", getErrorMessage(e))
    } finally {
      setIsDeleting(false)
      setDeleteTarget(null)
    }
  }

  const handleBatchDeleteConfirm = async () => {
    setIsBatchDeleting(true)
    try {
      await batchDeleteInventory(Array.from(selectedIds))
      setSelectedIds(new Set())
      setReloadToken((t) => t + 1)
    } catch (e) {
      showMessage("批量删除失败", getErrorMessage(e))
    } finally {
      setIsBatchDeleting(false)
      setBatchDeleteOpen(false)
    }
  }

  const handleToggleSelect = (id: number) => {
    setSelectedIds((prev) => {
      const next = new Set(prev)
      next.has(id) ? next.delete(id) : next.add(id)
      return next
    })
  }

  const handleToggleSelectAll = () => {
    setSelectedIds((prev) => {
      const allSelected = items.every((item) => prev.has(item.id))
      const next = new Set(prev)
      for (const item of items) allSelected ? next.delete(item.id) : next.add(item.id)
      return next
    })
  }

  const handleImport = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (!file) return
    setIsImporting(true)
    try {
      const result = await importInventory(file)
      showMessage("导入完成", result.message)
      setReloadToken((t) => t + 1)
    } catch (err) {
      showMessage("导入失败", getErrorMessage(err))
    } finally {
      setIsImporting(false)
      if (fileInputRef.current) fileInputRef.current.value = ""
    }
  }

  const handleExport = async () => {
    try {
      const response = await exportInventory()
      const blob = await response.blob()
      const url = URL.createObjectURL(blob)
      const a = document.createElement("a")
      a.href = url
      a.download = "进销存数据.xlsx"
      a.click()
      URL.revokeObjectURL(url)
    } catch (err) {
      showMessage("导出失败", getErrorMessage(err))
    }
  }

  const search = () => {
    setPage(1)
    setSubmittedFilters({
      date_start: searchDateStart,
      date_end: searchDateEnd,
      supplier: searchSupplier,
      warehouse: searchWarehouse,
      document_type: searchDocumentType,
    })
  }

  const clearSearch = () => {
    setSearchDateStart("")
    setSearchDateEnd("")
    setSearchSupplier("")
    setSearchWarehouse("")
    setSearchDocumentType("")
    setPage(1)
    setSubmittedFilters({})
  }

  const hasFilters = Object.keys(submittedFilters).length > 0
  const totalPages = Math.max(1, Math.ceil(total / pageSize))
  const allSelected = items.length > 0 && items.every((item) => selectedIds.has(item.id))
  const someSelected = items.some((item) => selectedIds.has(item.id))
  const pageRange = buildPageRange(page, totalPages)

  return (
    <div className="px-6 py-8">
      <div className="mx-auto flex w-full max-w-6xl flex-col gap-5">
        {/* Header */}
        <div className="flex items-center justify-between">
          <h1 className="text-xl font-semibold">进销存管理</h1>
          <div className="flex items-center gap-2">
            <Button variant="outline" size="sm" onClick={() => fileInputRef.current?.click()} disabled={isImporting} className="cursor-pointer">
              <Upload className="h-4 w-4" />
              <span className="ml-2 hidden sm:inline">{isImporting ? "导入中..." : "导入Excel"}</span>
            </Button>
            <input ref={fileInputRef} type="file" accept=".xlsx,.xls,.xlsm" className="hidden" onChange={handleImport} />
            <Button variant="outline" size="sm" onClick={handleExport} disabled={total === 0 || isLoading} className="cursor-pointer">
              <Download className="h-4 w-4" />
              <span className="ml-2 hidden sm:inline">导出Excel</span>
            </Button>
            <Button size="sm" onClick={openCreate} className="cursor-pointer">
              <Plus className="h-4 w-4" />
              <span className="ml-2 hidden sm:inline">新增记录</span>
            </Button>
          </div>
        </div>

        {/* Tabs */}
        <Tabs defaultValue="records" value={activeTab} onValueChange={setActiveTab}>
          <TabsList>
            <TabsTrigger value="records">进销存记录</TabsTrigger>
            <TabsTrigger value="ending">期末库存</TabsTrigger>
          </TabsList>

          {activeTab === "records" && (
            <>
              {/* Search Card */}
              <div className="rounded-xl border border-border bg-card p-4">
          <div className="flex flex-col gap-3">
            <div className="flex flex-wrap items-end gap-3">
              <div className="flex flex-col gap-1.5">
                <Label className="text-xs text-muted-foreground">日期范围</Label>
                <div className="flex items-center gap-2">
                  <input
                    type="date"
                    value={searchDateStart}
                    max={searchDateEnd || undefined}
                    onChange={(e) => setSearchDateStart(e.target.value)}
                    className="h-9 rounded-lg border border-input bg-background px-3 py-2 text-sm shadow-xs outline-none transition-colors focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/50"
                  />
                  <span className="text-xs text-muted-foreground">至</span>
                  <input
                    type="date"
                    value={searchDateEnd}
                    min={searchDateStart || undefined}
                    onChange={(e) => setSearchDateEnd(e.target.value)}
                    className="h-9 rounded-lg border border-input bg-background px-3 py-2 text-sm shadow-xs outline-none transition-colors focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/50"
                  />
                </div>
              </div>
              <div className="flex flex-col gap-1.5">
                <Label className="text-xs text-muted-foreground">单据类型</Label>
                <Select value={searchDocumentType} onChange={(e) => setSearchDocumentType(e.target.value)} className="w-36">
                  <option value="">全部</option>
                  {DOCUMENT_TYPES.map((dt) => (<option key={dt} value={dt}>{dt}</option>))}
                </Select>
              </div>
              <div className="flex flex-col gap-1.5">
                <Label className="text-xs text-muted-foreground">供应商</Label>
                <Select value={searchSupplier} onChange={(e) => setSearchSupplier(e.target.value)} className="w-36">
                  <option value="">全部</option>
                  {supplierOptions.map((s) => (<option key={s.id} value={s.name}>{s.name}</option>))}
                </Select>
              </div>
              <div className="flex flex-col gap-1.5">
                <Label className="text-xs text-muted-foreground">仓库</Label>
                <Select value={searchWarehouse} onChange={(e) => setSearchWarehouse(e.target.value)} className="w-36">
                  <option value="">全部</option>
                  {warehouseOptions.map((w) => (<option key={w.id} value={w.name}>{w.name}</option>))}
                </Select>
              </div>
              <div className="flex gap-2 pb-0.5">
                <Button size="sm" onClick={search} disabled={isLoading} className="cursor-pointer">
                  <Search className="h-4 w-4" />
                  <span className="ml-1.5">搜索</span>
                </Button>
                {hasFilters && (
                  <Button variant="outline" size="sm" onClick={clearSearch} className="cursor-pointer">
                    <X className="h-4 w-4" />
                    <span className="ml-1.5">清空</span>
                  </Button>
                )}
                <Button variant="outline" size="sm" onClick={() => setReloadToken((t) => t + 1)} disabled={isLoading} className="cursor-pointer">
                  <RefreshCw className={`h-4 w-4 ${isLoading ? "animate-spin" : ""}`} />
                </Button>
              </div>
            </div>
          </div>
        </div>

        {/* Selection & Summary Bar */}
        <div className="flex flex-col gap-2 text-sm text-muted-foreground sm:flex-row sm:items-center sm:justify-between">
          <div className="flex items-center gap-3">
            <input
              type="checkbox"
              checked={allSelected}
              ref={(el) => { if (el) el.indeterminate = !allSelected && someSelected }}
              onChange={handleToggleSelectAll}
              className="h-4 w-4 cursor-pointer rounded border border-input accent-primary"
            />
            <span>
              共 {total} 条{hasFilters ? " (已筛选)" : ""}
              {selectedIds.size > 0 && <span className="ml-2 font-medium text-foreground">已选 {selectedIds.size} 项</span>}
            </span>
          </div>
          <div className="flex items-center gap-2">
            {selectedIds.size > 0 && (
              <Button variant="outline" size="sm" className="text-destructive hover:text-destructive cursor-pointer" onClick={() => setBatchDeleteOpen(true)}>
                <Trash2 className="h-4 w-4" />
                <span className="ml-1.5">批量删除 ({selectedIds.size})</span>
              </Button>
            )}
            <span>每页</span>
            <Select value={String(pageSize)} onChange={(e) => { setPageSize(Number(e.target.value)); setPage(1) }} className="w-20">
              {PAGE_SIZES.map((s) => (<option key={s} value={String(s)}>{s} 条</option>))}
            </Select>
          </div>
        </div>

        {/* Error */}
        {error && !isLoading && (
          <Alert className="border-destructive/30">
            <AlertDescription>{error}</AlertDescription>
          </Alert>
        )}

        {/* Table */}
        <div className="overflow-x-auto rounded-xl border border-border bg-card">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-border bg-muted/40 text-left text-muted-foreground">
                <th className="px-4 py-3 w-10"></th>
                <th className="px-4 py-3 font-medium">入库单号</th>
                <th className="px-4 py-3 font-medium">日期</th>
                <th className="px-4 py-3 font-medium">单据类型</th>
                <th className="px-4 py-3 font-medium">供应商</th>
                <th className="px-4 py-3 text-right font-medium">总数</th>
                <th className="px-4 py-3 text-right font-medium">金额</th>
                <th className="px-4 py-3 font-medium">仓库</th>
                <th className="px-4 py-3 font-medium">摘要</th>
                <th className="px-4 py-3 w-28 font-medium">操作</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-border">
              {isLoading && (
                <tr>
                  <td colSpan={10} className="px-4 py-12 text-center text-muted-foreground">加载中...</td>
                </tr>
              )}
              {!isLoading && !error && items.length === 0 && (
                <tr>
                  <td colSpan={10} className="px-4 py-12 text-center text-muted-foreground">
                    {hasFilters ? "没有符合条件的数据" : "暂无数据"}
                  </td>
                </tr>
              )}
              {!isLoading && !error && items.map((item) => (
                <tr key={item.id} className="hover:bg-muted/30 transition-colors">
                  <td className="px-4 py-2.5">
                    <input
                      type="checkbox"
                      checked={selectedIds.has(item.id)}
                      onChange={() => handleToggleSelect(item.id)}
                      className="h-4 w-4 cursor-pointer rounded border border-input accent-primary"
                    />
                  </td>
                  <td className="px-4 py-2.5 font-mono text-xs tabular-nums">{item.id}</td>
                  <td className="px-4 py-2.5 whitespace-nowrap tabular-nums">{item.date || "-"}</td>
                  <td className="px-4 py-2.5 whitespace-nowrap">
                    {item.document_type ? (
                      <span className={`inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium ${
                        item.document_type === "工厂退货单" ? "bg-red-100 text-red-700"
                        : item.document_type === "报溢单" ? "bg-green-100 text-green-700"
                        : "bg-blue-100 text-blue-700"
                      }`}>
                        {item.document_type}
                      </span>
                    ) : "-"}
                  </td>
                  <td className="px-4 py-2.5">{item.supplier || "-"}</td>
                  <td className="px-4 py-2.5 text-right tabular-nums">{item.total_count || "-"}</td>
                  <td className="px-4 py-2.5 text-right tabular-nums">{item.amount || "-"}</td>
                  <td className="px-4 py-2.5">{item.warehouse || "-"}</td>
                  <td className="px-4 py-2.5 max-w-48 truncate">{item.summary || "-"}</td>
                  <td className="px-4 py-2.5">
                    <div className="flex items-center gap-0.5">
                      <Button variant="ghost" size="icon" onClick={() => setDetailDocumentId(item.id)} className="cursor-pointer" title="明细">
                        <List className="h-4 w-4" />
                      </Button>
                      <Button variant="ghost" size="icon" onClick={() => openEdit(item)} className="cursor-pointer">
                        <Edit className="h-4 w-4" />
                      </Button>
                      <Button variant="ghost" size="icon" onClick={() => setDeleteTarget(item)} className="cursor-pointer">
                        <Trash2 className="h-4 w-4 text-destructive" />
                      </Button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        {/* Pagination */}
        {totalPages > 1 && (
          <div className="flex items-center justify-center gap-4">
            <Pagination>
              <PaginationContent>
                <PaginationItem>
                  <PaginationPrevious
                    text="上一页"
                    onClick={() => setPage((p) => Math.max(1, p - 1))}
                    className={page <= 1 ? "pointer-events-none opacity-50" : "cursor-pointer"}
                  />
                </PaginationItem>
                {pageRange.map((p, i) =>
                  p === "ellipsis" ? (
                    <PaginationItem key={`ellipsis-${i}`}>
                      <PaginationEllipsis />
                    </PaginationItem>
                  ) : (
                    <PaginationItem key={p}>
                      <PaginationLink
                        isActive={p === page}
                        onClick={() => p !== page && setPage(p)}
                        className={p === page ? "cursor-default" : "cursor-pointer"}
                      >
                        {p}
                      </PaginationLink>
                    </PaginationItem>
                  )
                )}
                <PaginationItem>
                  <PaginationNext
                    text="下一页"
                    onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
                    className={page >= totalPages ? "pointer-events-none opacity-50" : "cursor-pointer"}
                  />
                </PaginationItem>
              </PaginationContent>
            </Pagination>
            <div className="flex items-center gap-1 text-sm text-muted-foreground whitespace-nowrap">
              <span>跳至</span>
              <input
                type="number"
                min={1}
                max={totalPages}
                className="h-8 w-16 rounded-md border border-input bg-background px-2 text-center text-sm outline-none focus-visible:border-ring focus-visible:ring-2 focus-visible:ring-ring/50"
                onKeyDown={(e) => {
                  if (e.key === "Enter") {
                    const target = parseInt((e.target as HTMLInputElement).value, 10)
                    if (target >= 1 && target <= totalPages) setPage(target)
                  }
                }}
              />
              <span>页</span>
            </div>
          </div>
        )}

        {/* Total summary footer */}
        <div className="text-center text-xs text-muted-foreground">
          共 {total} 条记录 · 第 {total === 0 ? 0 : (page - 1) * pageSize + 1}-{Math.min(page * pageSize, total)} 条
        </div>
            </>
          )}
          {activeTab === "ending" && <EndingInventoryTab />}
        </Tabs>
      </div>

      {/* Form Dialog */}
      <Dialog open={formOpen} onOpenChange={setFormOpen}>
        <DialogContent className="max-w-xl">
          <DialogHeader>
            <DialogTitle>{formMode === "create" ? "新增进销存记录" : "编辑进销存记录"}</DialogTitle>
          </DialogHeader>
          <div className="grid grid-cols-2 gap-4 py-2">
            {/* Date */}
            <div className="space-y-1.5">
              <Label htmlFor="form-date">日期</Label>
              <input
                id="form-date"
                type="date"
                value={formData.date || ""}
                onChange={(e) => setFormData((prev) => ({ ...prev, date: e.target.value }))}
                className="flex h-9 w-full rounded-lg border border-input bg-background px-3 py-2 text-sm shadow-xs outline-none transition-colors focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/50"
              />
            </div>
            {/* Document Type */}
            <div className="space-y-1.5">
              <Label htmlFor="form-doc-type">单据类型</Label>
              <Select
                value={formData.document_type || ""}
                onChange={(e) => setFormData((prev) => ({ ...prev, document_type: e.target.value }))}
              >
                <option value="">请选择</option>
                {DOCUMENT_TYPES.map((dt) => (<option key={dt} value={dt}>{dt}</option>))}
              </Select>
            </div>
            {/* Supplier */}
            <div className="space-y-1.5">
              <Label htmlFor="form-supplier">供应商</Label>
              <Select
                value={formData.supplier || ""}
                onChange={(e) => setFormData((prev) => ({ ...prev, supplier: e.target.value }))}
              >
                <option value="">请选择</option>
                {supplierOptions.map((s) => (<option key={s.id} value={s.name}>{s.name}</option>))}
              </Select>
            </div>
            {/* Warehouse */}
            <div className="space-y-1.5">
              <Label htmlFor="form-warehouse">仓库</Label>
              <Select
                value={formData.warehouse || ""}
                onChange={(e) => setFormData((prev) => ({ ...prev, warehouse: e.target.value }))}
              >
                <option value="">请选择</option>
                {warehouseOptions.map((w) => (<option key={w.id} value={w.name}>{w.name}</option>))}
              </Select>
            </div>
            {/* Total Count */}
            <div className="space-y-1.5">
              <Label htmlFor="form-total-count">总数</Label>
              <Input
                id="form-total-count"
                type="number"
                value={formData.total_count || ""}
                onChange={(e) => setFormData((prev) => ({ ...prev, total_count: e.target.value }))}
                placeholder="总数"
              />
            </div>
            {/* Amount */}
            <div className="space-y-1.5">
              <Label htmlFor="form-amount">金额</Label>
              <Input
                id="form-amount"
                type="number"
                step="0.01"
                value={formData.amount || ""}
                onChange={(e) => setFormData((prev) => ({ ...prev, amount: e.target.value }))}
                placeholder="金额"
              />
            </div>
            {/* Summary - full width */}
            <div className="col-span-2 space-y-1.5">
              <Label htmlFor="form-summary">摘要</Label>
              <Input
                id="form-summary"
                value={formData.summary || ""}
                onChange={(e) => setFormData((prev) => ({ ...prev, summary: e.target.value }))}
                placeholder="摘要"
              />
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setFormOpen(false)} disabled={isSaving} className="cursor-pointer">取消</Button>
            <Button onClick={handleSave} disabled={isSaving} className="cursor-pointer">{isSaving ? "保存中..." : "保存"}</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <ConfirmDialog
        open={deleteTarget !== null}
        title="确认删除"
        description={`确定删除记录 ${deleteTarget?.summary || deleteTarget?.id}？此操作不可撤销。`}
        confirmLabel={isDeleting ? "删除中..." : "删除"}
        variant="destructive"
        onConfirm={handleDeleteConfirm}
        onCancel={() => setDeleteTarget(null)}
      />

      <ConfirmDialog
        open={batchDeleteOpen}
        title="确认批量删除"
        description={`确定删除选中的 ${selectedIds.size} 条记录？此操作不可撤销。`}
        confirmLabel={isBatchDeleting ? "删除中..." : "删除"}
        variant="destructive"
        onConfirm={handleBatchDeleteConfirm}
        onCancel={() => setBatchDeleteOpen(false)}
      />

      <MessageDialog
        open={messageOpen}
        title={messageContent.title}
        description={messageContent.description}
        onClose={() => setMessageOpen(false)}
      />

      <InventoryDetailPanel
        documentId={detailDocumentId}
        onClose={() => setDetailDocumentId(null)}
        onTotalChanged={() => setReloadToken((t) => t + 1)}
      />
    </div>
  )
}
