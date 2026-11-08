"use client"

import { useAuth } from "@/components/auth/auth-provider"
import { PurchaseInboundDetailPage } from "@/components/inventory-admin/purchase-inbound-detail-page"

export function PurchaseOrderDetailPage() {
  const { hasPermission } = useAuth()
  if (!hasPermission("purchase.view")) {
    return <div className="p-6 text-sm text-muted-foreground">无权查看采购明细</div>
  }
  return <PurchaseInboundDetailPage mode="orders" canExport={hasPermission("purchase.export")} />
}
