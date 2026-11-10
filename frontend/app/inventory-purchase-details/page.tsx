"use client"

import { useAuth } from "@/components/auth/auth-provider"
import { PurchaseInboundDetailPage } from "@/components/inventory-admin/purchase-inbound-detail-page"

export default function InventoryPurchaseDetailsRoute() {
  const { hasPermission } = useAuth()
  return <PurchaseInboundDetailPage canExport={hasPermission("inventory.export")} />
}
