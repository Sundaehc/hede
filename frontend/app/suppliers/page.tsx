"use client"

import { useCallback, useEffect, useState } from "react"
import { Plus, Trash2, Edit } from "lucide-react"
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

function getErrorMessage(error: unknown) {
  if (error instanceof ApiError) return error.message || `请求失败（${error.status}）`
  if (error instanceof Error) return error.message
  return "发生未知错误"
}

export default function SuppliersPage() {
  const [items, setItems] = useState<SupplierItem[]>([])
  const [isLoading, setIsLoading] = useState(true)

  const [formOpen, setFormOpen] = useState(false)
  const [formMode, setFormMode] = useState<"create" | "edit">("create")
  const [formData, setFormData] = useState({ name: "", contact: "", address: "", notes: "" })
  const [editingId, setEditingId] = useState<number | null>(null)
  const [isSaving, setIsSaving] = useState(false)

  const [deleteTarget, setDeleteTarget] = useState<SupplierItem | null>(null)
  const [isDeleting, setIsDeleting] = useState(false)
  const [messageOpen, setMessageOpen] = useState(false)
  const [messageContent, setMessageContent] = useState({ title: "", description: "" })

  const load = useCallback(async () => {
    setIsLoading(true)
    try {
      const res = await listSuppliers()
      setItems(res.items)
    } catch (e) {
      setItems([])
    } finally {
      setIsLoading(false)
    }
  }, [])

  useEffect(() => { void load() }, [load])

  const showMessage = (title: string, description: string) => {
    setMessageContent({ title, description })
    setMessageOpen(true)
  }

  const openCreate = () => {
    setFormMode("create")
    setFormData({ name: "", contact: "", address: "", notes: "" })
    setEditingId(null)
    setFormOpen(true)
  }

  const openEdit = (item: SupplierItem) => {
    setFormMode("edit")
    setEditingId(item.id)
    setFormData({ name: item.name, contact: item.contact || "", address: item.address || "", notes: item.notes || "" })
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
      await load()
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

  return (
    <div className="app-page">
      <div className="app-content-narrow">
        <div className="page-header">
          <div className="flex items-center gap-3">
            <div>
              <h1 className="page-title">供应商管理</h1>
              <p className="page-subtitle">维护进销存单据中的供应商基础资料</p>
            </div>
            <span className="rounded-full border border-border bg-muted/45 px-3 py-1 text-sm text-muted-foreground tabular-nums">{items.length} 个</span>
          </div>
          <Button size="sm" onClick={openCreate} className="cursor-pointer">
            <Plus className="h-4 w-4" />
            <span className="ml-1.5">新增供应商</span>
          </Button>
        </div>

        <div className="table-panel overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="table-head-row">
                <th className="px-4 py-3 font-medium">名称</th>
                <th className="px-4 py-3 font-medium">联系方式</th>
                <th className="px-4 py-3 font-medium">地址</th>
                <th className="px-4 py-3 font-medium">备注</th>
                <th className="px-4 py-3 w-24 font-medium">操作</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-border">
              {isLoading && (
                <tr>
                  <td colSpan={5} className="px-4 py-12 text-center text-muted-foreground">加载中...</td>
                </tr>
              )}
              {!isLoading && items.length === 0 && (
                <tr>
                  <td colSpan={5} className="px-4 py-12 text-center text-muted-foreground">暂无供应商数据</td>
                </tr>
              )}
              {items.map((item) => (
                <tr key={item.id} className="table-row">
                  <td className="px-4 py-2.5 font-medium">{item.name}</td>
                  <td className="px-4 py-2.5">{item.contact || "-"}</td>
                  <td className="px-4 py-2.5">{item.address || "-"}</td>
                  <td className="px-4 py-2.5 max-w-48 truncate">{item.notes || "-"}</td>
                  <td className="px-4 py-2.5">
                    <div className="flex items-center gap-0.5">
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
