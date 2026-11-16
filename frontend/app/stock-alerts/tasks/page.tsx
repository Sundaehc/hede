import { Suspense } from "react"
import { StockAlertTasksPage } from "@/components/stock-alerts/tasks-page"

export default function StockAlertTasksRoute() {
  return (
    <Suspense
      fallback={
        <p className="p-6 text-sm text-muted-foreground">正在加载预警待办…</p>
      }
    >
      <StockAlertTasksPage />
    </Suspense>
  )
}
