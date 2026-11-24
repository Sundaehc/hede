import type {
  StockAlertTaskSummary,
  StockTaskKind,
  TaskCreate,
} from "./stock-alert-tasks"

export type OverviewKind = StockTaskKind | "review"
export type OverviewFilters = {
  brand: string
  kind: OverviewKind | "all"
  query: string
  page: number
}
export type ExitPolicy = {
  year: string
  season: string
  sale_start: string | null
  exit_date: string
  lead_days: number
  target_rate: number
  channel: string
  version: number
}
export type InventoryBucket = {
  key:
    | "selling"
    | "next_season"
    | "size_imbalance"
    | "clearance"
    | "watch"
    | "review"
  units: number
  styles: number
}
export type OverviewItem = {
  image_url?: string | null
  id: number
  brand: string
  sku: string
  original_sku: string | null
  product_name: string | null
  color: string | null
  season: string | null
  year: string | null
  upper_material: string | null
  launch_date: string | null
  first_inbound_date: string | null
  last_inbound_date: string | null
  sell_through_rate: string | null
  exit_date: string | null
  available_quantity: number
  regular_7: number | null
  regular_30: number | null
  clearance_7: number | null
  clearance_30: number | null
  kind: OverviewKind
  reason: string
  quantity: number | null
  due_date: string | null
  channel: string | null
  task: StockAlertTaskSummary | null
  signature: string | null
  sizes: Array<{ name: string; available: number; quantity: number }>
  size_inventory: Array<{
    name: string
    available: number | null
    core: boolean
    in_action: boolean
  }>
}
export type OverviewResponse = {
  inventory: {
    available: number | null
    total_30: number | null
    coverage_days: number | null
    regular_7: number | null
    regular_30: number | null
    clearance_7: number | null
    clearance_30: number | null
    buckets: InventoryBucket[]
  }
  sources: {
    stock_date: string | null
    sales_end: string | null
    aligned: boolean
    history_aligned: boolean
    scope_complete: boolean
    unmatched_stock_rows: number
  }
  scopes: Array<Pick<ExitPolicy, "year" | "season">>
  policies: ExitPolicy[]
  items: OverviewItem[]
  counts: Record<OverviewKind, number>
  assignable: number
  in_progress: number
  page: number
  page_size: number
  total: number
  today: string
}
export type OverviewWeek = {
  start: string
  end: string
  created: number
  completed: number
  overdue: number
  completed_styles: number
  net_sales: number | null
  stock_change: number | null
  clearance_net_sales: number | null
  recovery_amount: number | null
}
export type OverviewTaskCreate = Omit<TaskCreate, "kind"> & {
  kind: StockTaskKind
  signature: string
}

export type OverviewBatchTaskCreate = Omit<
  OverviewTaskCreate,
  "product_id" | "kind" | "signature"
> & {
  items: Array<Pick<OverviewTaskCreate, "product_id" | "kind" | "signature">>
}
