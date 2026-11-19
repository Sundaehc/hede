"use client"

import { Fragment, useCallback, useEffect, useMemo, useRef, useState, type Dispatch, type SetStateAction } from "react"
import { ArrowLeft, Download, RefreshCw, X } from "lucide-react"
import { Button } from "@/components/ui/button"
import { DateRangeControl } from "@/components/ui/date-range-control"
import { useAuth } from "@/components/auth/auth-provider"
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog"
import { defaultLedgerQuery, type LedgerQueryState } from "@/lib/supplier-ledger-tabs"
import {
  ApiError,
  downloadGeneralCustomerLedger,
  downloadCounterpartyLedger,
  listCounterpartyLedger,
  listDetails,
  type CounterpartyLedgerResponse,
  type InventoryDetail,
  type CounterpartyLedgerSortKey,
} from "@/lib/api"

type CounterpartyLedgerDialogProps = {
  open: boolean
  counterpartyType: "supplier" | "customer"
  name: string
  onOpenChange: (open: boolean) => void
  presentation?: "dialog" | "page"
  queryState?: LedgerQueryState
  onQueryChange?: Dispatch<SetStateAction<LedgerQueryState>>
}

function getErrorMessage(error: unknown) {
  if (error instanceof ApiError) return error.message || `请求失败（${error.status}）`
  if (error instanceof Error) return error.message
  return "发生未知错误"
}

function formatMoney(value: string | number | null | undefined) {
  if (!value) return "-"
  const numeric = Number(value)
  if (!Number.isFinite(numeric)) return value
  return new Intl.NumberFormat("zh-CN", { minimumFractionDigits: 0, maximumFractionDigits: 2 }).format(numeric)
}

const EU_SIZE_COLUMNS = ["35", "36", "37", "38", "39", "40", "41", "42", "43", "44"]
const MILLIMETER_SIZE_COLUMNS = ["220", "225", "230", "235", "240", "245", "250", "255", "260", "265", "270", "275", "280", "285"]
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
const LEDGER_COLUMN_COUNT = 7

function getDetailSizeColumns(details: InventoryDetail[]) {
  const hasMillimeterSize = details.some((detail) =>
    Object.keys(detail.size_quantities || {}).some((size) => MILLIMETER_SIZE_COLUMNS.includes(size)),
  )
  return hasMillimeterSize ? MILLIMETER_SIZE_COLUMNS : EU_SIZE_COLUMNS
}

function getDetailSizeQuantity(values: Record<string, string> | null | undefined, size: string, sizeColumns: string[]) {
  if (!values) return ""
  if (values[size]) return values[size]
  if (sizeColumns === MILLIMETER_SIZE_COLUMNS) {
    const euSize = MILLIMETER_TO_EU_SIZE[size]
    return euSize ? values[euSize] || "" : ""
  }
  const millimeterSize = EU_TO_MILLIMETER_SIZE[size]
  return millimeterSize ? values[millimeterSize] || "" : ""
}

