"use client"

import { useCallback, useEffect, useState } from "react"
import { ChevronLeft, ChevronRight, Edit, Plus, Search, Trash2, X } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import { ConfirmDialog, MessageDialog } from "@/components/confirm-dialog"
import {
  listSuppliers,
  createSupplier,
  updateSupplier,
  deleteSupplier,
  ApiError,
  type SupplierItem,
} from "@/lib/api"

const PAGE_SIZE = 30
type PageToken = number | "start-ellipsis" | "end-ellipsis"

function getErrorMessage(error: unknown) {
  if (error instanceof ApiError) return error.message || `请求失败（${error.status}）`
  if (error instanceof Error) return error.message
  return "发生未知错误"
}

function formatNumber(value: number) {
  return new Intl.NumberFormat("zh-CN").format(value)
}

function getPageTokens(currentPage: number, totalPages: number): PageToken[] {
  if (totalPages <= 7) {
    return Array.from({ length: totalPages }, (_, index) => index + 1)
  }

  const start = Math.max(2, currentPage - 1)
  const end = Math.min(totalPages - 1, currentPage + 1)
  const tokens: PageToken[] = [1]

  if (start > 2) {
    tokens.push("start-ellipsis")
  } else {
    for (let page = 2; page < start; page += 1) tokens.push(page)
  }

  for (let page = start; page <= end; page += 1) {
    tokens.push(page)
  }

  if (end < totalPages - 1) {
    tokens.push("end-ellipsis")
  } else {
    for (let page = end + 1; page < totalPages; page += 1) tokens.push(page)
  }

  tokens.push(totalPages)
  return tokens
}

