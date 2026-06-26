"use client"

import { useCallback, useEffect, useMemo, useRef, useState } from "react"
import { Plus, Trash2, Edit, X, Upload } from "lucide-react"
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
  lookupInventoryDetail,
  createDetail,
  updateDetail,
  deleteDetail,
  batchDeleteDetails,
  replaceDetailsFromExcel,
  matchSkuImage,
  listInventoryAccountSubjects,
  ApiError,
  type InventoryRecord,
  type InventoryDetail,
  type SupplierItem,
  type InventoryAccountSubject,
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
  remark: "",
}

const EU_SIZE_COLUMNS = ["35", "36", "37", "38", "39", "40", "41", "42", "43", "44"]
const MILLIMETER_SIZE_COLUMNS = ["220", "225", "230", "235", "240", "245", "250", "255", "260", "265", "270", "275", "280", "285"]
const EU_SIZE_BRANDS = new Set(["smiley", "ni", "nike"])
const MILLIMETER_SIZE_BRANDS = new Set(["cbanner_mens", "cbanner_womens", "yandou", "eblan"])
const MILLIMETER_TO_EU_SIZE: Record<string, string> = {
  "220": "34",
  "225": "35",
  "230": "36",
  "235": "37",
  "240": "38",
  "245": "39",
  "250": "40",
  "255": "41",
  "260": "42",
  "265": "43",
  "270": "44",
  "275": "45",
  "280": "46",
  "285": "47",
}
const EU_TO_MILLIMETER_SIZE = Object.fromEntries(
  Object.entries(MILLIMETER_TO_EU_SIZE).map(([millimeter, eu]) => [eu, millimeter]),
) as Record<string, string>
const ACCOUNTING_DOCUMENT_TYPES = new Set(["应付款减少", "应付款增加", "应收款减少", "应收款增加"])

type Props = {
  record: InventoryRecord | null
  suppliers: SupplierItem[]
  onClose: () => void
  onTotalChanged: () => void
}

function getImageKeys(productCode: string | null): string[] {
  const code = (productCode || "").trim()
  if (!code) return []

  const keys = [code]
  if (code.length > 2) keys.push(code.slice(0, -2))
  if (code.length > 5) keys.push(code.slice(0, -5))
  return Array.from(new Set(keys.filter(Boolean)))
}

function formatComputedNumber(value: number): string {
  if (!Number.isFinite(value)) return ""
  return Number.isInteger(value) ? String(value) : value.toFixed(2).replace(/\.?0+$/, "")
}

function sumSizeQuantities(values: Record<string, string>, sizeColumns: string[]): string {
  const total = sizeColumns.reduce((sum, size) => {
    const value = Number.parseFloat(values[size] || "0")
    return Number.isFinite(value) ? sum + value : sum
  }, 0)
  return total > 0 ? formatComputedNumber(total) : ""
}

function computeAmount(quantity: string, unitPrice: string): string {
  const qty = Number.parseFloat(quantity || "0")
  const price = Number.parseFloat(unitPrice || "0")
  if (!Number.isFinite(qty) || !Number.isFinite(price) || !quantity || !unitPrice) return ""
  return (qty * price).toFixed(2)
}

function isNiSupplierName(name: string | null | undefined) {
  const value = (name || "").trim()
  if (!value) return false
  const upper = value.toUpperCase()
  return /\bNI\b/.test(upper) || upper.includes("NIKE") || value.includes("耐克")
}

function isSmileySupplierName(name: string | null | undefined) {
  const value = (name || "").trim()
  return value.includes("笑脸") || value.includes("小莲")
}

function inferInventorySizeBrand(record: InventoryRecord | null, suppliers: SupplierItem[]) {
  const supplierName = (record?.supplier || "").trim()
  const supplier = suppliers.find((item) => item.name === supplierName)
  const brand = supplier?.brand || ""
  if (isNiSupplierName(supplierName) || isNiSupplierName(supplier?.name)) return "ni"
  if (isSmileySupplierName(supplierName) || isSmileySupplierName(supplier?.name)) return "smiley"
  if (brand === "ni") return brand
  if (brand && MILLIMETER_SIZE_BRANDS.has(brand)) return brand
  if (brand === "smiley") return brand
  return "cbanner_mens"
}