export function CounterpartyLedgerDialog({ open, counterpartyType, name, onOpenChange, presentation = "dialog", queryState, onQueryChange }: CounterpartyLedgerDialogProps) {
  const { user, hasPermission } = useAuth()
  const [localQuery, setLocalQuery] = useState(defaultLedgerQuery)
  const query = queryState ?? localQuery
  const { dateStart, dateEnd, dateStartInput, dateEndInput, sortBy, sortDirection } = query
  const updateQuery = (patch: Partial<LedgerQueryState>) => {
    const setQuery = onQueryChange ?? setLocalQuery
    setQuery((current) => ({ ...current, ...patch }))
  }
  const [refreshVersion, setRefreshVersion] = useState(0)
  const requestRef = useRef<AbortController | null>(null)
  const exportRef = useRef<AbortController | null>(null)
  const detailScopeRef = useRef(0)
  const [ledger, setLedger] = useState<CounterpartyLedgerResponse | null>(null)
  const [isLoading, setIsLoading] = useState(false)
  const [error, setError] = useState("")
  const [expandedId, setExpandedId] = useState<number | null>(null)
  const [detailsByDocumentId, setDetailsByDocumentId] = useState<Record<number, InventoryDetail[]>>({})
  const [detailLoadingId, setDetailLoadingId] = useState<number | null>(null)
  const [detailErrorByDocumentId, setDetailErrorByDocumentId] = useState<Record<number, string>>({})
  const [isExporting, setIsExporting] = useState(false)

  const title = counterpartyType === "supplier" ? "应付款-明细账本" : "应收款-明细账本"
  const unitLabel = counterpartyType === "supplier" ? "供应商" : "一般客户"
  const canExportCustomerLedger = counterpartyType === "customer" && (
    user?.role_code === "super_admin" || user?.department_code === "财务部"
  )
  const canExport = counterpartyType === "supplier" ? hasPermission("inventory.export") : canExportCustomerLedger

  const load = useCallback(async () => {
    if (!open || !name) return
    requestRef.current?.abort()
    const controller = new AbortController()
    requestRef.current = controller
    detailScopeRef.current += 1
    setIsLoading(true)
    setLedger(null)
    setError("")
    try {
      const response = await listCounterpartyLedger({
        counterpartyType,
        name,
        dateStart,
        dateEnd,
        sortBy,
        sortDirection,
      }, controller.signal)
      if (controller.signal.aborted) return
      setLedger(response)
      setExpandedId(null)
      setDetailsByDocumentId({})
      setDetailErrorByDocumentId({})
    } catch (err) {
      if (controller.signal.aborted) return
      setLedger(null)
      setError(getErrorMessage(err))
    } finally {
      if (!controller.signal.aborted) setIsLoading(false)
    }
  }, [counterpartyType, dateEnd, dateStart, name, open, sortBy, sortDirection])

  useEffect(() => {
    if (open) void load()
    return () => { requestRef.current?.abort(); detailScopeRef.current += 1 }
  }, [load, open, refreshVersion])

  useEffect(() => {
    setIsExporting(false)
    return () => { exportRef.current?.abort() }
  }, [open, counterpartyType, name, dateStart, dateEnd, sortBy, sortDirection])

  useEffect(() => {
    if (!open) {
      setExpandedId(null)
      setDetailsByDocumentId({})
      setDetailErrorByDocumentId({})
      setDetailLoadingId(null)
    }
  }, [open])

  const toggleDetails = useCallback(async (documentId: number) => {
    if (expandedId === documentId) {
      setExpandedId(null)
      return
    }

    setExpandedId(documentId)
    if (detailsByDocumentId[documentId]) return

    setDetailLoadingId(documentId)
    const scope = detailScopeRef.current
    setDetailErrorByDocumentId((current) => {
      const next = { ...current }
      delete next[documentId]
      return next
    })
    try {
      const response = await listDetails(documentId)
      if (scope !== detailScopeRef.current) return
      setDetailsByDocumentId((current) => ({ ...current, [documentId]: response.items }))
    } catch (err) {
      if (scope !== detailScopeRef.current) return
      setDetailErrorByDocumentId((current) => ({ ...current, [documentId]: getErrorMessage(err) }))
      setDetailsByDocumentId((current) => ({ ...current, [documentId]: [] }))
    } finally {
      if (scope === detailScopeRef.current) setDetailLoadingId((current) => (current === documentId ? null : current))
    }
  }, [detailsByDocumentId, expandedId])

  const handleExport = async () => {
    if (!canExport || !name || isExporting || isLoading || !ledger) return
    const controller = new AbortController()
    exportRef.current = controller
    setIsExporting(true)
    setError("")
    try {
      const params = { name, dateStart, dateEnd, sortBy, sortDirection }
      if (counterpartyType === "customer") await downloadGeneralCustomerLedger(params, controller.signal)
      else await downloadCounterpartyLedger("supplier", params, controller.signal)
    } catch (err) {
      if (controller.signal.aborted) return
      setError(getErrorMessage(err))
    } finally {
      if (!controller.signal.aborted) setIsExporting(false)
    }
  }

  const rows = ledger?.items ?? []
  const totals = useMemo(() => ({
    beginning: ledger?.beginning_balance ?? "0",
    increase: ledger?.increase_total ?? "0",
    decrease: ledger?.decrease_total ?? "0",
    ending: ledger?.ending_balance ?? "0",
  }), [ledger])

  const Heading = presentation === "page" ? "h1" : DialogTitle
  const columns: { key: CounterpartyLedgerSortKey; label: string; numeric?: boolean }[] = [
    { key: "row_number", label: "行号" }, { key: "date", label: "日期" },
    { key: "document_number", label: "单据编号" }, { key: "summary", label: "单据摘要" },
    { key: "increase_amount", label: "增加金额", numeric: true },
    { key: "decrease_amount", label: "减少金额", numeric: true },
    { key: "balance", label: "余额", numeric: true },
  ]
  const content = (
    <>
        <DialogHeader>
          <div className="flex items-center justify-between gap-3">
            <div>
              <Heading className={presentation === "page" ? "page-title" : undefined}>{title}</Heading>
              <p className="mt-1 text-sm text-muted-foreground">
                {unitLabel} <span className="font-medium text-foreground">{name || "-"}</span>
              </p>
            </div>
            <Button
              type="button"
              variant="ghost"
              size={presentation === "page" ? "sm" : "icon"}
              onClick={() => onOpenChange(false)}
              className={presentation === "page" ? "shrink-0 cursor-pointer" : "h-8 w-8 cursor-pointer"}
              aria-label={presentation === "page" ? "返回供应商管理" : "关闭明细账本"}
              title={presentation === "page" ? "返回供应商管理" : "关闭"}
            >
              {presentation === "page" ? <><ArrowLeft className="h-4 w-4" /><span>返回供应商管理</span></> : <X className="h-4 w-4" />}
            </Button>
          </div>
        </DialogHeader>

        <div className="mt-3 space-y-3 overflow-hidden">
          <div className="rounded-lg border border-border bg-muted/25 p-3">
            <DateRangeControl
              start={dateStartInput}
              end={dateEndInput}
              onStartChange={(value) => updateQuery({ dateStartInput: value })}
              onEndChange={(value) => updateQuery({ dateEndInput: value })}
              actions={<>
              <Button size="lg" onClick={() => {
                if (dateStartInput && dateEndInput && dateStartInput > dateEndInput) {
                  setError("起始日期不能晚于截止日期")
                  return
                }
                updateQuery({ dateStart: dateStartInput, dateEnd: dateEndInput })
                setRefreshVersion((value) => value + 1)
              }} disabled={isLoading || !name} className="cursor-pointer">
                <RefreshCw className={`h-4 w-4 ${isLoading ? "animate-spin" : ""}`} />
                <span>{isLoading ? "查询中..." : "查询"}</span>
              </Button>
              {canExport && (
                <Button type="button" size="lg" variant="outline" onClick={() => void handleExport()} disabled={isExporting || isLoading || !name || !ledger} className="cursor-pointer">
                  <Download className="h-4 w-4" />
                  <span>{isExporting ? "导出中..." : "导出 Excel"}</span>
                </Button>
              )}
              </>}
            />
          </div>

          <div className="grid gap-2 sm:grid-cols-4">
            <div className="rounded-lg border border-border bg-card px-3 py-2">
              <p className="text-xs text-muted-foreground">此前余额</p>
              <p className="mt-1 text-right font-mono text-sm tabular-nums">{formatMoney(totals.beginning)}</p>
            </div>
            <div className="rounded-lg border border-border bg-card px-3 py-2">
              <p className="text-xs text-muted-foreground">增加金额</p>
              <p className="mt-1 text-right font-mono text-sm tabular-nums">{formatMoney(totals.increase)}</p>
            </div>
            <div className="rounded-lg border border-border bg-card px-3 py-2">
              <p className="text-xs text-muted-foreground">减少金额</p>
              <p className="mt-1 text-right font-mono text-sm tabular-nums">{formatMoney(totals.decrease)}</p>
            </div>
            <div className="rounded-lg border border-border bg-card px-3 py-2">
              <p className="text-xs text-muted-foreground">期末余额</p>
              <p className="mt-1 text-right font-mono text-sm font-semibold tabular-nums">{formatMoney(totals.ending)}</p>
            </div>
          </div>

          {error && (
            <div role="alert" className="rounded-lg border border-destructive/25 bg-destructive/10 px-3 py-2 text-sm text-destructive">
              {error}
            </div>
          )}

          <p className="text-xs text-muted-foreground">点击表头可切换排序；余额按单据发生顺序计算，排序仅调整展示顺序。</p>
          <div className={`${presentation === "page" ? "max-h-[calc(100svh-23rem)] min-h-64" : "max-h-[46vh]"} overflow-auto rounded-lg border border-border`}>
            <table className="w-full min-w-[1120px] table-fixed text-sm">
              <colgroup>
                <col className="w-14" />
                <col className="w-28" />
                <col className="w-44" />
                <col />
                <col className="w-28" />
                <col className="w-28" />
                <col className="w-28" />
              </colgroup>
              <thead className="sticky top-0 z-10">
                <tr className="border-b border-border bg-muted text-left text-muted-foreground">
                  {columns.map((column) => <th key={column.key} aria-sort={sortBy === column.key ? sortDirection === "asc" ? "ascending" : "descending" : "none"} className={`whitespace-nowrap px-3 py-2 font-medium ${column.numeric ? "text-right" : ""}`}>
                    <button type="button" onClick={() => updateQuery({ sortBy: column.key, sortDirection: sortBy === column.key ? sortDirection === "asc" ? "desc" : "asc" : column.numeric ? "desc" : "asc" })} className="cursor-pointer rounded px-1 py-1 hover:bg-muted-foreground/10 focus-visible:outline-2 focus-visible:outline-ring" aria-label={`按${column.label}排序`}>
                      {column.label}<span aria-hidden="true" className="ml-1">{sortBy === column.key ? sortDirection === "asc" ? "↑" : "↓" : "↕"}</span>
                    </button>
                  </th>)}
                </tr>
              </thead>
              <tbody className="divide-y divide-border">
                {isLoading && rows.length === 0 && (
                  <tr>
                    <td colSpan={LEDGER_COLUMN_COUNT} className="px-4 py-10 text-center text-muted-foreground">加载中...</td>
                  </tr>
                )}
                {!isLoading && !error && rows.length === 0 && (
                  <tr>
                    <td colSpan={LEDGER_COLUMN_COUNT} className="px-4 py-10 text-center text-muted-foreground">该时间范围内暂无单据</td>
                  </tr>
                )}
                {rows.map((item) => {
                  const isExpanded = expandedId === item.id
                  const isAccountingDocument = ACCOUNTING_DOCUMENT_TYPES.has(item.document_type || "")
                  const details = detailsByDocumentId[item.id] ?? []
                  const sizeColumns = getDetailSizeColumns(details)
                  const detailError = detailErrorByDocumentId[item.id]
                  const isDetailLoading = detailLoadingId === item.id

                  return (
                    <Fragment key={item.id}>
                      <tr
                        className={`cursor-pointer transition-colors hover:bg-muted/35 ${isExpanded ? "bg-muted/30" : ""}`}
                        onClick={() => void toggleDetails(item.id)}
                        title={isExpanded ? "点击收起单据明细" : "点击查看单据明细"}
                      >
                        <td className="px-3 py-2 text-muted-foreground tabular-nums">{item.row_number}</td>
                        <td className="px-3 py-2 whitespace-nowrap tabular-nums">{item.date || "-"}</td>
                        <td className="px-3 py-2 font-mono text-xs leading-5 break-words">{item.document_number || item.id}</td>
                        <td className="px-3 py-2">
                          <div className="min-w-0">
                            <p className="truncate" title={item.summary || ""}>{item.summary || "-"}</p>
                            <p className="mt-0.5 text-xs text-muted-foreground">{item.document_type || "-"}</p>
                          </div>
                        </td>
                        <td className="whitespace-nowrap px-3 py-2 text-right font-mono tabular-nums">{formatMoney(item.increase_amount)}</td>
                        <td className="whitespace-nowrap px-3 py-2 text-right font-mono tabular-nums">{formatMoney(item.decrease_amount)}</td>
                        <td className="whitespace-nowrap px-3 py-2 text-right font-mono tabular-nums">{formatMoney(item.balance)}</td>
                      </tr>
                      {isExpanded && (
                        <tr className="bg-muted/20">
                          <td colSpan={LEDGER_COLUMN_COUNT} className="px-3 py-3">
                            <div className="overflow-hidden rounded-md border border-border bg-background">
                              {isDetailLoading ? (
                                <div className="px-4 py-6 text-center text-sm text-muted-foreground">明细加载中...</div>
                              ) : detailError ? (
                                <div className="px-4 py-3 text-sm text-destructive">{detailError}</div>
                              ) : details.length === 0 ? (
                                <div className="px-4 py-6 text-center text-sm text-muted-foreground">该单据暂无明细</div>
                              ) : isAccountingDocument ? (
                                <table className="w-full text-xs">
                                  <thead>
                                    <tr className="border-b border-border bg-muted/50 text-left text-muted-foreground">
                                      <th className="px-3 py-2 font-medium">序号</th>
                                      <th className="px-3 py-2 font-medium">费用项目名 / 科目</th>
                                      <th className="px-3 py-2 text-right font-medium">金额</th>
                                      <th className="px-3 py-2 font-medium">备注</th>
                                    </tr>
                                  </thead>
                                  <tbody className="divide-y divide-border">
                                    {details.map((detail, index) => (
                                      <tr key={detail.id}>
                                        <td className="px-3 py-2 text-muted-foreground tabular-nums">{index + 1}</td>
                                        <td className="px-3 py-2">{detail.product_name || "-"}</td>
                                        <td className="px-3 py-2 text-right font-mono tabular-nums">{formatMoney(detail.amount)}</td>
                                        <td className="px-3 py-2">{detail.remark || "-"}</td>
                                      </tr>
                                    ))}
                                  </tbody>
                                </table>
                              ) : (
                                <div className="overflow-x-auto">
                                  <table className="w-full min-w-[1080px] text-xs">
                                    <thead>
                                      <tr className="border-b border-border bg-muted/50 text-left text-muted-foreground">
                                        <th className="px-3 py-2 font-medium">序号</th>
                                        <th className="px-3 py-2 font-medium">货号</th>
                                        <th className="px-3 py-2 font-medium">商品全名</th>
                                        <th className="px-3 py-2 font-medium">颜色条码</th>
                                        <th className="px-3 py-2 font-medium">颜色名称</th>
                                        {sizeColumns.map((size) => (
                                          <th key={size} className="px-2 py-2 text-right font-medium">{size}</th>
                                        ))}
                                        <th className="px-3 py-2 text-right font-medium">数量</th>
                                        <th className="px-3 py-2 text-right font-medium">单价</th>
                                        <th className="px-3 py-2 text-right font-medium">金额</th>
                                      </tr>
                                    </thead>
                                    <tbody className="divide-y divide-border">
                                      {details.map((detail, index) => (
                                        <tr key={detail.id}>
                                          <td className="px-3 py-2 text-muted-foreground tabular-nums">{index + 1}</td>
                                          <td className="px-3 py-2 font-mono">{detail.product_code || "-"}</td>
                                          <td className="px-3 py-2">{detail.product_name || "-"}</td>
                                          <td className="px-3 py-2 font-mono">{detail.color_barcode || "-"}</td>
                                          <td className="px-3 py-2">{detail.color_name || detail.color_spec || "-"}</td>
                                          {sizeColumns.map((size) => (
                                            <td key={size} className="px-2 py-2 text-right font-mono tabular-nums">
                                              {getDetailSizeQuantity(detail.size_quantities, size, sizeColumns) || "-"}
                                            </td>
                                          ))}
                                          <td className="px-3 py-2 text-right font-mono tabular-nums">{detail.quantity || "-"}</td>
                                          <td className="px-3 py-2 text-right font-mono tabular-nums">{formatMoney(detail.unit_price)}</td>
                                          <td className="px-3 py-2 text-right font-mono tabular-nums">{formatMoney(detail.amount)}</td>
                                        </tr>
                                      ))}
                                    </tbody>
                                  </table>
                                </div>
                              )}
                            </div>
                          </td>
                        </tr>
                      )}
                    </Fragment>
                  )
                })}
              </tbody>
              {rows.length > 0 && (
                <tfoot className="sticky bottom-0 bg-card">
                  <tr className="border-t border-border font-medium">
                    <td className="px-3 py-2" colSpan={4}>合计</td>
                    <td className="px-3 py-2 text-right font-mono tabular-nums">{formatMoney(totals.increase)}</td>
                    <td className="px-3 py-2 text-right font-mono tabular-nums">{formatMoney(totals.decrease)}</td>
                    <td className="px-3 py-2 text-right font-mono tabular-nums">{formatMoney(totals.ending)}</td>
                  </tr>
                </tfoot>
              )}
            </table>
          </div>
        </div>
    </>
  )
  if (presentation === "page") return <div className="app-page"><div className="app-content-wide">{content}</div></div>
  return <Dialog open={open} onOpenChange={onOpenChange}><DialogContent className="max-h-[88vh] max-w-6xl overflow-hidden">{content}</DialogContent></Dialog>
}
