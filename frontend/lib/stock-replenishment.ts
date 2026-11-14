export type ReplenishmentRule = {
  lead_days: number
  min_order_qty: number
  cover_days: number
  size_ratios: Record<string, Record<string, number>>
  version: number
}

export type ReplenishmentGroups = Record<
  string,
  Array<{ name: string; barcode: string }>
>
export type ReplenishmentRuleResponse = {
  rule: ReplenishmentRule | null
  groups: ReplenishmentGroups
}
export type ReplenishmentFilters = {
  brand: string
  supplier: string
  query: string
  window_days: number
  deduct_transit: boolean
  status: "suggested" | "pending" | "all"
  page: number
}

export type SupplierReplenishmentSummary = {
  supplier: string
  suggested_quantity: number
  suggested_products: number
  pending_products: number
  min_order_qty: number | null
  moq_gap: number | null
  meets_moq: boolean | null
}

export type ReplenishmentItem = {
  id: number
  sku: string
  original_sku: string | null
  product_name: string | null
  color: string | null
  supplier: string
  size_group: string
  available_quantity: string
  purchase_in_transit: string
  net_sales: string
  sales_returns: string
  observation_days: number
  daily_sales: string | null
  stock_days: string | null
  suggested_quantity: number | null
  lead_days: number | null
  cover_days: number | null
  pending_reasons: string[]
  supplier_summary: SupplierReplenishmentSummary | null
  size_details: Array<{
    name: string
    ratio: number
    available_quantity: string
    purchase_in_transit: string
    daily_demand: string
    stock_days: string | null
    at_risk: boolean
    suggested_quantity: number
  }>
}

export type ReplenishmentResponse = {
  items: ReplenishmentItem[]
  total: number
  page: number
  page_size: number
  counts: Record<ReplenishmentFilters["status"], number>
  suggested_quantity: number
  supplier_summaries: SupplierReplenishmentSummary[]
  supplier_options: Record<string, ReplenishmentGroups>
  window_days: number
  stock_date: string | null
  sales_start: string | null
  sales_end: string | null
  ready: boolean
  source_issues: string[]
  unmatched_stock_rows: number
}
