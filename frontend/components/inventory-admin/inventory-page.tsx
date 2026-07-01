"use client"

import { useCallback, useEffect, useRef, useState } from "react"
import { Plus, Download, Upload, Trash2, Edit, Search, X, RefreshCw, List, BadgeDollarSign, FileText } from "lucide-react"
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
  createDetail,
  deleteInventoryRecord,
  listInventoryRecycleBin,
  restoreInventoryRecord,
  batchRestoreInventory,
  batchPermanentlyDeleteInventory,
  batchUpdateInventoryCosts,
  batchDeleteInventory,
  importPurchaseInventory,
  listPurchaseOrderRequirements,
  updatePurchaseOrderRequirement,
  buildInventoryExportUrl,
  listInventoryAccountSubjects,
  listGeneralCustomerShops,
  listSuppliers,
  listWarehouses,
  ApiError,
  type InventoryRecord,
  type InventoryAccountSubject,
  type PurchaseOrderRequirementBrand,
  type SupplierItem,
  type WarehouseItem,
} from "@/lib/api"
import type { GeneralCustomerShopItem } from "@/lib/types"

const PAGE_SIZES = [10, 50, 100]

const ACCOUNTING_DOCUMENT_TYPES = ["应付款减少", "应付款增加", "应收款减少", "应收款增加"]
const PURCHASE_ORDER_DOCUMENT_TYPE = "进货订单"
const INVENTORY_DOCUMENT_TYPES = ["进货单", "进货退货单", "报溢单", "报损单", "批发销售单", "批发销售退货单", "同价调拨单", ...ACCOUNTING_DOCUMENT_TYPES]
const DETAIL_IMPORT_DOCUMENT_TYPES = ["进货单", "进货退货单", "报溢单", "报损单", "批发销售单", "批发销售退货单", "同价调拨单"]
const WHOLESALE_DOCUMENT_TYPES = new Set(["批发销售单", "批发销售退货单"])
const TRANSFER_DOCUMENT_TYPES = new Set(["同价调拨单"])
const STOCK_ADJUSTMENT_DOCUMENT_TYPES = new Set(["报溢单", "报损单"])
const PAYABLE_DOCUMENT_TYPES = new Set(["应付款减少", "应付款增加"])
const RECEIVABLE_DOCUMENT_TYPES = new Set(["应收款减少", "应收款增加"])
const ACCOUNTING_DOCUMENT_TYPE_SET = new Set(ACCOUNTING_DOCUMENT_TYPES)
const OUTBOUND_DOCUMENT_TYPES = new Set(["进货退货单", "报损单", "批发销售单"])
const INBOUND_DOCUMENT_TYPES = new Set([PURCHASE_ORDER_DOCUMENT_TYPE, "进货单", "报溢单", "批发销售退货单"])
const COMPLETION_TABS = [
  { value: "completed", label: "已完成单据" },
  { value: "incomplete", label: "未完成单据" },
] as const
const PURCHASE_REQUIREMENT_BRAND_OPTIONS: Array<{ value: PurchaseOrderRequirementBrand; label: string }> = [
  { value: "cbanner_mens", label: "千百度男鞋" },
  { value: "cbanner_womens", label: "千百度女鞋" },
  { value: "yandou", label: "烟斗" },
  { value: "eblan", label: "伊伴" },
  { value: "smiley", label: "笑脸" },
  { value: "ni", label: "NI" },
]
type CompletionStatus = (typeof COMPLETION_TABS)[number]["value"]
type PurchaseExportMode = "summary" | "size_rows" | "production_order"
type SearchableOption = {
  value: string
  label: string
  keywords?: string
}

function todayInputValue() {
  const now = new Date()
  const year = now.getFullYear()
  const month = String(now.getMonth() + 1).padStart(2, "0")
  const day = String(now.getDate()).padStart(2, "0")
  return `${year}-${month}-${day}`
}

const EMPTY_FORM: Record<string, string> = {
  date: "",
  supplier: "",
  warehouse: "",
  document_type: "",
  delivery_date: "",
  handler: "",
  summary: "",
  additional_note: "",
  detail_subject: "",
  detail_amount: "",
  detail_remark: "",
}

const EMPTY_IMPORT_FORM: Record<string, string> = {
  date: "",
  supplier: "",
  warehouse: "",
  document_type: "",
  delivery_date: "",
  handler: "",
  summary: "",
}

const EMPTY_COST_FORM: Record<string, string> = {
  date_start: "",
  date_end: "",
  product_code: "",
  unit_price: "",
  batch_text: "",
}

function getErrorMessage(error: unknown) {
  if (error instanceof ApiError) return error.message || `请求失败（${error.status}）`
  if (error instanceof Error) return error.message
  return "发生未知错误"
}

function formatDeletedAt(value: string | null) {
  if (!value) return "-"
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return value
  return date.toLocaleString("zh-CN", { hour12: false })
}

