"use client"

import { useSessionQueryState } from "@/lib/session-query-state"
import { useCrossTabRefresh } from "@/lib/use-cross-tab-refresh"

import { useEffect, useMemo, useRef, useState } from "react"
import { ArrowDown, ArrowUp, Download, History, LoaderCircle, Search, X } from "lucide-react"

import { Alert, AlertDescription } from "@/components/ui/alert"
import { Button } from "@/components/ui/button"
import { OperationLogDialog } from "@/components/operation-log-dialog"
import { SearchableFilterInput, SearchableMultiFilterInput, type SearchableFilterOption } from "@/components/inventory-admin/searchable-filter-input"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { DateRangeControl } from "@/components/ui/date-range-control"
import {
  Pagination,
  PaginationContent,
  PaginationEllipsis,
  PaginationItem,
  PaginationLink,
  PaginationNext,
  PaginationPrevious,
} from "@/components/ui/pagination"
import { Select } from "@/components/ui/select"
import {
  Table,
  TableBody,
  TableCell,
  TableFooter,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"
import { ApiError, buildPurchaseInboundDetailExportUrl, listInventoryBrands, listInventoryDetailCandidates, listPurchaseInboundDetails, listSuppliers, listWarehouses, type InventoryDetailCandidate, type PurchaseInboundDetailItem, type SupplierItem, type WarehouseItem } from "@/lib/api"
import { buildPurchaseOrderDetailExportUrl, downloadSelectedDetailExport, getPurchaseOrderDetailOptions, listPurchaseOrderDetails } from "@/lib/api"
import { buildSalesDetailExportUrl, getSalesDetailOptions, listSalesDetails, type SalesDetailResponse } from "@/lib/api"
import { cn } from "@/lib/utils"

const PAGE_SIZES = [50, 100, 200]
const FILTER_FIELD_CLASS_NAME = "min-w-0 space-y-1"
const FILTER_LABEL_CLASS_NAME = "text-[11px] font-medium text-muted-foreground"
const FILTER_CONTROL_CLASS_NAME = "bg-background"
const SKELETON_ROWS = Array.from({ length: 14 }, (_, index) => index)
const SKELETON_WIDTHS = ["w-3/5", "w-4/5", "w-2/5", "w-3/4"]

function DetailTableSkeleton({ columnCount }: { columnCount: number }) {
  return SKELETON_ROWS.map((row) => (
    <TableRow key={row} aria-hidden="true" className="hover:bg-transparent">
      {Array.from({ length: columnCount }, (_, column) => (
        <TableCell key={column} className="h-9 py-2">
          <div className={cn(
            "h-2.5 rounded-sm bg-muted-foreground/10 motion-safe:animate-pulse",
            column === 0 ? "mx-auto h-3.5 w-3.5 rounded" : column === 1 ? "mx-auto w-5" : SKELETON_WIDTHS[(row + column) % SKELETON_WIDTHS.length],
            column >= columnCount - 6 && column <= columnCount - 4 && "ml-auto",
          )} />
        </TableCell>
      ))}
    </TableRow>
  ))
}

type SubmittedFilters = {
  date_start?: string
  date_end?: string
  brands?: string[]
  document_type?: string
  supplier?: string
  warehouse?: string[]
  product_code?: string
  product_name?: string
  color_name?: string
  size_name?: string
}

function getErrorMessage(error: unknown) {
  if (error instanceof ApiError) return error.message || `请求失败（${error.status}）`
  if (error instanceof Error) return error.message
  return "发生未知错误"
}

function buildPageRange(current: number, total: number): (number | "ellipsis")[] {
  if (total <= 7) return Array.from({ length: total }, (_, index) => index + 1)
  if (current <= 4) return [1, 2, 3, 4, 5, "ellipsis", total]
  if (current >= total - 3) return [1, "ellipsis", total - 4, total - 3, total - 2, total - 1, total]
  return [1, "ellipsis", current - 1, current, current + 1, "ellipsis", total]
}

function formatCell(value: string | number | null | undefined) {
  if (value === null || value === undefined || value === "") return "-"
  return value
}

function numericTone(value: string | null | undefined) {
  if (!value) return ""
  const numeric = Number(value)
  if (!Number.isFinite(numeric) || numeric >= 0) return ""
  return "text-destructive"
}

function selectionKey(item: PurchaseInboundDetailItem, byBarcode: boolean) {
  return byBarcode ? item.row_key ?? "" : String(item.detail_id)
}

function salesDisplayResponse(response: SalesDetailResponse) {
  const totals = (value: SalesDetailResponse["totals"]["all"]) => ({
    purchase_quantity: value.sales_quantity, purchase_amount: value.sales_amount, retail_amount: value.retail_amount,
  })
  return {
    ...response,
    items: response.items.map((item) => ({ ...item, purchase_quantity: item.sales_quantity, purchase_amount: item.sales_amount })),
    totals: { ...totals(response.totals), all: totals(response.totals.all), current_page: totals(response.totals.current_page) },
  }
}

export function PurchaseInboundDetailPage({ mode = "inbound", canExport = true }: { mode?: "inbound" | "orders" | "sales"; canExport?: boolean }) {
  const isPurchaseOrder = mode === "orders"
  const isSales = mode === "sales"
  const stateKey = isSales ? "sales-details" : isPurchaseOrder ? "purchase-order-details" : "purchase-inbound-details"
  const pageTitle = isSales ? "商品销售明细" : isPurchaseOrder ? "采购明细" : "商品进货明细"
  const quantityLabel = isSales ? "销售数量" : isPurchaseOrder ? "采购数量" : "进货数量"
  const amountLabel = isSales ? "销售金额" : isPurchaseOrder ? "采购金额" : "进货金额"
  const documentTypes = isSales ? ["批发销售单", "批发销售退货单"] : ["进货单", "进货退货单"]
  const [dateStart, setDateStart] = useSessionQueryState(`${stateKey}:dateStart`, "")
  const [dateEnd, setDateEnd] = useSessionQueryState(`${stateKey}:dateEnd`, "")
  const [brands, setBrands] = useSessionQueryState<string[]>(`${stateKey}:brands`, [])
  const [brandOptions, setBrandOptions] = useState<SearchableFilterOption[]>([])
  const [documentType, setDocumentType] = useSessionQueryState(`${stateKey}:documentType`, "")
  const [supplier, setSupplier] = useSessionQueryState(`${stateKey}:supplier`, "")
  const [supplierOptions, setSupplierOptions] = useState<(Pick<SupplierItem, "name"> & Partial<Pick<SupplierItem, "factory_code" | "contact" | "address">>)[]>([])
  const [warehouse, setWarehouse] = useSessionQueryState<string[]>(`${stateKey}:warehouse`, [])
  const [warehouseOptions, setWarehouseOptions] = useState<Pick<WarehouseItem, "name" | "brand">[]>([])
  const [productCode, setProductCode] = useSessionQueryState(`${stateKey}:productCode`, "")
  const [productCodeCandidates, setProductCodeCandidates] = useState<{ query: string; items: InventoryDetailCandidate[] }>({ query: "", items: [] })
  const productCodeOptions = !isPurchaseOrder && productCode.trim() === productCodeCandidates.query ? productCodeCandidates.items : []
  const [productName, setProductName] = useSessionQueryState(`${stateKey}:productName`, "")
  const [colorName, setColorName] = useSessionQueryState(`${stateKey}:colorName`, "")
  const [sizeName, setSizeName] = useSessionQueryState(`${stateKey}:sizeName`, "")
  const [submittedFilters, setSubmittedFilters] = useSessionQueryState<SubmittedFilters>(`${stateKey}:submittedFilters`, {})
  const [dateSort, setDateSort] = useSessionQueryState<"asc" | "desc">(`${stateKey}:dateSort`, "asc")
  const [displayMode, setDisplayMode] = useSessionQueryState<"goods" | "barcode">(`${stateKey}:displayMode`, "goods")
  const byBarcode = !isPurchaseOrder && displayMode === "barcode"
  const columnCount = (isPurchaseOrder ? 14 : byBarcode ? 17 : 12) + 1
  const [selection, setSelection] = useSessionQueryState<{ scope: string; rows: string[] }>(`${stateKey}:exportSelection`, { scope: "", rows: [] })
  const selectionScope = JSON.stringify([submittedFilters, byBarcode])
  const selectedRows = useMemo(() => new Set(selection.scope === selectionScope ? selection.rows : []), [selection, selectionScope])
  const [isExporting, setIsExporting] = useState(false)
  const exportController = useRef<AbortController | null>(null)
  useEffect(() => () => exportController.current?.abort(), [])
  const [page, setPage] = useSessionQueryState(`${stateKey}:page`, 1)
  const [pageSize, setPageSize] = useSessionQueryState(`${stateKey}:pageSize`, PAGE_SIZES[0])
  const [items, setItems] = useState<PurchaseInboundDetailItem[]>([])
  const [total, setTotal] = useState(0)
  const [totals, setTotals] = useState({
    purchase_quantity: "0",
    purchase_amount: "0",
    retail_amount: "",
    current_page: { purchase_quantity: "0", purchase_amount: "0", retail_amount: "" },
    all: { purchase_quantity: "0", purchase_amount: "0", retail_amount: "" },
  })
  const [isLoading, setIsLoading] = useState(true)
  const [loadedView, setLoadedView] = useState<{ mode: typeof mode; byBarcode: boolean; page: number; pageSize: number } | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [operationLogOpen, setOperationLogOpen] = useState(false)
  const [dataRevision, setDataRevision] = useState(0)
  const [referenceRevision, setReferenceRevision] = useState(0)
  useCrossTabRefresh(["inventory", "products"], () => { exportController.current?.abort(); setDataRevision((value) => value + 1) })
  useCrossTabRefresh(["reference-data"], () => setReferenceRevision((value) => value + 1))
  const salesOptionsRevision = isSales ? dataRevision : 0

  useEffect(() => {
    let cancelled = false

    async function loadOptions() {
      try {
        if (isSales) {
          const response = await getSalesDetailOptions()
          if (!cancelled) {
            setSupplierOptions(response.customers)
            setWarehouseOptions(response.warehouses)
            setBrandOptions(response.brands)
          }
          return
        }
        if (isPurchaseOrder) {
          const response = await getPurchaseOrderDetailOptions()
          if (!cancelled) {
            setSupplierOptions(response.suppliers)
            setWarehouseOptions(response.warehouses)
            setBrandOptions(response.brands)
          }
          return
        }
        const [suppliersResponse, warehousesResponse, brandsResponse] = await Promise.all([listSuppliers(), listWarehouses(), listInventoryBrands()])
        if (!cancelled) {
          setSupplierOptions(suppliersResponse.items)
          setWarehouseOptions(warehousesResponse.items)
          setBrandOptions(brandsResponse.items)
        }
      } catch {
        if (!cancelled) {
          setSupplierOptions([])
          setWarehouseOptions([])
          setBrandOptions([])
        }
      }
    }

    void loadOptions()
    return () => {
      cancelled = true
    }
  }, [isPurchaseOrder, isSales, referenceRevision, salesOptionsRevision])

  useEffect(() => {
    const query = productCode.trim()
    if (isPurchaseOrder || query.length < 2) {
      return
    }
    let cancelled = false
    const timer = window.setTimeout(async () => {
      try {
        const response = await listInventoryDetailCandidates({ query, limit: 30 })
        if (!cancelled) setProductCodeCandidates({ query, items: response.items })
      } catch {
        if (!cancelled) setProductCodeCandidates({ query, items: [] })
      }
    }, 220)
    return () => {
      cancelled = true
      window.clearTimeout(timer)
    }
  }, [isPurchaseOrder, productCode])

  useEffect(() => {
    let cancelled = false
    const controller = new AbortController()

    async function load() {
      setIsLoading(true)
      setError(null)
      try {
        const params = {
          ...submittedFilters,
          sort_direction: dateSort,
          ...(!isPurchaseOrder && displayMode === "barcode" ? { display_mode: displayMode } : {}),
          page,
          pageSize,
        }
        const response = isSales
          ? salesDisplayResponse(await listSalesDetails(params, controller.signal))
          : isPurchaseOrder
            ? await listPurchaseOrderDetails(params, controller.signal)
            : await listPurchaseInboundDetails(params, controller.signal)
        if (cancelled) return
        setItems(response.items)
        setTotal(response.total)
        setTotals(response.totals)
        setLoadedView({ mode, byBarcode: !isPurchaseOrder && displayMode === "barcode", page, pageSize })
      } catch (loadError) {
        if (cancelled) return
        setItems([])
        setTotal(0)
        setTotals({
          purchase_quantity: "0",
          purchase_amount: "0",
          retail_amount: "",
          current_page: { purchase_quantity: "0", purchase_amount: "0", retail_amount: "" },
          all: { purchase_quantity: "0", purchase_amount: "0", retail_amount: "" },
        })
        setError(getErrorMessage(loadError))
      } finally {
        if (!cancelled) setIsLoading(false)
      }
    }

    void load()

    return () => {
      cancelled = true
      controller.abort()
    }
  }, [dataRevision, dateSort, displayMode, isPurchaseOrder, isSales, mode, page, pageSize, submittedFilters])

  const totalPages = Math.max(1, Math.ceil(total / pageSize))
  const pageRange = useMemo(() => buildPageRange(page, totalPages), [page, totalPages])
  const pageSlotWidth = `${Math.max(2, String(totalPages).length) + 3}ch`
  const supplierFilterOptions = useMemo<SearchableFilterOption[]>(() => (
    supplierOptions.map((item) => ({
      value: item.name,
      label: item.name,
      keywords: [item.factory_code, item.contact, item.address].filter(Boolean).join(" "),
    }))
  ), [supplierOptions])
  const warehouseFilterOptions = useMemo<SearchableFilterOption[]>(() => (
    warehouseOptions.map((item) => ({ value: item.name, label: item.name, keywords: item.brand || "" }))
  ), [warehouseOptions])

  const submitSearch = () => {
    exportController.current?.abort()
    setSelection({ scope: "", rows: [] })
    setPage(1)
    setSubmittedFilters({
      date_start: dateStart || undefined,
      date_end: dateEnd || undefined,
      brands: brands.length ? brands : undefined,
      document_type: isPurchaseOrder ? undefined : documentType || undefined,
      supplier: supplier || undefined,
      warehouse: warehouse.length ? warehouse : undefined,
      product_code: productCode || undefined,
      product_name: productName || undefined,
      color_name: colorName || undefined,
      size_name: sizeName || undefined,
    })
  }

  const clearSearch = () => {
    exportController.current?.abort()
    setSelection({ scope: "", rows: [] })
    setDateStart("")
    setDateEnd("")
    setBrands([])
    setDocumentType("")
    setSupplier("")
    setWarehouse([])
    setProductCode("")
    setProductName("")
    setColorName("")
    setSizeName("")
    setPage(1)
    setSubmittedFilters({})
  }

  const showPreviousRows = isLoading && items.length > 0 && loadedView?.mode === mode && loadedView.byBarcode === byBarcode
  const displayedPage = showPreviousRows ? loadedView.page : page
  const displayedPageSize = showPreviousRows ? loadedView.pageSize : pageSize
  const firstRow = total === 0 ? 0 : (displayedPage - 1) * displayedPageSize + 1
  const lastRow = Math.min(displayedPage * displayedPageSize, total)
  const changePage = (nextPage: number) => {
    if (isLoading || nextPage === page || nextPage < 1 || nextPage > totalPages) return
    setPage(nextPage)
  }

  const handleExport = () => {
    const filters = { ...submittedFilters, sort_direction: dateSort, ...(!isPurchaseOrder && byBarcode ? { display_mode: displayMode } : {}) }
    const link = document.createElement("a")
    link.href = isSales
      ? buildSalesDetailExportUrl(filters)
      : isPurchaseOrder
        ? buildPurchaseOrderDetailExportUrl(filters)
        : buildPurchaseInboundDetailExportUrl(filters)
    link.rel = "noopener"
    link.click()
  }

  const toggleSelection = (keys: string[], checked: boolean) => {
    setSelection(current => {
      const next = new Set(current.scope === selectionScope ? current.rows : [])
      for (const key of keys) { if (checked) next.add(key); else next.delete(key) }
      return { scope: selectionScope, rows: Array.from(next) }
    })
  }
  const pageKeys = items.map(item => selectionKey(item, byBarcode)).filter(Boolean)
  const allPageSelected = pageKeys.length > 0 && pageKeys.every(key => selectedRows.has(key))
  const somePageSelected = pageKeys.some(key => selectedRows.has(key))

  const handleSelectedExport = async () => {
    if (!canExport || isExporting || exportController.current || selectedRows.size === 0) return
    const controller = new AbortController()
    exportController.current = controller
    setIsExporting(true)
    setError(null)
    try {
      await downloadSelectedDetailExport(mode, {
        ...submittedFilters, sort_direction: dateSort,
        ...(!isPurchaseOrder && byBarcode ? { display_mode: displayMode } : {}),
      }, Array.from(selectedRows), controller.signal)
    } catch (exportError) {
      if (!controller.signal.aborted) setError(getErrorMessage(exportError))
    } finally {
      if (exportController.current === controller) {
        exportController.current = null
        setIsExporting(false)
      }
    }
  }

  return (
    <div className="min-h-svh bg-background px-6 py-5">
      <div className="mx-auto flex max-w-[1600px] flex-col gap-4">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <h1 className="page-title">{pageTitle}</h1>
          </div>
          <div className="flex flex-wrap items-center gap-2 text-sm text-muted-foreground">
            <Button variant="outline" size="sm" aria-label="导出所选" onClick={() => void handleSelectedExport()} disabled={!canExport || selectedRows.size === 0 || isLoading || isExporting} className="cursor-pointer">
              <Download className="h-4 w-4" />
              <span className="ml-1.5">{isExporting ? "导出中…" : `导出所选${selectedRows.size ? ` (${selectedRows.size})` : ""}`}</span>
            </Button>
            <Button variant="outline" size="sm" aria-label="导出Excel" title="导出全部符合当前筛选的明细" onClick={handleExport} disabled={!canExport || total === 0 || isLoading || isExporting} className="cursor-pointer">
              <Download className="h-4 w-4" />
              <span className="ml-1.5 hidden sm:inline">导出Excel</span>
            </Button>
            <Button variant="outline" size="sm" aria-label="操作日志" onClick={() => setOperationLogOpen(true)} className="cursor-pointer">
              <History className="h-4 w-4" />
              <span className="ml-1.5 hidden sm:inline">操作日志</span>
            </Button>
            <span className="inline-flex min-w-[7rem] justify-end">{isLoading ? "总数更新中…" : `共 ${total} 条`}</span>
            <Select aria-label="每页条数" disabled={isLoading} value={String(pageSize)} onChange={(event) => { setPageSize(Number(event.target.value)); setPage(1) }} className="w-24">
              {PAGE_SIZES.map((size) => (
                <option key={size} value={String(size)}>{size} 条</option>
              ))}
            </Select>
          </div>
        </div>

        <div className="rounded-lg border border-border bg-card px-4 py-3 shadow-xs">
          <div className="grid items-end gap-x-3 gap-y-2.5 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-5">
            <DateRangeControl className="md:col-span-2 lg:col-span-3 xl:col-span-5" start={dateStart} end={dateEnd} onStartChange={setDateStart} onEndChange={setDateEnd} />
            <div className={FILTER_FIELD_CLASS_NAME}>
              <Label htmlFor={`${stateKey}-brand-filter`} className={FILTER_LABEL_CLASS_NAME}>品牌</Label>
              <SearchableMultiFilterInput
                id={`${stateKey}-brand-filter`}
                values={brands}
                options={brandOptions}
                onChange={setBrands}
                onSubmit={submitSearch}
                placeholder="选择品牌"
                className={FILTER_CONTROL_CLASS_NAME}
              />
            </div>
            <div className={FILTER_FIELD_CLASS_NAME}>
              <Label htmlFor={`${stateKey}-type-filter`} className={FILTER_LABEL_CLASS_NAME}>单据类型</Label>
              <Select id={`${stateKey}-type-filter`} className={FILTER_CONTROL_CLASS_NAME} value={isPurchaseOrder ? "进货订单" : documentType} disabled={isPurchaseOrder} onChange={(event) => setDocumentType(event.target.value)}>
                {isPurchaseOrder ? <option value="进货订单">进货订单</option> : <>
                <option value="">全部</option>
                {documentTypes.map((type) => <option key={type} value={type}>{type}</option>)}
                </>}
              </Select>
            </div>
            <div className={FILTER_FIELD_CLASS_NAME}>
              <Label htmlFor={`${stateKey}-warehouse-filter`} className={FILTER_LABEL_CLASS_NAME}>仓库全名</Label>
              <SearchableMultiFilterInput
                id={`${stateKey}-warehouse-filter`}
                values={warehouse}
                options={warehouseFilterOptions}
                onChange={setWarehouse}
                onSubmit={submitSearch}
                placeholder="输入仓库名称"
                className={FILTER_CONTROL_CLASS_NAME}
              />
            </div>
            <div className={FILTER_FIELD_CLASS_NAME}>
              <Label htmlFor={`${stateKey}-name-filter`} className={FILTER_LABEL_CLASS_NAME}>商品名称</Label>
              <Input id={`${stateKey}-name-filter`} className={FILTER_CONTROL_CLASS_NAME} value={productName} onChange={(event) => setProductName(event.target.value)} onKeyDown={(event) => { if (event.key === "Enter") submitSearch() }} />
            </div>
            <div className={FILTER_FIELD_CLASS_NAME}>
              <Label htmlFor={`${stateKey}-supplier-filter`} className={FILTER_LABEL_CLASS_NAME}>单位全名</Label>
              <SearchableFilterInput
                id={`${stateKey}-supplier-filter`}
                value={supplier}
                options={supplierFilterOptions}
                onChange={setSupplier}
                onSubmit={submitSearch}
                placeholder={isSales ? "输入客户名称" : "输入供应商"}
                className={FILTER_CONTROL_CLASS_NAME}
              />
            </div>
            <div className={FILTER_FIELD_CLASS_NAME}>
              <Label htmlFor={`${stateKey}-color-filter`} className={FILTER_LABEL_CLASS_NAME}>颜色名称</Label>
              <Input id={`${stateKey}-color-filter`} className={FILTER_CONTROL_CLASS_NAME} value={colorName} onChange={(event) => setColorName(event.target.value)} onKeyDown={(event) => { if (event.key === "Enter") submitSearch() }} />
            </div>
            <div className={FILTER_FIELD_CLASS_NAME}>
              <Label htmlFor={`${stateKey}-size-filter`} className={FILTER_LABEL_CLASS_NAME}>尺码名称</Label>
              <Input id={`${stateKey}-size-filter`} className={FILTER_CONTROL_CLASS_NAME} value={sizeName} onChange={(event) => setSizeName(event.target.value)} onKeyDown={(event) => { if (event.key === "Enter") submitSearch() }} />
            </div>
            <div className={FILTER_FIELD_CLASS_NAME}>
              <Label htmlFor={`${stateKey}-code-filter`} className={FILTER_LABEL_CLASS_NAME}>货号</Label>
              <SearchableFilterInput
                id={`${stateKey}-code-filter`}
                value={productCode}
                options={productCodeOptions.map((item) => ({
                  value: item.product_code,
                  label: item.product_code,
                  keywords: [item.product_name, item.original_sku, item.color_name, item.factory_code].filter(Boolean).join(" "),
                }))}
                onChange={setProductCode}
                onSubmit={submitSearch}
                placeholder="输入货号"
                className={FILTER_CONTROL_CLASS_NAME}
              />
            </div>
            <div className="grid grid-cols-2 gap-2 md:col-span-2 lg:col-span-3 xl:col-span-1">
              <Button size="lg" onClick={submitSearch} disabled={isLoading} className="min-w-0 cursor-pointer px-3">
                <Search className="h-4 w-4" />
                <span className="ml-1.5">查询</span>
              </Button>
              <Button size="lg" variant="outline" onClick={clearSearch} disabled={isLoading} className="min-w-0 cursor-pointer px-3">
                <X className="h-4 w-4" />
                <span className="ml-1.5">清空</span>
              </Button>
            </div>
          </div>
        </div>

        {error ? (
          <Alert className="border-destructive/30 bg-destructive/5 text-destructive">
            <AlertDescription>{error}</AlertDescription>
          </Alert>
        ) : null}

        <div className="flex min-h-8 flex-wrap items-center gap-3 text-sm">
          <span aria-live="polite" className="text-muted-foreground">已选 {selectedRows.size} 条</span>
          <Button variant="ghost" size="sm" onClick={() => setSelection({ scope: selectionScope, rows: [] })} disabled={selectedRows.size === 0 || isExporting} className="h-8 cursor-pointer px-2">清空选择</Button>
          {!isPurchaseOrder ? (
            <div role="group" aria-label="明细展示方式" className="flex w-fit gap-1 rounded-lg border border-border bg-muted/50 p-1">
              {(["goods", "barcode"] as const).map(value => (
                <Button
                  key={value}
                  size="sm"
                  variant={displayMode === value ? "secondary" : "ghost"}
                  aria-pressed={displayMode === value}
                  disabled={isLoading || isExporting}
                  onClick={() => { if (displayMode !== value) { setSelection({ scope: "", rows: [] }); setPage(1); setDisplayMode(value) } }}
                  className={cn("h-8 cursor-pointer", displayMode === value && "bg-background shadow-xs")}
                >
                  {value === "goods" ? "按货号" : "按编码"}
                </Button>
              ))}
            </div>
          ) : null}
        </div>

        <div className="relative isolate overflow-hidden rounded-lg border border-border bg-card">
          {isLoading ? (
            <>
              <div aria-hidden="true" className="pointer-events-none absolute inset-x-0 top-0 z-20 h-0.5 bg-primary/40 motion-safe:animate-pulse" />
              <div role="status" aria-live="polite" aria-atomic="true" className="pointer-events-none absolute inset-x-0 top-14 z-20 flex justify-center px-3">
                <div className="flex items-center gap-2 rounded-lg border border-border bg-background/95 px-3 py-2 text-xs text-foreground shadow-sm">
                  <LoaderCircle aria-hidden="true" className="size-3.5 shrink-0 text-muted-foreground motion-safe:animate-spin" />
                  <span>{showPreviousRows ? "正在更新，暂时显示上次结果" : "正在加载明细…"}</span>
                </div>
              </div>
            </>
          ) : null}
          <div
            role="region"
            aria-label={`${pageTitle}表格`}
            aria-busy={isLoading}
            data-scroll-restoration-key={`${stateKey}-table`}
            className="h-[max(26rem,calc(100dvh-22rem))] overflow-auto [overflow-anchor:none] [scrollbar-gutter:stable]"
          >
            <Table containerClassName="overflow-visible" className={cn("table-fixed text-xs [&_th]:whitespace-nowrap", byBarcode ? "min-w-[1800px]" : isPurchaseOrder ? "min-w-[1480px]" : "min-w-[1080px]")}>
              <colgroup>
                <col className="w-11" />
                <col className="w-14" /><col className="w-32" /><col className="w-44" />
                {isPurchaseOrder ? <><col className="w-24" /><col className="w-40" /></> : null}
                {byBarcode ? <><col className="w-56" /><col className="w-24" /><col className="w-24" /><col className="w-24" /><col className="w-24" /></> : null}
                <col className="w-24" /><col className="w-40" /><col className="w-28" />
                <col className="w-24" /><col className="w-28" /><col className="w-28" />
                <col className="w-24" /><col className="w-48" /><col className="w-48" />
              </colgroup>
              <TableHeader className="sticky top-0 z-10 bg-muted">
                <TableRow className="hover:bg-muted">
                  <TableHead className="text-center">
                    <input type="checkbox" aria-label="全选本页明细" checked={allPageSelected}
                      ref={element => { if (element) element.indeterminate = somePageSelected && !allPageSelected }}
                      onChange={event => toggleSelection(pageKeys, event.target.checked)} disabled={isLoading || isExporting || pageKeys.length === 0 || !canExport}
                      className="h-4 w-4 cursor-pointer rounded border border-input accent-primary disabled:cursor-not-allowed disabled:opacity-50" />
                  </TableHead>
                  <TableHead className="w-14 text-center">行号</TableHead>
                  <TableHead className="w-32">货号</TableHead>
                  <TableHead className="w-44">商品全名</TableHead>
                  {isPurchaseOrder ? <><TableHead className="w-24">颜色名称</TableHead><TableHead className="min-w-40">尺码及数量</TableHead></> : null}
                  {byBarcode ? <>
                    <TableHead className="w-56">商品编码</TableHead>
                    <TableHead className="w-24">颜色名称</TableHead>
                    <TableHead className="w-24">颜色条码</TableHead>
                    <TableHead className="w-24">尺码名称</TableHead>
                    <TableHead className="w-24">尺码条码</TableHead>
                  </> : null}
                  <TableHead className="w-24">单据类型</TableHead>
                  <TableHead className="w-40">单据编号</TableHead>
                  <TableHead className="w-28" aria-sort={dateSort === "asc" ? "ascending" : "descending"}>
                    <button
                      type="button"
                      disabled={isLoading}
                      aria-label={dateSort === "asc" ? "日期升序，点击切换为降序" : "日期降序，点击切换为升序"}
                      title={dateSort === "asc" ? "日期升序，点击切换为降序" : "日期降序，点击切换为升序"}
                      onClick={() => { setPage(1); setDateSort(dateSort === "asc" ? "desc" : "asc") }}
                      className="-ml-2 inline-flex h-8 cursor-pointer items-center gap-1 rounded-md px-2 hover:bg-muted-foreground/10 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:cursor-wait disabled:opacity-50"
                    >
                      日期
                      {dateSort === "asc" ? <ArrowUp aria-hidden="true" className="h-3.5 w-3.5" /> : <ArrowDown aria-hidden="true" className="h-3.5 w-3.5" />}
                    </button>
                  </TableHead>
                  <TableHead className="w-24 text-right">{quantityLabel}</TableHead>
                  <TableHead className="w-28 text-right">{amountLabel}</TableHead>
                  <TableHead className="w-28 text-right">{isPurchaseOrder ? "采购单价" : "零售金额"}</TableHead>
                  <TableHead className="w-24">单位编号</TableHead>
                  <TableHead className="w-48">单位全名</TableHead>
                  <TableHead className="w-48">仓库全名</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody className={showPreviousRows ? "opacity-45" : undefined}>
                {isLoading && !showPreviousRows ? (
                  <DetailTableSkeleton columnCount={columnCount} />
                ) : items.length === 0 ? (
                  <TableRow>
                    <TableCell colSpan={columnCount} className="h-40 text-center text-muted-foreground">{isSales ? "没有符合条件的销售明细" : isPurchaseOrder ? "没有符合条件的采购明细" : "没有符合条件的进货明细"}</TableCell>
                  </TableRow>
                ) : (
                  items.map((item) => (
                    <TableRow key={item.row_key ?? `${item.document_id}-${item.detail_id}`} data-state={selectedRows.has(selectionKey(item, byBarcode)) ? "selected" : undefined} className="odd:bg-muted/25">
                      <TableCell className="text-center">
                        <input type="checkbox" aria-label={`选择明细 ${item.document_number || item.document_id} ${item.product_code || item.detail_id}${byBarcode ? ` ${item.size_name || "未分配尺码"}` : ""}`}
                          checked={selectedRows.has(selectionKey(item, byBarcode))} onChange={event => toggleSelection([selectionKey(item, byBarcode)], event.target.checked)}
                          disabled={isLoading || isExporting || !canExport || !selectionKey(item, byBarcode)}
                          className="h-4 w-4 cursor-pointer rounded border border-input accent-primary disabled:cursor-not-allowed disabled:opacity-50" />
                      </TableCell>
                      <TableCell className="text-center text-muted-foreground tabular-nums">{item.row_number}</TableCell>
                      <TableCell className="truncate font-mono text-[11px]" title={item.product_code || ""}>{formatCell(item.product_code)}</TableCell>
                      <TableCell className="max-w-44 truncate" title={item.product_name || ""}>{formatCell(item.product_name)}</TableCell>
                      {isPurchaseOrder ? <>
                        <TableCell className="truncate" title={item.color_name || ""}>{formatCell(item.color_name)}</TableCell>
                        <TableCell className="whitespace-normal break-words font-mono text-[11px]">{Object.entries(item.size_quantities ?? {}).map(([size, quantity]) => `${size}: ${quantity}`).join("；") || "-"}</TableCell>
                      </> : null}
                      {byBarcode ? <>
                        <TableCell>
                          <div className="truncate font-mono text-[11px]" title={item.barcode || ""}>{formatCell(item.barcode)}</div>
                          {item.barcode_issue ? <p className="mt-1 whitespace-normal break-words text-[11px] text-amber-700 dark:text-amber-400">{item.barcode_issue}</p> : null}
                        </TableCell>
                        <TableCell className="truncate" title={item.color_name || ""}>{formatCell(item.color_name)}</TableCell>
                        <TableCell className="truncate font-mono" title={item.color_barcode || ""}>{formatCell(item.color_barcode)}</TableCell>
                        <TableCell className="truncate" title={item.size_name || ""}>{formatCell(item.size_name)}</TableCell>
                        <TableCell className="truncate font-mono" title={item.size_barcode || ""}>{formatCell(item.size_barcode)}</TableCell>
                      </> : null}
                      <TableCell>
                        <span className={cn(
                          "inline-flex whitespace-nowrap rounded-md px-2 py-0.5 text-[11px] font-medium",
                          isPurchaseOrder ? "bg-primary/10 text-primary" : item.document_type === documentTypes[1] ? "bg-red-100 text-red-700" : "bg-green-100 text-green-700",
                        )}>
                          {formatCell(item.document_type)}
                        </span>
                      </TableCell>
                      <TableCell className="truncate font-mono text-[11px]" title={item.document_number || ""}>{formatCell(item.document_number)}</TableCell>
                      <TableCell className="whitespace-nowrap tabular-nums">{formatCell(item.date)}</TableCell>
                      <TableCell className={cn("text-right font-mono tabular-nums", numericTone(item.purchase_quantity))}>{formatCell(item.purchase_quantity)}</TableCell>
                      <TableCell className={cn("text-right font-mono tabular-nums", numericTone(item.purchase_amount))}>{formatCell(item.purchase_amount)}</TableCell>
                      <TableCell className="text-right font-mono tabular-nums">{formatCell(isPurchaseOrder ? item.unit_price : item.retail_amount)}</TableCell>
                      <TableCell className="truncate font-mono text-[11px]" title={item.unit_code || ""}>{formatCell(item.unit_code)}</TableCell>
                      <TableCell className="max-w-48 truncate" title={item.unit_name || ""}>{formatCell(item.unit_name)}</TableCell>
                      <TableCell className="max-w-48 truncate" title={item.warehouse_name || ""}>{formatCell(item.warehouse_name)}</TableCell>
                    </TableRow>
                  ))
                )}
              </TableBody>
              <TableFooter className="sticky bottom-0 bg-muted">
                <TableRow>
                  <TableCell colSpan={(isPurchaseOrder ? 8 : byBarcode ? 11 : 6) + 1} className="font-medium">全部合计</TableCell>
                  <TableCell className={cn("text-right font-mono tabular-nums", numericTone(totals.all.purchase_quantity))}>{isLoading ? <div aria-label="合计更新中" className="ml-auto h-2.5 w-12 rounded-sm bg-muted-foreground/15 motion-safe:animate-pulse" /> : formatCell(totals.all.purchase_quantity)}</TableCell>
                  <TableCell className={cn("text-right font-mono tabular-nums", numericTone(totals.all.purchase_amount))}>{isLoading ? <div aria-label="合计更新中" className="ml-auto h-2.5 w-16 rounded-sm bg-muted-foreground/15 motion-safe:animate-pulse" /> : formatCell(totals.all.purchase_amount)}</TableCell>
                  <TableCell className="text-right font-mono tabular-nums">{isLoading ? <div aria-label="合计更新中" className="ml-auto h-2.5 w-16 rounded-sm bg-muted-foreground/15 motion-safe:animate-pulse" /> : isPurchaseOrder ? "-" : formatCell(totals.all.retail_amount)}</TableCell>
                  <TableCell colSpan={3} />
                </TableRow>
              </TableFooter>
            </Table>
          </div>
        </div>

        <div className="flex flex-wrap items-center justify-between gap-3 text-sm text-muted-foreground tabular-nums">
          <span>{isLoading ? showPreviousRows ? `上次结果：第 ${firstRow}-${lastRow} 条 / 共 ${total} 条` : "正在获取记录数…" : `第 ${firstRow}-${lastRow} 条 / 共 ${total} 条`}</span>
          {totalPages > 1 ? (
            <Pagination>
              <PaginationContent className="flex-nowrap">
                <PaginationItem>
                  <PaginationPrevious
                    text="上一页"
                    aria-disabled={isLoading || page <= 1}
                    tabIndex={isLoading || page <= 1 ? -1 : 0}
                    onClick={() => changePage(page - 1)}
                    onKeyDown={(event) => { if (event.key === "Enter") changePage(page - 1) }}
                    className={isLoading || page <= 1 ? "pointer-events-none opacity-50" : "cursor-pointer"}
                  />
                </PaginationItem>
                <PaginationItem className="sm:hidden">
                  <span className="px-2" aria-live="polite">{page} / {totalPages}</span>
                </PaginationItem>
                {pageRange.map((pageItem, index) =>
                  pageItem === "ellipsis" ? (
                    <PaginationItem key={`ellipsis-${index}`} className="hidden justify-center sm:flex" style={{ width: pageSlotWidth }}>
                      <PaginationEllipsis />
                    </PaginationItem>
                  ) : (
                    <PaginationItem key={pageItem} className="hidden justify-center sm:flex" style={{ width: pageSlotWidth }}>
                      <PaginationLink
                        isActive={pageItem === page}
                        aria-disabled={isLoading || pageItem === page}
                        tabIndex={isLoading || pageItem === page ? -1 : 0}
                        onClick={() => changePage(pageItem)}
                        onKeyDown={(event) => { if (event.key === "Enter") changePage(pageItem) }}
                        className={isLoading ? "pointer-events-none opacity-50" : pageItem === page ? "cursor-default" : "cursor-pointer"}
                      >
                        {pageItem}
                      </PaginationLink>
                    </PaginationItem>
                  ),
                )}
                <PaginationItem>
                  <PaginationNext
                    text="下一页"
                    aria-disabled={isLoading || page >= totalPages}
                    tabIndex={isLoading || page >= totalPages ? -1 : 0}
                    onClick={() => changePage(page + 1)}
                    onKeyDown={(event) => { if (event.key === "Enter") changePage(page + 1) }}
                    className={isLoading || page >= totalPages ? "pointer-events-none opacity-50" : "cursor-pointer"}
                  />
                </PaginationItem>
              </PaginationContent>
            </Pagination>
          ) : null}
        </div>
      </div>
      <OperationLogDialog
        module={isSales ? "sales_detail" : isPurchaseOrder ? "purchase_order_detail" : "purchase_inbound_detail"}
        title={`${pageTitle}操作日志`}
        open={operationLogOpen}
        onOpenChange={setOperationLogOpen}
      />
    </div>
  )
}
