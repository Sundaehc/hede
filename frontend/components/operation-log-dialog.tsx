"use client"

import { useEffect, useState } from "react"
import { History, RefreshCw, Search, X } from "lucide-react"

import { Button } from "@/components/ui/button"
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import { Input } from "@/components/ui/input"
import { listOperationLogs } from "@/lib/api"
import type { OperationLogChange, OperationLogItem } from "@/lib/types"

type OperationLogModule =
  | "product"
  | "size_group"
  | "product_goods"
  | "fine_table"
  | "inventory"
  | "purchase"
  | "purchase_inbound_detail"
  | "supplier"
  | "supplier_brand"
  | "warehouse"
  | "account_subject"
  | "general_customer"
  | "ai_query"
  | "user"

type OperationLogDialogProps = {
  module: OperationLogModule
  open: boolean
  title: string
  onOpenChange: (open: boolean) => void
}

const PAGE_SIZE = 20

const ACTION_LABELS: Record<string, string> = {
  create: "新增",
  update: "编辑",
  delete: "删除",
  batch_delete: "批量删除",
  restore: "恢复",
  batch_restore: "批量恢复",
  batch_permanent_delete: "彻底删除",
  import: "导入",
  export: "导出",
  create_brand: "新增品牌",
  update_brand: "编辑品牌",
  delete_brand: "删除品牌",
  import_purchase: "导入",
  detail_create: "新增明细",
  detail_update: "编辑明细",
  detail_delete: "删除明细",
  detail_batch_delete: "批量删除明细",
  replace_details_import: "覆盖明细",
  merge_details_import: "重新导入明细",
  batch_update_costs: "批量改价",
  update_requirement: "订单要求",
  refresh_images: "刷新图片",
}

function formatDateTime(value: string | null) {
  if (!value) return "-"
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return value
  return `${date.toLocaleDateString("zh-CN")}\n${date.toLocaleTimeString("zh-CN", { hour12: false })}`
}

function formatValue(value: unknown) {
  if (value === null || value === undefined || value === "") return "空"
  if (
    typeof value === "string" ||
    typeof value === "number" ||
    typeof value === "boolean"
  ) {
    return String(value)
  }
  try {
    const text = JSON.stringify(value)
    return text.length > 80 ? `${text.slice(0, 80)}...` : text
  } catch {
    return String(value)
  }
}

function ChangeList({ changes }: { changes: OperationLogChange[] | null }) {
  if (!changes || changes.length === 0) {
    return <span className="text-muted-foreground">-</span>
  }

  return (
    <details className="group">
      <summary className="cursor-pointer text-xs font-medium text-foreground outline-none hover:underline">
        {changes.length} 个字段
      </summary>
      <div className="mt-2 space-y-1.5">
        {changes.slice(0, 12).map((change) => (
          <div
            key={`${change.field}-${change.label}`}
            className="rounded-md bg-muted/55 px-2 py-1.5 text-xs"
          >
            <p className="font-medium text-foreground">
              {change.label || change.field}
            </p>
            <p className="mt-0.5 break-all text-muted-foreground">
              {formatValue(change.before)} → {formatValue(change.after)}
            </p>
          </div>
        ))}
        {changes.length > 12 ? (
          <p className="text-xs text-muted-foreground">
            还有 {changes.length - 12} 个字段未展开显示
          </p>
        ) : null}
      </div>
    </details>
  )
}

function actorName(item: OperationLogItem) {
  return item.display_name || item.username || "未知用户"
}