function remainingRecycleDays(value: string | null) {
  if (!value) return "-"
  const deletedAt = new Date(value).getTime()
  if (Number.isNaN(deletedAt)) return "-"
  const expiresAt = deletedAt + 10 * 24 * 60 * 60 * 1000
  const remaining = Math.ceil((expiresAt - Date.now()) / (24 * 60 * 60 * 1000))
  return `${Math.max(0, remaining)} 天`
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

function inferImportBrand(documentType: string, supplierName: string, suppliers: SupplierItem[]) {
  if (![PURCHASE_ORDER_DOCUMENT_TYPE, ...DETAIL_IMPORT_DOCUMENT_TYPES].includes(documentType)) return "cbanner_mens"
  const normalizedName = supplierName.trim()
  const upperName = normalizedName.toUpperCase()
  if (/\bNI\b/.test(upperName) || upperName.includes("NIKE") || normalizedName.includes("耐克")) return "ni"
  if (normalizedName.includes("笑脸") || normalizedName.includes("小莲")) return "smiley"
  const supplier = suppliers.find((item) => item.name === supplierName)
  if (supplier?.brand) return supplier.brand
  return "cbanner_mens"
}

function SearchableSelect({
  value,
  options,
  onChange,
  placeholder = "请选择",
  emptyText = "没有匹配项",
  onTouched,
}: {
  value: string
  options: SearchableOption[]
  onChange: (value: string) => void
  placeholder?: string
  emptyText?: string
  onTouched?: () => void
}) {
  const rootRef = useRef<HTMLDivElement>(null)
  const inputRef = useRef<HTMLInputElement>(null)
  const [open, setOpen] = useState(false)
  const [query, setQuery] = useState("")
  const selected = options.find((option) => option.value === value)
  const searchTerm = query.trim().toLowerCase()
  const visibleOptions = (searchTerm
    ? options.filter((option) => {
      const haystack = `${option.label} ${option.value} ${option.keywords || ""}`.toLowerCase()
      return haystack.includes(searchTerm)
    })
    : options
  ).slice(0, 80)

  useEffect(() => {
    function handlePointerDown(event: MouseEvent) {
      if (!rootRef.current?.contains(event.target as Node)) {
        setOpen(false)
        setQuery("")
      }
    }
    document.addEventListener("mousedown", handlePointerDown)
    return () => document.removeEventListener("mousedown", handlePointerDown)
  }, [])

  const selectValue = (nextValue: string) => {
    onTouched?.()
    onChange(nextValue)
    setOpen(false)
    setQuery("")
  }

  return (
    <div ref={rootRef} className="relative">
      <div className="relative">
        <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
        <input
          ref={inputRef}
          value={open ? query : selected?.label || ""}
          onFocus={() => { setOpen(true); setQuery("") }}
          onChange={(event) => { onTouched?.(); setQuery(event.target.value); setOpen(true) }}
          onKeyDown={(event) => {
            if (event.key === "Enter" && visibleOptions[0]) {
              event.preventDefault()
              selectValue(visibleOptions[0].value)
            }
            if (event.key === "Escape") {
              setOpen(false)
              setQuery("")
            }
          }}
          placeholder={placeholder}
          className="flex h-9 w-full cursor-pointer rounded-lg border border-input bg-card py-2 pl-9 pr-9 text-sm shadow-xs outline-none transition-colors placeholder:text-muted-foreground focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/35"
        />
        {value && (
          <button
            type="button"
            aria-label="清空"
            onClick={() => selectValue("")}
            className="absolute right-2 top-1/2 inline-flex h-6 w-6 -translate-y-1/2 cursor-pointer items-center justify-center rounded-md text-muted-foreground hover:bg-muted hover:text-foreground"
          >
            <X className="h-3.5 w-3.5" />
          </button>
        )}
      </div>
      {open && (
        <div className="absolute z-50 mt-1 max-h-72 w-full overflow-auto rounded-lg border border-border bg-popover p-1 text-sm shadow-lg">
          {visibleOptions.length === 0 ? (
            <div className="px-3 py-2 text-muted-foreground">{emptyText}</div>
          ) : (
            visibleOptions.map((option) => (
              <button
                key={`${option.value}-${option.label}`}
                type="button"
                onMouseDown={(event) => event.preventDefault()}
                onClick={() => selectValue(option.value)}
                className={`flex w-full cursor-pointer items-center justify-between gap-3 rounded-md px-3 py-2 text-left hover:bg-muted ${option.value === value ? "bg-muted text-foreground" : "text-foreground"}`}
              >
                <span className="min-w-0 truncate">{option.label}</span>
                {option.value === value && <span className="text-xs text-primary">已选</span>}
              </button>
            ))
          )}
          {searchTerm && visibleOptions.length === 80 && (
            <div className="border-t border-border px-3 py-2 text-xs text-muted-foreground">结果较多，请继续输入缩小范围</div>
          )}
        </div>
      )}
    </div>
  )
}

type InventoryPageProps = {
  mode?: "inventory" | "purchase-orders"
}

export function InventoryPage({ mode = "inventory" }: InventoryPageProps) {
  const isPurchasePage = mode === "purchase-orders"
  const [searchDateStart, setSearchDateStart] = useState("")
  const [searchDateEnd, setSearchDateEnd] = useState("")
  const [searchSupplier, setSearchSupplier] = useState("")
  const [searchWarehouse, setSearchWarehouse] = useState("")
  const [searchDocumentType, setSearchDocumentType] = useState("")
  const [searchSummary, setSearchSummary] = useState("")
  const [searchOriginalSku, setSearchOriginalSku] = useState("")
  const [searchProductCode, setSearchProductCode] = useState("")
  const [searchHandler, setSearchHandler] = useState("")
  const [submittedFilters, setSubmittedFilters] = useState<Record<string, string>>({})

  const [supplierOptions, setSupplierOptions] = useState<SupplierItem[]>([])
  const [warehouseOptions, setWarehouseOptions] = useState<WarehouseItem[]>([])
  const [customerShopOptions, setCustomerShopOptions] = useState<GeneralCustomerShopItem[]>([])
  const [accountSubjectOptions, setAccountSubjectOptions] = useState<InventoryAccountSubject[]>([])
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
  const [recycleOpen, setRecycleOpen] = useState(false)
  const [recycleItems, setRecycleItems] = useState<InventoryRecord[]>([])
  const [recycleTotal, setRecycleTotal] = useState(0)
  const [recyclePage, setRecyclePage] = useState(1)
  const [isRecycleLoading, setIsRecycleLoading] = useState(false)
  const [isRestoringId, setIsRestoringId] = useState<number | null>(null)
  const [selectedRecycleIds, setSelectedRecycleIds] = useState<Set<number>>(() => new Set())
  const [isBatchRestoring, setIsBatchRestoring] = useState(false)
  const [recycleBatchDeleteOpen, setRecycleBatchDeleteOpen] = useState(false)
  const [isRecycleBatchDeleting, setIsRecycleBatchDeleting] = useState(false)
  const [messageOpen, setMessageOpen] = useState(false)
  const [messageContent, setMessageContent] = useState({ title: "", description: "" })

  const [formOpen, setFormOpen] = useState(false)
  const [formMode, setFormMode] = useState<"create" | "edit">("create")
  const [formData, setFormData] = useState<Record<string, string>>({ ...EMPTY_FORM })
  const [editingId, setEditingId] = useState<number | null>(null)
  const [isSaving, setIsSaving] = useState(false)

  const [costDialogOpen, setCostDialogOpen] = useState(false)
  const [costFormData, setCostFormData] = useState<Record<string, string>>({ ...EMPTY_COST_FORM })
  const [costError, setCostError] = useState("")
  const [isUpdatingCosts, setIsUpdatingCosts] = useState(false)

  const [detailDocumentId, setDetailDocumentId] = useState<number | null>(null)
  const [activeTab, setActiveTab] = useState("records")
  const [recordCompletionStatus, setRecordCompletionStatus] = useState<CompletionStatus>("completed")
  const activeTabValue = isPurchasePage ? "purchase-orders" : activeTab
  const isPurchaseOrderTab = activeTabValue === "purchase-orders"

  const fileInputRef = useRef<HTMLInputElement>(null)
  const [isImporting, setIsImporting] = useState(false)
  const [importDialogOpen, setImportDialogOpen] = useState(false)
  const [importFormData, setImportFormData] = useState<Record<string, string>>({ ...EMPTY_IMPORT_FORM })
  const [importFile, setImportFile] = useState<File | null>(null)
  const [importError, setImportError] = useState("")
  const [requirementsDialogOpen, setRequirementsDialogOpen] = useState(false)
  const [requirementDrafts, setRequirementDrafts] = useState<Record<string, string>>({})
  const [selectedRequirementBrand, setSelectedRequirementBrand] = useState<PurchaseOrderRequirementBrand>("cbanner_mens")
  const [requirementsError, setRequirementsError] = useState("")
  const [isRequirementsLoading, setIsRequirementsLoading] = useState(false)
  const [isSavingRequirement, setIsSavingRequirement] = useState(false)

  useEffect(() => {
    async function loadOptions() {
      try {
        const [suppliersRes, warehousesRes, customerShopsRes, accountSubjectsRes] = await Promise.all([
          listSuppliers(),
          listWarehouses(),
          listGeneralCustomerShops(),
          listInventoryAccountSubjects(),
        ])
        setSupplierOptions(suppliersRes.items)
        setWarehouseOptions(warehousesRes.items)
        setCustomerShopOptions(customerShopsRes.items)
        setAccountSubjectOptions(accountSubjectsRes.items)
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
          document_type: isPurchaseOrderTab ? PURCHASE_ORDER_DOCUMENT_TYPE : submittedFilters.document_type || undefined,
          exclude_document_type: isPurchaseOrderTab ? undefined : PURCHASE_ORDER_DOCUMENT_TYPE,
          summary: submittedFilters.summary || undefined,
          original_sku: isPurchaseOrderTab ? undefined : submittedFilters.original_sku || undefined,
          product_code: submittedFilters.product_code || undefined,
          handler: submittedFilters.handler || undefined,
          completion_status: isPurchaseOrderTab ? undefined : recordCompletionStatus,
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
  }, [isPurchaseOrderTab, page, pageSize, recordCompletionStatus, reloadToken, submittedFilters])

  useEffect(() => { setSelectedIds(new Set()) }, [page, recordCompletionStatus, submittedFilters])

  const showMessage = useCallback((title: string, description: string) => {
    setMessageContent({ title, description })
    setMessageOpen(true)
  }, [])

  const openRequirementDialog = async () => {
    setRequirementsDialogOpen(true)
    setRequirementsError("")
    setRequirementDrafts({})
    setIsRequirementsLoading(true)
    try {
      const response = await listPurchaseOrderRequirements()
      const drafts: Record<string, string> = {}
      for (const item of response.items) {
        drafts[item.brand] = item.content ?? ""
      }
      for (const option of PURCHASE_REQUIREMENT_BRAND_OPTIONS) {
        if (drafts[option.value] === undefined) drafts[option.value] = ""
      }
      setRequirementDrafts(drafts)
      if (!response.items.some((item) => item.brand === selectedRequirementBrand)) {
        setSelectedRequirementBrand("cbanner_mens")
      }
    } catch (e) {
      setRequirementDrafts({})
      setRequirementsError(getErrorMessage(e))
    } finally {
      setIsRequirementsLoading(false)
    }
  }

  const handleRequirementBrandChange = (value: string) => {
    const option = PURCHASE_REQUIREMENT_BRAND_OPTIONS.find((item) => item.value === value)
    if (option) setSelectedRequirementBrand(option.value)
  }

  const handleSavePurchaseRequirement = async () => {
    setRequirementsError("")
    setIsSavingRequirement(true)
    try {
      const result = await updatePurchaseOrderRequirement(
        selectedRequirementBrand,
        requirementDrafts[selectedRequirementBrand] ?? "",
      )
      setRequirementDrafts((prev) => ({ ...prev, [result.item.brand]: result.item.content ?? "" }))
      showMessage("保存成功", "订单要求已更新")
    } catch (e) {
      setRequirementsError(getErrorMessage(e))
    } finally {
      setIsSavingRequirement(false)
    }
  }

  const loadRecycleBin = useCallback(async () => {
    setIsRecycleLoading(true)
    try {
      const response = await listInventoryRecycleBin({
        page: recyclePage,
        pageSize: 10,
        document_type: isPurchasePage ? PURCHASE_ORDER_DOCUMENT_TYPE : undefined,
        exclude_document_type: isPurchasePage ? undefined : PURCHASE_ORDER_DOCUMENT_TYPE,
      })
      setRecycleItems(response.items)
      setRecycleTotal(response.total)
    } catch (e) {
      setRecycleItems([])
      setRecycleTotal(0)
      showMessage("回收站加载失败", getErrorMessage(e))
    } finally {
      setIsRecycleLoading(false)
    }
  }, [isPurchasePage, recyclePage, showMessage])

  useEffect(() => {
    if (recycleOpen) void loadRecycleBin()
  }, [loadRecycleBin, recycleOpen])

  useEffect(() => {
    setSelectedRecycleIds(new Set())
  }, [recyclePage, recycleOpen])

  useEffect(() => {
    setRecyclePage(1)
    setSelectedRecycleIds(new Set())
    setRecycleItems([])
    setRecycleTotal(0)
  }, [isPurchasePage])

  const openCreate = () => {
    setFormMode("create")
    setFormData({
      ...EMPTY_FORM,
      date: todayInputValue(),
      document_type: isPurchaseOrderTab ? PURCHASE_ORDER_DOCUMENT_TYPE : "",
    })
    setEditingId(null)
    void listInventoryAccountSubjects()
      .then((response) => setAccountSubjectOptions(response.items))
      .catch(() => undefined)
    setFormOpen(true)
  }

  const openImportDialog = () => {
    setImportError("")
    setImportFile(null)
    if (fileInputRef.current) fileInputRef.current.value = ""
    setImportFormData((prev) => ({
      ...EMPTY_IMPORT_FORM,
      date: todayInputValue(),
      document_type: isPurchaseOrderTab ? PURCHASE_ORDER_DOCUMENT_TYPE : "",
      handler: prev.handler || "",
    }))
    setImportDialogOpen(true)
  }

  const openEdit = (item: InventoryRecord) => {
    setFormMode("edit")
    setEditingId(item.id)
    setFormData({
      date: item.date || "",
      supplier: item.supplier || "",
      warehouse: item.warehouse || "",
      document_type: item.document_type || "",
      delivery_date: typeof item.extra_fields?.delivery_date === "string" ? item.extra_fields.delivery_date : "",
      handler: item.handler || "",
      summary: item.summary || "",
      additional_note: item.additional_note || "",
    })
    setFormOpen(true)
  }

  const handleSave = async () => {
    const shouldCreateAccountingDetail = formMode === "create" && ACCOUNTING_DOCUMENT_TYPE_SET.has(formData.document_type || "")
    if (shouldCreateAccountingDetail && (!formData.detail_subject?.trim() || !formData.detail_amount?.trim())) {
      showMessage("保存失败", "请填写费用项目名/科目和金额")
      return
    }
    setIsSaving(true)
    try {
      const { detail_subject, detail_amount, detail_remark, delivery_date, ...recordFormData } = formData
      if (formData.document_type === PURCHASE_ORDER_DOCUMENT_TYPE && !delivery_date) {
        showMessage("保存失败", "请选择交货日期")
        setIsSaving(false)
        return
      }
      const payload = {
        ...recordFormData,
        extra_fields: formData.document_type === PURCHASE_ORDER_DOCUMENT_TYPE && delivery_date ? { delivery_date } : undefined,
        warehouse: ACCOUNTING_DOCUMENT_TYPE_SET.has(formData.document_type || "") ? "" : formData.warehouse,
      }
      if (formMode === "create") {
        const result = await createInventoryRecord(payload)
        if (shouldCreateAccountingDetail) {
          await createDetail(result.item.id, {
            product_code: "",
            product_name: detail_subject,
            amount: detail_amount,
            remark: detail_remark,
          })
        }
      } else if (editingId !== null) {
        await updateInventoryRecord(editingId, payload)
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
      const result = await deleteInventoryRecord(deleteTarget.id)
      setSelectedIds((prev) => { const next = new Set(prev); next.delete(deleteTarget.id); return next })
      setReloadToken((t) => t + 1)
      showMessage("已移入回收站", result.message)
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
      const result = await batchDeleteInventory(Array.from(selectedIds))
      setSelectedIds(new Set())
      setReloadToken((t) => t + 1)
      showMessage("已移入回收站", result.message)
    } catch (e) {
      showMessage("批量删除失败", getErrorMessage(e))
    } finally {
      setIsBatchDeleting(false)
      setBatchDeleteOpen(false)
    }
  }

  const handleRestoreRecord = async (recordId: number) => {
    setIsRestoringId(recordId)
    try {
      const result = await restoreInventoryRecord(recordId)
      setSelectedRecycleIds((prev) => {
        const next = new Set(prev)
        next.delete(recordId)
        return next
      })
      showMessage("恢复成功", result.message)
      await loadRecycleBin()
      setReloadToken((t) => t + 1)
    } catch (e) {
      showMessage("恢复失败", getErrorMessage(e))
    } finally {
      setIsRestoringId(null)
    }
  }

  const handleToggleRecycleSelect = (id: number) => {
    setSelectedRecycleIds((prev) => {
      const next = new Set(prev)
      next.has(id) ? next.delete(id) : next.add(id)
      return next
    })
  }

  const handleToggleRecycleSelectAll = () => {
    setSelectedRecycleIds((prev) => {
      const allSelected = recycleItems.length > 0 && recycleItems.every((item) => prev.has(item.id))
      const next = new Set(prev)
      for (const item of recycleItems) allSelected ? next.delete(item.id) : next.add(item.id)
      return next
    })
  }

  const handleBatchRestore = async () => {
    const ids = Array.from(selectedRecycleIds)
    if (ids.length === 0) return
    setIsBatchRestoring(true)
    try {
      const result = await batchRestoreInventory(ids)
      setSelectedRecycleIds(new Set())
      showMessage("批量恢复完成", result.message)
      await loadRecycleBin()
      setReloadToken((t) => t + 1)
    } catch (e) {
      showMessage("批量恢复失败", getErrorMessage(e))
    } finally {
      setIsBatchRestoring(false)
    }
  }

  const handleRecycleBatchDeleteConfirm = async () => {
    const ids = Array.from(selectedRecycleIds)
    if (ids.length === 0) {
      setRecycleBatchDeleteOpen(false)
      return
    }
    setIsRecycleBatchDeleting(true)
    try {
      const result = await batchPermanentlyDeleteInventory(ids)
      setSelectedRecycleIds(new Set())
      showMessage("批量删除完成", result.message)
      await loadRecycleBin()
      setReloadToken((t) => t + 1)
    } catch (e) {
      showMessage("批量删除失败", getErrorMessage(e))
    } finally {
      setIsRecycleBatchDeleting(false)
      setRecycleBatchDeleteOpen(false)
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

  const handleImport = async () => {
    setImportError("")
    if (!importFile) {
      setImportError("请选择 Excel 文件")
      return
    }
    if (!importFormData.document_type) {
      setImportError("请选择单据类型")
      return
    }
    const isWholesaleImport = WHOLESALE_DOCUMENT_TYPES.has(importFormData.document_type)
    const isTransferImport = TRANSFER_DOCUMENT_TYPES.has(importFormData.document_type)
    const isStockAdjustmentImport = STOCK_ADJUSTMENT_DOCUMENT_TYPES.has(importFormData.document_type)
    const canReadDocumentFieldsFromExcel = isPurchaseOrderTab && importFormData.document_type === PURCHASE_ORDER_DOCUMENT_TYPE
    if (!canReadDocumentFieldsFromExcel && ((!isStockAdjustmentImport && !importFormData.supplier) || !importFormData.warehouse || !importFormData.handler || !importFormData.summary)) {
      const requiredFields = isTransferImport ? "出货仓库、入货仓库" : isWholesaleImport ? "收货客户、发货仓库" : "供货单位、收货仓库"
      setImportError(`请填写${isStockAdjustmentImport ? "仓库" : requiredFields}、经手人和摘要`)
      return
    }
    if (!canReadDocumentFieldsFromExcel && importFormData.document_type === PURCHASE_ORDER_DOCUMENT_TYPE && !importFormData.delivery_date) {
      setImportError("请选择交货日期")
      return
    }
    setIsImporting(true)
    try {
      const result = await importPurchaseInventory({
        file: importFile,
        date: importFormData.date,
        delivery_date: importFormData.delivery_date,
        supplier: importFormData.supplier,
        warehouse: importFormData.warehouse,
        document_type: importFormData.document_type,
        handler: importFormData.handler,
        summary: importFormData.summary,
        brand: inferImportBrand(importFormData.document_type, importFormData.supplier, supplierOptions),
      })
      showMessage("导入完成", result.message)
      setImportDialogOpen(false)
      setImportFile(null)
      setReloadToken((t) => t + 1)
    } catch (err) {
      setImportError(getErrorMessage(err))
    } finally {
      setIsImporting(false)
      if (fileInputRef.current) fileInputRef.current.value = ""
    }
  }

  const handleExport = async (purchaseExportMode?: PurchaseExportMode) => {
    try {
      if (ACCOUNTING_DOCUMENT_TYPE_SET.has(submittedFilters.document_type || "")) {
        showMessage("暂不支持导出", "应付款/应收款四类单据暂时不导出 Excel")
        return
      }
      const selectedExportIds = Array.from(selectedIds)
      const a = document.createElement("a")
      a.href = buildInventoryExportUrl({
        ids: selectedExportIds.length > 0 ? selectedExportIds : undefined,
        date_start: submittedFilters.date_start || undefined,
        date_end: submittedFilters.date_end || undefined,
        supplier: submittedFilters.supplier || undefined,
        warehouse: submittedFilters.warehouse || undefined,
        document_type: isPurchaseOrderTab ? PURCHASE_ORDER_DOCUMENT_TYPE : submittedFilters.document_type || undefined,
        exclude_document_type: isPurchaseOrderTab ? undefined : PURCHASE_ORDER_DOCUMENT_TYPE,
        summary: submittedFilters.summary || undefined,
        original_sku: isPurchaseOrderTab ? undefined : submittedFilters.original_sku || undefined,
        product_code: submittedFilters.product_code || undefined,
        handler: submittedFilters.handler || undefined,
        completion_status: isPurchaseOrderTab ? undefined : recordCompletionStatus,
        purchase_export_mode: isPurchaseOrderTab ? purchaseExportMode ?? "summary" : undefined,
      })
      a.rel = "noopener"
      a.click()
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
      document_type: isPurchaseOrderTab ? PURCHASE_ORDER_DOCUMENT_TYPE : searchDocumentType,
      summary: searchSummary,
      original_sku: isPurchaseOrderTab ? "" : searchOriginalSku,
      product_code: isPurchaseOrderTab ? searchOriginalSku : searchProductCode,
      handler: searchHandler,
    })
  }

  const openCostDialog = () => {
    setCostError("")
    setCostFormData({ ...EMPTY_COST_FORM })
    setCostDialogOpen(true)
  }

  const parseCostUpdates = () => {
    const updates: Record<string, string> = {}
    const singleCode = costFormData.product_code.trim()
    const singlePrice = costFormData.unit_price.trim()
    if (singleCode || singlePrice) {
      if (!singleCode || !singlePrice) throw new Error("单个修改需要同时填写货号和新单价")
      updates[singleCode] = singlePrice
    }
    for (const line of costFormData.batch_text.split(/\r?\n/)) {
      const trimmed = line.trim()
      if (!trimmed) continue
      const parts = trimmed.split(/[\s,，\t]+/).filter(Boolean)
      if (parts.length < 2) throw new Error(`无法识别：${trimmed}`)
      updates[parts[0]] = parts[1]
    }
    return updates
  }

  const handleBatchUpdateCosts = async () => {
    setCostError("")
    let updates: Record<string, string>
    try {
      updates = parseCostUpdates()
    } catch (error) {
      setCostError(getErrorMessage(error))
      return
    }
    if (!costFormData.date_start || !costFormData.date_end) {
      setCostError("请选择开始日期和结束日期")
      return
    }
    if (Object.keys(updates).length === 0) {
      setCostError("请填写至少一个货号和新单价")
      return
    }
    setIsUpdatingCosts(true)
    try {
      const result = await batchUpdateInventoryCosts({
        date_start: costFormData.date_start,
        date_end: costFormData.date_end,
        updates,
      })
      setCostDialogOpen(false)
      setReloadToken((t) => t + 1)
      showMessage("批量改价完成", result.message)
    } catch (error) {
      setCostError(getErrorMessage(error))
    } finally {
      setIsUpdatingCosts(false)
    }
  }

  const clearSearch = () => {
    setSearchDateStart("")
    setSearchDateEnd("")
    setSearchSupplier("")
    setSearchWarehouse("")
    setSearchDocumentType("")
    setSearchSummary("")
    setSearchOriginalSku("")
    setSearchProductCode("")
    setSearchHandler("")
    setPage(1)
    setSubmittedFilters(isPurchaseOrderTab ? { document_type: PURCHASE_ORDER_DOCUMENT_TYPE } : {})
  }

  const handleCompletionTabChange = (value: string) => {
    setRecordCompletionStatus(value as CompletionStatus)
    setPage(1)
    setSelectedIds(new Set())
  }

  const handleMainTabChange = (value: string) => {
    if (isPurchasePage) return
    setActiveTab(value)
    setPage(1)
    setSelectedIds(new Set())
    setSearchDocumentType("")
    setSubmittedFilters({})
  }

  const hasFilters = Object.entries(submittedFilters).some(
    ([key, value]) => value && !(isPurchaseOrderTab && key === "document_type" && value === PURCHASE_ORDER_DOCUMENT_TYPE),
  )
  const totalPages = Math.max(1, Math.ceil(total / pageSize))
  const recycleTotalPages = Math.max(1, Math.ceil(recycleTotal / 10))
  const allSelected = items.length > 0 && items.every((item) => selectedIds.has(item.id))
  const someSelected = items.some((item) => selectedIds.has(item.id))
  const allRecycleSelected = recycleItems.length > 0 && recycleItems.every((item) => selectedRecycleIds.has(item.id))
  const recycleActionBusy = isBatchRestoring || isRecycleBatchDeleting
  const detailRecord = detailDocumentId === null ? null : items.find((item) => item.id === detailDocumentId) ?? null
  const completionLabel = isPurchaseOrderTab ? "采购单" : COMPLETION_TABS.find((item) => item.value === recordCompletionStatus)?.label ?? "单据"
  const pageRange = buildPageRange(page, totalPages)
  const isFormWholesale = WHOLESALE_DOCUMENT_TYPES.has(formData.document_type || "")
  const isFormTransfer = TRANSFER_DOCUMENT_TYPES.has(formData.document_type || "")
  const isFormStockAdjustment = STOCK_ADJUSTMENT_DOCUMENT_TYPES.has(formData.document_type || "")
  const isFormPayable = PAYABLE_DOCUMENT_TYPES.has(formData.document_type || "")
  const isFormReceivable = RECEIVABLE_DOCUMENT_TYPES.has(formData.document_type || "")
  const isFormAccounting = ACCOUNTING_DOCUMENT_TYPE_SET.has(formData.document_type || "")
  const shouldShowAccountingInlineDetail = formMode === "create" && isFormAccounting
  const isImportWholesale = WHOLESALE_DOCUMENT_TYPES.has(importFormData.document_type)
  const isImportTransfer = TRANSFER_DOCUMENT_TYPES.has(importFormData.document_type)
  const isImportStockAdjustment = STOCK_ADJUSTMENT_DOCUMENT_TYPES.has(importFormData.document_type)
  const isImportPurchaseOrder = isPurchaseOrderTab && importFormData.document_type === PURCHASE_ORDER_DOCUMENT_TYPE
  const supplierSelectOptions = supplierOptions.map((supplier) => ({
    value: supplier.name,
    label: supplier.name,
    keywords: [supplier.factory_code, supplier.contact, supplier.address].filter(Boolean).join(" "),
  }))
  const warehouseSelectOptions = warehouseOptions.map((warehouse) => ({
    value: warehouse.name,
    label: warehouse.name,
  }))
  const customerShopSelectOptions = customerShopOptions.map((shop) => ({
    value: shop.shop_name,
    label: `${shop.customer_name} / ${shop.shop_name}`,
    keywords: shop.customer_name,
  }))
  const formCounterpartyOptions = isFormTransfer ? warehouseSelectOptions : (isFormWholesale || isFormReceivable) ? customerShopSelectOptions : supplierSelectOptions
  const importCounterpartyOptions = isImportTransfer ? warehouseSelectOptions : isImportWholesale ? customerShopSelectOptions : supplierSelectOptions
  const documentTypeOptions = INVENTORY_DOCUMENT_TYPES
  const detailImportDocumentTypeOptions = DETAIL_IMPORT_DOCUMENT_TYPES
  const currentRequirementContent = requirementDrafts[selectedRequirementBrand] ?? ""

  return (
    <div className="app-page">
      <div className="app-content">
        <div className="page-header">
          <div>
            <h1 className="page-title">{isPurchasePage ? "采购单管理" : "进销存管理"}</h1>
          </div>
          <div className="flex items-center gap-2">
            <Button variant="outline" size="sm" onClick={openImportDialog} disabled={isImporting} className="cursor-pointer">
              <Upload className="h-4 w-4" />
              <span className="ml-2 hidden sm:inline">{isImporting ? "导入中..." : isPurchaseOrderTab ? "导入采购单" : "导入Excel"}</span>
            </Button>
            {isPurchaseOrderTab ? (
              <>
                <Button variant="outline" size="sm" onClick={() => handleExport("summary")} disabled={total === 0 || isLoading} className="cursor-pointer">
                  <Download className="h-4 w-4" />
                  <span className="ml-2 hidden sm:inline">汇总导出</span>
                </Button>
                <Button variant="outline" size="sm" onClick={() => handleExport("size_rows")} disabled={total === 0 || isLoading} className="cursor-pointer">
                  <Download className="h-4 w-4" />
                  <span className="ml-2 hidden sm:inline">尺码明细导出</span>
                </Button>
                <Button variant="outline" size="sm" onClick={() => handleExport("production_order")} disabled={total === 0 || isLoading} className="cursor-pointer">
                  <Download className="h-4 w-4" />
                  <span className="ml-2 hidden sm:inline">生产采购单导出</span>
                </Button>
                <Button variant="outline" size="sm" onClick={openRequirementDialog} disabled={isRequirementsLoading} className="cursor-pointer">
                  <FileText className="h-4 w-4" />
                  <span className="ml-2 hidden sm:inline">订单要求</span>
                </Button>
              </>
            ) : (
              <Button variant="outline" size="sm" onClick={() => handleExport()} disabled={total === 0 || isLoading} className="cursor-pointer">
                <Download className="h-4 w-4" />
                <span className="ml-2 hidden sm:inline">导出Excel</span>
              </Button>
            )}
            {!isPurchasePage && (
              <Button variant="outline" size="sm" onClick={openCostDialog} disabled={isUpdatingCosts} className="cursor-pointer">
                <BadgeDollarSign className="h-4 w-4" />
                <span className="ml-2 hidden sm:inline">批量改成本价</span>
              </Button>
            )}
            <Button
              variant="outline"
              size="sm"
              onClick={() => {
                setRecyclePage(1)
                setSelectedRecycleIds(new Set())
                setRecycleItems([])
                setRecycleTotal(0)
                setRecycleOpen(true)
              }}
              className="cursor-pointer"
            >
              <Trash2 className="h-4 w-4" />
              <span className="ml-2 hidden sm:inline">回收站</span>
            </Button>
            <Button size="sm" onClick={openCreate} className="cursor-pointer">
              <Plus className="h-4 w-4" />
              <span className="ml-2 hidden sm:inline">{isPurchaseOrderTab ? "新增采购单" : "新增经营历程"}</span>
            </Button>
          </div>
        </div>

        <Tabs defaultValue="records" value={activeTab} onValueChange={handleMainTabChange}>
          {!isPurchasePage && (
            <TabsList className="rounded-xl bg-muted/60 p-1">
              <TabsTrigger value="records">经营历程</TabsTrigger>
              <TabsTrigger value="ending">期末库存</TabsTrigger>
            </TabsList>
          )}

          {(activeTabValue === "records" || activeTabValue === "purchase-orders") && (
            <>
              {!isPurchaseOrderTab && (
                <div className="surface-panel p-1.5">
                  <Tabs defaultValue="completed" value={recordCompletionStatus} onValueChange={handleCompletionTabChange}>
                    <TabsList className="rounded-xl bg-muted/60 p-1">
                      {COMPLETION_TABS.map((item) => (
                        <TabsTrigger key={item.value} value={item.value} className="cursor-pointer">
                          {item.label}
                        </TabsTrigger>
                      ))}
                    </TabsList>
                  </Tabs>
                </div>
              )}
              <div className="surface-panel p-4">
                <div className="grid gap-3 xl:grid-cols-[1fr_auto] xl:items-end">
                  <div className="grid gap-3 lg:grid-cols-12">
                    <div className="space-y-1.5 lg:col-span-6 xl:col-span-5">
                      <Label className="text-xs text-muted-foreground">日期范围</Label>
                      <div className="grid grid-cols-[minmax(8.75rem,1fr)_auto_minmax(8.75rem,1fr)] items-center gap-2">
                        <input
                          type="date"
                          value={searchDateStart}
                          max={searchDateEnd || undefined}
                          onChange={(e) => setSearchDateStart(e.target.value)}
                          className="h-9 min-w-0 rounded-lg border border-input bg-card px-3 py-2 text-sm shadow-xs outline-none transition-colors focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/35"
                        />
                        <span className="text-xs text-muted-foreground">至</span>
                        <input
                          type="date"
                          value={searchDateEnd}
                          min={searchDateStart || undefined}
                          onChange={(e) => setSearchDateEnd(e.target.value)}
                          className="h-9 min-w-0 rounded-lg border border-input bg-card px-3 py-2 text-sm shadow-xs outline-none transition-colors focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/35"
                        />
                      </div>
                    </div>
                    {!isPurchaseOrderTab && (
                      <div className="space-y-1.5 lg:col-span-3 xl:col-span-2">
                        <Label className="text-xs text-muted-foreground">单据类型</Label>
                        <Select
                          value={searchDocumentType}
                          onChange={(e) => setSearchDocumentType(e.target.value)}
                          className="w-full"
                        >
                          <option value="">全部</option>
                          {documentTypeOptions.map((dt) => (<option key={dt} value={dt}>{dt}</option>))}
                        </Select>
                      </div>
                    )}
                    <div className="space-y-1.5 lg:col-span-3 xl:col-span-2">
                      <Label className="text-xs text-muted-foreground">仓库</Label>
                      <Select value={searchWarehouse} onChange={(e) => setSearchWarehouse(e.target.value)} className="w-full">
                        <option value="">全部</option>
                        {warehouseOptions.map((w) => (<option key={w.id} value={w.name}>{w.name}</option>))}
                      </Select>
                    </div>
                    <div className="space-y-1.5 lg:col-span-3 xl:col-span-3">
                      <Label className="text-xs text-muted-foreground">客户/供应商</Label>
                      <Input value={searchSupplier} onChange={(e) => setSearchSupplier(e.target.value)} placeholder="客户/供应商" className="h-9" />
                    </div>
                    <div className="space-y-1.5 lg:col-span-3 xl:col-span-2">
                      <Label className="text-xs text-muted-foreground">经手人</Label>
                      <Input value={searchHandler} onChange={(e) => setSearchHandler(e.target.value)} placeholder="经手人" className="h-9" />
                    </div>
                    <div className="space-y-1.5 lg:col-span-3 xl:col-span-2">
                      <Label className="text-xs text-muted-foreground">{isPurchaseOrderTab ? "货号" : "原始货号"}</Label>
                      <Input value={searchOriginalSku} onChange={(e) => setSearchOriginalSku(e.target.value)} placeholder={isPurchaseOrderTab ? "货号" : "原始货号"} className="h-9" />
                    </div>
                    {!isPurchaseOrderTab && (
                      <div className="space-y-1.5 lg:col-span-3 xl:col-span-2">
                        <Label className="text-xs text-muted-foreground">商品编码</Label>
                        <Input value={searchProductCode} onChange={(e) => setSearchProductCode(e.target.value)} placeholder="商品编码" className="h-9" />
                      </div>
                    )}
                    <div className="space-y-1.5 lg:col-span-6 xl:col-span-4">
                      <Label className="text-xs text-muted-foreground">备注</Label>
                      <Input value={searchSummary} onChange={(e) => setSearchSummary(e.target.value)} placeholder="摘要/备注" className="h-9" />
                    </div>
                  </div>
                  <div className="flex flex-wrap gap-2 xl:justify-end">
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
              <div className="table-panel overflow-x-auto">
                <table className={isPurchaseOrderTab ? "w-full min-w-[1280px] table-fixed text-sm" : "w-full min-w-[1320px] table-fixed text-sm"}>
                  <colgroup>
                    <col className="w-12" />
                    <col className={isPurchaseOrderTab ? "w-40" : "w-36"} />
                    <col className="w-28" />
                    {isPurchaseOrderTab && <col className="w-28" />}
                    {!isPurchaseOrderTab && <col className="w-28" />}
                    <col className={isPurchaseOrderTab ? "w-48" : "w-44"} />
                    {!isPurchaseOrderTab && <col className="w-20" />}
                    {!isPurchaseOrderTab && <col className="w-24" />}
                    {!isPurchaseOrderTab && <col className="w-48" />}
                    <col className="w-24" />
                    <col />
                    {isPurchaseOrderTab && <col />}
                    <col className="w-28" />
                  </colgroup>
                  <thead>
                    <tr className="table-head-row">
                      <th className="px-4 py-3"></th>
                      <th className="px-4 py-3 font-medium">单据编号</th>
                      <th className="px-4 py-3 font-medium">{isPurchaseOrderTab ? "订货日期" : "日期"}</th>
                      {isPurchaseOrderTab && <th className="px-4 py-3 font-medium">交货日期</th>}
                      {!isPurchaseOrderTab && <th className="px-4 py-3 font-medium">单据类型</th>}
                      <th className="px-4 py-3 font-medium">供应商</th>
                      {!isPurchaseOrderTab && <th className="px-4 py-3 text-right font-medium">总数</th>}
                      {!isPurchaseOrderTab && <th className="px-4 py-3 text-right font-medium">金额</th>}
                      {!isPurchaseOrderTab && <th className="px-4 py-3 font-medium">仓库</th>}
                      <th className="px-4 py-3 font-medium">经手人</th>
                      <th className="px-4 py-3 font-medium">摘要</th>
                      {isPurchaseOrderTab && <th className="px-4 py-3 font-medium">附加说明</th>}
                      <th className="px-4 py-3 text-center font-medium">操作</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-border">
                    {isLoading && (
                      <tr>
                        <td colSpan={isPurchaseOrderTab ? 9 : 11} className="px-4 py-12 text-center text-muted-foreground">加载中...</td>
                      </tr>
                    )}
                    {!isLoading && !error && items.length === 0 && (
                      <tr>
                        <td colSpan={isPurchaseOrderTab ? 9 : 11} className="px-4 py-12 text-center text-muted-foreground">
                          {hasFilters ? `没有符合条件的${completionLabel}` : `暂无${completionLabel}`}
                        </td>
                      </tr>
                    )}
                    {!isLoading && !error && items.map((item) => {
                      const isAccountingRow = ACCOUNTING_DOCUMENT_TYPE_SET.has(item.document_type || "")
                      return (
                        <tr key={item.id} className="table-row">
                          <td className="px-4 py-3 align-middle">
                            <input
                              type="checkbox"
                              checked={selectedIds.has(item.id)}
                              onChange={() => handleToggleSelect(item.id)}
                              className="h-4 w-4 cursor-pointer rounded border border-input accent-primary"
                            />
                          </td>
                          <td className="px-4 py-3 align-middle font-mono text-xs leading-4 tabular-nums">
                            <span className="block truncate" title={String(item.document_number || item.id)}>{item.document_number || item.id}</span>
                          </td>
                          <td className="px-4 py-3 align-middle whitespace-nowrap tabular-nums">{item.date || "-"}</td>
                          {isPurchaseOrderTab && (
                            <td className="px-4 py-3 align-middle whitespace-nowrap tabular-nums">
                              {typeof item.extra_fields?.delivery_date === "string" ? item.extra_fields.delivery_date : "-"}
                            </td>
                          )}
                          {!isPurchaseOrderTab && (
                            <td className="px-4 py-3 align-middle whitespace-nowrap">
                              {item.document_type ? (
                                <span className={`inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium ${OUTBOUND_DOCUMENT_TYPES.has(item.document_type) ? "bg-red-100 text-red-700"
                                    : INBOUND_DOCUMENT_TYPES.has(item.document_type) ? "bg-green-100 text-green-700"
                                      : "bg-blue-100 text-blue-700"
                                  }`}>
                                  {item.document_type}
                                </span>
                              ) : "-"}
                            </td>
                          )}
                          <td className="px-4 py-3 align-middle">
                            <span className="block truncate" title={item.supplier || ""}>{item.supplier || "-"}</span>
                          </td>
                          {!isPurchaseOrderTab && <td className="px-4 py-3 align-middle text-right font-mono tabular-nums">{isAccountingRow ? "" : item.total_count || "-"}</td>}
                          {!isPurchaseOrderTab && <td className="px-4 py-3 align-middle text-right font-mono tabular-nums">{isAccountingRow ? "" : item.amount || "-"}</td>}
                          {!isPurchaseOrderTab && (
                            <td className="px-4 py-3 align-middle">
                              <span className="block truncate" title={item.warehouse || ""}>{isAccountingRow ? "" : item.warehouse || "-"}</span>
                            </td>
                          )}
                          <td className="px-4 py-3 align-middle">
                            <span className="block truncate" title={item.handler || ""}>{item.handler || "-"}</span>
                          </td>
                          <td className="px-4 py-3 align-middle">
                            <span className="block whitespace-normal break-words leading-5" title={item.summary || ""}>{item.summary || "-"}</span>
                          </td>
                          {isPurchaseOrderTab && (
                            <td className="px-4 py-3 align-middle">
                              <span className="block whitespace-normal break-words leading-5" title={item.additional_note || ""}>{item.additional_note || "-"}</span>
                            </td>
                          )}
                          <td className="px-4 py-3 align-middle">
                            <div className="flex items-center justify-center gap-1">
                              <Button variant="ghost" size="icon-sm" onClick={() => setDetailDocumentId(item.id)} className="cursor-pointer" title="明细">
                                <List className="h-4 w-4" />
                              </Button>
                              <Button variant="ghost" size="icon-sm" onClick={() => openEdit(item)} className="cursor-pointer" title="编辑">
                                <Edit className="h-4 w-4" />
                              </Button>
                              <Button variant="ghost" size="icon-sm" onClick={() => setDeleteTarget(item)} className="cursor-pointer" title="删除">
                                <Trash2 className="h-4 w-4 text-destructive" />
                              </Button>
                            </div>
                          </td>
                        </tr>
                      )
                    })}
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
                      className="h-8 w-16 rounded-md border border-input bg-card px-2 text-center text-sm outline-none focus-visible:border-ring focus-visible:ring-2 focus-visible:ring-ring/35"
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
                {completionLabel}共 {total} 条 · 第 {total === 0 ? 0 : (page - 1) * pageSize + 1}-{Math.min(page * pageSize, total)} 条
              </div>
            </>
          )}
          {!isPurchasePage && activeTabValue === "ending" && <EndingInventoryTab />}
        </Tabs>
      </div>

      {/* Form Dialog */}
      <Dialog open={formOpen} onOpenChange={setFormOpen}>
        <DialogContent className="max-w-xl">
          <DialogHeader>
            <DialogTitle>{formMode === "create" ? (isPurchaseOrderTab ? "新增采购单" : "新增经营历程") : (formData.document_type === PURCHASE_ORDER_DOCUMENT_TYPE ? "编辑采购单" : "编辑经营历程")}</DialogTitle>
          </DialogHeader>
          <div className="grid grid-cols-2 gap-4 py-2">
            {/* Date */}
            <div className="space-y-1.5">
              <Label htmlFor="form-date">{formData.document_type === PURCHASE_ORDER_DOCUMENT_TYPE ? "订货日期" : "日期"}</Label>
              <input
                id="form-date"
                type="date"
                value={formData.date || ""}
                onChange={(e) => setFormData((prev) => ({ ...prev, date: e.target.value }))}
                className="flex h-9 w-full rounded-lg border border-input bg-card px-3 py-2 text-sm shadow-xs outline-none transition-colors focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/35"
              />
            </div>
            {!isPurchaseOrderTab && (
              <div className="space-y-1.5">
                <Label htmlFor="form-doc-type">单据类型</Label>
                <Select
                  value={formData.document_type || ""}
                  onChange={(e) => setFormData((prev) => ({
                    ...prev,
                    document_type: e.target.value,
                    supplier: "",
                    detail_subject: "",
                    detail_amount: "",
                    detail_remark: "",
                    delivery_date: e.target.value === PURCHASE_ORDER_DOCUMENT_TYPE ? prev.delivery_date : "",
                  }))}
                >
                  <option value="">请选择</option>
                  {documentTypeOptions.map((dt) => (<option key={dt} value={dt}>{dt}</option>))}
                </Select>
              </div>
            )}
            {formData.document_type === PURCHASE_ORDER_DOCUMENT_TYPE && (
              <div className="space-y-1.5">
                <Label htmlFor="form-delivery-date">交货日期</Label>
                <input
                  id="form-delivery-date"
                  type="date"
                  value={formData.delivery_date || ""}
                  min={formData.date || undefined}
                  onChange={(e) => setFormData((prev) => ({ ...prev, delivery_date: e.target.value }))}
                  className="flex h-9 w-full rounded-lg border border-input bg-card px-3 py-2 text-sm shadow-xs outline-none transition-colors focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/35"
                />
              </div>
            )}
            <div className="space-y-1.5">
              <Label htmlFor="form-handler">经手人</Label>
              <Input id="form-handler" value={formData.handler || ""} onChange={(e) => setFormData((prev) => ({ ...prev, handler: e.target.value }))} placeholder="经手人" />
            </div>
            {!isFormStockAdjustment && (
              <div className="space-y-1.5">
                <Label htmlFor="form-supplier">{isFormAccounting ? "单位全名" : isFormTransfer ? "出货仓库" : isFormWholesale ? "收货客户" : "供应商"}</Label>
                <SearchableSelect
                  value={formData.supplier || ""}
                  options={formCounterpartyOptions}
                  onChange={(nextValue) => setFormData((prev) => ({ ...prev, supplier: nextValue }))}
                  placeholder={isFormAccounting ? (isFormPayable ? "搜索供应商" : "搜索一般客户") : isFormTransfer ? "搜索出货仓库" : isFormWholesale ? "搜索收货客户" : "搜索供应商"}
                />
              </div>
            )}
            {/* Warehouse */}
            {!isFormAccounting && (
              <div className="space-y-1.5">
                <Label htmlFor="form-warehouse">{isFormStockAdjustment ? "仓库" : isFormTransfer ? "入货仓库" : isFormWholesale ? "发货仓库" : "仓库"}</Label>
                <SearchableSelect
                  value={formData.warehouse || ""}
                  options={warehouseSelectOptions}
                  onChange={(nextValue) => setFormData((prev) => ({ ...prev, warehouse: nextValue }))}
                  placeholder={isFormStockAdjustment ? "搜索仓库" : isFormTransfer ? "搜索入货仓库" : isFormWholesale ? "搜索发货仓库" : "搜索仓库"}
                />
              </div>
            )}
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
            {formData.document_type === PURCHASE_ORDER_DOCUMENT_TYPE && (
              <div className="col-span-2 space-y-1.5">
                <Label htmlFor="form-additional-note">附加说明</Label>
                <textarea
                  id="form-additional-note"
                  value={formData.additional_note || ""}
                  onChange={(e) => setFormData((prev) => ({ ...prev, additional_note: e.target.value }))}
                  placeholder="附加说明"
                  rows={3}
                  className="flex min-h-20 w-full resize-y rounded-lg border border-input bg-card px-3 py-2 text-sm shadow-xs outline-none transition-colors focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/35"
                />
              </div>
            )}
            {shouldShowAccountingInlineDetail && (
              <div className="col-span-2 rounded-lg border border-border bg-muted/20 p-3">
                <div className="mb-3 flex items-center justify-between gap-3">
                  <p className="text-sm font-medium">单据明细</p>
                  <span className="text-xs text-muted-foreground">保存单据时自动生成</span>
                </div>
                <div className="grid grid-cols-2 gap-3">
                  <div className="space-y-1.5">
                    <Label htmlFor="form-detail-subject">费用项目名 / 科目</Label>
                    <Select
                      id="form-detail-subject"
                      value={formData.detail_subject || ""}
                      onChange={(e) => setFormData((prev) => ({ ...prev, detail_subject: e.target.value }))}
                    >
                      <option value="">请选择科目</option>
                      {accountSubjectOptions.map((subject) => (
                        <option key={subject.id} value={subject.name}>{subject.name}</option>
                      ))}
                    </Select>
                  </div>
                  <div className="space-y-1.5">
                    <Label htmlFor="form-detail-amount">{formData.document_type?.includes("减少") ? "减少金额" : "增加金额"}</Label>
                    <Input
                      id="form-detail-amount"
                      type="number"
                      step="0.01"
                      value={formData.detail_amount || ""}
                      onChange={(e) => setFormData((prev) => ({ ...prev, detail_amount: e.target.value }))}
                      placeholder="0.00"
                    />
                  </div>
                  <div className="col-span-2 space-y-1.5">
                    <Label htmlFor="form-detail-remark">明细备注</Label>
                    <Input
                      id="form-detail-remark"
                      value={formData.detail_remark || ""}
                      onChange={(e) => setFormData((prev) => ({ ...prev, detail_remark: e.target.value }))}
                      placeholder="可选"
                    />
                  </div>
                </div>
              </div>
            )}
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setFormOpen(false)} disabled={isSaving} className="cursor-pointer">取消</Button>
            <Button onClick={handleSave} disabled={isSaving} className="cursor-pointer">{isSaving ? "保存中..." : "保存"}</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <Dialog open={importDialogOpen} onOpenChange={setImportDialogOpen}>
        <DialogContent className="max-w-xl">
          <DialogHeader>
            <DialogTitle>{isPurchaseOrderTab ? "导入采购单" : "导入单据明细"}</DialogTitle>
          </DialogHeader>
          {importError && (
            <Alert className="border-destructive/30 bg-destructive/5 text-destructive">
              <AlertDescription>{importError}</AlertDescription>
            </Alert>
          )}
          <div className="grid grid-cols-2 gap-4 py-2">
            {!isImportPurchaseOrder && (
              <>
                <div className="space-y-1.5">
                  <Label>{importFormData.document_type === PURCHASE_ORDER_DOCUMENT_TYPE ? "订货日期" : "单据日期"}</Label>
                  <input
                    type="date"
                    value={importFormData.date}
                    onChange={(e) => { setImportError(""); setImportFormData((prev) => ({ ...prev, date: e.target.value })) }}
                    className="flex h-9 w-full rounded-lg border border-input bg-card px-3 py-2 text-sm shadow-xs outline-none transition-colors focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/35"
                  />
                </div>
                {!isPurchaseOrderTab && (
                  <div className="space-y-1.5">
                    <Label>单据类型</Label>
                    <Select
                      value={importFormData.document_type}
                      onChange={(e) => { setImportError(""); setImportFormData((prev) => ({ ...prev, document_type: e.target.value, supplier: "" })) }}
                    >
                      <option value="">请选择</option>
                      {detailImportDocumentTypeOptions.map((dt) => (<option key={dt} value={dt}>{dt}</option>))}
                    </Select>
                  </div>
                )}
                {importFormData.document_type === PURCHASE_ORDER_DOCUMENT_TYPE && (
                  <div className="space-y-1.5">
                    <Label>交货日期</Label>
                    <input
                      type="date"
                      value={importFormData.delivery_date}
                      min={importFormData.date || undefined}
                      onChange={(e) => { setImportError(""); setImportFormData((prev) => ({ ...prev, delivery_date: e.target.value })) }}
                      className="flex h-9 w-full rounded-lg border border-input bg-card px-3 py-2 text-sm shadow-xs outline-none transition-colors focus-visible:border-ring focus-visible:ring-ring/35"
                    />
                  </div>
                )}
                {!isImportStockAdjustment && (
                  <div className="space-y-1.5">
                    <Label>{isImportTransfer ? "出货仓库" : isImportWholesale ? "收货客户" : "供货单位"}</Label>
                    <SearchableSelect
                      value={importFormData.supplier}
                      options={importCounterpartyOptions}
                      onChange={(nextValue) => setImportFormData((prev) => ({ ...prev, supplier: nextValue }))}
                      onTouched={() => setImportError("")}
                      placeholder={isImportTransfer ? "搜索出货仓库" : isImportWholesale ? "搜索收货客户" : "搜索供货单位"}
                    />
                  </div>
                )}
                <div className="space-y-1.5">
                  <Label>{isImportStockAdjustment ? "仓库" : isImportTransfer ? "入货仓库" : isImportWholesale ? "发货仓库" : "收货仓库"}</Label>
                  <SearchableSelect
                    value={importFormData.warehouse}
                    options={warehouseSelectOptions}
                    onChange={(nextValue) => setImportFormData((prev) => ({ ...prev, warehouse: nextValue }))}
                    onTouched={() => setImportError("")}
                    placeholder={isImportStockAdjustment ? "搜索仓库" : isImportTransfer ? "搜索入货仓库" : isImportWholesale ? "搜索发货仓库" : "搜索收货仓库"}
                  />
                </div>
                <div className="space-y-1.5">
                  <Label>经手人</Label>
                  <Input value={importFormData.handler} onChange={(e) => { setImportError(""); setImportFormData((prev) => ({ ...prev, handler: e.target.value })) }} placeholder="经手人" />
                </div>
                <div className="col-span-2 space-y-1.5">
                  <Label>摘要</Label>
                  <Input value={importFormData.summary} onChange={(e) => { setImportError(""); setImportFormData((prev) => ({ ...prev, summary: e.target.value })) }} placeholder="摘要" />
                </div>
              </>
            )}
            <div className="col-span-2 space-y-1.5">
              <Label>Excel 文件</Label>
              <input
                ref={fileInputRef}
                type="file"
                accept=".xlsx,.xls,.xlsm"
                onChange={(e) => { setImportError(""); setImportFile(e.target.files?.[0] ?? null) }}
                className="flex h-9 w-full rounded-lg border border-input bg-card px-3 py-1.5 text-sm shadow-xs outline-none transition-colors file:mr-3 file:rounded-md file:border-0 file:bg-muted file:px-2 file:py-1 file:text-xs"
              />
              <p className="text-xs text-muted-foreground">
                如果这张单据已经导入过，请打开该单据明细，用“重新导入明细”覆盖。
              </p>
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setImportDialogOpen(false)} disabled={isImporting} className="cursor-pointer">取消</Button>
            <Button onClick={handleImport} disabled={isImporting} className="cursor-pointer">{isImporting ? "导入中..." : "导入"}</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <Dialog
        open={requirementsDialogOpen}
        onOpenChange={(open) => {
          setRequirementsDialogOpen(open)
          if (!open) setRequirementsError("")
        }}
      >
        <DialogContent className="max-w-4xl">
          <DialogHeader>
            <DialogTitle>订单要求</DialogTitle>
          </DialogHeader>
          {requirementsError && (
            <Alert className="border-destructive/30 bg-destructive/5 text-destructive">
              <AlertDescription>{requirementsError}</AlertDescription>
            </Alert>
          )}
          <div className="grid gap-4 py-2 md:grid-cols-[12rem_1fr]">
            <div className="space-y-1.5">
              <Label>品牌</Label>
              <Select
                value={selectedRequirementBrand}
                onChange={(event) => {
                  setRequirementsError("")
                  handleRequirementBrandChange(event.target.value)
                }}
                disabled={isRequirementsLoading || isSavingRequirement}
              >
                {PURCHASE_REQUIREMENT_BRAND_OPTIONS.map((option) => (
                  <option key={option.value} value={option.value}>{option.label}</option>
                ))}
              </Select>
            </div>
            <div className="space-y-1.5">
              <Label>内容</Label>
              <textarea
                value={isRequirementsLoading ? "加载中..." : currentRequirementContent}
                onChange={(event) => {
                  setRequirementsError("")
                  setRequirementDrafts((prev) => ({
                    ...prev,
                    [selectedRequirementBrand]: event.target.value,
                  }))
                }}
                disabled={isRequirementsLoading || isSavingRequirement}
                className="min-h-[28rem] w-full resize-y rounded-lg border border-input bg-card px-3 py-2 text-sm leading-6 shadow-xs outline-none transition-colors placeholder:text-muted-foreground focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/35 disabled:cursor-not-allowed disabled:bg-muted disabled:opacity-70"
              />
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setRequirementsDialogOpen(false)} disabled={isSavingRequirement} className="cursor-pointer">取消</Button>
            <Button onClick={handleSavePurchaseRequirement} disabled={isRequirementsLoading || isSavingRequirement} className="cursor-pointer">
              {isSavingRequirement ? "保存中..." : "保存"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {!isPurchasePage && (
        <Dialog open={costDialogOpen} onOpenChange={setCostDialogOpen}>
          <DialogContent className="max-w-2xl">
            <DialogHeader>
              <DialogTitle>批量改成本价</DialogTitle>
            </DialogHeader>
            {costError && (
              <Alert className="border-destructive/30 bg-destructive/5 text-destructive">
                <AlertDescription>{costError}</AlertDescription>
              </Alert>
            )}
            <div className="grid grid-cols-2 gap-4 py-2">
              <div className="space-y-1.5">
                <Label>开始日期</Label>
                <input
                  type="date"
                  value={costFormData.date_start}
                  max={costFormData.date_end || undefined}
                  onChange={(e) => { setCostError(""); setCostFormData((prev) => ({ ...prev, date_start: e.target.value })) }}
                  className="flex h-9 w-full rounded-lg border border-input bg-card px-3 py-2 text-sm shadow-xs outline-none transition-colors focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/35"
                />
              </div>
              <div className="space-y-1.5">
                <Label>结束日期</Label>
                <input
                  type="date"
                  value={costFormData.date_end}
                  min={costFormData.date_start || undefined}
                  onChange={(e) => { setCostError(""); setCostFormData((prev) => ({ ...prev, date_end: e.target.value })) }}
                  className="flex h-9 w-full rounded-lg border border-input bg-card px-3 py-2 text-sm shadow-xs outline-none transition-colors focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/35"
                />
              </div>
              <div className="space-y-1.5">
                <Label>货号</Label>
                <Input
                  value={costFormData.product_code}
                  onChange={(e) => { setCostError(""); setCostFormData((prev) => ({ ...prev, product_code: e.target.value })) }}
                  placeholder="例如 C2221633DO"
                />
              </div>
              <div className="space-y-1.5">
                <Label>新单价</Label>
                <Input
                  type="number"
                  min="0"
                  step="0.01"
                  value={costFormData.unit_price}
                  onChange={(e) => { setCostError(""); setCostFormData((prev) => ({ ...prev, unit_price: e.target.value })) }}
                  placeholder="例如 129.00"
                />
              </div>
              <div className="col-span-2 space-y-1.5">
                <Label>批量货号和新单价</Label>
                <textarea
                  value={costFormData.batch_text}
                  onChange={(e) => { setCostError(""); setCostFormData((prev) => ({ ...prev, batch_text: e.target.value })) }}
                  placeholder={"每行一个：货号,新单价\nC2221633DO,129\nC2221633DJ,135"}
                  className="min-h-28 w-full resize-y rounded-lg border border-input bg-card px-3 py-2 text-sm shadow-xs outline-none transition-colors placeholder:text-muted-foreground focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/35"
                />
              </div>
              <div className="col-span-2 rounded-lg border border-border bg-muted/40 px-3 py-2 text-xs text-muted-foreground">
                只会更新所选日期范围内的进货单、进货退货单明细；金额按数量 × 新单价重算，单据总金额会自动重算。
              </div>
            </div>
            <DialogFooter>
              <Button variant="outline" onClick={() => setCostDialogOpen(false)} disabled={isUpdatingCosts} className="cursor-pointer">取消</Button>
              <Button onClick={handleBatchUpdateCosts} disabled={isUpdatingCosts} className="cursor-pointer">{isUpdatingCosts ? "更新中..." : "确认更新"}</Button>
            </DialogFooter>
          </DialogContent>
        </Dialog>
      )}

      <Dialog open={recycleOpen} onOpenChange={setRecycleOpen}>
        <DialogContent className="max-w-5xl">
          <DialogHeader>
            <div className="flex items-center justify-between gap-3">
              <DialogTitle>{isPurchasePage ? "采购单回收站" : "进销存回收站"}</DialogTitle>
              <Button
                type="button"
                variant="ghost"
                size="icon"
                onClick={() => setRecycleOpen(false)}
                className="h-8 w-8 cursor-pointer"
                aria-label={isPurchasePage ? "关闭采购单回收站" : "关闭进销存回收站"}
                title="关闭"
              >
                <X className="h-4 w-4" />
              </Button>
            </div>
          </DialogHeader>
          <div className="space-y-3 py-2">
            <div className="rounded-lg border border-border bg-muted/30 px-3 py-2 text-xs text-muted-foreground">
              删除的{isPurchasePage ? "采购单" : "进销存单据"}会在这里保留 10 天，超过 10 天后自动彻底删除。
            </div>
            <div className="overflow-hidden rounded-lg border border-border">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-border bg-muted/40 text-left text-muted-foreground">
                    <th className="w-10 px-3 py-2 font-medium">
                      <input
                        type="checkbox"
                        checked={allRecycleSelected}
                        disabled={recycleItems.length === 0 || isRecycleLoading || recycleActionBusy}
                        onChange={handleToggleRecycleSelectAll}
                        className="h-4 w-4 cursor-pointer rounded border border-input accent-primary"
                        aria-label={`选择当前页全部${isPurchasePage ? "采购单" : "进销存"}回收站单据`}
                      />
                    </th>
                    <th className="px-3 py-2 font-medium">单据编号</th>
                    <th className="px-3 py-2 font-medium">日期</th>
                    <th className="px-3 py-2 font-medium">单据类型</th>
                    <th className="px-3 py-2 font-medium">单位全名</th>
                    <th className="px-3 py-2 font-medium">摘要</th>
                    <th className="px-3 py-2 font-medium">删除时间</th>
                    <th className="px-3 py-2 font-medium">剩余</th>
                    <th className="px-3 py-2 text-right font-medium">操作</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-border">
                  {isRecycleLoading && (
                    <tr>
                      <td colSpan={9} className="px-4 py-10 text-center text-muted-foreground">加载中...</td>
                    </tr>
                  )}
                  {!isRecycleLoading && recycleItems.length === 0 && (
                    <tr>
                      <td colSpan={9} className="px-4 py-10 text-center text-muted-foreground">
                        {isPurchasePage ? "采购单回收站暂无单据" : "进销存回收站暂无单据"}
                      </td>
                    </tr>
                  )}
                  {!isRecycleLoading && recycleItems.map((item) => (
                    <tr key={item.id} className="hover:bg-muted/30">
                      <td className="px-3 py-2">
                        <input
                          type="checkbox"
                          checked={selectedRecycleIds.has(item.id)}
                          disabled={recycleActionBusy || isRestoringId === item.id}
                          onChange={() => handleToggleRecycleSelect(item.id)}
                          className="h-4 w-4 cursor-pointer rounded border border-input accent-primary"
                          aria-label={`选择回收站单据 ${item.document_number || item.id}`}
                        />
                      </td>
                      <td className="px-3 py-2 font-mono text-xs">{item.document_number || item.id}</td>
                      <td className="px-3 py-2 whitespace-nowrap">{item.date || "-"}</td>
                      <td className="px-3 py-2 whitespace-nowrap">{item.document_type || "-"}</td>
                      <td className="px-3 py-2 max-w-40 truncate">{item.supplier || "-"}</td>
                      <td className="px-3 py-2 max-w-56 truncate">{item.summary || "-"}</td>
                      <td className="px-3 py-2 whitespace-nowrap text-xs">{formatDeletedAt(item.deleted_at)}</td>
                      <td className="px-3 py-2 whitespace-nowrap">{remainingRecycleDays(item.deleted_at)}</td>
                      <td className="px-3 py-2 text-right">
                        <Button
                          size="sm"
                          variant="outline"
                          onClick={() => handleRestoreRecord(item.id)}
                          disabled={isRestoringId === item.id || recycleActionBusy}
                          className="cursor-pointer"
                        >
                          <RefreshCw className="h-3.5 w-3.5" />
                          <span className="ml-1.5">{isRestoringId === item.id ? "恢复中..." : "恢复"}</span>
                        </Button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <div className="flex flex-wrap items-center justify-between gap-3 text-sm text-muted-foreground">
              <span>
                共 {recycleTotal} 条
                {selectedRecycleIds.size > 0 && <span className="ml-2 font-medium text-foreground">已选 {selectedRecycleIds.size} 项</span>}
              </span>
              <div className="flex items-center gap-2">
                {selectedRecycleIds.size > 0 && (
                  <>
                    <Button
                      size="sm"
                      variant="outline"
                      onClick={handleBatchRestore}
                      disabled={recycleActionBusy || isRecycleLoading}
                      className="cursor-pointer"
                    >
                      <RefreshCw className={`h-4 w-4 ${isBatchRestoring ? "animate-spin" : ""}`} />
                      <span className="ml-1.5">{isBatchRestoring ? "恢复中..." : `批量恢复 (${selectedRecycleIds.size})`}</span>
                    </Button>
                    <Button
                      size="sm"
                      variant="destructive"
                      onClick={() => setRecycleBatchDeleteOpen(true)}
                      disabled={recycleActionBusy || isRecycleLoading}
                      className="cursor-pointer"
                    >
                      <Trash2 className="h-4 w-4" />
                      <span className="ml-1.5">{isRecycleBatchDeleting ? "删除中..." : `批量彻底删除 (${selectedRecycleIds.size})`}</span>
                    </Button>
                  </>
                )}
                <Button
                  size="sm"
                  variant="outline"
                  onClick={() => setRecyclePage((p) => Math.max(1, p - 1))}
                  disabled={recyclePage <= 1 || isRecycleLoading || recycleActionBusy}
                  className="cursor-pointer"
                >
                  上一页
                </Button>
                <span className="tabular-nums">{recyclePage} / {recycleTotalPages}</span>
                <Button
                  size="sm"
                  variant="outline"
                  onClick={() => setRecyclePage((p) => Math.min(recycleTotalPages, p + 1))}
                  disabled={recyclePage >= recycleTotalPages || isRecycleLoading || recycleActionBusy}
                  className="cursor-pointer"
                >
                  下一页
                </Button>
              </div>
            </div>
          </div>
        </DialogContent>
      </Dialog>

      <ConfirmDialog
        open={deleteTarget !== null}
        title="确认删除"
        description={`确定把单据编号 ${deleteTarget?.document_number || deleteTarget?.id} 移入回收站？10 天内可以恢复。`}
        confirmLabel={isDeleting ? "处理中..." : "移入回收站"}
        variant="destructive"
        onConfirm={handleDeleteConfirm}
        onCancel={() => setDeleteTarget(null)}
      />

      <ConfirmDialog
        open={batchDeleteOpen}
        title="确认批量删除"
        description={`确定把选中的 ${selectedIds.size} 条记录移入回收站？10 天内可以恢复。`}
        confirmLabel={isBatchDeleting ? "处理中..." : "移入回收站"}
        variant="destructive"
        onConfirm={handleBatchDeleteConfirm}
        onCancel={() => setBatchDeleteOpen(false)}
      />

      <ConfirmDialog
        open={recycleBatchDeleteOpen}
        title="确认彻底删除"
        description={`确定彻底删除回收站中选中的 ${selectedRecycleIds.size} 条单据？删除后无法恢复。`}
        confirmLabel={isRecycleBatchDeleting ? "删除中..." : "彻底删除"}
        variant="destructive"
        onConfirm={handleRecycleBatchDeleteConfirm}
        onCancel={() => setRecycleBatchDeleteOpen(false)}
      />

      <MessageDialog
        open={messageOpen}
        title={messageContent.title}
        description={messageContent.description}
        onClose={() => setMessageOpen(false)}
      />

      <InventoryDetailPanel
        record={detailRecord}
        suppliers={supplierOptions}
        onClose={() => setDetailDocumentId(null)}
        onTotalChanged={() => setReloadToken((t) => t + 1)}
      />
    </div>
  )
}
