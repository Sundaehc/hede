import type { ReactNode } from "react"
import { PurchaseOrdersWorkspace } from "@/components/inventory-admin/purchase-orders-workspace"

export default function PurchaseOrdersLayout({
  children,
}: {
  children: ReactNode
}) {
  return <PurchaseOrdersWorkspace>{children}</PurchaseOrdersWorkspace>
}
