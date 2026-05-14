"use client"

import { useEffect, useState } from "react"
import { Search, X } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"
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
import { Alert, AlertDescription } from "@/components/ui/alert"
import {
  listEndingInventory,
  ApiError,
  type EndingInventoryItem,
} from "@/lib/api"

const PAGE_SIZES = [10, 50, 100]

function getErrorMessage(error: unknown) {
  if (error instanceof ApiError) return error.message || `请求失败（${error.status}）`
  if (error instanceof Error) return error.message
  return "发生未知错误"
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

function getTodayMMDD(): string {
  const now = new Date()
  const mm = String(now.getMonth() + 1).padStart(2, "0")
  const dd = String(now.getDate()).padStart(2, "0")
  return `${mm}.${dd}`
}

export function EndingInventoryTab() {
  const [dateStart, setDateStart] = useState("")
  const [dateEnd, setDateEnd] = useState("")
  const [productCode, setProductCode] = useState("")
  const [submittedFilters, setSubmittedFilters] = useState<{
    stock_date: string
    date_start?: string
    date_end?: string
    product_code?: string
  } | null>(null)

  const [page, setPage] = useState(1)
  const [pageSize, setPageSize] = useState(PAGE_SIZES[0])
  const [items, setItems] = useState<EndingInventoryItem[]>([])
  const [total, setTotal] = useState(0)
  const [isLoading, setIsLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (!submittedFilters) return

    const filters = submittedFilters
    let cancelled = false
    async function load() {
      setIsLoading(true)
      setError(null)
      try {
        const response = await listEndingInventory({
          stock_date: filters.stock_date,
          date_start: filters.date_start,
          date_end: filters.date_end,
          product_code: filters.product_code,
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
  }, [page, pageSize, submittedFilters])

  const search = () => {
    setPage(1)
    setSubmittedFilters({
      stock_date: getTodayMMDD(),
      date_start: dateStart || undefined,
      date_end: dateEnd || undefined,
      product_code: productCode || undefined,
    })
  }

  const clearSearch = () => {
    setDateStart("")
    setDateEnd("")
    setProductCode("")
    setPage(1)
    setSubmittedFilters(null)
    setItems([])
    setTotal(0)
    setError(null)
  }

  const totalPages = Math.max(1, Math.ceil(total / pageSize))
  const pageRange = buildPageRange(page, totalPages)
  const hasData = submittedFilters !== null

  return (
    <div className="flex flex-col gap-5">
      {/* Search Card */}
      <div className="rounded-xl border border-border bg-card p-4">
        <div className="flex flex-wrap items-end gap-3">
          <div className="flex flex-col gap-1.5">
            <Label className="text-xs text-muted-foreground">单据日期范围</Label>
            <div className="flex items-center gap-2">
              <input
                type="date"
                value={dateStart}
                max={dateEnd || undefined}
                onChange={(e) => setDateStart(e.target.value)}
                className="h-9 rounded-lg border border-input bg-background px-3 py-2 text-sm shadow-xs outline-none transition-colors focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/50"
              />
              <span className="text-xs text-muted-foreground">至</span>
              <input
                type="date"
                value={dateEnd}
                min={dateStart || undefined}
                onChange={(e) => setDateEnd(e.target.value)}
                className="h-9 rounded-lg border border-input bg-background px-3 py-2 text-sm shadow-xs outline-none transition-colors focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/50"
              />
            </div>
          </div>
          <div className="flex flex-col gap-1.5">
            <Label className="text-xs text-muted-foreground">商品编码</Label>
            <Input
              value={productCode}
              onChange={(e) => setProductCode(e.target.value)}
              placeholder="商品编码"
              className="w-36"
              onKeyDown={(e) => { if (e.key === "Enter") search() }}
            />
          </div>
          <div className="flex gap-2 pb-0.5">
            <Button size="sm" onClick={search} className="cursor-pointer">
              <Search className="h-4 w-4" />
              <span className="ml-1.5">查询</span>
            </Button>
            {hasData && (
              <Button variant="outline" size="sm" onClick={clearSearch} className="cursor-pointer">
                <X className="h-4 w-4" />
                <span className="ml-1.5">清空</span>
              </Button>
            )}
          </div>
        </div>
      </div>

      {/* Summary Bar */}
      {hasData && (
        <div className="flex items-center justify-between text-sm text-muted-foreground">
          <span>共 {total} 条</span>
          <div className="flex items-center gap-2">
            <span>每页</span>
            <Select value={String(pageSize)} onChange={(e) => { setPageSize(Number(e.target.value)); setPage(1) }} className="w-20">
              {PAGE_SIZES.map((s) => (<option key={s} value={String(s)}>{s} 条</option>))}
            </Select>
          </div>
        </div>
      )}

      {/* Error */}
      {error && !isLoading && (
        <Alert className="border-destructive/30">
          <AlertDescription>{error}</AlertDescription>
        </Alert>
      )}

      {/* Placeholder before search */}
      {!hasData && !isLoading && !error && (
        <div className="rounded-xl border border-border bg-card py-20 text-center text-muted-foreground">
          点击查询查看期末库存
        </div>
      )}

      {/* Table */}
      {hasData && (
        <div className="rounded-xl border border-border bg-card">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>商品编码</TableHead>
                <TableHead>商品名称</TableHead>
                <TableHead>颜色及规格</TableHead>
                <TableHead className="text-right">期初库存</TableHead>
                <TableHead className="text-right">本期入库</TableHead>
                <TableHead className="text-right">本期出库</TableHead>
                <TableHead className="text-right">期末库存</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {isLoading && (
                <TableRow>
                  <TableCell colSpan={7} className="h-24 text-center text-muted-foreground">
                    加载中...
                  </TableCell>
                </TableRow>
              )}
              {!isLoading && items.length === 0 && (
                <TableRow>
                  <TableCell colSpan={7} className="h-24 text-center text-muted-foreground">
                    没有符合条件的数据
                  </TableCell>
                </TableRow>
              )}
              {items.map((item, i) => (
                <TableRow key={`${item.product_code}-${i}`}>
                  <TableCell className="font-mono text-xs">{item.product_code || "-"}</TableCell>
                  <TableCell>{item.product_name || "-"}</TableCell>
                  <TableCell className="max-w-32 truncate">{item.color_spec || "-"}</TableCell>
                  <TableCell className="text-right tabular-nums">{item.beginning_qty || "-"}</TableCell>
                  <TableCell className="text-right tabular-nums">{item.inbound_qty || "-"}</TableCell>
                  <TableCell className="text-right tabular-nums">{item.return_qty || "-"}</TableCell>
                  <TableCell className="text-right tabular-nums font-medium">{item.ending_qty || "-"}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
      )}

      {/* Pagination */}
      {hasData && totalPages > 1 && (
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
        </div>
      )}

      {/* Footer */}
      {hasData && (
        <div className="text-center text-xs text-muted-foreground">
          共 {total} 条记录 · 第 {total === 0 ? 0 : (page - 1) * pageSize + 1}-{Math.min(page * pageSize, total)} 条
        </div>
      )}
    </div>
  )
}
