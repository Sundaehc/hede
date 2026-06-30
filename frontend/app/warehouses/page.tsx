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
    <div className="app-page">
      <div className="app-content-narrow">
        <div className="page-header">
          <div className="flex items-center gap-3">
            <div>
              <h1 className="page-title">仓库管理</h1>
            </div>
            <span className="rounded-full border border-border bg-muted/45 px-3 py-1 text-sm text-muted-foreground tabular-nums">{items.length} 个</span>
          </div>
          <Button size="sm" onClick={openCreate} className="cursor-pointer">
            <Plus className="h-4 w-4" />
            <span className="ml-1.5">新增仓库</span>
          </Button>
        </div>

        <div className="table-panel overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="table-head-row">
                <th className="px-4 py-3 font-medium">名称</th>
                <th className="px-4 py-3 font-medium">地址</th>
                <th className="px-4 py-3 font-medium">备注</th>
                <th className="px-4 py-3 w-24 font-medium">操作</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-border">
              {isLoading && (
                <tr>
                  <td colSpan={4} className="px-4 py-12 text-center text-muted-foreground">加载中...</td>
                </tr>
              )}
              {!isLoading && items.length === 0 && (
                <tr>
                  <td colSpan={4} className="px-4 py-12 text-center text-muted-foreground">暂无仓库数据</td>
                </tr>
              )}
              {items.map((item) => (
                <tr key={item.id} className="table-row">
                  <td className="px-4 py-2.5 font-medium">{item.name}</td>
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
            <DialogTitle>{formMode === "create" ? "新增仓库" : "编辑仓库"}</DialogTitle>
          </DialogHeader>
          <div className="space-y-4 py-2">
            <div className="space-y-1.5">
              <Label htmlFor="warehouse-name">名称 *</Label>
              <Input id="warehouse-name" value={formData.name} onChange={(e) => setFormData((prev) => ({ ...prev, name: e.target.value }))} placeholder="仓库名称" />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="warehouse-address">地址</Label>
              <Input id="warehouse-address" value={formData.address} onChange={(e) => setFormData((prev) => ({ ...prev, address: e.target.value }))} placeholder="仓库地址" />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="warehouse-notes">备注</Label>
              <Input id="warehouse-notes" value={formData.notes} onChange={(e) => setFormData((prev) => ({ ...prev, notes: e.target.value }))} placeholder="备注" />
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
