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
  matchSkuImage,
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
  product_name: "",
  color_spec: "",
  color_barcode: "",
  color_name: "",
  quantity: "",
  unit_price: "",
  amount: "",
}

const SIZE_COLUMNS = ["35", "36", "37", "38", "39", "40", "41", "42", "43", "44"]

type Props = {
  documentId: number | null
  onClose: () => void
  onTotalChanged: () => void
}

function getImageKey(productCode: string | null): string | null {
  if (!productCode || productCode.length <= 5) return null
  return productCode.slice(0, -5)
}

export function InventoryDetailPanel({ documentId, onClose, onTotalChanged }: Props) {
  const [items, setItems] = useState<InventoryDetail[]>([])
  const [isLoading, setIsLoading] = useState(false)
  const [imageUrls, setImageUrls] = useState<Record<number, string | null>>({})

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

  // Load images for all detail items
  useEffect(() => {
    const controller = new AbortController()
    async function loadImages() {
      const urls: Record<number, string | null> = {}
      for (const item of items) {
        const key = getImageKey(item.product_code)
        if (!key) {
          urls[item.id] = null
          continue
        }
        try {
          const result = await matchSkuImage(key)
          urls[item.id] = result.found ? result.image_url : null
        } catch {
          urls[item.id] = null
        }
      }
      if (!controller.signal.aborted) {
        setImageUrls(urls)
      }
    }
    void loadImages()
    return () => { controller.abort() }
  }, [items])

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
      product_name: item.product_name || "",
      color_spec: item.color_spec || "",
      color_barcode: item.color_barcode || "",
      color_name: item.color_name || "",
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
      <div className="fixed inset-y-0 right-0 z-50 w-full max-w-6xl border-l border-border bg-background shadow-2xl flex flex-col">
        {/* Header */}
        <div className="flex items-center justify-between border-b border-border px-6 py-4 shrink-0">
          <div>
            <h2 className="text-lg font-semibold">单据明细</h2>
            <p className="text-xs text-muted-foreground">单据 {documentId}</p>
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
              <tr className="sticky top-0 z-10 border-b border-border bg-muted/40 text-left text-muted-foreground">
                <th className="px-4 py-2.5 w-20 font-medium"></th>
                <th className="px-3 py-2.5 font-medium">货号</th>
                <th className="px-3 py-2.5 font-medium">商品全名</th>
                <th className="px-3 py-2.5 font-medium">颜色条码</th>
                <th className="px-3 py-2.5 font-medium">颜色名称</th>
                {SIZE_COLUMNS.map((size) => (
                  <th key={size} className="px-2 py-2.5 text-right font-medium">{size}</th>
                ))}
                <th className="px-3 py-2.5 text-right font-medium">数量</th>
                <th className="px-3 py-2.5 text-right font-medium">单价</th>
                <th className="px-3 py-2.5 text-right font-medium">金额</th>
                <th className="px-4 py-2.5 w-20 font-medium">操作</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-border">
              {isLoading && (
                <tr>
                  <td colSpan={19} className="px-6 py-12 text-center text-muted-foreground">加载中...</td>
                </tr>
              )}
              {!isLoading && items.length === 0 && (
                <tr>
                  <td colSpan={19} className="px-6 py-12 text-center text-muted-foreground">暂无明细数据</td>
                </tr>
              )}
              {items.map((item) => (
                <tr key={item.id} className="hover:bg-muted/30 transition-colors">
                  <td className="px-4 py-1.5">
                    {imageUrls[item.id] ? (
                      <img
                        src={`/api${imageUrls[item.id]}`}
                        alt={item.product_code || ""}
                        className="h-16 w-16 object-contain"
                      />
                    ) : (
                      <div className="h-16 w-16 rounded-lg border border-border bg-muted/10 flex items-center justify-center text-[10px] text-muted-foreground/50">
                        无图
                      </div>
                    )}
                  </td>
                  <td className="px-3 py-2.5 font-mono text-xs">{item.product_code || "-"}</td>
                  <td className="px-3 py-2.5">{item.product_name || "-"}</td>
                  <td className="px-3 py-2.5 font-mono text-xs">{item.color_barcode || "-"}</td>
                  <td className="px-3 py-2.5">{item.color_name || item.color_spec || "-"}</td>
                  {SIZE_COLUMNS.map((size) => (
                    <td key={size} className="px-2 py-2.5 text-right tabular-nums">{item.size_quantities?.[size] || "-"}</td>
                  ))}
                  <td className="px-3 py-2.5 text-right tabular-nums">{item.quantity || "-"}</td>
                  <td className="px-3 py-2.5 text-right tabular-nums">{item.unit_price || "-"}</td>
                  <td className="px-3 py-2.5 text-right tabular-nums">{item.amount || "-"}</td>
                  <td className="px-4 py-2.5">
                    <div className="flex items-center gap-0.5">
                      <Button variant="ghost" size="icon" onClick={() => openEdit(item)} className="h-8 w-8 cursor-pointer">
                        <Edit className="h-3.5 w-3.5" />
                      </Button>
                      <Button variant="ghost" size="icon" onClick={() => setDeleteTarget(item)} className="h-8 w-8 cursor-pointer">
                        <Trash2 className="h-3.5 w-3.5 text-destructive" />
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
              <Label htmlFor="detail-product-code">货号</Label>
              <Input
                id="detail-product-code"
                value={formData.product_code || ""}
                onChange={(e) => setFormData((prev) => ({ ...prev, product_code: e.target.value }))}
                placeholder="货号"
              />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="detail-product-name">商品全名</Label>
              <Input
                id="detail-product-name"
                value={formData.product_name || ""}
                onChange={(e) => setFormData((prev) => ({ ...prev, product_name: e.target.value }))}
                placeholder="商品全名"
              />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="detail-color-barcode">颜色条码</Label>
              <Input
                id="detail-color-barcode"
                value={formData.color_barcode || ""}
                onChange={(e) => setFormData((prev) => ({ ...prev, color_barcode: e.target.value }))}
                placeholder="颜色条码"
              />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="detail-color-name">颜色名称</Label>
              <Input
                id="detail-color-name"
                value={formData.color_name || ""}
                onChange={(e) => setFormData((prev) => ({ ...prev, color_name: e.target.value, color_spec: e.target.value }))}
                placeholder="颜色名称"
              />
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div className="space-y-1.5">
                <Label htmlFor="detail-quantity">数量</Label>
                <Input
                  id="detail-quantity"
                  type="number"
                  value={formData.quantity || ""}
                  onChange={(e) => {
                    const qty = e.target.value
                    const price = formData.unit_price || ""
                    const amount = qty && price ? (parseFloat(qty) * parseFloat(price)).toFixed(2) : formData.amount
                    setFormData((prev) => ({ ...prev, quantity: qty, amount }))
                  }}
                  placeholder="0"
                />
              </div>
              <div className="space-y-1.5">
                <Label htmlFor="detail-unit-price">单价</Label>
                <Input
                  id="detail-unit-price"
                  type="number"
                  step="0.01"
                  value={formData.unit_price || ""}
                  onChange={(e) => {
                    const price = e.target.value
                    const qty = formData.quantity || ""
                    const amount = qty && price ? (parseFloat(qty) * parseFloat(price)).toFixed(2) : formData.amount
                    setFormData((prev) => ({ ...prev, unit_price: price, amount }))
                  }}
                  placeholder="0.00"
                />
              </div>
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="detail-amount">金额</Label>
              <Input
                id="detail-amount"
                type="number"
                step="0.01"
                value={formData.amount || ""}
                onChange={(e) => setFormData((prev) => ({ ...prev, amount: e.target.value }))}
                placeholder="自动计算"
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
