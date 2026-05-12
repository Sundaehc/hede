"use client"

import { useCallback, useEffect, useState } from "react"
import { Plus, Trash2, Edit } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { ConfirmDialog, MessageDialog } from "@/components/confirm-dialog"
import {
  listWarehouses,
  createWarehouse,
  updateWarehouse,
  deleteWarehouse,
  ApiError,
  type WarehouseItem,
} from "@/lib/api"

function getErrorMessage(error: unknown) {
  if (error instanceof ApiError) return error.message || `请求失败（${error.status}）`
  if (error instanceof Error) return error.message
  return "发生未知错误"
}

export default function WarehousesPage() {
  const [items, setItems] = useState<WarehouseItem[]>([])
  const [isLoading, setIsLoading] = useState(true)

  const [formOpen, setFormOpen] = useState(false)
  const [formMode, setFormMode] = useState<"create" | "edit">("create")
  const [formData, setFormData] = useState({ name: "", address: "", notes: "" })
  const [editingId, setEditingId] = useState<number | null>(null)
  const [isSaving, setIsSaving] = useState(false)

  const [deleteTarget, setDeleteTarget] = useState<WarehouseItem | null>(null)
  const [isDeleting, setIsDeleting] = useState(false)
  const [messageOpen, setMessageOpen] = useState(false)
  const [messageContent, setMessageContent] = useState({ title: "", description: "" })

  const load = useCallback(async () => {
    setIsLoading(true)
    try {
      const res = await listWarehouses()
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
    setFormData({ name: "", address: "", notes: "" })
    setEditingId(null)
    setFormOpen(true)
  }

  const openEdit = (item: WarehouseItem) => {
    setFormMode("edit")
    setEditingId(item.id)
    setFormData({ name: item.name, address: item.address || "", notes: item.notes || "" })
    setFormOpen(true)
  }

  const handleSave = async () => {
    if (!formData.name.trim()) {
      showMessage("保存失败", "仓库名称不能为空")
      return
    }
    setIsSaving(true)
    try {
      if (formMode === "create") {
        await createWarehouse(formData)
      } else if (editingId !== null) {
        await updateWarehouse(editingId, formData)
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
      await deleteWarehouse(deleteTarget.id)
      setDeleteTarget(null)
      await load()
    } catch (e) {
      showMessage("删除失败", getErrorMessage(e))
    } finally {
      setIsDeleting(false)
    }
  }

  return (
    <div className="px-6 py-8">
      <div className="mx-auto flex w-full max-w-3xl flex-col gap-6">
        <div className="flex items-center justify-between">
          <h1 className="text-xl font-semibold">仓库管理</h1>
          <Button onClick={openCreate} className="cursor-pointer">
            <Plus className="h-4 w-4" />
            <span className="ml-2">新增仓库</span>
          </Button>
        </div>

        <div className="overflow-x-auto rounded-xl border border-border bg-muted/20">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-border text-left text-muted-foreground">
                <th className="px-4 py-3">名称</th>
                <th className="px-4 py-3">地址</th>
                <th className="px-4 py-3">备注</th>
                <th className="px-4 py-3 w-24">操作</th>
              </tr>
            </thead>
            <tbody>
              {isLoading && (
                <tr><td colSpan={4} className="px-4 py-8 text-center text-muted-foreground">加载中...</td></tr>
              )}
              {!isLoading && items.length === 0 && (
                <tr><td colSpan={4} className="px-4 py-8 text-center text-muted-foreground">暂无仓库数据</td></tr>
              )}
              {items.map((item) => (
                <tr key={item.id} className="border-b border-border hover:bg-muted/30">
                  <td className="px-4 py-2 font-medium">{item.name}</td>
                  <td className="px-4 py-2">{item.address || "-"}</td>
                  <td className="px-4 py-2 max-w-40 truncate">{item.notes || "-"}</td>
                  <td className="px-4 py-2">
                    <div className="flex items-center gap-1">
                      <Button variant="ghost" size="icon" onClick={() => openEdit(item)} className="cursor-pointer"><Edit className="h-4 w-4" /></Button>
                      <Button variant="ghost" size="icon" onClick={() => setDeleteTarget(item)} className="cursor-pointer"><Trash2 className="h-4 w-4 text-destructive" /></Button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      {formOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50">
          <div className="bg-background rounded-xl border border-border shadow-xl w-full max-w-md mx-4">
            <div className="px-6 py-4 border-b border-border font-semibold">
              {formMode === "create" ? "新增仓库" : "编辑仓库"}
            </div>
            <div className="px-6 py-4 space-y-4">
              <div className="space-y-1">
                <label className="text-sm font-medium">名称 *</label>
                <Input value={formData.name} onChange={(e) => setFormData((prev) => ({ ...prev, name: e.target.value }))} placeholder="仓库名称" />
              </div>
              <div className="space-y-1">
                <label className="text-sm font-medium">地址</label>
                <Input value={formData.address} onChange={(e) => setFormData((prev) => ({ ...prev, address: e.target.value }))} placeholder="仓库地址" />
              </div>
              <div className="space-y-1">
                <label className="text-sm font-medium">备注</label>
                <Input value={formData.notes} onChange={(e) => setFormData((prev) => ({ ...prev, notes: e.target.value }))} placeholder="备注" />
              </div>
            </div>
            <div className="px-6 py-4 border-t border-border flex justify-end gap-2">
              <Button variant="outline" onClick={() => setFormOpen(false)} disabled={isSaving} className="cursor-pointer">取消</Button>
              <Button onClick={handleSave} disabled={isSaving} className="cursor-pointer">{isSaving ? "保存中..." : "保存"}</Button>
            </div>
          </div>
        </div>
      )}

      <ConfirmDialog
        open={deleteTarget !== null}
        title="确认删除"
        description={`确定删除仓库 ${deleteTarget?.name}？此操作不可撤销。`}
        confirmLabel={isDeleting ? "删除中..." : "删除"}
        variant="destructive"
        onConfirm={handleDelete}
        onCancel={() => setDeleteTarget(null)}
      />

      <MessageDialog open={messageOpen} title={messageContent.title} description={messageContent.description} onClose={() => setMessageOpen(false)} />
    </div>
  )
}