function getSizeColumns(brand: string) {
  return EU_SIZE_BRANDS.has(brand.toLowerCase()) ? EU_SIZE_COLUMNS : MILLIMETER_SIZE_COLUMNS
}

function getSizeQuantity(values: Record<string, string> | null | undefined, size: string, brand: string) {
  if (!values) return ""
  if (values[size]) return values[size]
  if (!EU_SIZE_BRANDS.has(brand.toLowerCase())) {
    const euSize = MILLIMETER_TO_EU_SIZE[size]
    return euSize ? values[euSize] || "" : ""
  }
  const millimeterSize = EU_TO_MILLIMETER_SIZE[size]
  return millimeterSize ? values[millimeterSize] || "" : ""
}

function normalizeSizeQuantitiesForBrand(values: Record<string, string> | null | undefined, brand: string) {
  const next: Record<string, string> = {}
  for (const size of getSizeColumns(brand)) {
    const value = getSizeQuantity(values, size, brand)
    if (value) next[size] = value
  }
  return next
}

export function InventoryDetailPanel({ record, suppliers, onClose, onTotalChanged }: Props) {
  const documentId = record?.id ?? null
  const documentType = record?.document_type || ""
  const isAccountingDocument = ACCOUNTING_DOCUMENT_TYPES.has(documentType)
  const accountingAmountLabel = documentType.includes("减少") ? "减少金额" : "增加金额"
  const inventorySizeBrand = useMemo(() => inferInventorySizeBrand(record, suppliers), [record, suppliers])
  const sizeColumns = useMemo(() => getSizeColumns(inventorySizeBrand), [inventorySizeBrand])
  const detailColumnCount = isAccountingDocument ? 6 : 10 + sizeColumns.length
  const [items, setItems] = useState<InventoryDetail[]>([])
  const [isLoading, setIsLoading] = useState(false)
  const [imageUrls, setImageUrls] = useState<Record<number, string | null>>({})
  const [selectedIds, setSelectedIds] = useState<Set<number>>(new Set())
  const replaceInputRef = useRef<HTMLInputElement>(null)
  const [replaceFile, setReplaceFile] = useState<File | null>(null)
  const [isReplacing, setIsReplacing] = useState(false)

  const [formOpen, setFormOpen] = useState(false)
  const [formMode, setFormMode] = useState<"create" | "edit">("create")
  const [formData, setFormData] = useState<Record<string, string>>({ ...EMPTY_DETAIL })
  const [sizeQuantities, setSizeQuantities] = useState<Record<string, string>>({})
  const [isLookupLoading, setIsLookupLoading] = useState(false)
  const [lookupToken, setLookupToken] = useState(0)
  const lookupSourceCodeRef = useRef("")
  const lookupReasonRef = useRef<"code" | "quantity">("code")
  const [editingId, setEditingId] = useState<number | null>(null)
  const [isSaving, setIsSaving] = useState(false)
  const [subjects, setSubjects] = useState<InventoryAccountSubject[]>([])

  const [deleteTarget, setDeleteTarget] = useState<InventoryDetail | null>(null)
  const [batchDeleteOpen, setBatchDeleteOpen] = useState(false)
  const [isDeleting, setIsDeleting] = useState(false)
  const [messageOpen, setMessageOpen] = useState(false)
  const [messageContent, setMessageContent] = useState({ title: "", description: "" })

  const load = useCallback(async () => {
    if (!documentId) return
    setIsLoading(true)
    try {
      const res = await listDetails(documentId)
      setItems(res.items)
      setSelectedIds((current) => {
        if (current.size === 0) return current
        const existingIds = new Set(res.items.map((item) => item.id))
        const next = new Set(Array.from(current).filter((id) => existingIds.has(id)))
        return next.size === current.size ? current : next
      })
    } catch {
      setItems([])
      setSelectedIds(new Set())
    } finally {
      setIsLoading(false)
    }
  }, [documentId])

  useEffect(() => { void load() }, [load])

  useEffect(() => {
    setSelectedIds(new Set())
  }, [documentId])

  // Load images for all detail items
  useEffect(() => {
    const controller = new AbortController()
    async function loadImages() {
      if (isAccountingDocument) {
        setImageUrls({})
        return
      }
      const urls: Record<number, string | null> = {}
      for (const item of items) {
        const keys = getImageKeys(item.product_code)
        if (keys.length === 0) {
          urls[item.id] = null
          continue
        }
        try {
          let imageUrl: string | null = null
          for (const key of keys) {
            const result = await matchSkuImage(key)
            if (result.found && result.image_url) {
              imageUrl = result.image_url
              break
            }
          }
          urls[item.id] = imageUrl
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
  }, [items, isAccountingDocument])

  const loadSubjects = useCallback(async () => {
    try {
      const res = await listInventoryAccountSubjects()
      setSubjects(res.items)
    } catch {
      setSubjects([])
    }
  }, [])

  useEffect(() => {
    if (isAccountingDocument) void loadSubjects()
  }, [isAccountingDocument, loadSubjects])

  const showMessage = (title: string, description: string) => {
    setMessageContent({ title, description })
    setMessageOpen(true)
  }

  const openCreate = () => {
    setFormMode("create")
    setFormData({ ...EMPTY_DETAIL })
    setSizeQuantities({})
    setLookupToken(0)
    lookupSourceCodeRef.current = ""
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
      remark: item.remark || "",
    })
    setSizeQuantities(normalizeSizeQuantitiesForBrand(item.size_quantities, inventorySizeBrand))
    setLookupToken(0)
    lookupSourceCodeRef.current = item.product_code || ""
    setFormOpen(true)
  }

  const handleSave = async () => {
    if (!documentId) return
    if (isAccountingDocument && (!formData.product_name?.trim() || !formData.amount?.trim())) {
      showMessage("保存失败", "请填写科目和金额")
      return
    }
    setIsSaving(true)
    try {
      const payload = isAccountingDocument
        ? {
            product_code: "",
            product_name: formData.product_name,
            amount: formData.amount,
            remark: formData.remark,
          }
        : { ...formData, size_quantities: sizeQuantities }
      if (formMode === "create") {
        await createDetail(documentId, payload)
      } else if (editingId !== null) {
        await updateDetail(documentId, editingId, payload)
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

  const handleSubjectSelect = (subjectName: string) => {
    setFormData((prev) => ({
      ...prev,
      product_name: subjectName,
      product_code: "",
    }))
  }

  useEffect(() => {
    if (isAccountingDocument || !formOpen || lookupToken === 0) return
    const productCode = (lookupSourceCodeRef.current || formData.product_code || "").trim()
    if (!productCode) {
      setSizeQuantities({})
      return
    }
    const controller = new AbortController()
    const timer = window.setTimeout(async () => {
      setIsLookupLoading(true)
      try {
        const res = await lookupInventoryDetail({
          productCode,
          quantity: formData.quantity || undefined,
          brand: inventorySizeBrand,
        })
        if (controller.signal.aborted) return
        const item = res.item
        setFormData((prev) => ({
          ...prev,
          product_code: item.product_code || prev.product_code,
          product_name: item.product_name || prev.product_name,
          color_spec: item.color_spec || prev.color_spec,
          color_barcode: item.color_barcode || prev.color_barcode,
          color_name: item.color_name || prev.color_name,
          unit_price: item.unit_price || prev.unit_price,
          amount: item.amount || prev.amount,
        }))
        setSizeQuantities((prev) => {
          const next = item.size_quantities || {}
          if (Object.keys(next).length > 0) return next
          if (lookupReasonRef.current !== "quantity") return {}
          const filledSizes = Object.keys(prev).filter((size) => prev[size])
          if (filledSizes.length === 1 && formData.quantity) {
            return { [filledSizes[0]]: formData.quantity }
          }
          return prev
        })
      } catch {
        // Keep manually entered data if matching fails.
      } finally {
        if (!controller.signal.aborted) setIsLookupLoading(false)
      }
    }, 350)
    return () => {
      controller.abort()
      window.clearTimeout(timer)
    }
  }, [formOpen, lookupToken, formData.product_code, formData.quantity, isAccountingDocument, inventorySizeBrand])

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

  const toggleSelected = (id: number) => {
    setSelectedIds((current) => {
      const next = new Set(current)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })
  }

  const toggleAllSelected = () => {
    setSelectedIds((current) => {
      if (items.length > 0 && items.every((item) => current.has(item.id))) return new Set()
      return new Set(items.map((item) => item.id))
    })
  }

  const handleBatchDelete = async () => {
    if (!documentId || selectedIds.size === 0) return
    setIsDeleting(true)
    try {
      const result = await batchDeleteDetails(documentId, Array.from(selectedIds))
      setBatchDeleteOpen(false)
      setSelectedIds(new Set())
      await load()
      onTotalChanged()
      showMessage("删除完成", result.message)
    } catch (e) {
      showMessage("删除失败", getErrorMessage(e))
    } finally {
      setIsDeleting(false)
    }
  }

  const handleReplaceImport = async () => {
    if (!documentId || !replaceFile) return
    setIsReplacing(true)
    try {
      const result = await replaceDetailsFromExcel({
        documentId,
        file: replaceFile,
        brand: inventorySizeBrand,
      })
      setReplaceFile(null)
      if (replaceInputRef.current) replaceInputRef.current.value = ""
      await load()
      onTotalChanged()
      showMessage("导入完成", result.message)
    } catch (e) {
      showMessage("导入失败", getErrorMessage(e))
    } finally {
      setIsReplacing(false)
    }
  }

  if (documentId === null) return null

  const allSelected = items.length > 0 && items.every((item) => selectedIds.has(item.id))

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
            <p className="text-xs text-muted-foreground">单据 {record?.document_number || documentId}</p>
          </div>
          <div className="flex items-center gap-2">
            {!isAccountingDocument && (
              <>
                <input
                  ref={replaceInputRef}
                  type="file"
                  accept=".xlsx,.xls,.xlsm"
                  className="hidden"
                  onChange={(event) => {
                    const file = event.target.files?.[0] ?? null
                    if (file) setReplaceFile(file)
                  }}
                />
                <Button
                  size="sm"
                  variant="outline"
                  onClick={() => replaceInputRef.current?.click()}
                  disabled={isReplacing}
                  className="cursor-pointer"
                  title="用 Excel 重新导入并覆盖当前单据明细"
                >
                  <Upload className="h-4 w-4" />
                  <span className="ml-1.5">重新导入明细</span>
                </Button>
              </>
            )}
            {selectedIds.size > 0 && (
              <Button
                size="sm"
                variant="destructive"
                onClick={() => setBatchDeleteOpen(true)}
                disabled={isDeleting}
                className="cursor-pointer"
              >
                <Trash2 className="h-4 w-4" />
                <span className="ml-1.5">删除选中 {selectedIds.size}</span>
              </Button>
            )}
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
              {isAccountingDocument ? (
                <tr className="sticky top-0 z-10 border-b border-border bg-muted/40 text-left text-muted-foreground">
                  <th className="w-10 px-3 py-2.5 font-medium">
                    <input
                      type="checkbox"
                      checked={allSelected}
                      disabled={items.length === 0 || isLoading}
                      onChange={toggleAllSelected}
                      className="h-4 w-4 cursor-pointer rounded border-border"
                      aria-label="选择全部明细"
                    />
                  </th>
                  <th className="px-3 py-2.5 w-16 font-medium">序号</th>
                  <th className="px-3 py-2.5 font-medium">费用项目名 / 科目</th>
                  <th className="px-3 py-2.5 text-right font-medium">{accountingAmountLabel}</th>
                  <th className="px-3 py-2.5 font-medium">备注</th>
                  <th className="px-4 py-2.5 w-20 font-medium">操作</th>
                </tr>
              ) : (
                <tr className="sticky top-0 z-10 border-b border-border bg-muted/40 text-left text-muted-foreground">
                  <th className="w-10 px-3 py-2.5 font-medium">
                    <input
                      type="checkbox"
                      checked={allSelected}
                      disabled={items.length === 0 || isLoading}
                      onChange={toggleAllSelected}
                      className="h-4 w-4 cursor-pointer rounded border-border"
                      aria-label="选择全部明细"
                    />
                  </th>
                  <th className="px-4 py-2.5 w-20 font-medium"></th>
                  <th className="px-3 py-2.5 font-medium">货号</th>
                  <th className="px-3 py-2.5 font-medium">商品全名</th>
                  <th className="px-3 py-2.5 font-medium">颜色条码</th>
                  <th className="px-3 py-2.5 font-medium">颜色名称</th>
                  {sizeColumns.map((size) => (
                    <th key={size} className="px-2 py-2.5 text-right font-medium">{size}</th>
                  ))}
                  <th className="px-3 py-2.5 text-right font-medium">数量</th>
                  <th className="px-3 py-2.5 text-right font-medium">单价</th>
                  <th className="px-3 py-2.5 text-right font-medium">金额</th>
                  <th className="px-4 py-2.5 w-20 font-medium">操作</th>
                </tr>
              )}
            </thead>
            <tbody className="divide-y divide-border">
              {isLoading && (
                <tr>
                    <td colSpan={detailColumnCount} className="px-6 py-12 text-center text-muted-foreground">加载中...</td>
                </tr>
              )}
              {!isLoading && items.length === 0 && (
                <tr>
                  <td colSpan={detailColumnCount} className="px-6 py-12 text-center text-muted-foreground">暂无明细数据</td>
                </tr>
              )}
              {items.map((item, index) => (
                <tr key={item.id} className="hover:bg-muted/30 transition-colors">
                  <td className="px-3 py-2.5">
                    <input
                      type="checkbox"
                      checked={selectedIds.has(item.id)}
                      onChange={() => toggleSelected(item.id)}
                      className="h-4 w-4 cursor-pointer rounded border-border"
                      aria-label={`选择明细 ${item.product_code || item.id}`}
                    />
                  </td>
                  {isAccountingDocument ? (
                    <>
                      <td className="px-3 py-2.5 text-muted-foreground tabular-nums">{index + 1}</td>
                      <td className="px-3 py-2.5">{item.product_name || "-"}</td>
                      <td className="px-3 py-2.5 text-right tabular-nums">{item.amount || "-"}</td>
                      <td className="px-3 py-2.5 max-w-64 truncate">{item.remark || "-"}</td>
                    </>
                  ) : (
                    <>
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
                      {sizeColumns.map((size) => (
                        <td key={size} className="px-2 py-2.5 text-right tabular-nums">
                          {getSizeQuantity(item.size_quantities, size, inventorySizeBrand) || "-"}
                        </td>
                      ))}
                      <td className="px-3 py-2.5 text-right tabular-nums">{item.quantity || "-"}</td>
                      <td className="px-3 py-2.5 text-right tabular-nums">{item.unit_price || "-"}</td>
                      <td className="px-3 py-2.5 text-right tabular-nums">{item.amount || "-"}</td>
                    </>
                  )}
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
        <DialogContent className="max-w-2xl">
          <DialogHeader>
            <DialogTitle>{formMode === "create" ? "新增明细" : "编辑明细"}</DialogTitle>
          </DialogHeader>
          <div className="space-y-4 py-2">
            {isAccountingDocument ? (
              <>
                <div className="space-y-1.5">
                  <Label htmlFor="detail-subject">费用项目名 / 科目</Label>
                  <select
                    id="detail-subject"
                    value={formData.product_name || ""}
                    onChange={(event) => handleSubjectSelect(event.target.value)}
                    className="flex h-9 w-full cursor-pointer rounded-lg border border-input bg-card px-3 py-2 text-sm shadow-xs outline-none transition-colors focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/35"
                  >
                    <option value="">请选择科目</option>
                    {subjects.map((subject) => (
                      <option key={subject.id} value={subject.name}>
                        {subject.name}
                      </option>
                    ))}
                  </select>
                </div>
                <div className="space-y-1.5">
                  <Label htmlFor="detail-accounting-amount">{accountingAmountLabel}</Label>
                  <Input
                    id="detail-accounting-amount"
                    type="number"
                    step="0.01"
                    value={formData.amount || ""}
                    onChange={(event) => setFormData((prev) => ({ ...prev, amount: event.target.value }))}
                    placeholder="0.00"
                  />
                </div>
                <div className="space-y-1.5">
                  <Label htmlFor="detail-remark">备注</Label>
                  <Input
                    id="detail-remark"
                    value={formData.remark || ""}
                    onChange={(event) => setFormData((prev) => ({ ...prev, remark: event.target.value }))}
                    placeholder="备注"
                  />
                </div>
              </>
            ) : (
              <>
            <div className="space-y-1.5">
              <Label htmlFor="detail-product-code">货号</Label>
              <Input
                id="detail-product-code"
                value={formData.product_code || ""}
                onChange={(e) => {
                  lookupSourceCodeRef.current = e.target.value
                  lookupReasonRef.current = "code"
                  setLookupToken((token) => token + 1)
                  setFormData((prev) => ({ ...prev, product_code: e.target.value }))
                }}
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
                    const amount = computeAmount(qty, price)
                    lookupReasonRef.current = "quantity"
                    setLookupToken((token) => token + 1)
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
                    const amount = computeAmount(qty, price)
                    setFormData((prev) => ({ ...prev, unit_price: price, amount }))
                  }}
                  placeholder="0.00"
                />
              </div>
            </div>
            <div className="space-y-1.5">
              <Label>尺码</Label>
              <div className="grid grid-cols-5 gap-1.5 rounded-lg border border-border bg-muted/20 p-2">
                {sizeColumns.map((size) => (
                  <label key={size} className="flex flex-col gap-1 rounded-md border border-border bg-background p-1.5 text-xs">
                    <span className="text-center text-muted-foreground">{size}</span>
                    <Input
                      value={sizeQuantities[size] || ""}
                      onChange={(e) => {
                        const value = e.target.value
                        setSizeQuantities((prev) => {
                          const next = { ...prev }
                          if (value) next[size] = value
                          else delete next[size]
                          const quantity = sumSizeQuantities(next, sizeColumns)
                          const amount = computeAmount(quantity, formData.unit_price || "")
                          setFormData((current) => ({
                            ...current,
                            quantity,
                            amount,
                          }))
                          return next
                        })
                      }}
                      inputMode="numeric"
                      className="h-7 px-1 text-center text-xs tabular-nums"
                      placeholder="-"
                    />
                  </label>
                ))}
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
              </>
            )}
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setFormOpen(false)} disabled={isSaving} className="cursor-pointer">取消</Button>
            <Button onClick={handleSave} disabled={isSaving || isLookupLoading} className="cursor-pointer">
              {isSaving ? "保存中..." : isLookupLoading ? "匹配中..." : "保存"}
            </Button>
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

      <ConfirmDialog
        open={batchDeleteOpen}
        title="确认批量删除"
        description={`确定删除选中的 ${selectedIds.size} 条明细？删除后单据总数和金额会自动重算。`}
        confirmLabel={isDeleting ? "删除中..." : "删除"}
        variant="destructive"
        onConfirm={handleBatchDelete}
        onCancel={() => setBatchDeleteOpen(false)}
      />

      <ConfirmDialog
        open={replaceFile !== null}
        title="确认覆盖明细"
        description={`确定用 ${replaceFile?.name || "这个 Excel"} 覆盖当前单据的全部明细？原明细会先删除，再写入新 Excel 解析出的明细。`}
        confirmLabel={isReplacing ? "导入中..." : "覆盖导入"}
        variant="destructive"
        onConfirm={handleReplaceImport}
        onCancel={() => {
          if (isReplacing) return
          setReplaceFile(null)
          if (replaceInputRef.current) replaceInputRef.current.value = ""
        }}
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