export function OperationLogDialog({
  module,
  open,
  title,
  onOpenChange,
}: OperationLogDialogProps) {
  const [items, setItems] = useState<OperationLogItem[]>([])
  const [total, setTotal] = useState(0)
  const [page, setPage] = useState(1)
  const [queryInput, setQueryInput] = useState("")
  const [submittedQuery, setSubmittedQuery] = useState("")
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState("")
  const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE))

  const load = async () => {
    setLoading(true)
    setError("")
    try {
      const response = await listOperationLogs({
        module,
        page,
        pageSize: PAGE_SIZE,
        query: submittedQuery || undefined,
      })
      setItems(response.items)
      setTotal(response.total)
    } catch (err) {
      setItems([])
      setTotal(0)
      setError(err instanceof Error ? err.message : "操作日志加载失败")
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    if (open) {
      setPage(1)
      setQueryInput("")
      setSubmittedQuery("")
    }
  }, [open, module])

  useEffect(() => {
    if (open) {
      void load()
    }
  }, [open, module, page, submittedQuery])

  const submitSearch = () => {
    setPage(1)
    setSubmittedQuery(queryInput.trim())
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="flex max-h-[88svh] max-w-[min(96vw,1180px)] flex-col overflow-hidden p-0">
        <DialogHeader className="flex flex-row items-center justify-between gap-4 border-b border-border px-5 py-4">
          <div className="flex min-w-0 items-center gap-2">
            <History className="h-4 w-4 shrink-0 text-muted-foreground" />
            <DialogTitle className="truncate text-base">{title}</DialogTitle>
          </div>
          <Button
            type="button"
            variant="ghost"
            size="icon"
            onClick={() => onOpenChange(false)}
            aria-label="关闭操作日志"
            className="cursor-pointer"
          >
            <X className="h-4 w-4" />
          </Button>
        </DialogHeader>

        <div className="flex items-center gap-2 border-b border-border px-5 py-3">
          <div className="relative min-w-0 flex-1">
            <Search className="pointer-events-none absolute top-1/2 left-3 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
            <Input
              value={queryInput}
              onChange={(event) => setQueryInput(event.target.value)}
              onKeyDown={(event) => {
                if (event.key === "Enter") submitSearch()
              }}
              placeholder="搜索操作内容、对象或操作人"
              className="pl-9"
            />
          </div>
          <Button
            type="button"
            variant="outline"
            onClick={submitSearch}
            disabled={loading}
            className="cursor-pointer disabled:cursor-not-allowed"
          >
            搜索
          </Button>
          <Button
            type="button"
            variant="outline"
            size="icon"
            onClick={() => void load()}
            disabled={loading}
            aria-label="刷新操作日志"
            className="cursor-pointer disabled:cursor-not-allowed"
          >
            <RefreshCw
              className={loading ? "h-4 w-4 animate-spin" : "h-4 w-4"}
            />
          </Button>
        </div>

        <div className="min-h-0 flex-1 overflow-auto">
          <table className="w-full min-w-[900px] table-fixed text-sm">
            <colgroup>
              <col className="w-[120px]" />
              <col className="w-[112px]" />
              <col className="w-[84px]" />
              <col className="w-[150px]" />
              <col />
              <col className="w-[168px]" />
            </colgroup>
            <thead className="sticky top-0 z-10 border-b border-border bg-muted text-xs text-muted-foreground">
              <tr>
                <th className="px-4 py-3 text-left font-medium">时间</th>
                <th className="px-4 py-3 text-left font-medium">操作人</th>
                <th className="px-4 py-3 text-left font-medium whitespace-nowrap">
                  动作
                </th>
                <th className="px-4 py-3 text-left font-medium">对象</th>
                <th className="px-4 py-3 text-left font-medium">修改内容</th>
                <th className="px-4 py-3 text-left font-medium">
                  修改字段
                </th>
              </tr>
            </thead>
            <tbody className="divide-y divide-border">
              {loading && items.length === 0 ? (
                <tr>
                  <td
                    colSpan={6}
                    className="px-4 py-12 text-center text-muted-foreground"
                  >
                    正在加载操作日志...
                  </td>
                </tr>
              ) : null}
              {!loading && error ? (
                <tr>
                  <td
                    colSpan={6}
                    className="px-4 py-12 text-center text-destructive"
                  >
                    {error}
                  </td>
                </tr>
              ) : null}
              {!loading && !error && items.length === 0 ? (
                <tr>
                  <td
                    colSpan={6}
                    className="px-4 py-12 text-center text-muted-foreground"
                  >
                    暂无操作日志
                  </td>
                </tr>
              ) : null}
              {items.map((item) => (
                <tr key={item.id} className="align-top hover:bg-muted/35">
                  <td className="px-4 py-3 text-xs leading-5 whitespace-pre-line text-muted-foreground">
                    {formatDateTime(item.created_at)}
                  </td>
                  <td className="px-4 py-3 whitespace-nowrap">
                    <p className="truncate font-medium" title={actorName(item)}>{actorName(item)}</p>
                    {item.department_name ? (
                      <p className="mt-0.5 truncate text-xs text-muted-foreground" title={item.department_name}>
                        {item.department_name}
                      </p>
                    ) : null}
                  </td>
                  <td className="px-4 py-3 whitespace-nowrap">
                    <span className="inline-flex rounded-md border border-border bg-background px-2 py-1 text-xs whitespace-nowrap">
                      {ACTION_LABELS[item.action] || item.action}
                    </span>
                  </td>
                  <td className="px-4 py-3">
                    <p className="truncate font-medium" title={item.entity_label || "-"}>
                      {item.entity_label || "-"}
                    </p>
                    {item.entity_id ? (
                      <p className="mt-0.5 truncate text-xs text-muted-foreground" title={String(item.entity_id)}>
                        {item.entity_id}
                      </p>
                    ) : null}
                  </td>
                  <td className="px-4 py-3 leading-6">
                    <p className="[overflow-wrap:anywhere]">{item.summary}</p>
                  </td>
                  <td className="px-4 py-3 [overflow-wrap:anywhere]">
                    <ChangeList changes={item.changed_fields} />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        <div className="flex items-center justify-between border-t border-border px-5 py-3 text-sm text-muted-foreground">
          <span>共 {total} 条</span>
          <div className="flex items-center gap-2">
            <Button
              type="button"
              variant="outline"
              size="sm"
              onClick={() => setPage((current) => Math.max(1, current - 1))}
              disabled={page <= 1 || loading}
              className="cursor-pointer disabled:cursor-not-allowed"
            >
              上一页
            </Button>
            <span className="min-w-20 text-center">
              第 {page} / {totalPages} 页
            </span>
            <Button
              type="button"
              variant="outline"
              size="sm"
              onClick={() =>
                setPage((current) => Math.min(totalPages, current + 1))
              }
              disabled={page >= totalPages || loading}
              className="cursor-pointer disabled:cursor-not-allowed"
            >
              下一页
            </Button>
          </div>
        </div>
      </DialogContent>
    </Dialog>
  )
}
