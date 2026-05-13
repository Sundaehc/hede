"use client"

import { useCallback, useEffect, useState } from "react"
import { Plus, Trash2, Edit, X } from "lucide-react"
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
  listDetails,
  createDetail,
  updateDetail,
  deleteDetail,
  ApiError,
  type InventoryDetail,
} from "@/lib/api"

function getErrorMessage(error: unknown) {
  if (error instanceof ApiError) return error.message || `请求失败（${error.status}）`
  if (error instanceof Error) return error.message
  return "发生未知错误"
}

const EMPTY_DETAIL: Record<string, string> = {
  product_code: "",
  quantity: "",
  unit_price: "",
  amount: "",
}

type Props = {
  documentId: number | null
  onClose: () => void
  onTotalChanged: () => void
}

export function InventoryDetailPanel({ documentId, onClose, onTotalChanged }: Props) {
  const [items, setItems] = useState<InventoryDetail[]>([])
  const [isLoading, setIsLoading] = useState(false)

  const [formOpen, setFormOpen] = useState(false)
  const [formMode, setFormMode] = useState<"create" | "edit">("create")
  const [formData, setFormData] = useState<Record<string, string>>({ ...EMPTY_DETAIL })
  const [editingId, setEditingId] = useState<number | null>(null)
  const [isSaving, setIsSaving] = useState(false)

  const [deleteTarget, setDeleteTarget] = useState<InventoryDetail | null>(null)
  const [isDeleting, setIsDeleting] = useState(false)
  const [messageOpen, setMessageOpen] = useState(false)
  const [messageContent, setMessageContent] = useState({ title: "", description: "" })

  const load = useCallback(async () => {
    if (!documentId) return
    setIsLoading(true)
    try {
      const res = await listDetails(documentId)
      setItems(res.items)
    } catch {
      setItems([])
    } finally {
      setIsLoading(false)
    }
  }, [documentId])

  useEffect(() => { void load() }, [load])

  const showMessage = (title: string, description: string) => {
    setMessageContent({ title, description })
    setMessageOpen(true)
  }

  const openCreate = () => {
    setFormMode("create")
    setFormData({ ...EMPTY_DETAIL })
    setEditingId(null)
    setFormOpen(true)
  }

  const openEdit = (item: InventoryDetail) => {
    setFormMode("edit")
    setEditingId(item.id)
    setFormData({
      product_code: item.product_code || "",
      quantity: item.quantity || "",
      unit_price: item.unit_price || "",
      amount: item.amount || "",
    })
    setFormOpen(true)
  }

  const handleSave = async () => {
    if (!documentId) return
    setIsSaving(true)
    try {
      if (formMode === "create") {
        await createDetail(documentId, formData)
      } else if (editingId !== null) {
        await updateDetail(documentId, editingId, formData)
      }
      setFormOpen(false)
      await load()
      onTotalChanged()
    } catch (e) {
      showMessage("保存失败", getErrorMessage(e))
    } finally {
      setIsSaving(false)
    }
  }

  const handleDelete = async () => {
    if (!deleteTarget || !documentId) return
    setIsDeleting(true)
    try {
      await deleteDetail(documentId, deleteTarget.id)
      setDeleteTarget(null)
      await load()
      onTotalChanged()
    } catch (e) {
      showMessage("删除失败", getErrorMessage(e))
    } finally {
      setIsDeleting(false)
    }
  }

  if (documentId === null) return null

  return (
    <>
      {/* Backdrop */}
      <div className="fixed inset-0 z-40 bg-black/30 transition-opacity" onClick={onClose} />

      {/* Panel */}
      <div className="fixed inset-y-0 right-0 z-50 w-full max-w-lg border-l border-border bg-background shadow-2xl flex flex-col">
        {/* Header */}
        <div className="flex items-center justify-between border-b border-border px-6 py-4 shrink-0">
          <div>
            <h2 className="text-lg font-semibold">单据明细</h2>
            <p className="text-xs text-muted-foreground">单据 #{documentId}</p>
          </div>
          <div className="flex items-center gap-2">
            <Button size="sm" onClick={openCreate} className="cursor-pointer">
              <Plus className="h-4 w-4" />
              <span className="ml-1.5">新增明细</span>
            </Button>
            <Button variant="ghost" size="icon" onClick={onClose} className="cursor-pointer">
              <X className="h-5 w-5" />
            </Button>
          </div>
        </div>

        {/* Table */}
        <div className="flex-1 overflow-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="sticky top-0 border-b border-border bg-muted/40 text-left text-muted-foreground">
                <th className="px-6 py-3 font-medium">商品编码</th>
                <th className="px-6 py-3 text-right font-medium">数量</th>
                <th className="px-6 py-3 text-right font-medium">单价</th>
                <th className="px-6 py-3 text-right font-medium">金额</th>
                <th className="px-6 py-3 w-20 font-medium">操作</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-border">
              {isLoading && (
                <tr>
                  <td colSpan={5} className="px-6 py-12 text-center text-muted-foreground">加载中...</td>
                </tr>
              )}
              {!isLoading && items.length === 0 && (
                <tr>
                  <td colSpan={5} className="px-6 py-12 text-center text-muted-foreground">暂无明细数据</td>
                </tr>
              )}
              {items.map((item) => (
                <tr key={item.id} className="hover:bg-muted/30 transition-colors">
                  <td className="px-6 py-2.5 font-mono text-xs">{item.product_code || "-"}</td>
                  <td className="px-6 py-2.5 text-right tabular-nums">{item.quantity || "-"}</td>
                  <td className="px-6 py-2.5 text-right tabular-nums">{item.unit_price || "-"}</td>
                  <td className="px-6 py-2.5 text-right tabular-nums">{item.amount || "-"}</td>
                  <td className="px-6 py-2.5">
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

      {/* Detail Form Dialog */}
      <Dialog open={formOpen} onOpenChange={setFormOpen}>
        <DialogContent className="max-w-md">
          <DialogHeader>
            <DialogTitle>{formMode === "create" ? "新增明细" : "编辑明细"}</DialogTitle>
          </DialogHeader>
          <div className="space-y-4 py-2">
            <div className="space-y-1.5">
              <Label htmlFor="detail-product-code">商品编码</Label>
              <Input
                id="detail-product-code"
                value={formData.product_code || ""}
                onChange={(e) => setFormData((prev) => ({ ...prev, product_code: e.target.value }))}
                placeholder="商品编码"
              />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="detail-quantity">数量</Label>
              <Input
                id="detail-quantity"
                type="number"
                value={formData.quantity || ""}
                onChange={(e) => setFormData((prev) => ({ ...prev, quantity: e.target.value }))}
                placeholder="数量"
              />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="detail-unit-price">单价</Label>
              <Input
                id="detail-unit-price"
                type="number"
                step="0.01"
                value={formData.unit_price || ""}
                onChange={(e) => setFormData((prev) => ({ ...prev, unit_price: e.target.value }))}
                placeholder="单价"
              />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="detail-amount">金额</Label>
              <Input
                id="detail-amount"
                type="number"
                step="0.01"
                value={formData.amount || ""}
                onChange={(e) => setFormData((prev) => ({ ...prev, amount: e.target.value }))}
                placeholder="金额"
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
        description={`确定删除明细 ${deleteTarget?.product_code || deleteTarget?.id}？此操作不可撤销。`}
        confirmLabel={isDeleting ? "删除中..." : "删除"}
        variant="destructive"
        onConfirm={handleDelete}
        onCancel={() => setDeleteTarget(null)}
      />

      <MessageDialog
        open={messageOpen}
        title={messageContent.title}
        description={messageContent.description}
        onClose={() => setMessageOpen(false)}
      />
    </>
  )
}
