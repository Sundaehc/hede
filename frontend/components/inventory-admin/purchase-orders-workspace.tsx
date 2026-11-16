"use client"

import { createContext, useContext, useReducer, type ReactNode } from "react"
import { usePathname } from "next/navigation"

import { InventoryPage } from "./inventory-page"
import { purchaseDetailId } from "@/lib/purchase-detail-tabs"

const PurchaseListRefresh = createContext<(() => void) | null>(null)

export function usePurchaseListRefresh() {
  return useContext(PurchaseListRefresh)
}

export function PurchaseOrdersWorkspace({ children }: { children: ReactNode }) {
  const pathname = usePathname()
  const [revision, refresh] = useReducer((value: number) => value + 1, 0)
  const detailOpen = purchaseDetailId(pathname) !== null

  return (
    <PurchaseListRefresh.Provider value={refresh}>
      <div hidden={detailOpen}>
        <InventoryPage
          mode="purchase-orders"
          refreshRevision={revision}
          detailOverlayOpen={detailOpen}
        />
      </div>
      {children}
    </PurchaseListRefresh.Provider>
  )
}
