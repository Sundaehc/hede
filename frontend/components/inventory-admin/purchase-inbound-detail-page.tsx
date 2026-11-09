"use client"

import { useSessionQueryState } from "@/lib/session-query-state"
import { useCrossTabRefresh } from "@/lib/use-cross-tab-refresh"

import { useEffect, useMemo, useState } from "react"
import { Download, History, Search, X } from "lucide-react"

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
import { buildPurchaseOrderDetailExportUrl, getPurchaseOrderDetailOptions, listPurchaseOrderDetails } from "@/lib/api"
import { cn } from "@/lib/utils"

const PAGE_SIZES = [50, 100, 200]
const FILTER_FIELD_CLASS_NAME = "min-w-0 space-y-1"
const FILTER_LABEL_CLASS_NAME = "text-[11px] font-medium text-muted-foreground"
const FILTER_CONTROL_CLASS_NAME = "bg-background"

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
  const pages: (number | "ellipsis")[] = [1]
  if (current > 3) pages.push("ellipsis")
  const start = Math.max(2, current - 1)
  const end = Math.min(total - 1, current + 1)
  for (let page = start; page <= end; page += 1) pages.push(page)
  if (current < total - 2) pages.push("ellipsis")
  pages.push(total)
  return pages
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

export function PurchaseInboundDetailPage({ mode = "inbound", canExport = true }: { mode?: "inbound" | "orders"; canExport?: boolean }) {
  const isPurchaseOrder = mode === "orders"
  const stateKey = isPurchaseOrder ? "purchase-order-details" : "purchase-inbound-details"
  const pageTitle = isPurchaseOrder ? "采购明细" : "商品进货明细"
  const quantityLabel = isPurchaseOrder ? "采购数量" : "进货数量"
  const amountLabel = isPurchaseOrder ? "采购金额" : "进货金额"
  const [dateStart, setDateStart] = useSessionQueryState(`${stateKey}:dateStart`, "")
  const [dateEnd, setDateEnd] = useSessionQueryState(`${stateKey}:dateEnd`, "")
  const [brands, setBrands] = useSessionQueryState<string[]>(`${stateKey}:brands`, [])
  const [brandOptions, setBrandOptions] = useState<SearchableFilterOption[]>([])
  const [documentType, setDocumentType] = useSessionQueryState(`${stateKey}:documentType`, "")
  const [supplier, setSupplier] = useSessionQueryState(`${stateKey}:supplier`, "")
  const [supplierOptions, setSupplierOptions] = useState<(Pick<SupplierItem, "name" | "factory_code"> & Partial<Pick<SupplierItem, "contact" | "address">>)[]>([])
  const [warehouse, setWarehouse] = useSessionQueryState<string[]>(`${stateKey}:warehouse`, [])
  const [warehouseOptions, setWarehouseOptions] = useState<Pick<WarehouseItem, "name" | "brand">[]>([])
  const [productCode, setProductCode] = useSessionQueryState(`${stateKey}:productCode`, "")
  const [productCodeCandidates, setProductCodeCandidates] = useState<{ query: string; items: InventoryDetailCandidate[] }>({ query: "", items: [] })
  const productCodeOptions = !isPurchaseOrder && productCode.trim() === productCodeCandidates.query ? productCodeCandidates.items : []
  const [productName, setProductName] = useSessionQueryState(`${stateKey}:productName`, "")
  const [colorName, setColorName] = useSessionQueryState(`${stateKey}:colorName`, "")
  const [sizeName, setSizeName] = useSessionQueryState(`${stateKey}:sizeName`, "")
  const [submittedFilters, setSubmittedFilters] = useSessionQueryState<SubmittedFilters>(`${stateKey}:submittedFilters`, {})
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
  const [isLoading, setIsLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [operationLogOpen, setOperationLogOpen] = useState(false)
  const [dataRevision, setDataRevision] = useState(0)
  const [referenceRevision, setReferenceRevision] = useState(0)
  useCrossTabRefresh(["inventory", "products"], () => setDataRevision((value) => value + 1))
  useCrossTabRefresh(["reference-data"], () => setReferenceRevision((value) => value + 1))

  useEffect(() => {
    let cancelled = false

    async function loadOptions() {
      try {
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
  }, [isPurchaseOrder, referenceRevision])

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
          page,
          pageSize,
        }
        const response = isPurchaseOrder
          ? await listPurchaseOrderDetails(params, controller.signal)
          : await listPurchaseInboundDetails(params)
        if (cancelled) return
        setItems(response.items)
        setTotal(response.total)
        setTotals(response.totals)
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
  }, [dataRevision, isPurchaseOrder, page, pageSize, submittedFilters])

  const totalPages = Math.max(1, Math.ceil(total / pageSize))
  const pageRange = useMemo(() => buildPageRange(page, totalPages), [page, totalPages])
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

  const firstRow = total === 0 ? 0 : (page - 1) * pageSize + 1
  const lastRow = Math.min(page * pageSize, total)

  const handleExport = () => {
    const link = document.createElement("a")
    link.href = isPurchaseOrder
      ? buildPurchaseOrderDetailExportUrl(submittedFilters)
      : buildPurchaseInboundDetailExportUrl(submittedFilters)
    link.rel = "noopener"
    link.click()
  }

  return (
    <div className="min-h-svh bg-background px-6 py-5">
      <div className="mx-auto flex max-w-[1600px] flex-col gap-4">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <h1 className="page-title">{pageTitle}</h1>
          </div>
          <div className="flex items-center gap-2 text-sm text-muted-foreground">
            <Button variant="outline" size="sm" aria-label="导出Excel" onClick={handleExport} disabled={!canExport || total === 0 || isLoading} className="cursor-pointer">
              <Download className="h-4 w-4" />
              <span className="ml-1.5 hidden sm:inline">导出Excel</span>
            </Button>
            <Button variant="outline" size="sm" aria-label="操作日志" onClick={() => setOperationLogOpen(true)} className="cursor-pointer">
              <History className="h-4 w-4" />
              <span className="ml-1.5 hidden sm:inline">操作日志</span>
            </Button>
            <span>共 {total} 条</span>
            <Select value={String(pageSize)} onChange={(event) => { setPageSize(Number(event.target.value)); setPage(1) }} className="w-24">
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
                <option value="进货单">进货单</option>
                <option value="进货退货单">进货退货单</option>
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
                placeholder="输入供应商"
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

        <div className="overflow-hidden rounded-lg border border-border bg-card">
          <div data-scroll-restoration-key={`${stateKey}-table`} className="max-h-[calc(100vh-22rem)] min-h-[26rem] overflow-auto">
            <Table className={cn("text-xs", isPurchaseOrder ? "min-w-[1480px] [&_th]:whitespace-nowrap" : "min-w-[1080px]")}>
              <TableHeader className="sticky top-0 z-10 bg-muted">
                <TableRow className="hover:bg-muted">
                  <TableHead className="w-14 text-center">行号</TableHead>
                  <TableHead className="w-32">货号</TableHead>
                  <TableHead className="w-44">商品全名</TableHead>
                  {isPurchaseOrder ? <><TableHead className="w-24">颜色名称</TableHead><TableHead className="min-w-40">尺码及数量</TableHead></> : null}
                  <TableHead className="w-24">单据类型</TableHead>
                  <TableHead className="w-40">单据编号</TableHead>
                  <TableHead className="w-28">日期</TableHead>
                  <TableHead className="w-24 text-right">{quantityLabel}</TableHead>
                  <TableHead className="w-28 text-right">{amountLabel}</TableHead>
                  <TableHead className="w-28 text-right">{isPurchaseOrder ? "采购单价" : "零售金额"}</TableHead>
                  <TableHead className="w-24">单位编号</TableHead>
                  <TableHead className="w-48">单位全名</TableHead>
                  <TableHead className="w-48">仓库全名</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {isLoading ? (
                  <TableRow>
                    <TableCell colSpan={isPurchaseOrder ? 14 : 12} className="h-40 text-center text-muted-foreground">加载中...</TableCell>
                  </TableRow>
                ) : items.length === 0 ? (
                  <TableRow>
                    <TableCell colSpan={isPurchaseOrder ? 14 : 12} className="h-40 text-center text-muted-foreground">{isPurchaseOrder ? "没有符合条件的采购明细" : "没有符合条件的进货明细"}</TableCell>
                  </TableRow>
                ) : (
                  items.map((item) => (
                    <TableRow key={`${item.document_id}-${item.detail_id}`} className="odd:bg-muted/25">
                      <TableCell className="text-center text-muted-foreground tabular-nums">{item.row_number}</TableCell>
                      <TableCell className="font-mono text-[11px]">{formatCell(item.product_code)}</TableCell>
                      <TableCell className="max-w-44 truncate" title={item.product_name || ""}>{formatCell(item.product_name)}</TableCell>
                      {isPurchaseOrder ? <>
                        <TableCell>{formatCell(item.color_name)}</TableCell>
                        <TableCell className="max-w-64 whitespace-normal font-mono text-[11px]">{Object.entries(item.size_quantities ?? {}).map(([size, quantity]) => `${size}: ${quantity}`).join("；") || "-"}</TableCell>
                      </> : null}
                      <TableCell>
                        <span className={cn(
                          "inline-flex rounded-md px-2 py-0.5 text-[11px] font-medium",
                          isPurchaseOrder ? "bg-primary/10 text-primary" : item.document_type === "进货退货单" ? "bg-red-100 text-red-700" : "bg-green-100 text-green-700",
                        )}>
                          {formatCell(item.document_type)}
                        </span>
                      </TableCell>
                      <TableCell className="font-mono text-[11px]">{formatCell(item.document_number)}</TableCell>
                      <TableCell className="tabular-nums">{formatCell(item.date)}</TableCell>
                      <TableCell className={cn("text-right font-mono tabular-nums", numericTone(item.purchase_quantity))}>{formatCell(item.purchase_quantity)}</TableCell>
                      <TableCell className={cn("text-right font-mono tabular-nums", numericTone(item.purchase_amount))}>{formatCell(item.purchase_amount)}</TableCell>
                      <TableCell className="text-right font-mono tabular-nums">{formatCell(isPurchaseOrder ? item.unit_price : item.retail_amount)}</TableCell>
                      <TableCell className="font-mono text-[11px]">{formatCell(item.unit_code)}</TableCell>
                      <TableCell className="max-w-48 truncate" title={item.unit_name || ""}>{formatCell(item.unit_name)}</TableCell>
                      <TableCell className="max-w-48 truncate" title={item.warehouse_name || ""}>{formatCell(item.warehouse_name)}</TableCell>
                    </TableRow>
                  ))
                )}
              </TableBody>
              <TableFooter className="sticky bottom-0 bg-muted">
                <TableRow>
                  <TableCell colSpan={isPurchaseOrder ? 8 : 6} className="font-medium">全部合计</TableCell>
                  <TableCell className={cn("text-right font-mono tabular-nums", numericTone(totals.all.purchase_quantity))}>{formatCell(totals.all.purchase_quantity)}</TableCell>
                  <TableCell className={cn("text-right font-mono tabular-nums", numericTone(totals.all.purchase_amount))}>{formatCell(totals.all.purchase_amount)}</TableCell>
                  <TableCell className="text-right font-mono tabular-nums">{isPurchaseOrder ? "-" : formatCell(totals.all.retail_amount)}</TableCell>
                  <TableCell colSpan={3} />
                </TableRow>
              </TableFooter>
            </Table>
          </div>
        </div>

        <div className="flex flex-wrap items-center justify-between gap-3 text-sm text-muted-foreground">
          <span>第 {firstRow}-{lastRow} 条 / 共 {total} 条</span>
          {totalPages > 1 ? (
            <Pagination>
              <PaginationContent>
                <PaginationItem>
                  <PaginationPrevious
                    text="上一页"
                    onClick={() => setPage((current) => Math.max(1, current - 1))}
                    className={page <= 1 ? "pointer-events-none opacity-50" : "cursor-pointer"}
                  />
                </PaginationItem>
                {pageRange.map((pageItem, index) =>
                  pageItem === "ellipsis" ? (
                    <PaginationItem key={`ellipsis-${index}`}>
                      <PaginationEllipsis />
                    </PaginationItem>
                  ) : (
                    <PaginationItem key={pageItem}>
                      <PaginationLink
                        isActive={pageItem === page}
                        onClick={() => pageItem !== page && setPage(pageItem)}
                        className={pageItem === page ? "cursor-default" : "cursor-pointer"}
                      >
                        {pageItem}
                      </PaginationLink>
                    </PaginationItem>
                  ),
                )}
                <PaginationItem>
                  <PaginationNext
                    text="下一页"
                    onClick={() => setPage((current) => Math.min(totalPages, current + 1))}
                    className={page >= totalPages ? "pointer-events-none opacity-50" : "cursor-pointer"}
                  />
                </PaginationItem>
              </PaginationContent>
            </Pagination>
          ) : null}
        </div>
      </div>
      <OperationLogDialog
        module={isPurchaseOrder ? "purchase_order_detail" : "purchase_inbound_detail"}
        title={`${pageTitle}操作日志`}
        open={operationLogOpen}
        onOpenChange={setOperationLogOpen}
      />
    </div>
  )
}
