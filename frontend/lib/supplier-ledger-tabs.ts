"use client"

import { useCallback } from "react"
import { useSessionQueryState } from "@/lib/session-query-state"
import type { CounterpartyLedgerSortKey } from "@/lib/api"

export const SUPPLIER_LEDGER_CACHE_TTL = 10 * 60 * 1000

export type LedgerQueryState = {
  dateStartInput: string
  dateEndInput: string
  dateStart: string
  dateEnd: string
  sortBy: CounterpartyLedgerSortKey
  sortDirection: "asc" | "desc"
}

export function defaultLedgerQuery(
  dateStart = "",
  dateEnd = ""
): LedgerQueryState {
  if (!dateStart && !dateEnd) {
    const today = new Date()
    const month = `${today.getFullYear()}-${String(today.getMonth() + 1).padStart(2, "0")}`
    dateStart = `${month}-01`
    dateEnd = `${month}-${String(today.getDate()).padStart(2, "0")}`
  }
  return {
    dateStartInput: dateStart,
    dateEndInput: dateEnd,
    dateStart,
    dateEnd,
    sortBy: "row_number",
    sortDirection: "asc",
  }
}

type SupplierLedgerTab = { id: number; name: string; query: LedgerQueryState }

export function supplierLedgerPath(id: number) {
  return `/suppliers/${id}/ledger`
}

export function supplierLedgerId(path: string): number | null {
  const match = /^\/suppliers\/([1-9]\d*)\/ledger$/.exec(path)
  const id = match ? Number(match[1]) : NaN
  return Number.isSafeInteger(id) ? id : null
}

function normalizeTabs(value: unknown): SupplierLedgerTab[] {
  if (!Array.isArray(value)) return []
  const seen = new Set<number>()
  return value.filter((tab): tab is SupplierLedgerTab => {
    if (
      !tab ||
      typeof tab !== "object" ||
      !Number.isSafeInteger(tab.id) ||
      tab.id <= 0 ||
      typeof tab.name !== "string" ||
      !tab.query ||
      !["dateStartInput", "dateEndInput", "dateStart", "dateEnd"].every(
        (key) => typeof tab.query[key] === "string"
      ) ||
      ![
        "row_number",
        "date",
        "document_number",
        "summary",
        "increase_amount",
        "decrease_amount",
        "balance",
      ].includes(tab.query.sortBy) ||
      !["asc", "desc"].includes(tab.query.sortDirection) ||
      seen.has(tab.id)
    )
      return false
    seen.add(tab.id)
    return true
  })
}

export function useSupplierLedgerTabs() {
  const [saved, setSaved] = useSessionQueryState<SupplierLedgerTab[]>(
    "workspace:supplier-ledger-tabs:v1",
    []
  )
  const [, setPaths] = useSessionQueryState<string[]>(
    "workspace:manual-tabs",
    []
  )
  const tabs = normalizeTabs(saved)
  const openLedger = useCallback(
    (id: number, name: string, dateStart = "", dateEnd = "") => {
      if (!Number.isSafeInteger(id) || id <= 0) return
      const entry = { id, name, query: defaultLedgerQuery(dateStart, dateEnd) }
      setSaved((current) => [
        ...normalizeTabs(current).filter((tab) => tab.id !== id),
        entry,
      ])
      setPaths((current) => [
        ...new Set([...current, "/suppliers", supplierLedgerPath(id)]),
      ])
    },
    [setSaved, setPaths]
  )
  const updateLedger = useCallback(
    (
      id: number,
      patch:
        | Partial<Pick<SupplierLedgerTab, "name" | "query">>
        | ((
            tab: SupplierLedgerTab
          ) => Partial<Pick<SupplierLedgerTab, "name" | "query">>)
    ) => {
      setSaved((current) =>
        normalizeTabs(current).map((tab) =>
          tab.id === id
            ? { ...tab, ...(typeof patch === "function" ? patch(tab) : patch) }
            : tab
        )
      )
    },
    [setSaved]
  )
  const closeLedger = useCallback(
    (id: number) => {
      setSaved((current) =>
        normalizeTabs(current).filter((tab) => tab.id !== id)
      )
      setPaths((current) =>
        current.filter((path) => path !== supplierLedgerPath(id))
      )
    },
    [setSaved, setPaths]
  )
  return { tabs, openLedger, updateLedger, closeLedger }
}
