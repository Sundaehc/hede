export type SeasonalStatus = "all" | "single" | "pending" | "arrivals" | "zero"

export type SeasonalFilters = {
  brand: string
  year: number
  quarter: number
  season: string
  query: string
  status: SeasonalStatus
  page: number
}
export type SeasonalSummary = {
  quarter: number
  cutoff: string | null
  state: "not_started" | "incomplete" | "available"
  missing_days: number
  product_count: number
  gross_sales: number | null
  net_sales: number | null
  period_net_sales: number | null
  sales_share: number | null
  inbound_quantity: string | null
  received_quantity: string | null
  sell_through_rate: number | null
  single_order_count: number
  multiple_order_count: number
  unknown_order_count: number
}
export type SeasonalItem = {
  image_url?: string | null
  id: number
  sku: string
  original_sku: string | null
  product_name: string | null
  color: string | null
  season: string
  launch_date: string | null
  listed_days: number | null
  available_quantity: string | null
  order_state: "single" | "multiple" | "unknown"
  inbound_dates: string[]
  pending_reasons: string[]
  gross_sales: number | null
  net_sales: number | null
  received_quantity: string | null
  inbound_quantity: string | null
  sell_through_rate: number | null
}
export type SeasonalResponse = {
  year: number
  quarter: number
  summary: SeasonalSummary
  quarters: SeasonalSummary[]
  order_groups: Array<
    Omit<
      SeasonalSummary,
      "quarter" | "cutoff" | "state" | "missing_days" | "period_net_sales"
    > & { order_state: "single" | "multiple" | "unknown" }
  >
  activity: Array<{
    days: number
    eligible: number
    valid: number
    active: number
    pending: number
    immature: number
    rate: number | null
  }>
  trend: Array<{ date: string; gross: number | null; net: number | null }>
  items: SeasonalItem[]
  total: number
  page: number
  page_size: number
  counts: Record<SeasonalStatus, number>
  followup_ready: { arrivals: boolean; zero: boolean }
  sales_end: string | null
  stock_date: string | null
  seasons: string[]
  years: number[]
  source_issues: string[]
  missing_launch_count: number
  missing_launch_items: Array<{
    id: number
    sku: string | null
    original_sku: string | null
    product_name: string | null
    color: string | null
    invalid_launch: boolean
  }>
  unmatched_stock_rows: number
  unmatched_purchase_rows: number
  purchase_ready: boolean
}

export type SeasonalItemReview = {
  first_inbound_date: string | null
  launch_date: string | null
  receipt_end: string | null
  show_receipt_numbers: boolean
  sales: {
    start: string | null
    end: string | null
    first_sale_date: string | null
    missing_days: number | null
    channels: Array<{ channel: string; gross_sales: number; net_sales: number }>
  }
  receipts: {
    quantity: string
    total: number
    page: number
    pages: number
    items: Array<{
      inbound_date: string
      quantity: string
      inbound_id?: string
      purchase_order_id?: string | null
    }>
  } | null
}
