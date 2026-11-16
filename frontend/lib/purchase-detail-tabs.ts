"use client"

import { useCallback } from "react"
import { useSessionQueryState } from "@/lib/session-query-state"

type PurchaseDetailTab = { id: number; documentNumber: string; summary?: string }

export function purchaseDetailPath(id: number) {
  return `/purchase-orders/${id}`
}

export function purchaseDetailId(path: string): number | null {
  const match = /^\/purchase-orders\/([1-9]\d*)$/.exec(path)
  const id = match ? Number(match[1]) : NaN
  return Number.isSafeInteger(id) ? id : null
}

function normalizeTabs(value: unknown): PurchaseDetailTab[] {
  if (!Array.isArray(value)) return []
  const seen = new Set<number>()
  return value.filter((tab): tab is PurchaseDetailTab => {
    if (
      !tab ||
      typeof tab !== "object" ||
      !Number.isSafeInteger(tab.id) ||
      tab.id <= 0 ||
      typeof tab.documentNumber !== "string" ||
      (tab.summary !== undefined && typeof tab.summary !== "string") ||
      seen.has(tab.id)
    )
      return false
    seen.add(tab.id)
    return true
  })
}

export function usePurchaseDetailTabs() {
  const [saved, setSaved] = useSessionQueryState<PurchaseDetailTab[]>(
    "workspace:purchase-detail-tabs:v1",
    []
  )
  const [, setPaths] = useSessionQueryState<string[]>(
    "workspace:manual-tabs",
    []
  )
  const tabs = normalizeTabs(saved)

  const openDetail = useCallback(
    (id: number, documentNumber: string | null, summary: string | null = null) => {
      if (!Number.isSafeInteger(id) || id <= 0) return
      setSaved((current) => {
        const next = normalizeTabs(current)
        const entry = { id, documentNumber: documentNumber || String(id), summary: summary?.trim() || "" }
        const existing = next.findIndex((tab) => tab.id === id)
        if (existing < 0) return [...next, entry]
        return next.map((tab, index) => (index === existing ? entry : tab))
      })
      setPaths((current) => [
        ...new Set([...current, "/purchase-orders", purchaseDetailPath(id)]),
      ])
    },
    [setSaved, setPaths]
  )

  const updateDetail = useCallback(
    (id: number, documentNumber: string | null, summary: string | null) => {
      setSaved((current) => normalizeTabs(current).map((tab) =>
        tab.id === id
          ? { id, documentNumber: documentNumber || String(id), summary: summary?.trim() || "" }
          : tab
      ))
    },
    [setSaved]
  )

  const closeDetail = useCallback(
    (id: number) => {
      setSaved((current) =>
        normalizeTabs(current).filter((tab) => tab.id !== id)
      )
      setPaths((current) =>
        current.filter((path) => path !== purchaseDetailPath(id))
      )
    },
    [setSaved, setPaths]
  )

  return { tabs, openDetail, updateDetail, closeDetail }
}
