"use client"

import { useCallback, useEffect, useRef, useState } from "react"
import { Plus, Download, Upload, Trash2, Edit, Search, X, RefreshCw } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { ConfirmDialog, MessageDialog } from "@/components/confirm-dialog"
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

const FIELD_LABELS: Record<string, string> = {
  date: "日期",
  supplier: "供应商",
  product_code: "商品编码",
  quantity: "数量",
  unit_price: "单价",
  warehouse: "仓库",
  document_type: "单据类型",
  summary: "摘要",
}

const DOCUMENT_TYPES = ["工厂进货单", "工厂退货单"]

const EMPTY_FORM: Record<string, string> = {
  date: "",
  supplier: "",
  product_code: "",
  quantity: "",
  unit_price: "",
  warehouse: "",
  document_type: "",
  summary: "",
}

function getErrorMessage(error: unknown) {
  if (error instanceof ApiError) return error.message || `请求失败（${error.status}）`
  if (error instanceof Error) return error.message
  return "发生未知错误"
}

export function InventoryPage() {
  const [searchDateStart, setSearchDateStart] = useState("")
  const [searchDateEnd, setSearchDateEnd] = useState("")
  const [searchSupplier, setSearchSupplier] = useState("")
  const [searchProductCode, setSearchProductCode] = useState("")
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

  const fileInputRef = useRef<HTMLInputElement>(null)
  const [isImporting, setIsImporting] = useState(false)

  useEffect(() => {
    async function loadOptions() {
      try {
        const [suppliersRes, warehousesRes] = await Promise.all([
          listSuppliers(),
          listWarehouses(),
        ])
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
          product_code: submittedFilters.product_code || undefined,
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
      product_code: item.product_code || "",
      quantity: item.quantity || "",
      unit_price: item.unit_price || "",
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
      setSelectedIds((prev) => {
        const next = new Set(prev)
        next.delete(deleteTarget.id)
        return next
      })
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
      for (const item of items) {
        allSelected ? next.delete(item.id) : next.add(item.id)
      }
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
      product_code: searchProductCode.trim(),
      warehouse: searchWarehouse,
      document_type: searchDocumentType,
    })
  }

  const clearSearch = () => {
    setSearchDateStart("")
    setSearchDateEnd("")
    setSearchSupplier("")
    setSearchProductCode("")
    setSearchWarehouse("")
    setSearchDocumentType("")
    setPage(1)
    setSubmittedFilters({})
  }

  const totalPages = Math.max(1, Math.ceil(total / pageSize))

  return (
    <div className="px-6 py-8">
      <div className="mx-auto flex w-full max-w-6xl flex-col gap-6">
        <div className="flex flex-col gap-3">
          <div className="flex flex-wrap items-center gap-2">
            <input
              type="date"
              value={searchDateStart}
              onChange={(e) => setSearchDateStart(e.target.value)}
              className="rounded-md border border-border bg-background px-3 py-2 text-sm w-36"
              title="开始日期"
            />
            <span className="text-muted-foreground text-sm">至</span>
            <input
              type="date"
              value={searchDateEnd}
              onChange={(e) => setSearchDateEnd(e.target.value)}
              className="rounded-md border border-border bg-background px-3 py-2 text-sm w-36"
              title="结束日期"
            />
            <select
              value={searchDocumentType}
              onChange={(e) => setSearchDocumentType(e.target.value)}
              className="rounded-md border border-border bg-background px-3 py-2 text-sm w-32"
            >
              <option value="">单据类型</option>
              {DOCUMENT_TYPES.map((dt) => (
                <option key={dt} value={dt}>{dt}</option>
              ))}
            </select>
            <select
              value={searchSupplier}
              onChange={(e) => setSearchSupplier(e.target.value)}
              className="rounded-md border border-border bg-background px-3 py-2 text-sm max-w-32"
            >
              <option value="">供应商</option>
              {supplierOptions.map((s) => (
                <option key={s.id} value={s.name}>{s.name}</option>
              ))}
            </select>
            <Input
              placeholder="商品编码"
              value={searchProductCode}
              onChange={(e) => setSearchProductCode(e.target.value)}
              onKeyDown={(e) => { if (e.key === "Enter") search() }}
              className="w-28"
            />
            <select
              value={searchWarehouse}
              onChange={(e) => setSearchWarehouse(e.target.value)}
              className="rounded-md border border-border bg-background px-3 py-2 text-sm max-w-32"
            >
              <option value="">仓库</option>
              {warehouseOptions.map((w) => (
                <option key={w.id} value={w.name}>{w.name}</option>
              ))}
            </select>
            <Button variant="outline" size="icon" onClick={search}>
              <Search className="h-4 w-4" />
            </Button>
            {Object.keys(submittedFilters).length > 0 && (
              <Button variant="ghost" size="icon" onClick={clearSearch}>
                <X className="h-4 w-4" />
              </Button>
            )}
          </div>
          <div className="flex items-center gap-2">
            <Button variant="outline" size="icon" onClick={() => setReloadToken((t) => t + 1)} disabled={isLoading}>
              <RefreshCw className={`h-4 w-4 ${isLoading ? "animate-spin" : ""}`} />
            </Button>
            <Button variant="outline" onClick={() => fileInputRef.current?.click()} disabled={isImporting}>
              <Upload className="h-4 w-4" />
              <span className="ml-2 hidden sm:inline">{isImporting ? "导入中..." : "导入Excel"}</span>
            </Button>
            <input ref={fileInputRef} type="file" accept=".xlsx,.xls,.xlsm" className="hidden" onChange={handleImport} />
            <Button variant="outline" onClick={handleExport} disabled={total === 0 || isLoading}>
              <Download className="h-4 w-4" />
              <span className="ml-2 hidden sm:inline">导出Excel</span>
            </Button>
            <Button onClick={openCreate}>
              <Plus className="h-4 w-4" />
              <span className="ml-2 hidden sm:inline">新增记录</span>
            </Button>
          </div>
        </div>

        {selectedIds.size > 0 && (
          <div className="flex items-center gap-2 rounded-lg border border-border bg-muted/30 px-4 py-2">
            <span className="text-sm text-muted-foreground">已选 {selectedIds.size} 条</span>
            <Button variant="destructive" size="sm" onClick={() => setBatchDeleteOpen(true)}>
              <Trash2 className="h-4 w-4" />
              <span className="ml-1">批量删除</span>
            </Button>
          </div>
        )}

        {/* Table */}
        <div className="overflow-x-auto rounded-xl border border-border bg-muted/20">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-border text-left text-muted-foreground">
                <th className="px-3 py-3 w-10">
                  <input
                    type="checkbox"
                    checked={items.length > 0 && items.every((item) => selectedIds.has(item.id))}
                    onChange={handleToggleSelectAll}
                    className="h-4 w-4"
                  />
                </th>
                <th className="px-3 py-3">日期</th>
                <th className="px-3 py-3">单据类型</th>
                <th className="px-3 py-3">供应商</th>
                <th className="px-3 py-3">商品编码</th>
                <th className="px-3 py-3 text-right">数量</th>
                <th className="px-3 py-3 text-right">单价</th>
                <th className="px-3 py-3">仓库</th>
                <th className="px-3 py-3">摘要</th>
                <th className="px-3 py-3 w-24">操作</th>
              </tr>
            </thead>
            <tbody>
              {isLoading && (
                <tr>
                  <td colSpan={10} className="px-3 py-8 text-center text-muted-foreground">
                    加载中...
                  </td>
                </tr>
              )}
              {!isLoading && error && (
                <tr>
                  <td colSpan={10} className="px-3 py-8 text-center text-destructive">{error}</td>
                </tr>
              )}
              {!isLoading && !error && items.length === 0 && (
                <tr>
                  <td colSpan={10} className="px-3 py-8 text-center text-muted-foreground">暂无数据</td>
                </tr>
              )}
              {!isLoading && !error && items.map((item) => (
                <tr key={item.id} className="border-b border-border hover:bg-muted/30">
                  <td className="px-3 py-2">
                    <input
                      type="checkbox"
                      checked={selectedIds.has(item.id)}
                      onChange={() => handleToggleSelect(item.id)}
                      className="h-4 w-4"
                    />
                  </td>
                  <td className="px-3 py-2 whitespace-nowrap">{item.date || "-"}</td>
                  <td className="px-3 py-2 whitespace-nowrap">{item.document_type || "-"}</td>
                  <td className="px-3 py-2">{item.supplier || "-"}</td>
                  <td className="px-3 py-2">{item.product_code || "-"}</td>
                  <td className="px-3 py-2 text-right">{item.quantity || "-"}</td>
                  <td className="px-3 py-2 text-right">{item.unit_price || "-"}</td>
                  <td className="px-3 py-2">{item.warehouse || "-"}</td>
                  <td className="px-3 py-2 max-w-40 truncate">{item.summary || "-"}</td>
                  <td className="px-3 py-2">
                    <div className="flex items-center gap-1">
                      <Button variant="ghost" size="icon" onClick={() => openEdit(item)}>
                        <Edit className="h-4 w-4" />
                      </Button>
                      <Button variant="ghost" size="icon" onClick={() => setDeleteTarget(item)}>
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
        <div className="flex items-center justify-between text-sm text-muted-foreground">
          <div className="flex items-center gap-2">
            <span>每页</span>
            <select
              value={pageSize}
              onChange={(e) => { setPageSize(Number(e.target.value)); setPage(1) }}
              className="rounded border border-border bg-background px-2 py-1"
            >
              {PAGE_SIZES.map((s) => (
                <option key={s} value={s}>{s}</option>
              ))}
            </select>
            <span>条，共 {total} 条</span>
          </div>
          <div className="flex items-center gap-1">
            <Button variant="outline" size="sm" onClick={() => setPage(1)} disabled={page <= 1}>首页</Button>
            <Button variant="outline" size="sm" onClick={() => setPage((p) => Math.max(1, p - 1))} disabled={page <= 1}>上一页</Button>
            <span className="px-2 tabular-nums">{page} / {totalPages}</span>
            <Button variant="outline" size="sm" onClick={() => setPage((p) => Math.min(totalPages, p + 1))} disabled={page >= totalPages}>下一页</Button>
            <Button variant="outline" size="sm" onClick={() => setPage(totalPages)} disabled={page >= totalPages}>末页</Button>
          </div>
        </div>
      </div>

      {/* Form Dialog */}
      {formOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50">
          <div className="bg-background rounded-xl border border-border shadow-xl w-full max-w-lg mx-4 max-h-[90vh] overflow-y-auto">
            <div className="px-6 py-4 border-b border-border font-semibold">
              {formMode === "create" ? "新增进销存记录" : "编辑进销存记录"}
            </div>
            <div className="px-6 py-4 space-y-4">
              {Object.entries(FIELD_LABELS).map(([key, label]) => {
                if (key === "document_type") {
                  return (
                    <div key={key} className="space-y-1">
                      <label className="text-sm font-medium">{label}</label>
                      <select
                        value={formData[key] || ""}
                        onChange={(e) => setFormData((prev) => ({ ...prev, [key]: e.target.value }))}
                        className="w-full rounded-md border border-border bg-background px-3 py-2 text-sm"
                      >
                        <option value="">请选择</option>
                        {DOCUMENT_TYPES.map((dt) => (
                          <option key={dt} value={dt}>{dt}</option>
                        ))}
                      </select>
                    </div>
                  )
                }
                if (key === "supplier") {
                  return (
                    <div key={key} className="space-y-1">
                      <label className="text-sm font-medium">{label}</label>
                      <select
                        value={formData[key] || ""}
                        onChange={(e) => setFormData((prev) => ({ ...prev, [key]: e.target.value }))}
                        className="w-full rounded-md border border-border bg-background px-3 py-2 text-sm"
                      >
                        <option value="">请选择</option>
                        {supplierOptions.map((s) => (
                          <option key={s.id} value={s.name}>{s.name}</option>
                        ))}
                      </select>
                    </div>
                  )
                }
                if (key === "warehouse") {
                  return (
                    <div key={key} className="space-y-1">
                      <label className="text-sm font-medium">{label}</label>
                      <select
                        value={formData[key] || ""}
                        onChange={(e) => setFormData((prev) => ({ ...prev, [key]: e.target.value }))}
                        className="w-full rounded-md border border-border bg-background px-3 py-2 text-sm"
                      >
                        <option value="">请选择</option>
                        {warehouseOptions.map((w) => (
                          <option key={w.id} value={w.name}>{w.name}</option>
                        ))}
                      </select>
                    </div>
                  )
                }
                if (key === "date") {
                  return (
                    <div key={key} className="space-y-1">
                      <label className="text-sm font-medium">{label}</label>
                      <input
                        type="date"
                        value={formData[key] || ""}
                        onChange={(e) => setFormData((prev) => ({ ...prev, [key]: e.target.value }))}
                        className="w-full rounded-md border border-border bg-background px-3 py-2 text-sm"
                      />
                    </div>
                  )
                }
                return (
                  <div key={key} className="space-y-1">
                    <label className="text-sm font-medium">{label}</label>
                    <Input
                      value={formData[key] || ""}
                      onChange={(e) => setFormData((prev) => ({ ...prev, [key]: e.target.value }))}
                      placeholder={label}
                    />
                  </div>
                )
              })}
            </div>
            <div className="px-6 py-4 border-t border-border flex justify-end gap-2">
              <Button variant="outline" onClick={() => setFormOpen(false)} disabled={isSaving}>取消</Button>
              <Button onClick={handleSave} disabled={isSaving}>
                {isSaving ? "保存中..." : "保存"}
              </Button>
            </div>
          </div>
        </div>
      )}

      <ConfirmDialog
        open={deleteTarget !== null}
        title="确认删除"
        description={`确定删除记录 ${deleteTarget?.product_code || deleteTarget?.id}？此操作不可撤销。`}
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
    </div>
  )
}
