import type { BrandKey } from "@/lib/brands"

export type ProductListItem = {
  id: number
  brand: BrandKey
  image_path: string | null
  image_url: string | null
  sku: string | null
  original_sku: string | null
  group_name: string | null
  product_level: string | null
  cost: string | null
  factory_sku: string | null
  color: string | null
  season_category: string | null
  year: string | null
  upper_material: string | null
  lining_material: string | null
  outsole_material: string | null
  insole_material: string | null
  execution_standard: string | null
  heel_height: string | null
  shoe_width: string | null
  shoe_length: string | null
  shaft_circumference: string | null
  shaft_height: string | null
  internal_height_increase: string | null
  internal_height_note: string | null
  upper_height: string | null
  toe_shape: string | null
  closure_type: string | null
  shoe_box_spec: string | null
  first_order_time: string | null
  size_range: string | null
  product_model: string | null
  supplier_name: string | null
  color_code: string | null
  launch_date: string | null
  source_workbook: string
  source_sheet: string
  source_row_number: string
}

export type ProductListResponse = {
  items: ProductListItem[]
  total: number
  page: number
  page_size: number
}

export type FineTableShopSale = {
  shop_name: string
  quantity: number
}

export type FineTableDailySale = {
  date: string
  quantity: number
  uv: number
}

export type FineTableItem = ProductListItem & {
  factory_code: string | null
  goods_id: string | null
  p_spu: string | null
  style_code: string | null
  category_l3: string | null
  product_name: string | null
  main_style: string | null
  goods_status: string | null
  status_key: "online" | "partial" | "offline" | "unknown"
  sales_tag: string | null
  goods_tag: string | null
  latest_purchase_price: number | null
  final_price: number | null
  vip_price: number | null
  market_price: number | null
  price_band: string | null
  activity_profit: number | null
  margin_rate: number | null
  discount_rate: number | null
  vip_1d_sales: number
  vip_3d_sales: number
  vip_7d_sales: number
  vip_15d_sales: number
  vip_30d_sales: number
  vip_3d_uv: number
  vip_7d_uv: number
  vip_30d_uv: number
  vip_3d_ctr: string | null
  vip_7d_ctr: string | null
  vip_30d_ctr: string | null
  vip_3d_conversion: string | null
  vip_7d_conversion: string | null
  vip_30d_conversion: string | null
  vip_3d_sales_change_rate: number | null
  vip_3d_uv_change_rate: number | null
  vip_3d_ctr_change_rate: number | null
  vip_3d_conversion_change_rate: number | null
  vip_7d_sales_change_rate: number | null
  vip_7d_uv_change_rate: number | null
  vip_7d_ctr_change_rate: number | null
  vip_7d_conversion_change_rate: number | null
  vip_30d_reject_count: number
  vip_30d_reject_rate: string | null
  vip_daily_average_sales: number
  other_3d_sales: number
  other_7d_sales: number
  other_15d_sales: number
  other_30d_sales: number
  original_other_3d_sales: number
  original_other_7d_sales: number
  original_other_15d_sales: number
  original_other_30d_sales: number
  shop_30d_sales: FineTableShopSale[]
  stock_qty: number
  original_stock_qty: number
  size_stock: Record<string, number>
  purchase_diff: number
  inbound_qty: number
  defect_stock: number
  original_defect_stock: number
  original_inbound_qty: number
  original_order_in_transit_stock: number
  original_defect_in_transit_stock: number
  off_shelf_stock: number
  order_occupy_stock: number
  defect_in_transit_stock: number
  projected_15d_stock: number
  daily_sales: FineTableDailySale[]
}

export type FineTableResponse = {
  items: FineTableItem[]
  total: number
  page: number
  page_size: number
  latest_order_date: string | null
}

export type FineTableSnapshotBatch = {
  id: number
  brand: Exclude<BrandKey, "all">
  snapshot_date: string
  total_rows: number
  latest_order_date: string | null
  created_at: string | null
  updated_at: string | null
}

