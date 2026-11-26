import type { StockTaskKind } from "./stock-alert-tasks"

export type PortfolioStatus =
  | "selling"
  | "next_season"
  | "size_imbalance"
  | "clearance"
  | "watch"
  | "review"
  | "confirmed"
export type PortfolioFilters = {
  year: string
  season: string
  category: string
  status: PortfolioStatus | ""
  query: string
  page: number
}
export type PortfolioResponse = {
  items: Array<{
    product_id: number
    sku: string
    product_name: string | null
    available_quantity: number
    children: number
    confirmed_clearance_quantity: number
    statuses: PortfolioStatus[]
  }>
  total: number
  page: number
  page_size: number
  totals: Partial<Record<PortfolioStatus, number>>
  years: string[]
  seasons: string[]
  categories: string[]
  sell_through: number | null
  sell_through_covered: number
  sources: {
    stock_date: string | null
    aligned: boolean
    unmatched_stock_rows: number
  }
}
export type ClearanceDecision = {
  confirmed: boolean
  reason: string
  version: number
  updated_at: string
  updated_by: number
}
export type PortfolioChild = {
  id: number
  image_url?: string | null
  sku: string
  original_sku: string | null
  product_name: string | null
  color: string | null
  launch_date: string | null
  year: string | null
  season_category: string | null
  category: string | null
  available_quantity: number | null
  purchase_in_transit: number | null
  stock: Array<{
    size: string
    warehouse: string
    available: number
    transit: number
  }>
  clearance: ClearanceDecision | null
}
export type PortfolioMetrics = {
  gross: number
  returns: number | null
  net: number
}
export type PortfolioDetail = {
  original_sku: string | null
  stock_date: string | null
  unmatched_stock: number
  items: PortfolioChild[]
  sales: {
    cutoff: string | null
    windows: Record<string, boolean>
    unmatched?: number
    channels: Array<{
      platform: string
      shop: string
      windows: Record<string, PortfolioMetrics | null>
    }>
  }
  receipts: {
    by_product: Record<
      string,
      { first: string | null; last: string | null; quantity: number }
    >
    recent: Array<{
      product_id: number
      date: string
      inbound_id: string | null
      purchase_order_id: string | null
      quantity: number
    }> | null
  } | null
  orders: Array<{
    id: number
    product_id: number
    number: string | null
    date: string | null
    delivery_date: string | null
    quantity: number
  }> | null
}
export type AutoAssignmentRule = {
  kind: StockTaskKind
  assignee_id: number
  enabled: boolean
  due_days: number
  version: number
}
export const portfolioStatusLabels: Record<PortfolioStatus, string> = {
  selling: "正常销售",
  next_season: "跨季待售",
  size_imbalance: "尺码不均衡",
  clearance: "建议清货",
  watch: "继续观察",
  review: "待核对",
  confirmed: "已确认清仓",
}
