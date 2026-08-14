"use client"

import { useCallback, useEffect, useState } from "react"
import { Edit, History, Plus, Trash2 } from "lucide-react"

import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog"
import { ConfirmDialog, MessageDialog } from "@/components/confirm-dialog"
import { OperationLogDialog } from "@/components/operation-log-dialog"
import { ApiError, createSupplierBrand, deleteSupplierBrand, listSupplierBrands, updateSupplierBrand, type SupplierBrandItem } from "@/lib/api"
import { useAuth } from "@/components/auth/auth-provider"

function getErrorMessage(error: unknown) {
  if (error instanceof ApiError) return error.message || `请求失败（${error.status}）`
  if (error instanceof Error) return error.message
  return "发生未知错误"
}

export default function SupplierBrandsPage() {
  const { hasPermission } = useAuth()
  const [items, setItems] = useState<SupplierBrandItem[]>([])
  const [isLoading, setIsLoading] = useState(true)
  const [formOpen, setFormOpen] = useState(false)
  const [editingItem, setEditingItem] = useState<SupplierBrandItem | null>(null)
  const [deleteTarget, setDeleteTarget] = useState<SupplierBrandItem | null>(null)
  const [name, setName] = useState("")
  const [isSaving, setIsSaving] = useState(false)
  const [isDeleting, setIsDeleting] = useState(false)
  const [operationLogOpen, setOperationLogOpen] = useState(false)
  const [messageOpen, setMessageOpen] = useState(false)
  const [messageContent, setMessageContent] = useState({ title: "", description: "" })
  const canManage = hasPermission("inventory.manage")

  const load = useCallback(async () => {
    setIsLoading(true)
    try {
      const response = await listSupplierBrands()
      setItems(response.items)
    } catch (error) {
      setItems([])
      setMessageContent({ title: "加载失败", description: getErrorMessage(error) })
      setMessageOpen(true)
    } finally {
      setIsLoading(false)
    }
  }, [])

  useEffect(() => {
    void load()
  }, [load])

  const showMessage = (title: string, description: string) => {
    setMessageContent({ title, description })
    setMessageOpen(true)
  }

  const openCreate = () => {
    setEditingItem(null)
    setName("")
    setFormOpen(true)
  }

  const openEdit = (item: SupplierBrandItem) => {
    setEditingItem(item)
    setName(item.name)
    setFormOpen(true)
  }

  const handleSave = async () => {
    const normalizedName = name.trim()
    if (!normalizedName) {
      showMessage("保存失败", "品牌名称不能为空")
      return
    }
    setIsSaving(true)
    try {
      if (editingItem) await updateSupplierBrand(editingItem.id, { name: normalizedName })
      else await createSupplierBrand({ name: normalizedName })
      setFormOpen(false)
      await load()
    } catch (error) {
      showMessage("保存失败", getErrorMessage(error))
    } finally {
      setIsSaving(false)
    }
  }

  const handleDelete = async () => {
    if (!deleteTarget) return
    setIsDeleting(true)
    try {
      await deleteSupplierBrand(deleteTarget.id)
      setDeleteTarget(null)
      await load()
    } catch (error) {
      showMessage("删除失败", getErrorMessage(error))
    } finally {
      setIsDeleting(false)
    }
  }

  return (
    <div className="app-page">
      <div className="app-content-narrow">
        <div className="page-header">
          <div className="flex items-center gap-3">
            <h1 className="page-title">品牌管理</h1>
            <span className="min-w-20 rounded-full border border-border bg-muted/45 px-3 py-1 text-center text-sm text-muted-foreground tabular-nums">{items.length} 个</span>
          </div>
          <div className="flex items-center gap-2">
            <Button size="sm" variant="outline" className="cursor-pointer" onClick={() => setOperationLogOpen(true)}>
              <History className="h-4 w-4" />
              <span className="ml-1.5">操作日志</span>
            </Button>
            {canManage && <Button size="sm" className="cursor-pointer" onClick={openCreate}><Plus className="h-4 w-4" /><span className="ml-1.5">新增品牌</span></Button>}
          </div>
        </div>

        <div className="table-panel overflow-hidden">
          <div className="overflow-x-auto">
            <table className="w-full min-w-[680px] table-fixed text-sm">
              <colgroup><col className="w-[80%]" /><col className="w-[20%]" /></colgroup>
              <thead><tr className="table-head-row"><th className="px-4 py-3 text-left font-medium">品牌名称</th><th className="sticky right-0 z-10 border-l border-border bg-muted px-4 py-3 text-center font-medium">操作</th></tr></thead>
              <tbody className="divide-y divide-border">
                {isLoading && <tr><td colSpan={2} className="px-4 py-12 text-center text-muted-foreground">加载中...</td></tr>}
                {!isLoading && !items.length && <tr><td colSpan={2} className="px-4 py-12 text-center text-muted-foreground">暂无品牌数据</td></tr>}
                {!isLoading && items.map((item) => <tr key={item.id} className="table-row"><td className="px-4 py-3 font-medium">{item.name}</td><td className="sticky right-0 z-10 border-l border-border bg-card px-4 py-2 text-center">{canManage && <div className="flex items-center justify-center gap-1"><Button variant="ghost" size="icon" className="cursor-pointer" title={`编辑 ${item.name}`} aria-label={`编辑 ${item.name}`} onClick={() => openEdit(item)}><Edit className="h-4 w-4" /></Button><Button variant="ghost" size="icon" className="cursor-pointer text-destructive hover:bg-destructive/10 hover:text-destructive" title={`删除 ${item.name}`} aria-label={`删除 ${item.name}`} onClick={() => setDeleteTarget(item)}><Trash2 className="h-4 w-4" /></Button></div>}</td></tr>)}
              </tbody>
            </table>
          </div>
        </div>
      </div>

      <Dialog open={formOpen} onOpenChange={setFormOpen}>
        <DialogContent className="max-w-md">
          <DialogHeader><DialogTitle>{editingItem ? "编辑品牌" : "新增品牌"}</DialogTitle></DialogHeader>
          <div className="py-2"><Label htmlFor="supplier-brand-name">品牌名称 *</Label><Input id="supplier-brand-name" className="mt-1.5" value={name} onChange={(event) => setName(event.target.value)} placeholder="品牌名称" autoFocus /></div>
          <DialogFooter><Button variant="outline" className="cursor-pointer" disabled={isSaving} onClick={() => setFormOpen(false)}>取消</Button><Button className="cursor-pointer" disabled={isSaving} onClick={handleSave}>{isSaving ? "保存中..." : "保存"}</Button></DialogFooter>
        </DialogContent>
      </Dialog>

      <MessageDialog open={messageOpen} title={messageContent.title} description={messageContent.description} onClose={() => setMessageOpen(false)} />
      <ConfirmDialog
        open={deleteTarget !== null}
        title="确认删除品牌"
        description={`确定删除品牌“${deleteTarget?.name || ""}”吗？品牌下仍有关联供应商或商品档案时不能删除。`}
        confirmLabel={isDeleting ? "删除中..." : "删除"}
        variant="destructive"
        onConfirm={() => void handleDelete()}
        onCancel={() => !isDeleting && setDeleteTarget(null)}
      />
      <OperationLogDialog module="supplier" title="品牌管理操作日志" open={operationLogOpen} onOpenChange={setOperationLogOpen} />
    </div>
  )
}
