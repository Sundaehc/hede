"use client"

import { useEffect, useState, type ReactNode } from "react"
import { useRouter } from "next/navigation"
import { ArrowLeft, LoaderCircle, RotateCcw, X } from "lucide-react"

import { useAuth } from "@/components/auth/auth-provider"
import { InventoryDetailPanel } from "@/components/inventory-admin/inventory-detail-panel"
import { usePurchaseListRefresh } from "./purchase-orders-workspace"
import { Button } from "@/components/ui/button"
import {
  ApiError,
  getInventoryRecord,
  listSuppliers,
  type InventoryRecord,
  type SupplierItem,
} from "@/lib/api"
import {
  purchaseDetailId,
  usePurchaseDetailTabs,
} from "@/lib/purchase-detail-tabs"

function DocumentStatusView({
  children,
  onClose,
}: {
  children: ReactNode
  onClose: () => void
}) {
  return (
    <div className="flex h-[calc(100dvh-var(--page-tabs-height,2.75rem))] min-h-96 w-full flex-col overflow-hidden bg-background">
      <div className="flex items-center justify-between border-b border-border px-6 py-4">
        <h2 className="text-lg font-semibold">单据明细</h2>
        <Button
          variant="ghost"
          size="icon"
          onClick={onClose}
          aria-label="关闭单据明细"
        >
          <X className="size-5" />
        </Button>
      </div>
      {children}
    </div>
  )
}

export function PurchaseOrderDocumentPage({ recordId }: { recordId: string }) {
  const { hasPermission } = useAuth()
  const allowed = hasPermission("purchase.view")
  const id = purchaseDetailId(`/purchase-orders/${recordId}`)
  const validId = id !== null
  const router = useRouter()
  const { openDetail } = usePurchaseDetailTabs()
  const refreshList = usePurchaseListRefresh()
  const [revision, setRevision] = useState(0)
  const [state, setState] = useState<{
    id: number | null
    record: InventoryRecord | null
    error: string
  }>({ id: null, record: null, error: "" })
  const [suppliers, setSuppliers] = useState<SupplierItem[]>([])

  useEffect(() => {
    if (!allowed || id === null) return
    const controller = new AbortController()
    void getInventoryRecord(id, controller.signal)
      .then((record) => {
        if (controller.signal.aborted) return
        if (record.document_type !== "进货订单")
          throw new Error("该单据不是采购单，请从经营历程查看")
        setState({ id, record, error: "" })
      })
      .catch((error: unknown) => {
        if (controller.signal.aborted) return
        setState({
          id,
          record: null,
          error:
            error instanceof ApiError && error.status === 404
              ? "采购单不存在或已移入回收站"
              : error instanceof Error
                ? error.message
                : "读取采购单失败，请重试",
        })
      })
    return () => controller.abort()
  }, [allowed, id, revision])

  useEffect(() => {
    if (!allowed || !validId) return
    let cancelled = false
    void listSuppliers()
      .then((response) => {
        if (!cancelled) setSuppliers(response.items)
      })
      .catch(() => {})
    return () => {
      cancelled = true
    }
  }, [allowed, validId])

  const record = state.id === id ? state.record : null
  const number = record?.document_number
  const summary = record?.summary
  useEffect(() => {
    if (allowed && id !== null && number !== undefined) openDetail(id, number, summary)
  }, [allowed, id, number, summary, openDetail])

  function returnToList() {
    router.push("/purchase-orders", { scroll: false })
  }

  const error = !allowed
    ? "暂无采购单查看权限"
    : id === null
      ? "采购单地址无效"
      : state.id === id
        ? state.error
        : ""
  if (error)
    return (
      <DocumentStatusView onClose={returnToList}>
        <div
          role="alert"
          className="flex min-h-64 flex-col items-center justify-center gap-4 p-6 text-sm"
        >
          <p>{error}</p>
          <div className="flex gap-2">
            <Button variant="outline" onClick={returnToList}>
              <ArrowLeft />
              返回采购单管理
            </Button>
            {allowed && id !== null && (
              <Button onClick={() => setRevision((value) => value + 1)}>
                <RotateCcw />
                重试
              </Button>
            )}
          </div>
        </div>
      </DocumentStatusView>
    )
  if (!record)
    return (
      <DocumentStatusView onClose={returnToList}>
        <div
          role="status"
          className="flex min-h-64 items-center justify-center gap-2 text-sm text-muted-foreground"
        >
          <LoaderCircle className="size-4 animate-spin" />
          正在读取采购单明细...
        </div>
      </DocumentStatusView>
    )

  return (
    <InventoryDetailPanel
      key={record.id}
      record={record}
      suppliers={suppliers}
      presentation="page"
      onClose={returnToList}
      onTotalChanged={() => {
        setRevision((value) => value + 1)
        refreshList?.()
      }}
    />
  )
}