export type FineTableSnapshotListResponse = {
  items: FineTableSnapshotBatch[]
  total: number
  page: number
  page_size: number
}

export type FineTableSnapshotResponse = {
  items: FineTableItem[]
  total: number
  page: number
  page_size: number
  snapshot: FineTableSnapshotBatch
}

export type FineTableSnapshotCreateResult = {
  item: FineTableSnapshotBatch
  rows: number
  replaced: boolean
  message: string
}

export type ImageLookupResult = {
  found: boolean
  image_path: string | null
  matched_by: "original_sku" | "sku" | "none"
  message: string
}

export type ProductImageRefreshRun = {
  id: string
  brands: string[]
  overwrite: boolean
  started_at: string
  finished_at?: string
  status: "running" | "completed" | "failed"
  scanned?: number
  updated?: number
  results?: Record<string, {
    scanned: number
    matched: number
    updated: number
    missing: number
  }>
  error?: string
  message: string
}

export type ProductImageRefreshStatus = {
  in_progress: boolean
  current_run?: ProductImageRefreshRun | null
  last_run?: ProductImageRefreshRun | null
  runs?: ProductImageRefreshRun[]
}

export type RefreshProductImagesResult = {
  accepted: boolean
  in_progress: boolean
  message: string
  status?: ProductImageRefreshStatus
}

export type CompletedRefreshProductImagesResult = {
  updated: number
  scanned: number
  results: Record<string, {
    scanned: number
    matched: number
    updated: number
    missing: number
  }>
  message: string
}

export type ProductFormValues = {
  brand: BrandKey | ""
  image_path: string
  sku: string
  original_sku: string
  group_name: string
  product_level: string
  cost: string
  factory_sku: string
  color: string
  season_category: string
  year: string
  upper_material: string
  lining_material: string
  outsole_material: string
  insole_material: string
  execution_standard: string
  heel_height: string
  shoe_width: string
  shoe_length: string
  shaft_circumference: string
  shaft_height: string
  internal_height_increase: string
  internal_height_note: string
  upper_height: string
  toe_shape: string
  closure_type: string
  shoe_box_spec: string
  first_order_time: string
  size_range: string
  product_model: string
  supplier_name: string
  color_code: string
  launch_date: string
}

export type ProductMutationPayload = Record<string, unknown> & {
  image_path?: string | null
  sku?: string | null
  original_sku?: string | null
  group_name?: string | null
  product_level?: string | null
  cost?: string | null
  factory_sku?: string | null
  color?: string | null
  season_category?: string | null
  year?: string | null
  upper_material?: string | null
  lining_material?: string | null
  outsole_material?: string | null
  insole_material?: string | null
  execution_standard?: string | null
  heel_height?: string | null
  shoe_width?: string | null
  shoe_length?: string | null
  shaft_circumference?: string | null
  shaft_height?: string | null
  internal_height_increase?: string | null
  internal_height_note?: string | null
  upper_height?: string | null
  toe_shape?: string | null
  closure_type?: string | null
  shoe_box_spec?: string | null
  first_order_time?: string | null
  size_range?: string | null
  product_model?: string | null
  supplier_name?: string | null
  color_code?: string | null
  launch_date?: string | null
}

export type ImageLookupStatusState = {
  status: "idle" | "loading" | "success" | "warning" | "error"
  message: string | null
}


export type GeneralCustomerShopItem = {
  id: number
  customer_name: string
  shop_name: string
  created_at: string | null
  updated_at: string | null
}

export type GeneralCustomerShopListResponse = {
  items: GeneralCustomerShopItem[]
}

export type GeneralCustomerBrandItem = {
  id: number
  name: string
  shop_count: number
  created_at: string | null
  updated_at: string | null
}

export type GeneralCustomerBrandListResponse = {
  items: GeneralCustomerBrandItem[]
}
