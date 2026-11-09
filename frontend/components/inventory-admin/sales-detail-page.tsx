"use client"

import { useAuth } from "@/components/auth/auth-provider"
import { PurchaseInboundDetailPage } from "@/components/inventory-admin/purchase-inbound-detail-page"

export function SalesDetailPage() {
  const { hasPermission } = useAuth()
  return <PurchaseInboundDetailPage mode="sales" canExport={hasPermission("inventory.export")} />
}
