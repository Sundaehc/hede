"use client"

import { useEffect, useMemo, useState } from "react"
import { Search, X } from "lucide-react"

import { Alert, AlertDescription } from "@/components/ui/alert"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
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
import { ApiError, listPurchaseInboundDetails, type PurchaseInboundDetailItem } from "@/lib/api"
import { cn } from "@/lib/utils"

const PAGE_SIZES = [50, 100, 200]
const FILTER_FIELD_CLASS_NAME = "min-w-0 space-y-1"
const FILTER_LABEL_CLASS_NAME = "text-[11px] font-medium text-muted-foreground"
const FILTER_CONTROL_CLASS_NAME = "bg-background"

type SubmittedFilters = {
  date_start?: string
  date_end?: string
  document_type?: string
  supplier?: string
  warehouse?: string
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

export function PurchaseInboundDetailPage() {
  const [dateStart, setDateStart] = useState("")
  const [dateEnd, setDateEnd] = useState("")
  const [documentType, setDocumentType] = useState("")
  const [supplier, setSupplier] = useState("")
  const [warehouse, setWarehouse] = useState("")
  const [productCode, setProductCode] = useState("")
  const [productName, setProductName] = useState("")
  const [colorName, setColorName] = useState("")
  const [sizeName, setSizeName] = useState("")
  const [submittedFilters, setSubmittedFilters] = useState<SubmittedFilters>({})
  const [page, setPage] = useState(1)
  const [pageSize, setPageSize] = useState(PAGE_SIZES[0])
  const [items, setItems] = useState<PurchaseInboundDetailItem[]>([])
  const [total, setTotal] = useState(0)
  const [totals, setTotals] = useState({ purchase_quantity: "0", purchase_amount: "0", retail_amount: "" })
  const [isLoading, setIsLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false

    async function load() {
      setIsLoading(true)
      setError(null)
      try {
        const response = await listPurchaseInboundDetails({
          ...submittedFilters,
          page,
          pageSize,
        })
        if (cancelled) return
        setItems(response.items)
        setTotal(response.total)
        setTotals(response.totals)
      } catch (loadError) {
        if (cancelled) return
        setItems([])
        setTotal(0)
        setTotals({ purchase_quantity: "0", purchase_amount: "0", retail_amount: "" })
        setError(getErrorMessage(loadError))
      } finally {
        if (!cancelled) setIsLoading(false)
      }
    }

    void load()

    return () => {
      cancelled = true
    }
  }, [page, pageSize, submittedFilters])

  const totalPages = Math.max(1, Math.ceil(total / pageSize))
  const pageRange = useMemo(() => buildPageRange(page, totalPages), [page, totalPages])

  const submitSearch = () => {
    setPage(1)
    setSubmittedFilters({
      date_start: dateStart || undefined,
      date_end: dateEnd || undefined,
      document_type: documentType || undefined,
      supplier: supplier || undefined,
      warehouse: warehouse || undefined,
      product_code: productCode || undefined,
      product_name: productName || undefined,
      color_name: colorName || undefined,
      size_name: sizeName || undefined,
    })
  }

  const clearSearch = () => {
    setDateStart("")
    setDateEnd("")
    setDocumentType("")
    setSupplier("")
    setWarehouse("")
    setProductCode("")
    setProductName("")
    setColorName("")
    setSizeName("")
    setPage(1)
    setSubmittedFilters({})
  }

  const firstRow = total === 0 ? 0 : (page - 1) * pageSize + 1
  const lastRow = Math.min(page * pageSize, total)

  return (
    <div className="min-h-svh bg-background px-6 py-5">
      <div className="mx-auto flex max-w-[1600px] flex-col gap-4">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <h1 className="page-title">商品进货明细</h1>
          </div>
          <div className="flex items-center gap-2 text-sm text-muted-foreground">
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
            <div className={FILTER_FIELD_CLASS_NAME}>
              <Label className={FILTER_LABEL_CLASS_NAME}>开始日期</Label>
              <Input className={FILTER_CONTROL_CLASS_NAME} type="date" value={dateStart} max={dateEnd || undefined} onChange={(event) => setDateStart(event.target.value)} />
            </div>
            <div className={FILTER_FIELD_CLASS_NAME}>
              <Label className={FILTER_LABEL_CLASS_NAME}>结束日期</Label>
              <Input className={FILTER_CONTROL_CLASS_NAME} type="date" value={dateEnd} min={dateStart || undefined} onChange={(event) => setDateEnd(event.target.value)} />
            </div>
            <div className={FILTER_FIELD_CLASS_NAME}>
              <Label className={FILTER_LABEL_CLASS_NAME}>单据类型</Label>
              <Select className={FILTER_CONTROL_CLASS_NAME} value={documentType} onChange={(event) => setDocumentType(event.target.value)}>
                <option value="">全部</option>
                <option value="进货单">进货单</option>
                <option value="进货退货单">进货退货单</option>
              </Select>
            </div>
            <div className={FILTER_FIELD_CLASS_NAME}>
              <Label className={FILTER_LABEL_CLASS_NAME}>仓库全名</Label>
              <Input className={FILTER_CONTROL_CLASS_NAME} value={warehouse} onChange={(event) => setWarehouse(event.target.value)} onKeyDown={(event) => { if (event.key === "Enter") submitSearch() }} />
            </div>
            <div className={FILTER_FIELD_CLASS_NAME}>
              <Label className={FILTER_LABEL_CLASS_NAME}>商品名称</Label>
              <Input className={FILTER_CONTROL_CLASS_NAME} value={productName} onChange={(event) => setProductName(event.target.value)} onKeyDown={(event) => { if (event.key === "Enter") submitSearch() }} />
            </div>
            <div className={FILTER_FIELD_CLASS_NAME}>
              <Label className={FILTER_LABEL_CLASS_NAME}>单位全名</Label>
              <Input className={FILTER_CONTROL_CLASS_NAME} value={supplier} onChange={(event) => setSupplier(event.target.value)} onKeyDown={(event) => { if (event.key === "Enter") submitSearch() }} />
            </div>
            <div className={FILTER_FIELD_CLASS_NAME}>
              <Label className={FILTER_LABEL_CLASS_NAME}>颜色名称</Label>
              <Input className={FILTER_CONTROL_CLASS_NAME} value={colorName} onChange={(event) => setColorName(event.target.value)} onKeyDown={(event) => { if (event.key === "Enter") submitSearch() }} />
            </div>
            <div className={FILTER_FIELD_CLASS_NAME}>
              <Label className={FILTER_LABEL_CLASS_NAME}>尺码名称</Label>
              <Input className={FILTER_CONTROL_CLASS_NAME} value={sizeName} onChange={(event) => setSizeName(event.target.value)} onKeyDown={(event) => { if (event.key === "Enter") submitSearch() }} />
            </div>
            <div className={FILTER_FIELD_CLASS_NAME}>
              <Label className={FILTER_LABEL_CLASS_NAME}>货号</Label>
              <Input className={FILTER_CONTROL_CLASS_NAME} value={productCode} onChange={(event) => setProductCode(event.target.value)} onKeyDown={(event) => { if (event.key === "Enter") submitSearch() }} />
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
          <div className="max-h-[calc(100vh-22rem)] min-h-[26rem] overflow-auto">
            <Table className="min-w-[1080px] text-xs">
              <TableHeader className="sticky top-0 z-10 bg-muted">
                <TableRow className="hover:bg-muted">
                  <TableHead className="w-14 text-center">行号</TableHead>
                  <TableHead className="w-32">货号</TableHead>
                  <TableHead className="w-44">商品全名</TableHead>
                  <TableHead className="w-24">单据类型</TableHead>
                  <TableHead className="w-40">单据编号</TableHead>
                  <TableHead className="w-28">日期</TableHead>
                  <TableHead className="w-24 text-right">进货数量</TableHead>
                  <TableHead className="w-28 text-right">进货金额</TableHead>
                  <TableHead className="w-28 text-right">零售金额</TableHead>
                  <TableHead className="w-24">单位编号</TableHead>
                  <TableHead className="w-48">单位全名</TableHead>
                  <TableHead className="w-48">仓库全名</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {isLoading ? (
                  <TableRow>
                    <TableCell colSpan={12} className="h-40 text-center text-muted-foreground">加载中...</TableCell>
                  </TableRow>
                ) : items.length === 0 ? (
                  <TableRow>
                    <TableCell colSpan={12} className="h-40 text-center text-muted-foreground">没有符合条件的进货明细</TableCell>
                  </TableRow>
                ) : (
                  items.map((item) => (
                    <TableRow key={`${item.document_id}-${item.detail_id}`} className="odd:bg-muted/25">
                      <TableCell className="text-center text-muted-foreground tabular-nums">{item.row_number}</TableCell>
                      <TableCell className="font-mono text-[11px]">{formatCell(item.product_code)}</TableCell>
                      <TableCell className="max-w-44 truncate" title={item.product_name || ""}>{formatCell(item.product_name)}</TableCell>
                      <TableCell>
                        <span className={cn(
                          "inline-flex rounded-md px-2 py-0.5 text-[11px] font-medium",
                          item.document_type === "进货退货单" ? "bg-red-100 text-red-700" : "bg-green-100 text-green-700",
                        )}>
                          {formatCell(item.document_type)}
                        </span>
                      </TableCell>
                      <TableCell className="font-mono text-[11px]">{formatCell(item.document_number)}</TableCell>
                      <TableCell className="tabular-nums">{formatCell(item.date)}</TableCell>
                      <TableCell className={cn("text-right font-mono tabular-nums", numericTone(item.purchase_quantity))}>{formatCell(item.purchase_quantity)}</TableCell>
                      <TableCell className={cn("text-right font-mono tabular-nums", numericTone(item.purchase_amount))}>{formatCell(item.purchase_amount)}</TableCell>
                      <TableCell className="text-right font-mono tabular-nums">{formatCell(item.retail_amount)}</TableCell>
                      <TableCell className="font-mono text-[11px]">{formatCell(item.unit_code)}</TableCell>
                      <TableCell className="max-w-48 truncate" title={item.unit_name || ""}>{formatCell(item.unit_name)}</TableCell>
                      <TableCell className="max-w-48 truncate" title={item.warehouse_name || ""}>{formatCell(item.warehouse_name)}</TableCell>
                    </TableRow>
                  ))
                )}
              </TableBody>
              <TableFooter className="sticky bottom-0 bg-muted">
                <TableRow>
                  <TableCell colSpan={6} className="font-medium">合计</TableCell>
                  <TableCell className={cn("text-right font-mono tabular-nums", numericTone(totals.purchase_quantity))}>{formatCell(totals.purchase_quantity)}</TableCell>
                  <TableCell className={cn("text-right font-mono tabular-nums", numericTone(totals.purchase_amount))}>{formatCell(totals.purchase_amount)}</TableCell>
                  <TableCell className="text-right font-mono tabular-nums">{formatCell(totals.retail_amount)}</TableCell>
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
    </div>
  )
}
