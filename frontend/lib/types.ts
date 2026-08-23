import type {
  BrandKey,
  ProductArchiveBrandKey,
  ProductArchiveRecordBrandKey,
} from "@/lib/brands"

export type AuthUser = {
  id: number
  username: string
  display_name: string
  department_code: string
  department_name: string
  role_code: string
  role_name: string
  status: string
  permissions: string[]
  created_at?: string | null
  updated_at?: string | null
  last_login_at?: string | null
}

export type AuthDepartment = {
  id: number
  code: string
  name: string
}

export type AuthRole = {
  id: number
  code: string
  name: string
  department_code: string | null
  description: string | null
  permissions: string[]
}

export type OperationLogChange = {
  field: string
  label: string
  before: unknown
  after: unknown
}

export type OperationLogItem = {
  id: number
  module:
    | "product"
    | "product_goods"
    | "fine_table"
    | "inventory"
    | "purchase"
    | "purchase_inbound_detail"
    | "supplier"
    | "warehouse"
    | "account_subject"
    | "general_customer"
    | "ai_query"
    | "user"
  action: string
  entity_type: string
  entity_id: string | null
  entity_label: string | null
  summary: string
  changed_fields: OperationLogChange[] | null
  before_data: unknown
  after_data: unknown
  user_id: number | null
  username: string | null
  display_name: string | null
  department_name: string | null
  created_at: string | null
}

export type OperationLogResponse = {
  items: OperationLogItem[]
  total: number
  page: number
  page_size: number
}

export type AiQueryColumn = {
  key: string
  label: string
  type?: "text" | "number" | "date"
}

export type AiQueryCondition = {
  label: string
  value: string
}

export type AiQueryMetric = {
  label: string
  value: string | number
  hint?: string
  tone?: "slate" | "blue" | "violet" | "orange" | "emerald"
}

export type AiQueryContext = {
  questions: string[]
  brand: string | null
  product_codes: string[]
  year: number | null
  intent: string | null
  used_previous?: boolean
}

export type AiQueryResponse = {
  query_id: string
  question: string
  intent: string
  query_mode?: "business_rules" | "ai_sql" | "ai_staged_sql"
  generated_sql?: string | null
  supported: boolean
  needs_clarification: boolean
  title: string
  summary: string
  conditions: AiQueryCondition[]
  metrics: AiQueryMetric[]
  columns: AiQueryColumn[]
  rows: Array<Record<string, unknown>>
  data_as_of: Array<{ label: string; value: string }>
  sources: string[]
  warnings: string[]
  link: { label: string; href: string } | null
  suggestions: string[]
  context?: AiQueryContext
}

export type ProductListItem = {
  id: number
  brand: ProductArchiveBrandKey
  image_path: string | null
  image_url: string | null
  sku: string | null
  original_sku: string | null
  product_name: string | null
  group_name: string | null
  category: string | null
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
  sole_style?: string | null
  fashion_elements?: string | null
  shoe_width: string | null
  shoe_length: string | null
  shaft_circumference: string | null
  shaft_height: string | null
  internal_height_increase: string | null
  internal_height_note: string | null
  upper_height: string | null
  opening_depth?: string | null
  boot_shaft?: string | null
  toe_shape: string | null
  closure_type: string | null
  mesh_upper_type?: string | null
  shoe_box_spec: string | null
  shoe_box_type: string | null
  selling_points: string | null
  first_order_time: string | null
  size_range: string | null
  product_model: string | null
  supplier_name: string | null
  color_code: string | null
  barcode_build_rule: string | null
  launch_date: string | null
  gender_costs?: { female: string; male: string } | null
  factory_code?: string | null
  market_price?: string | number | null
  barcode?: string | null
  accessories?: string | null
  source_workbook: string
  source_sheet: string
  source_row_number: string
}

export type ProductListResponse = {
  items: ProductListItem[]
  total: number
  page: number
  page_size: number
  snapshot_date?: string | null
}