export default function SuppliersPage() {
  const [items, setItems] = useState<SupplierItem[]>([])
  const [total, setTotal] = useState(0)
  const [page, setPage] = useState(1)
  const [queryInput, setQueryInput] = useState("")
  const [query, setQuery] = useState("")
  const [isLoading, setIsLoading] = useState(true)

  const [formOpen, setFormOpen] = useState(false)
  const [formMode, setFormMode] = useState<"create" | "edit">("create")
  const [formData, setFormData] = useState({ name: "", factory_code: "", contact: "", address: "", notes: "" })
  const [editingId, setEditingId] = useState<number | null>(null)
  const [isSaving, setIsSaving] = useState(false)

  const [deleteTarget, setDeleteTarget] = useState<SupplierItem | null>(null)
  const [isDeleting, setIsDeleting] = useState(false)
  const [messageOpen, setMessageOpen] = useState(false)
  const [messageContent, setMessageContent] = useState({ title: "", description: "" })

  const load = useCallback(async () => {
    setIsLoading(true)
    try {
      const res = await listSuppliers({ page, pageSize: PAGE_SIZE, query })
      const nextTotalPages = Math.max(1, Math.ceil(res.total / PAGE_SIZE))
      if (page > nextTotalPages) {
        setPage(nextTotalPages)
        return
      }
      setItems(res.items)
      setTotal(res.total)
    } catch {
      setItems([])
      setTotal(0)
    } finally {
      setIsLoading(false)
    }
  }, [page, query])

  useEffect(() => {
    const timer = window.setTimeout(() => {
      void load()
    }, 0)
    return () => window.clearTimeout(timer)
  }, [load])

  const showMessage = (title: string, description: string) => {
    setMessageContent({ title, description })
    setMessageOpen(true)
  }

  const openCreate = () => {
    setFormMode("create")
    setFormData({ name: "", factory_code: "", contact: "", address: "", notes: "" })
    setEditingId(null)
    setFormOpen(true)
  }

  const openEdit = (item: SupplierItem) => {
    setFormMode("edit")
    setEditingId(item.id)
    setFormData({
      name: item.name,
      factory_code: item.factory_code || "",
      contact: item.contact || "",
      address: item.address || "",
      notes: item.notes || "",
    })
    setFormOpen(true)
  }

  const handleSave = async () => {
    if (!formData.name.trim()) {
      showMessage("保存失败", "供应商名称不能为空")
      return
    }
    setIsSaving(true)
    try {
      if (formMode === "create") {
        await createSupplier(formData)
      } else if (editingId !== null) {
        await updateSupplier(editingId, formData)
      }
      setFormOpen(false)
      if (formMode === "create" && page !== 1) {
        setPage(1)
      } else {
        await load()
      }
    } catch (e) {
      showMessage("保存失败", getErrorMessage(e))
    } finally {
      setIsSaving(false)
    }
  }

  const handleDelete = async () => {
    if (!deleteTarget) return
    setIsDeleting(true)
    try {
      await deleteSupplier(deleteTarget.id)
      setDeleteTarget(null)
      await load()
    } catch (e) {
      showMessage("删除失败", getErrorMessage(e))
    } finally {
      setIsDeleting(false)
    }
  }

  const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE))
  const start = total === 0 ? 0 : (page - 1) * PAGE_SIZE + 1
  const end = total === 0 ? 0 : Math.min(page * PAGE_SIZE, total)
  const pageTokens = getPageTokens(page, totalPages)

  return (
    <div className="app-page">
      <div className="app-content-narrow">
        <div className="page-header">
          <div className="flex items-center gap-3">
            <div>
              <h1 className="page-title">供应商管理</h1>
              <p className="page-subtitle">维护进销存单据中的供应商基础资料</p>
            </div>
            <span className="rounded-full border border-border bg-muted/45 px-3 py-1 text-sm text-muted-foreground tabular-nums">{formatNumber(total)} 个</span>
          </div>
          <Button size="sm" onClick={openCreate} className="cursor-pointer">
            <Plus className="h-4 w-4" />
            <span className="ml-1.5">新增供应商</span>
          </Button>
        </div>

        <form
          className="surface-panel mb-3 flex flex-col gap-2 p-3 sm:flex-row sm:items-center"
          onSubmit={(event) => {
            event.preventDefault()
            setPage(1)
            setQuery(queryInput.trim())
          }}
        >
          <div className="relative min-w-0 flex-1">
            <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
            <Input
              value={queryInput}
              onChange={(event) => setQueryInput(event.target.value)}
              placeholder="搜索名称或工厂代码"
              className="pl-9"
              aria-label="搜索供应商名称或工厂代码"
            />
          </div>
          <div className="flex items-center gap-2">
            <Button type="submit" disabled={isLoading}>
              查询
            </Button>
            {(queryInput || query) && (
              <Button
                type="button"
                variant="outline"
                size="icon"
                disabled={isLoading}
                onClick={() => {
                  setQueryInput("")
                  setQuery("")
                  setPage(1)
                }}
                aria-label="清空搜索"
              >
                <X className="h-4 w-4" />
              </Button>
            )}
          </div>
        </form>

        <div className="table-panel overflow-hidden">
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="table-head-row">
                  <th className="px-4 py-3 font-medium">名称</th>
                  <th className="px-4 py-3 font-medium">工厂代码</th>
                  <th className="px-4 py-3 font-medium">联系方式</th>
                  <th className="px-4 py-3 font-medium">地址</th>
                  <th className="px-4 py-3 font-medium">备注</th>
                  <th className="px-4 py-3 w-24 font-medium">操作</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-border">
                {isLoading && (
                  <tr>
                    <td colSpan={6} className="px-4 py-12 text-center text-muted-foreground">加载中...</td>
                  </tr>
                )}
                {!isLoading && items.length === 0 && (
                  <tr>
                    <td colSpan={6} className="px-4 py-12 text-center text-muted-foreground">
                      {query ? "暂无匹配供应商" : "暂无供应商数据"}
                    </td>
                  </tr>
                )}
                {!isLoading && items.map((item) => (
                  <tr key={item.id} className="table-row">
                    <td className="px-4 py-2.5 font-medium">{item.name}</td>
                    <td className="px-4 py-2.5 tabular-nums">{item.factory_code || "-"}</td>
                    <td className="px-4 py-2.5">{item.contact || "-"}</td>
                    <td className="px-4 py-2.5">{item.address || "-"}</td>
                    <td className="px-4 py-2.5 max-w-48 truncate">{item.notes || "-"}</td>
                    <td className="px-4 py-2.5">
                      <div className="flex items-center gap-0.5">
                        <Button variant="ghost" size="icon" onClick={() => openEdit(item)} className="cursor-pointer" aria-label={`编辑 ${item.name}`}>
                          <Edit className="h-4 w-4" />
                        </Button>
                        <Button variant="ghost" size="icon" onClick={() => setDeleteTarget(item)} className="cursor-pointer" aria-label={`删除 ${item.name}`}>
                          <Trash2 className="h-4 w-4 text-destructive" />
                        </Button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <div className="flex flex-wrap items-center justify-between gap-3 border-t border-border px-4 py-3">
            <p className="text-sm text-muted-foreground">
              共 {formatNumber(total)} 条 · 第 {formatNumber(start)}-{formatNumber(end)} 条 · 第 {page} / {totalPages} 页
            </p>
            <div className="flex items-center gap-1">
              <Button
                type="button"
                variant="outline"
                size="icon"
                disabled={page <= 1 || isLoading}
                onClick={() => setPage((current) => Math.max(1, current - 1))}
                aria-label="上一页"
              >
                <ChevronLeft className="h-4 w-4" />
              </Button>
              {pageTokens.map((token) => (
                typeof token === "number" ? (
                  <Button
                    key={token}
                    type="button"
                    variant={token === page ? "default" : "outline"}
                    size="icon"
                    disabled={isLoading}
                    onClick={() => setPage(token)}
                    aria-label={`第 ${token} 页`}
                  >
                    {token}
                  </Button>
                ) : (
                  <span key={token} className="flex h-9 w-9 items-center justify-center text-muted-foreground">...</span>
                )
              ))}
              <Button
                type="button"
                variant="outline"
                size="icon"
                disabled={page >= totalPages || isLoading}
                onClick={() => setPage((current) => Math.min(totalPages, current + 1))}
                aria-label="下一页"
              >
                <ChevronRight className="h-4 w-4" />
              </Button>
            </div>
          </div>
        </div>
      </div>

      <Dialog open={formOpen} onOpenChange={setFormOpen}>
        <DialogContent className="max-w-md">
          <DialogHeader>
            <DialogTitle>{formMode === "create" ? "新增供应商" : "编辑供应商"}</DialogTitle>
          </DialogHeader>
          <div className="space-y-4 py-2">
            <div className="space-y-1.5">
              <Label htmlFor="supplier-name">名称 *</Label>
              <Input id="supplier-name" value={formData.name} onChange={(e) => setFormData((prev) => ({ ...prev, name: e.target.value }))} placeholder="供应商名称" />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="supplier-factory-code">工厂代码</Label>
              <Input id="supplier-factory-code" value={formData.factory_code} onChange={(e) => setFormData((prev) => ({ ...prev, factory_code: e.target.value }))} placeholder="单位编号" />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="supplier-contact">联系方式</Label>
              <Input id="supplier-contact" value={formData.contact} onChange={(e) => setFormData((prev) => ({ ...prev, contact: e.target.value }))} placeholder="电话/联系人" />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="supplier-address">地址</Label>
              <Input id="supplier-address" value={formData.address} onChange={(e) => setFormData((prev) => ({ ...prev, address: e.target.value }))} placeholder="地址" />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="supplier-notes">备注</Label>
              <Input id="supplier-notes" value={formData.notes} onChange={(e) => setFormData((prev) => ({ ...prev, notes: e.target.value }))} placeholder="备注" />
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
        description={`确定删除供应商 ${deleteTarget?.name}？此操作不可撤销。`}
        confirmLabel={isDeleting ? "删除中..." : "删除"}
        variant="destructive"
        onConfirm={handleDelete}
        onCancel={() => setDeleteTarget(null)}
      />

      <MessageDialog open={messageOpen} title={messageContent.title} description={messageContent.description} onClose={() => setMessageOpen(false)} />
    </div>
  )
}
