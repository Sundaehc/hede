"use client"

import Link from "next/link"
import { useEffect, useRef, useState } from "react"
import { useRouter } from "next/navigation"
import { useAuth } from "@/components/auth/auth-provider"
import { CounterpartyLedgerDialog } from "@/components/inventory-admin/counterparty-ledger-dialog"
import { getSupplier, type SupplierItem } from "@/lib/api"
import { SUPPLIER_LEDGER_CACHE_TTL, useSupplierLedgerTabs } from "@/lib/supplier-ledger-tabs"
import { getBusinessDataChangeToken } from "@/lib/business-data-sync"
import { loadStockModuleQuery, readStockModuleQuery } from "@/lib/stock-module-cache"

export function SupplierLedgerPage({ id }: { id: number }) {
  const router = useRouter()
  const { user, hasPermission } = useAuth()
  const canView = hasPermission("inventory.view")
  const { tabs, openLedger, updateLedger } = useSupplierLedgerTabs()
  const tab = tabs.find((entry) => entry.id === id)
  const registeredId = useRef<number | null>(null)
  const [retry, setRetry] = useState(0)
  const family = `supplier-ledger-directory:${user?.id}:${id}`
  const key = user?.id ? JSON.stringify([family, getBusinessDataChangeToken(["reference-data"])]) : null
  const [result, setResult] = useState<{
    id: number
    key: string | null
    retry: number
    supplier: SupplierItem | null
    error: string
  } | null>(null)
  const current = result?.id === id && result.key === key && result.retry === retry ? result : null
  const supplier = current?.supplier ?? (key && readStockModuleQuery<SupplierItem>(key)?.data)
  const error = current?.error

  useEffect(() => {
    if (!canView) return
    const controller = new AbortController()
    const load = (signal: AbortSignal) => getSupplier(id, signal).then(({ item }) => item)
    const request = key
      ? loadStockModuleQuery(key, family, load, controller.signal, SUPPLIER_LEDGER_CACHE_TTL, SUPPLIER_LEDGER_CACHE_TTL)
      : load(controller.signal)
    request
      .then((item) => {
        if (!controller.signal.aborted)
          setResult({ id, key, retry, supplier: item, error: "" })
      })
      .catch((err: unknown) => {
        if (!controller.signal.aborted)
          setResult({
            id,
            key,
            retry,
            supplier: null,
            error: err instanceof Error ? err.message : "供应商加载失败",
          })
      })
    return () => controller.abort()
  }, [id, canView, family, key, retry])

  useEffect(() => {
    if (!supplier || registeredId.current === id) return
    registeredId.current = id
    if (!tab) openLedger(id, supplier.name)
    else if (tab.name !== supplier.name)
      updateLedger(id, { name: supplier.name })
  }, [id, supplier, tab, openLedger, updateLedger])

  if (!canView || error || !supplier || !tab) {
    return (
      <div className="app-page">
        <div className="app-content-wide space-y-3">
          <Link
            href="/suppliers"
            scroll={false}
            className="text-sm underline underline-offset-4"
          >
            返回供应商管理
          </Link>
          {!canView ? (
            <p role="alert">没有供应商查看权限</p>
          ) : error ? (
            <div role="alert">
              <p>{error}</p>
              <button
                className="mt-2 cursor-pointer text-sm underline"
                onClick={() => setRetry((value) => value + 1)}
              >
                重试
              </button>
            </div>
          ) : (
            <p role="status" className="text-sm text-muted-foreground">
              正在加载供应商账本...
            </p>
          )}
        </div>
      </div>
    )
  }
  return (
    <CounterpartyLedgerDialog
      key={id}
      open
      counterpartyType="supplier"
      name={supplier.name}
      presentation="page"
      queryState={tab.query}
      onQueryChange={(action) =>
        updateLedger(id, (current) => ({
          query: typeof action === "function" ? action(current.query) : action,
        }))
      }
      onOpenChange={(open) => {
        if (!open) router.push("/suppliers", { scroll: false })
      }}
    />
  )
}