export type ProductRecycleItem = {
  id: number
  brand: ProductArchiveBrandKey
  image_path: string | null
  image_url: string | null
  sku: string | null
  original_sku: string | null
  product_name: string | null
  color: string | null
  year: string | null
  deleted_at: string | null
}

export type ProductRecycleResponse = {
  items: ProductRecycleItem[]
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
  platform: string | null
  factory_code: string | null
  factory_name: string | null
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
  vip_30d_reject_count: number | null
  vip_30d_reject_rate: string | null
  vip_daily_average_sales: number
  other_3d_sales: number
  other_7d_sales: number
  other_15d_sales: number
  other_30d_sales: number
  original_other_3d_sales: number
  original_other_7d_sales: number
  original_all_7d_sales: number
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
  results?: Record<
    string,
    {
      scanned: number
      matched: number
      updated: number
      missing: number
    }
  >
  error?: string
  message: string
}

export type ProductImageRefreshStatus = {
  in_progress: boolean
  current_run?: ProductImageRefreshRun | null
  last_run?: ProductImageRefreshRun | null
  runs?: ProductImageRefreshRun[]
}

export type ProductGoodsItem = {
  id: number
  brand: BrandKey
  is_style_summary?: boolean
  year: string | null
  season: string | null
  platform: string | null
  category_l4: string | null
  first_order_date: string | null
  factory_sku: string | null
  factory_code: string | null
  factory_name: string | null
  style_code: string | null
  goods_code: string | null
  color: string | null
  image_url: string | null
  cost: string | null
  product_role: string | null
  product_type: string | null
  douyin_hot: string | boolean | null
  clearance: string | boolean | null
  remark: string | null
  stock_by_size: Record<string, number>
  stock_total: number
  in_transit_total: number
  inventory_total: number
  recent_14_day_sales: number | null
  recent_30_day_sales: number | null
  recent_30_day_sales_by_size: Record<string, number>
  daily_sales_by_date: Record<string, number>
  annual_sales: Record<string, number>
  monthly_sales: Record<string, number>
  platform_sales: Record<string, number>
  daily_platform_sales: Record<string, number>
  weekly_platform_sales: Record<string, number>
  monthly_platform_sales: Record<string, number>
  in_transit_by_size: Record<string, number>
  inventory_by_size: Record<string, number>
  shortage_by_size: Record<string, number>
  sales_by_size: Record<string, number>
  replenishment_by_size: Record<string, number>
  post_replenishment_by_size: Record<string, number>
  metrics: Record<string, number | string | null>
}

export type ProductGoodsResponse = {
  items: ProductGoodsItem[]
  total: number
  page: number
  page_size: number
  daily_dates: string[]
  annual_sales_columns: string[]
  monthly_sales_columns: string[]
  size_columns: string[]
  platform_columns: string[]
  snapshot_date: string | null
  snapshot_dates: string[]
}

export type FactoryChannelDashboardItem = {
  factory_name: string
  factory_code: string | null
  style_count: number
  total_sales: number
  total_net_sales: number
  total_returns: number
  traditional_sales: number
  traditional_net_sales: number
  traditional_returns: number
  live_sales: number
  live_net_sales: number
  live_returns: number
  clearance_sales: number
  clearance_net_sales: number
  clearance_returns: number
  traditional_ratio: number
  live_ratio: number
  clearance_ratio: number
}

