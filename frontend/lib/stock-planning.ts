export type Quantities = Record<string, number>
export type Campaign = {
  id: number
  name: string
  start_date: string
  end_date: string
  factor: string | number
}
export type CampaignWrite = Omit<Campaign, "id">
export type ArrivalConfirmation = {
  eta: string | null
  sizes: Quantities
  note: string
  credible: boolean
}
export type PlanningOrder = {
  id: number
  product_id: number
  sku: string
  supplier: string | null
  external_number: string | null
  receipts_verified: boolean
  number: string | null
  date: string | null
  due: string | null
  ordered: number
  received: number | null
  remaining: number | null
  remaining_sizes: Quantities
  kind: string
  status: "received" | "unknown" | "overdue" | "due_soon" | "scheduled"
  confirmation: ArrivalConfirmation | null
}
export type ArrivalScope = "confirmed" | "due_soon" | "overdue"
export type ArrivalBoard = {
  items: PlanningOrder[]
  today: string
  through: string
  source_ready: boolean
  page: number
  page_size: number
  total: number
}
export type PlanFilters = {
  need_by?: string
  total?: number
  campaign_id?: number
  season?: string
  reference_category?: string
  reference_product_id?: number
}
export type StockPlan = {
  sku: string
  product_name: string | null
  color: string | null
  category: string
  season: string | null
  allocation_season: string
  allocation_seasons: string[]
  heel_group: string
  related_categories: string[]
  other_colors: Array<{ id: number; sku: string; color: string }>
  reference: {
    kind: "other_color" | "category" | "related_category"
    label: string
    color?: string
    sales?: Quantities | null
    sales_start?: string | null
    cutoff?: string | null
    weights: Quantities
  } | null
  size_group: string
  sizes: string[]
  stock_date: string | null
  stock_ready: boolean
  sales_start: string | null
  cutoff: string | null
  sales_complete: boolean
  sales_days: number
  known_volume: number
  sales_volume: number
  stock: Quantities
  source_transit: Quantities
  eligible_transit: Quantities
  sales: Quantities
  weights: Quantities
  baseline: Quantities | null
  legacy_baseline: Quantities | null
  basis:
    | "same_product"
    | "category"
    | "other_color"
    | "related_category"
    | "manual"
  today: string
  need_by: string
  total: number | null
  blocked_reason: string | null
  suggested: Quantities | null
  campaigns: Campaign[]
  selected_campaign: Campaign | null
  orders: PlanningOrder[] | null
  demand: {
    normal: number | null
    campaign: number | null
    days: number | null
    campaign_days: number
    normal_shortage: number | null
    campaign_shortage: number | null
  }
}
export type OrderLinkWrite = {
  order_id: number
  external_number: string
  note: string
}
export type ArrivalWrite = {
  order_id: number
  eta: string | null
  sizes: Quantities
  note: string
}
export type ClearanceRecovery = { amount: string; reference: string }
export type ClearanceWeek = {
  start: string
  end: string
  can_confirm: boolean
  stock_covered: number
  clearance_products: number
  recovery_amount: string | null
  recovery_covered: number
  items: Array<{
    product_id: number
    sku: string
    net_sales: number | null
    ending_stock: number | null
    recovery: ClearanceRecovery | null
  }>
}
