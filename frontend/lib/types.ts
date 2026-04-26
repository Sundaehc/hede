import type { BrandKey } from "@/lib/brands"

export type ProductListItem = {
  id: number
  brand: BrandKey
  image_path: string | null
  image_url: string | null
  sku: string | null
  original_sku: string | null
  group_name: string | null
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

export type ImageLookupResult = {
  found: boolean
  image_path: string | null
  matched_by: "original_sku" | "sku" | "none"
  message: string
}

export type ProductFormValues = {
  brand: BrandKey | ""
  image_path: string
  sku: string
  original_sku: string
  group_name: string
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
}

export type ProductMutationPayload = Record<string, unknown> & {
  image_path?: string | null
  sku?: string | null
  original_sku?: string | null
  group_name?: string | null
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
}

export type ImageLookupStatusState = {
  status: "idle" | "loading" | "success" | "warning" | "error"
  message: string | null
}