export type FactoryChannelDashboardResponse = {
  brand: Exclude<BrandKey, "all">
  sales_year: number
  product_year: string | null
  date_start: string | null
  date_end: string | null
  latest_sales_date: string | null
  sales_date_coverage: {
    expected_start: string | null
    expected_end: string | null
    missing_date_count: number
    missing_dates: string[]
    sources: Array<{
      source: "historical" | "jst" | "vip"
      label: string
      available_start: string | null
      available_end: string | null
      missing_date_count: number
      missing_dates: string[]
    }>
  }
  available_sales_years: number[]
  available_product_years: string[]
  summary: {
    factory_count: number
    style_count: number
    total_sales: number
    total_net_sales: number
    total_returns: number
    traditional_sales: number
    traditional_net_sales: number
    traditional_returns: number
    live_sales: number
    live_net_sales: number
    live_returns: number
    clearance_sales: number
    clearance_net_sales: number
    clearance_returns: number
    unmatched_sales: number
    unclassified_style_count: number
    unclassified_sales: number
  }
  seasons: Array<{
    key: "spring_summer" | "autumn_winter"
    label: string
    items: FactoryChannelDashboardItem[]
  }>
}

export type ProductColorBarcodeItem = {
  brand: string
  color_code: string
  color_name: string
}

export type ProductColorBarcodeListResponse = {
  items: ProductColorBarcodeItem[]
  source_brand: string
}

export type SizeGroupItem = {
  id: number
  size_name: string
  barcode: string
  sort_order: number
}

export type SizeGroup = {
  id: number
  name: string
  product_count: number
  items: SizeGroupItem[]
}

export type SizeGroupWritePayload = {
  name: string
  items: Array<Pick<SizeGroupItem, "size_name" | "barcode">>
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
  results: Record<
    string,
    {
      scanned: number
      matched: number
      updated: number
      missing: number
    }
  >
  message: string
}

export type ProductFormValues = {
  brand: ProductArchiveRecordBrandKey | ""
  image_path: string
  sku: string
  original_sku: string
  product_name: string
  group_name: string
  category: string
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
  sole_style: string
  fashion_elements: string
  shoe_width: string
  shoe_length: string
  shaft_circumference: string
  shaft_height: string
  internal_height_increase: string
  internal_height_note: string
  upper_height: string
  opening_depth: string
  boot_shaft: string
  toe_shape: string
  closure_type: string
  mesh_upper_type: string
  shoe_box_spec: string
  shoe_box_type: string
  selling_points: string
  first_order_time: string
  size_range: string
  product_model: string
  supplier_name: string
  color_code: string
  barcode_build_rule: string
  launch_date: string
}

export type ProductMutationPayload = Record<string, unknown> & {
  image_path?: string | null
  sku?: string | null
  original_sku?: string | null
  product_name?: string | null
  group_name?: string | null
  category?: string | null
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
  sole_style?: string | null
  fashion_elements?: string | null
  shoe_width?: string | null
  shoe_length?: string | null
  shaft_circumference?: string | null
  shaft_height?: string | null
  internal_height_increase?: string | null
  internal_height_note?: string | null
  upper_height?: string | null
  opening_depth?: string | null
  boot_shaft?: string | null
  toe_shape?: string | null
  closure_type?: string | null
  mesh_upper_type?: string | null
  shoe_box_spec?: string | null
  shoe_box_type?: string | null
  selling_points?: string | null
  first_order_time?: string | null
  size_range?: string | null
  product_model?: string | null
  supplier_name?: string | null
  color_code?: string | null
  barcode_build_rule?: string | null
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
  sort_order: number
  unit_count: number
  created_at: string | null
  updated_at: string | null
}

export type GeneralCustomerShopListResponse = {
  items: GeneralCustomerShopItem[]
}

export type GeneralCustomerBrandItem = {
  id: number
  name: string
  sort_order: number
  shop_count: number
  created_at: string | null
  updated_at: string | null
}

export type GeneralCustomerBrandListResponse = {
  items: GeneralCustomerBrandItem[]
}

export type GeneralCustomerUnitItem = {
  id: number
  shop_id: number
  unit_name: string
  sort_order: number
  customer_name: string
  shop_name: string
  created_at: string | null
  updated_at: string | null
}

export type GeneralCustomerUnitListResponse = {
  items: GeneralCustomerUnitItem[]
}
