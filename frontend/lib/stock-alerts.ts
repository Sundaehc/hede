export type StockAlertKind = "zero" | "slow"
export type StockAlertRule = {
  age_days: number
  rate: string
  version: number
  source: "season" | "brand" | "default"
}
export type StockAlertFilters = {
  brand: string
  season: string
  query: string
  status: "warning" | "pending"
  page: number
}
export type StockAlertItem = {
  id: number
  brand: string
  sku: string
  original_sku: string | null
  product_name: string | null
  color: string | null
  year: string | null
  season: string | null
  launch_date: string | null
  listed_days: number | null
  first_inbound_date: string | null
  last_inbound_date: string | null
  last_sales_date: string | null
  available_quantity: string
  purchase_received_reference: string
  gross_sales: string
  net_sales: string
  sales_returns: string
  sell_through_rate: string | null
  sales_issues: string[]
  inbound_issues: string[]
  warning: boolean
  pending_reasons: string[]
  rule_age_days: number
  rule_rate: string
  rule_source: string
}
export type StockAlertResponse = {
  items: StockAlertItem[]
  total: number
  page: number
  page_size: number
  counts: { warning: number; pending: number }
  warning_stock: string
  stock_products: number
  seasons: string[]
  stock_date: string | null
  sales_end: string | null
  source_issues: string[]
  unmatched_stock_rows: number
  ready: boolean
  rule: StockAlertRule
}
export type StockAlertRuleWrite = {
  brand: string
  season: string
  kind: StockAlertKind
  age_days: number
  rate: string
  version: number
}
