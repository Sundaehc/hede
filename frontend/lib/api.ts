import type {
  BrandKey,
  ProductArchiveBrandKey,
  ProductArchiveRecordBrandKey,
} from "@/lib/brands"
import type {
  ImageLookupResult,
  ProductListItem,
  ProductListResponse,
  ProductRecycleResponse,
  ProductGoodsResponse,
  FactoryChannelDashboardResponse,
  ProductMutationPayload,
  ProductColorBarcodeListResponse,
  SizeGroup,
  SizeGroupWritePayload,
  ProductImageRefreshStatus,
  RefreshProductImagesResult,
  AuthDepartment,
  AuthRole,
  AuthUser,
  AiQueryContext,
  AiQueryResponse,
  FineTableResponse,
  FineTableSnapshotListResponse,
  FineTableSnapshotResponse,
  GeneralCustomerBrandItem,
  GeneralCustomerBrandListResponse,
  GeneralCustomerShopItem,
  GeneralCustomerShopListResponse,
  GeneralCustomerUnitItem,
  GeneralCustomerUnitListResponse,
  OperationLogResponse,
} from "@/lib/types"

const API_PREFIX = "/api"

export class ApiError extends Error {
  constructor(
    public readonly status: number,
    message: string
  ) {
    super(message)
    this.name = "ApiError"
  }
}

async function readApiError(response: Response) {
  const text = await response.text()
  if (!text) {
    return `请求失败（${response.status}）`
  }
  try {
    const parsed = JSON.parse(text) as { detail?: unknown }
    if (typeof parsed.detail === "string") {
      return parsed.detail
    }
  } catch {
    // Fall through to plain text.
  }
  return text
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const response = await fetch(`${API_PREFIX}${path}`, {
    ...init,
    credentials: "include",
    headers: {
      "Content-Type": "application/json",
      ...(init.headers ?? {}),
    },
  })

  if (!response.ok) {
    throw new ApiError(response.status, await readApiError(response))
  }

  return (await response.json()) as T
}

export function login(payload: { username: string; password: string }) {
  return request<{ user: AuthUser; message: string }>("/auth/login", {
    method: "POST",
    body: JSON.stringify(payload),
  })
}

export function register(payload: {
  username: string
  password: string
  display_name: string
  department_code: string
}) {
  return request<{ user: AuthUser; message: string }>("/auth/register", {
    method: "POST",
    body: JSON.stringify(payload),
  })
}

export function logout() {
  return request<{ message: string }>("/auth/logout", {
    method: "POST",
  })
}

export function getCurrentUser() {
  return request<{ user: AuthUser }>("/auth/me")
}

export function runAiQuery(
  question: string,
  context?: AiQueryContext | null,
  init: Pick<RequestInit, "signal"> = {}
) {
  return request<AiQueryResponse>("/ai-query/query", {
    ...init,
    method: "POST",
    body: JSON.stringify({ question, context }),
  })
}

export function listAiQueryHistory() {
  return request<{ items: string[] }>("/ai-query/history")
}

export function clearAiQueryHistory() {
  return request<{ message: string }>("/ai-query/history", {
    method: "DELETE",
  })
}

export function getAuthOptions() {
  return request<{
    departments: AuthDepartment[]
    roles: AuthRole[]
    has_users: boolean
  }>("/auth/options")
}

export function listAdminUsers(params: { page: number; pageSize: number }) {
  const search = new URLSearchParams({
    page: String(params.page),
    page_size: String(params.pageSize),
  })
  return request<{
    items: AuthUser[]
    total: number
    page: number
    page_size: number
    stats: { active: number; disabled: number; department_count: number }
  }>(`/auth/admin/users?${search.toString()}`)
}

export function updateAdminUser(
  id: number,
  payload: Partial<
    Pick<AuthUser, "display_name" | "department_code" | "role_code" | "status">
  > & { password?: string }
) {
  return request<{ item: AuthUser; message: string }>(
    `/auth/admin/users/${id}`,
    {
      method: "PATCH",
      body: JSON.stringify(payload),
    }
  )
}

export function listOperationLogs(params: {
  module:
    | "product"
    | "size_group"
    | "product_goods"
    | "fine_table"
    | "inventory"
    | "purchase"
    | "purchase_inbound_detail"
    | "supplier"
    | "supplier_brand"
    | "warehouse"
    | "account_subject"
    | "general_customer"
    | "ai_query"
    | "user"
  query?: string
  page: number
  pageSize: number
}) {
  const search = new URLSearchParams({
    module: params.module,
    page: String(params.page),
    page_size: String(params.pageSize),
  })
  if (params.query) search.set("query", params.query)
  return request<OperationLogResponse>(`/operation-logs?${search.toString()}`)
}

export function getProductYears(brand: ProductArchiveBrandKey) {
  return request<{ years: string[] }>(`/products/${brand}/years`)
}

export function listProductColorBarcodes(brand: ProductArchiveRecordBrandKey) {
  const search = new URLSearchParams({ brand })
  return request<ProductColorBarcodeListResponse>(
    `/products/color-barcodes?${search.toString()}`
  )
}

export function listSizeGroups() {
  return request<{ items: SizeGroup[] }>("/size-groups")
}

export function createSizeGroup(payload: SizeGroupWritePayload) {
  return request<{ item: SizeGroup; message: string }>("/size-groups", {
    method: "POST",
    body: JSON.stringify(payload),
  })
}

export function updateSizeGroup(id: number, payload: SizeGroupWritePayload) {
  return request<{ item: SizeGroup; message: string }>(`/size-groups/${id}`, {
    method: "PUT",
    body: JSON.stringify(payload),
  })
}

export function deleteSizeGroup(id: number) {
  return request<{ message: string }>(`/size-groups/${id}`, {
    method: "DELETE",
  })
}

export function listProducts(params: {
  brand: ProductArchiveBrandKey
  query?: string
  skuPrefix?: string
  year?: string
  page: number
  pageSize: number
}) {
  const search = new URLSearchParams({
    brand: params.brand,
    page: String(params.page),
    page_size: String(params.pageSize),
  })

  if (params.query) {
    search.set("query", params.query)
  }
  if (params.skuPrefix) {
    search.set("sku_prefix", params.skuPrefix)
  }
  if (params.year) {
    search.set("year", params.year)
  }

  return request<ProductListResponse>(`/products?${search.toString()}`)
}

export type FineTableFilterField =
  | "sku"
  | "original_sku"
  | "status"
  | "group_name"
  | "product_level"
  | "year"
  | "season_category"
  | "platform"
  | "factory_code"
  | "factory_name"
  | "product_name"
  | "main_style"
  | "style_code"
  | "goods_id"
  | "p_spu"
  | "category_l3"
  | "factory_sku"
  | "execution_standard"
  | "upper_material"
  | "lining_material"
  | "outsole_material"
  | "insole_material"
  | "first_order_time"
  | "sales_tag"
  | "goods_tag"
  | "cost"
  | "final_price"
  | "vip_price"
  | "market_price"
  | "price_band"
  | "activity_profit"
  | "margin_rate"
  | "vip_1d_sales"
  | "vip_3d_sales"
  | "vip_7d_sales"
  | "vip_15d_sales"
  | "vip_30d_sales"
  | "vip_daily_average_sales"
  | "vip_projected_15d_sales"
  | "other_3d_sales"
  | "other_7d_sales"
  | "other_15d_sales"
  | "other_30d_sales"
  | "other_daily_average_sales"
  | "other_projected_15d_sales"
  | "original_other_3d_sales"
  | "original_other_7d_sales"
  | "original_all_7d_sales"
  | "original_other_15d_sales"
  | "original_other_30d_sales"
  | "vip_3d_uv"
  | "vip_7d_uv"
  | "vip_30d_uv"
  | "vip_3d_ctr"
  | "vip_7d_ctr"
  | "vip_30d_ctr"
  | "vip_3d_exposure"
  | "vip_7d_exposure"
  | "vip_30d_exposure"
  | "vip_3d_conversion"
  | "vip_7d_conversion"
  | "vip_30d_conversion"
  | "vip_3d_sales_change_rate"
  | "vip_3d_uv_change_rate"
  | "vip_3d_ctr_change_rate"
  | "vip_3d_conversion_change_rate"
  | "vip_7d_sales_change_rate"
  | "vip_7d_uv_change_rate"
  | "vip_7d_ctr_change_rate"
  | "vip_7d_conversion_change_rate"
  | "vip_30d_reject_count"
  | "vip_30d_reject_rate"
  | "stock_qty"
  | "original_stock_qty"
  | "projected_5d_stock_no_inbound"
  | "inbound_qty"
  | "defect_stock"
  | "original_defect_stock"
  | "original_inbound_qty"
  | "original_order_in_transit_stock"
  | "original_defect_in_transit_stock"
  | "off_shelf_stock"
  | "order_occupy_stock"
  | "order_in_transit_stock"
  | "defect_in_transit_stock"
  | "vip_projected_15d_stock"
  | "other_projected_15d_stock"
  | "risk"
  | "image"
  | `daily_sales_${number}_${"quantity" | "uv"}`
  | `size_${string}`
export type FineTableFilter = {
  field: FineTableFilterField
  operator: "in" | "not_in"
  values: string[]
}
export type FineTableFilterOption = { value: string; count: number }
export type FineTableFilterOptionsResponse = {
  field: FineTableFilterField
  total: number
  truncated: boolean
  options: FineTableFilterOption[]
}

export function listFineTable(params: {
  brand: Exclude<BrandKey, "all">
  query?: string
  skuPrefix?: string
  filters?: FineTableFilter[]
  page: number
  pageSize: number
  cacheBust?: number | string
}) {
  const search = new URLSearchParams({
    brand: params.brand,
    page: String(params.page),
    page_size: String(params.pageSize),
  })
  if (params.query) search.set("query", params.query)
  if (params.skuPrefix) search.set("sku_prefix", params.skuPrefix)
  if (params.filters?.length)
    search.set("filters", JSON.stringify(params.filters))
  if (params.cacheBust) search.set("cache_bust", String(params.cacheBust))
  return request<FineTableResponse>(`/fine-table?${search.toString()}`)
}

export function listFineTableFilterOptions(params: {
  brand: Exclude<BrandKey, "all">
  field: FineTableFilterField
  filters?: FineTableFilter[]
  query?: string
  skuPrefix?: string
  snapshotDate?: string
}) {
  const search = new URLSearchParams({
    brand: params.brand,
    field: params.field,
  })
  if (params.filters?.length)
    search.set("filters", JSON.stringify(params.filters))
  if (params.query) search.set("query", params.query)
  if (params.skuPrefix) search.set("sku_prefix", params.skuPrefix)
  if (params.snapshotDate) search.set("snapshot_date", params.snapshotDate)
  return request<FineTableFilterOptionsResponse>(
    `/fine-table/filter-options?${search.toString()}`
  )
}

export type ProductGoodsFilterField =
  | "year"
  | "season"
  | "platform"
  | "category_l4"
  | "first_order_date"
  | "factory_sku"
  | "factory_code"
  | "factory_name"
  | "style_code"
  | "goods_code"
  | "color"
  | "cost"
  | "product_role"
  | "product_type"
  | "douyin_hot"
  | "clearance"
  | "remark"
export type ProductGoodsFilterOperator =
  | "contains"
  | "equals"
  | "empty"
  | "not_empty"
  | "in"
  | "not_in"
export type ProductGoodsFilter = {
  field: ProductGoodsFilterField
  operator: ProductGoodsFilterOperator
  value?: string
  values?: string[]
}
export type ProductGoodsFilterOption = { value: string; count: number }
export type ProductGoodsFilterOptionsResponse = {
  field: ProductGoodsFilterField
  total: number
  truncated: boolean
  options: ProductGoodsFilterOption[]
}

export function listProductGoods(params: {
  brand?: BrandKey
  view?: "goods" | "style_summary" | "shortage_risk"
  query?: string
  platform?: string
  filters?: ProductGoodsFilter[]
  snapshotDate?: string
  page: number
  pageSize: number
  cacheBust?: number | string
}) {
  const search = new URLSearchParams({
    brand: params.brand ?? "cbanner_womens",
    page: String(params.page),
    page_size: String(params.pageSize),
  })
  if (params.view && params.view !== "goods") search.set("view", params.view)
  if (params.query) search.set("query", params.query)
  if (params.platform) search.set("platform", params.platform)
  if (params.filters?.length)
    search.set("filters", JSON.stringify(params.filters))
  if (params.snapshotDate) search.set("snapshot_date", params.snapshotDate)
  if (params.cacheBust) search.set("cache_bust", String(params.cacheBust))
  return request<ProductGoodsResponse>(`/product-goods?${search.toString()}`)
}

export function listProductGoodsFilterOptions(params: {
  brand?: BrandKey
  field: ProductGoodsFilterField
  filters?: ProductGoodsFilter[]
  query?: string
  search?: string
}) {
  const requestParams = new URLSearchParams({
    brand: params.brand ?? "cbanner_womens",
    field: params.field,
  })
  if (params.filters?.length)
    requestParams.set("filters", JSON.stringify(params.filters))
  if (params.query) requestParams.set("query", params.query)
  if (params.search) requestParams.set("search", params.search)
  return request<ProductGoodsFilterOptionsResponse>(
    `/product-goods/filter-options?${requestParams.toString()}`
  )
}

export function getFactoryChannelDashboard(params: {
  brand: Exclude<BrandKey, "all">
  salesYear?: number
  productYear?: string
  dateStart?: string
  dateEnd?: string
}) {
  const search = new URLSearchParams({ brand: params.brand })
  if (params.salesYear) search.set("sales_year", String(params.salesYear))
  if (params.productYear) search.set("product_year", params.productYear)
  if (params.dateStart) search.set("date_start", params.dateStart)
  if (params.dateEnd) search.set("date_end", params.dateEnd)
  return request<FactoryChannelDashboardResponse>(
    `/product-goods/factory-channel-dashboard?${search.toString()}`
  )
}

export function updateProductGoods(
  brand: BrandKey,
  id: number,
  payload: Record<
    string,
    string | boolean | number | Record<string, number> | null
  >
) {
  return request<{ message: string }>(`/product-goods/${id}?brand=${brand}`, {
    method: "PATCH",
    body: JSON.stringify(payload),
  })
}

export function logProductGoodsExport(payload: {
  brand: Exclude<BrandKey, "all">
  brand_label?: string
  exported_rows: number
  total_rows?: number
  view: "goods" | "style_summary"
  query?: string
  filters?: number
  history_date?: string
  column_count?: number
  filename?: string
}) {
  return request<{ message: string }>("/product-goods/export-log", {
    method: "POST",
    body: JSON.stringify(payload),
  })
}

export function logFineTableExport(payload: {
  brand: Exclude<BrandKey, "all">
  brand_label?: string
  exported_rows: number
  total_rows?: number
  view?: string
  query?: string
  sku_prefix?: string
  history_date?: string
  column_mode?: string
  column_count?: number
  filename?: string
}) {
  return request<{ message: string }>("/fine-table/export-log", {
    method: "POST",
    body: JSON.stringify(payload),
  })
}

export function listFineTableSnapshots(params: {
  brand: Exclude<BrandKey, "all">
  page: number
  pageSize: number
}) {
  const search = new URLSearchParams({
    brand: params.brand,
    page: String(params.page),
    page_size: String(params.pageSize),
  })
  return request<FineTableSnapshotListResponse>(
    `/fine-table/snapshots?${search.toString()}`
  )
}

export function getFineTableSnapshot(params: {
  id: number
  query?: string
  skuPrefix?: string
  filters?: FineTableFilter[]
  page: number
  pageSize: number
}) {
  const search = new URLSearchParams({
    page: String(params.page),
    page_size: String(params.pageSize),
  })
  if (params.query) search.set("query", params.query)
  if (params.skuPrefix) search.set("sku_prefix", params.skuPrefix)
  if (params.filters?.length)
    search.set("filters", JSON.stringify(params.filters))
  return request<FineTableSnapshotResponse>(
    `/fine-table/snapshots/${params.id}?${search.toString()}`
  )
}

export function getFineTableSnapshotByDate(params: {
  brand: Exclude<BrandKey, "all">
  snapshotDate: string
  query?: string
  skuPrefix?: string
  filters?: FineTableFilter[]
  page: number
  pageSize: number
}) {
  const search = new URLSearchParams({
    brand: params.brand,
    snapshot_date: params.snapshotDate,
    page: String(params.page),
    page_size: String(params.pageSize),
  })
  if (params.query) search.set("query", params.query)
  if (params.skuPrefix) search.set("sku_prefix", params.skuPrefix)
  if (params.filters?.length)
    search.set("filters", JSON.stringify(params.filters))
  return request<FineTableSnapshotResponse>(
    `/fine-table/snapshots/by-date?${search.toString()}`
  )
}

export function getProduct(brand: ProductArchiveRecordBrandKey, id: number) {
  return request<ProductListItem>(`/products/${brand}/${id}`)
}

export function createProduct(
  brand: ProductArchiveRecordBrandKey,
  payload: ProductMutationPayload
) {
  return request<{ item: ProductListItem; message: string }>("/products", {
    method: "POST",
    body: JSON.stringify({ brand, payload }),
  })
}

export function updateProduct(
  brand: ProductArchiveRecordBrandKey,
  id: number,
  payload: ProductMutationPayload
) {
  return request<{ item: ProductListItem; message: string }>(
    `/products/${brand}/${id}`,
    {
      method: "PUT",
      body: JSON.stringify({ brand, payload }),
    }
  )
}

export function deleteProduct(brand: ProductArchiveRecordBrandKey, id: number) {
  return request<{ message: string }>(`/products/${brand}/${id}`, {
    method: "DELETE",
  })
}

export type BatchDeleteResult = {
  deleted: number
  message: string
}

export function batchDeleteProducts(
  brand: ProductArchiveRecordBrandKey,
  ids: number[]
) {
  return request<BatchDeleteResult>("/products/batch-delete", {
    method: "POST",
    body: JSON.stringify({ brand, ids }),
  })
}

export function lookupImage(params: {
  brand: ProductArchiveRecordBrandKey
  originalSku: string | null
  sku: string | null
}) {
  return request<ImageLookupResult>("/images/lookup", {
    method: "POST",
    body: JSON.stringify({
      brand: params.brand,
      original_sku: params.originalSku,
      sku: params.sku,
    }),
  })
}

export function refreshProductImages(brand: ProductArchiveBrandKey) {
  const search = new URLSearchParams()
  if (brand !== "all") {
    search.set("brand", brand)
  }
  const suffix = search.toString() ? `?${search.toString()}` : ""
  return request<RefreshProductImagesResult>(
    `/images/refresh-product-images${suffix}`,
    {
      method: "POST",
    }
  )
}

export function getProductImageRefreshStatus() {
  return request<ProductImageRefreshStatus>(
    "/images/refresh-product-images/status"
  )
}

export function buildProductExportUrl(
  brand: ProductArchiveBrandKey,
  ids?: number[],
  mode?: "with_sizes",
  activityDateStart?: string,
  activityDateEnd?: string,
  year?: string,
  query?: string,
  skuPrefix?: string
) {
  const params = new URLSearchParams({ brand })
  if (brand !== "all" && ids && ids.length > 0) {
    params.set("ids", ids.join(","))
  }
  if (mode) {
    params.set("mode", mode)
  }
  if (activityDateStart) {
    params.set("activity_date_start", activityDateStart)
  }
  if (activityDateEnd) {
    params.set("activity_date_end", activityDateEnd)
  }
  if (year) {
    params.set("year", year)
  }
  if (query?.trim()) {
    params.set("query", query.trim())
  }
  if (skuPrefix?.trim()) {
    params.set("sku_prefix", skuPrefix.trim())
  }
  return `${API_PREFIX}/export?${params.toString()}`
}

export type ProductExportProgress = {
  phase: "preparing" | "downloading"
  loaded: number
  total: number | null
  percent: number | null
}

function filenameFromContentDisposition(
  header: string | null,
  fallback: string
) {
  if (!header) return fallback
  const encodedMatch = /filename\*=UTF-8''([^;]+)/i.exec(header)
  if (encodedMatch?.[1]) {
    try {
      return decodeURIComponent(encodedMatch[1].replace(/^"|"$/g, ""))
    } catch {
      return encodedMatch[1].replace(/^"|"$/g, "")
    }
  }
  const plainMatch = /filename="?([^";]+)"?/i.exec(header)
  return plainMatch?.[1] || fallback
}

function downloadBlob(blob: Blob, filename: string) {
  const url = URL.createObjectURL(blob)
  const a = document.createElement("a")
  a.href = url
  a.download = filename
  a.style.display = "none"
  document.body.appendChild(a)
  a.click()
  document.body.removeChild(a)
  window.setTimeout(() => URL.revokeObjectURL(url), 0)
}

export async function downloadProductExport(
  brand: ProductArchiveBrandKey,
  ids?: number[],
  mode?: "with_sizes",
  onProgress?: (progress: ProductExportProgress) => void,
  activityDateStart?: string,
  activityDateEnd?: string,
  year?: string,
  query?: string,
  skuPrefix?: string
) {
  onProgress?.({ phase: "preparing", loaded: 0, total: null, percent: null })
  const response = await fetch(
    buildProductExportUrl(
      brand,
      ids,
      mode,
      activityDateStart,
      activityDateEnd,
      year,
      query,
      skuPrefix
    ),
    {
      credentials: "include",
    }
  )
  if (!response.ok) {
    throw new ApiError(response.status, await readApiError(response))
  }

  const totalHeader = response.headers.get("content-length")
  const parsedTotal = totalHeader
    ? Number.parseInt(totalHeader, 10)
    : Number.NaN
  const total =
    Number.isFinite(parsedTotal) && parsedTotal > 0 ? parsedTotal : null
  const contentType =
    response.headers.get("content-type") ||
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
  const filename = filenameFromContentDisposition(
    response.headers.get("content-disposition"),
    "商品信息档案.xlsx"
  )

  onProgress?.({
    phase: "downloading",
    loaded: 0,
    total,
    percent: total ? 0 : null,
  })

  if (!response.body) {
    const blob = await response.blob()
    onProgress?.({
      phase: "downloading",
      loaded: blob.size,
      total: total ?? blob.size,
      percent: 100,
    })
    downloadBlob(blob, filename)
    return { filename, size: blob.size }
  }

  const reader = response.body.getReader()
  const chunks: BlobPart[] = []
  let loaded = 0
  while (true) {
    const { done, value } = await reader.read()
    if (done) break
    if (!value) continue
    const chunk = new Uint8Array(value.byteLength)
    chunk.set(value)
    chunks.push(chunk.buffer)
    loaded += value.byteLength
    onProgress?.({
      phase: "downloading",
      loaded,
      total,
      percent: total ? Math.min(100, Math.round((loaded / total) * 100)) : null,
    })
  }

  const blob = new Blob(chunks, { type: contentType })
  onProgress?.({
    phase: "downloading",
    loaded,
    total: total ?? loaded,
    percent: 100,
  })
  downloadBlob(blob, filename)
  return { filename, size: loaded }
}

export async function assertProductExportAllowed(
  brand: ProductArchiveBrandKey,
  ids?: number[],
  mode?: "with_sizes",
  activityDateStart?: string,
  activityDateEnd?: string,
  year?: string,
  query?: string,
  skuPrefix?: string
) {
  const response = await fetch(
    buildProductExportUrl(
      brand,
      ids,
      mode,
      activityDateStart,
      activityDateEnd,
      year,
      query,
      skuPrefix
    ),
    {
      credentials: "include",
      method: "HEAD",
    }
  )
  if (!response.ok) {
    throw new ApiError(response.status, await readApiError(response))
  }
}

export function exportProducts(
  brand: ProductArchiveBrandKey,
  ids?: number[],
  mode?: "with_sizes",
  activityDateStart?: string,
  activityDateEnd?: string,
  year?: string,
  query?: string,
  skuPrefix?: string
) {
  return fetch(
    buildProductExportUrl(
      brand,
      ids,
      mode,
      activityDateStart,
      activityDateEnd,
      year,
      query,
      skuPrefix
    ),
    {
      credentials: "include",
    }
  ).then(async (response) => {
    if (!response.ok) {
      throw new ApiError(response.status, await response.text())
    }
    return response
  })
}

export type ImportResult = {
  created: number
  updated: number
  skus: string[]
  message: string
}

export async function downloadProductImportTemplate() {
  const response = await fetch(`${API_PREFIX}/import/template`, {
    credentials: "include",
  })
  if (!response.ok) {
    throw new ApiError(response.status, await readApiError(response))
  }

  const filename = filenameFromContentDisposition(
    response.headers.get("content-disposition"),
    "商品信息档案导入模板.xlsx"
  )
  const blob = await response.blob()
  downloadBlob(blob, filename)
  return { filename, size: blob.size }
}

export function importProducts(
  brand: ProductArchiveRecordBrandKey,
  file: File
) {
  const formData = new FormData()
  formData.append("file", file)

  return fetch(`${API_PREFIX}/import?brand=${brand}`, {
    method: "POST",
    body: formData,
    credentials: "include",
  }).then(async (response) => {
    if (!response.ok) {
      throw new ApiError(response.status, await readApiError(response))
    }
    return (await response.json()) as ImportResult
  })
}

export function listProductRecycleBin(params: {
  brand?: ProductArchiveBrandKey
  page?: number
  pageSize?: number
}) {
  const search = new URLSearchParams({
    page: String(params.page ?? 1),
    page_size: String(params.pageSize ?? 20),
  })
  if (params.brand) search.set("brand", params.brand)
  return request<ProductRecycleResponse>(
    `/products/recycle-bin?${search.toString()}`
  )
}

export function restoreProductFromRecycleBin(
  brand: ProductArchiveRecordBrandKey,
  id: number
) {
  return request<{ item: ProductListItem; message: string }>(
    `/products/recycle-bin/${brand}/${id}/restore`,
    {
      method: "POST",
    }
  )
}

export function permanentlyDeleteProduct(
  brand: ProductArchiveRecordBrandKey,
  id: number
) {
  return request<{ message: string }>(`/products/recycle-bin/${brand}/${id}`, {
    method: "DELETE",
  })
}

export function listProductArchiveBrands() {
  return request<{ items: SupplierBrandItem[] }>("/products/brands")
}

// ── Inventory ────────────────────────────────────────────────────

export type InventoryRecord = {
  id: number
  document_number: string | null
  date: string | null
  supplier: string | null
  total_count: string | null
  amount: string | null
  warehouse: string | null
  document_type: string | null
  handler: string | null
  summary: string | null
  additional_note: string | null
  extra_fields: Record<string, string> | null
  source_workbook: string
  source_sheet: string
  source_row_number: string
  deleted_at: string | null
  created_at: string | null
  updated_at: string | null
}

export type MatchSkuResult = {
  found: boolean
  image_url: string | null
  brand: string | null
}

export function matchSkuImage(sku: string) {
  return request<MatchSkuResult>("/images/match-sku", {
    method: "POST",
    body: JSON.stringify({ sku }),
  })
}

export type InventoryDetail = {
  id: number
  document_id: number
  product_code: string | null
  product_name: string | null
  color_spec: string | null
  color_barcode: string | null
  color_name: string | null
  size_quantities: Record<string, string> | null
  extra_fields: Record<string, string> | null
  quantity: string | null
  unit_price: string | null
  amount: string | null
  remark: string | null
  created_at: string | null
  updated_at: string | null
}

export type InventoryDetailLookupResult = {
  matched_product: boolean
  product_code: string | null
  product_name: string | null
  color_spec: string | null
  color_barcode: string | null
  color_name: string | null
  size_range: string | null
  size_labels: string[]
  quantity: string | null
  unit_price: string | null
  amount: string | null
  size_quantities: Record<string, string> | null
  extra_fields: Record<string, string> | null
}

export type InventoryDetailCandidate = {
  product_code: string
  sku: string
  original_sku: string
  product_name: string
  color_name: string
  factory_code: string
  brand: string
}

export type InventoryListResponse = {
  items: InventoryRecord[]
  total: number
  page: number
  page_size: number
}

export type CounterpartyLedgerItem = {
  id: number
  row_number: number
  document_number: string | null
  date: string | null
  document_type: string | null
  summary: string | null
  handler: string | null
  warehouse: string | null
  increase_amount: string
  decrease_amount: string
  balance: string
}

export type CounterpartyLedgerResponse = {
  items: CounterpartyLedgerItem[]
  counterparty_type: "supplier" | "customer"
  name: string
  date_start: string | null
  date_end: string | null
  beginning_balance: string
  increase_total: string
  decrease_total: string
  ending_balance: string
}

export type SupplierItem = {
  id: number
  brand: string
  name: string
  factory_code: string | null
  contact: string | null
  wechat: string | null
  cooperation_status: string | null
  address: string | null
  notes: string | null
}

export type SupplierListResponse = {
  items: SupplierItem[]
  total: number
  page: number
  page_size: number
}

export type WarehouseItem = {
  id: number
  brand: string | null
  name: string
  address: string | null
  notes: string | null
  sort_order: number
}

export type SupplierBrandItem = {
  id: number
  code: string
  name: string
  sort_order: number
  created_at: string | null
  updated_at: string | null
}

export type WarehouseBrandItem = {
  id: number
  name: string
  sort_order: number
  warehouse_count: number
  created_at: string | null
  updated_at: string | null
}

export type WarehouseInventoryItem = {
  product_code: string | null
  product_name: string | null
  color_name: string | null
  color_spec: string | null
  beginning_qty: string
  inbound_qty: string
  outbound_qty: string
  ending_qty: string
}

export type WarehouseInventoryResponse = {
  items: WarehouseInventoryItem[]
  total: number
  page: number
  page_size: number
  totals: {
    beginning_qty: string
    inbound_qty: string
    outbound_qty: string
    ending_qty: string
  }
}

export type WarehouseInventoryMovementItem = {
  detail_id: number
  document_id: number
  date: string | null
  date_value: string | null
  document_type: string | null
  document_number: string | null
  supplier: string | null
  warehouse: string | null
  summary: string | null
  handler: string | null
  product_code: string | null
  product_name: string | null
  color_name: string | null
  color_spec: string | null
  inbound_qty: string
  outbound_qty: string
  change_qty: string
}

export type WarehouseInventoryMovementResponse = {
  items: WarehouseInventoryMovementItem[]
  total: number
  page: number
  page_size: number
}

export type InventoryAccountSubject = {
  id: number
  code: string | null
  name: string
  created_at: string | null
  updated_at: string | null
}

export type PurchaseOrderRequirementBrand =
  | Exclude<BrandKey, "all">
  | "smiley"
  | "ni"

export type PurchaseOrderRequirementTemplate = {
  brand: PurchaseOrderRequirementBrand
  label: string
  content: string
  default_content: string
  updated_at: string | null
  is_custom: boolean
}

export function listInventory(params: {
  date_start?: string
  date_end?: string
  supplier?: string
  warehouse?: string
  document_type?: string
  exclude_document_type?: string
  summary?: string
  original_sku?: string
  product_code?: string
  handler?: string
  completion_status?: string
  sortBy?: string
  sortDirection?: "asc" | "desc"
  sortRules?: Array<{ key: string; direction: "asc" | "desc" }>
  page: number
  pageSize: number
}) {
  const search = new URLSearchParams({
    page: String(params.page),
    page_size: String(params.pageSize),
  })
  if (params.date_start) search.set("date_start", params.date_start)
  if (params.date_end) search.set("date_end", params.date_end)
  if (params.supplier) search.set("supplier", params.supplier)
  if (params.warehouse) search.set("warehouse", params.warehouse)
  if (params.document_type) search.set("document_type", params.document_type)
  if (params.exclude_document_type)
    search.set("exclude_document_type", params.exclude_document_type)
  if (params.summary) search.set("summary", params.summary)
  if (params.original_sku) search.set("original_sku", params.original_sku)
  if (params.product_code) search.set("product_code", params.product_code)
  if (params.handler) search.set("handler", params.handler)
  if (params.completion_status)
    search.set("completion_status", params.completion_status)
  if (params.sortBy) search.set("sort_by", params.sortBy)
  if (params.sortDirection) search.set("sort_direction", params.sortDirection)
  for (const rule of params.sortRules ?? []) {
    search.append("sort", `${rule.key}:${rule.direction}`)
  }
  return request<InventoryListResponse>(`/inventory?${search.toString()}`)
}

export function createInventoryRecord(payload: Record<string, unknown>) {
  return request<{
    item: InventoryRecord
    message: string
    appended?: boolean
  }>("/inventory", {
    method: "POST",
    body: JSON.stringify(payload),
  })
}

export function updateInventoryRecord(
  id: number,
  payload: Record<string, unknown>
) {
  return request<{ item: InventoryRecord; message: string }>(
    `/inventory/${id}`,
    {
      method: "PUT",
      body: JSON.stringify(payload),
    }
  )
}

export function deleteInventoryRecord(id: number) {
  return request<{ message: string }>(`/inventory/${id}`, {
    method: "DELETE",
  })
}

export function listInventoryRecycleBin(params: {
  page: number
  pageSize: number
  document_type?: string
  exclude_document_type?: string
}) {
  const search = new URLSearchParams({
    page: String(params.page),
    page_size: String(params.pageSize),
  })
  if (params.document_type) search.set("document_type", params.document_type)
  if (params.exclude_document_type)
    search.set("exclude_document_type", params.exclude_document_type)
  return request<InventoryListResponse>(
    `/inventory/recycle-bin?${search.toString()}`
  )
}

export function listCounterpartyLedger(params: {
  counterpartyType: "supplier" | "customer"
  name: string
  dateStart?: string
  dateEnd?: string
}) {
  const search = new URLSearchParams({
    counterparty_type: params.counterpartyType,
    name: params.name,
  })
  if (params.dateStart) search.set("date_start", params.dateStart)
  if (params.dateEnd) search.set("date_end", params.dateEnd)
  return request<CounterpartyLedgerResponse>(
    `/inventory/counterparty-ledger?${search.toString()}`
  )
}

export function restoreInventoryRecord(id: number) {
  return request<{ item: InventoryRecord; message: string }>(
    `/inventory/${id}/restore`,
    {
      method: "POST",
    }
  )
}

export function batchRestoreInventory(ids: number[]) {
  return request<{ restored: number; message: string }>(
    "/inventory/batch-restore",
    {
      method: "POST",
      body: JSON.stringify({ ids }),
    }
  )
}

export function batchPermanentlyDeleteInventory(ids: number[]) {
  return request<{ deleted: number; message: string }>(
    "/inventory/recycle-bin/batch-delete",
    {
      method: "POST",
      body: JSON.stringify({ ids }),
    }
  )
}

export type BatchUpdateInventoryCostsResult = {
  updated_details: number
  updated_documents: number
  message: string
  items: Array<Record<string, unknown>>
}

export function batchUpdateInventoryCosts(payload: {
  date_start?: string
  date_end?: string
  updates: Record<string, string>
}) {
  return request<BatchUpdateInventoryCostsResult>(
    "/inventory/batch-update-costs",
    {
      method: "POST",
      body: JSON.stringify(payload),
    }
  )
}

export function batchDeleteInventory(ids: number[]) {
  return request<{ deleted: number; message: string }>(
    "/inventory/batch-delete",
    {
      method: "POST",
      body: JSON.stringify({ ids }),
    }
  )
}

export type InventoryImportResult = {
  created: number
  details?: number
  appended?: number
  message: string
  item?: InventoryRecord
}

export function importInventory(file: File) {
  const formData = new FormData()
  formData.append("file", file)
  return fetch(`${API_PREFIX}/inventory/import`, {
    method: "POST",
    body: formData,
    credentials: "include",
  }).then(async (response) => {
    if (!response.ok) {
      throw new ApiError(response.status, await response.text())
    }
    return (await response.json()) as InventoryImportResult
  })
}

export function buildInventoryExportUrl(
  params: {
    ids?: number[]
    date_start?: string
    date_end?: string
    supplier?: string
    warehouse?: string
    document_type?: string
    exclude_document_type?: string
    summary?: string
    original_sku?: string
    product_code?: string
    handler?: string
    completion_status?: string
    purchase_export_mode?: "summary" | "size_rows" | "production_order"
  } = {}
) {
  const search = new URLSearchParams()
  if (params.ids && params.ids.length > 0)
    search.set("ids", params.ids.join(","))
  if (params.date_start) search.set("date_start", params.date_start)
  if (params.date_end) search.set("date_end", params.date_end)
  if (params.supplier) search.set("supplier", params.supplier)
  if (params.warehouse) search.set("warehouse", params.warehouse)
  if (params.document_type) search.set("document_type", params.document_type)
  if (params.exclude_document_type)
    search.set("exclude_document_type", params.exclude_document_type)
  if (params.summary) search.set("summary", params.summary)
  if (params.original_sku) search.set("original_sku", params.original_sku)
  if (params.product_code) search.set("product_code", params.product_code)
  if (params.handler) search.set("handler", params.handler)
  if (params.completion_status)
    search.set("completion_status", params.completion_status)
  if (params.purchase_export_mode)
    search.set("purchase_export_mode", params.purchase_export_mode)
  const suffix = search.toString() ? `?${search.toString()}` : ""
  return `${API_PREFIX}/inventory/export${suffix}`
}

export function buildPurchaseImportTemplateUrl() {
  return `${API_PREFIX}/inventory/import-purchase/template`
}

export function exportInventory(
  params: {
    ids?: number[]
    date_start?: string
    date_end?: string
    supplier?: string
    warehouse?: string
    document_type?: string
    exclude_document_type?: string
    summary?: string
    original_sku?: string
    product_code?: string
    handler?: string
    completion_status?: string
    purchase_export_mode?: "summary" | "size_rows" | "production_order"
  } = {}
) {
  return fetch(buildInventoryExportUrl(params), {
    credentials: "include",
  }).then(async (response) => {
    if (!response.ok) {
      throw new ApiError(response.status, await response.text())
    }
    return response
  })
}

export function listGeneralCustomerShops() {
  return request<GeneralCustomerShopListResponse>(
    "/inventory/general-customer-shops"
  )
}

export function importPurchaseInventory(payload: {
  file: File
  date?: string
  delivery_date?: string
  supplier: string
  warehouse: string
  document_type: string
  handler: string
  summary: string
  brand?: string
}) {
  const formData = new FormData()
  formData.append("file", payload.file)
  formData.append("date", payload.date ?? "")
  formData.append("delivery_date", payload.delivery_date ?? "")
  formData.append("supplier", payload.supplier)
  formData.append("warehouse", payload.warehouse)
  formData.append("document_type", payload.document_type)
  formData.append("handler", payload.handler)
  formData.append("summary", payload.summary)
  formData.append("brand", payload.brand ?? "")
  const controller = new AbortController()
  const timeout = window.setTimeout(() => controller.abort(), 120_000)
  return fetch(`${API_PREFIX}/inventory/import-purchase`, {
    method: "POST",
    body: formData,
    signal: controller.signal,
    credentials: "include",
  })
    .then(async (response) => {
      if (!response.ok) {
        throw new ApiError(response.status, await response.text())
      }
      return (await response.json()) as InventoryImportResult
    })
    .catch((error) => {
      if (error instanceof DOMException && error.name === "AbortError") {
        throw new ApiError(
          408,
          "导入超过 2 分钟未返回，请检查 Excel 行数或稍后刷新确认是否已导入"
        )
      }
      throw error
    })
    .finally(() => window.clearTimeout(timeout))
}

export function listGeneralCustomerBrands() {
  return request<GeneralCustomerBrandListResponse>(
    "/inventory/general-customer-brands"
  )
}

export function listInventoryAccountSubjects() {
  return request<{ items: InventoryAccountSubject[] }>(
    "/inventory/account-subjects"
  )
}

export function listPurchaseOrderRequirements() {
  return request<{ items: PurchaseOrderRequirementTemplate[] }>(
    "/inventory/purchase-order-requirements"
  )
}

export function updatePurchaseOrderRequirement(
  brand: PurchaseOrderRequirementBrand,
  content: string
) {
  return request<{ item: PurchaseOrderRequirementTemplate; message: string }>(
    `/inventory/purchase-order-requirements/${brand}`,
    {
      method: "PUT",
      body: JSON.stringify({ content }),
    }
  )
}

export function createInventoryAccountSubject(
  payload: Record<string, unknown>
) {
  return request<{ item: InventoryAccountSubject; message: string }>(
    "/inventory/account-subjects",
    {
      method: "POST",
      body: JSON.stringify(payload),
    }
  )
}

export function updateInventoryAccountSubject(
  id: number,
  payload: Record<string, unknown>
) {
  return request<{
    item: InventoryAccountSubject
    message: string
    synced_detail_count: number
  }>(
    `/inventory/account-subjects/${id}`,
    {
      method: "PUT",
      body: JSON.stringify(payload),
    }
  )
}

export function deleteInventoryAccountSubject(id: number) {
  return request<{ message: string }>(`/inventory/account-subjects/${id}`, {
    method: "DELETE",
  })
}

export function createGeneralCustomerBrand(payload: Record<string, unknown>) {
  return request<{ item: GeneralCustomerBrandItem; message: string }>(
    "/inventory/general-customer-brands",
    {
      method: "POST",
      body: JSON.stringify(payload),
    }
  )
}

export function updateGeneralCustomerBrand(
  id: number,
  payload: Record<string, unknown>
) {
  return request<{ item: GeneralCustomerBrandItem; message: string }>(
    `/inventory/general-customer-brands/${id}`,
    {
      method: "PUT",
      body: JSON.stringify(payload),
    }
  )
}

export function deleteGeneralCustomerBrand(id: number) {
  return request<{ message: string }>(
    `/inventory/general-customer-brands/${id}`,
    {
      method: "DELETE",
    }
  )
}

export function createGeneralCustomerShop(payload: Record<string, unknown>) {
  return request<{ item: GeneralCustomerShopItem; message: string }>(
    "/inventory/general-customer-shops",
    {
      method: "POST",
      body: JSON.stringify(payload),
    }
  )
}

export function updateGeneralCustomerShop(
  id: number,
  payload: Record<string, unknown>
) {
  return request<{ item: GeneralCustomerShopItem; message: string }>(
    `/inventory/general-customer-shops/${id}`,
    {
      method: "PUT",
      body: JSON.stringify(payload),
    }
  )
}

export function deleteGeneralCustomerShop(id: number) {
  return request<{ message: string }>(
    `/inventory/general-customer-shops/${id}`,
    {
      method: "DELETE",
    }
  )
}

export function reorderGeneralCustomerShops(
  customer_name: string,
  ids: number[]
) {
  return request<{ message: string }>(
    "/inventory/general-customer-shops/order",
    {
      method: "PUT",
      body: JSON.stringify({ customer_name, ids }),
    }
  )
}

export function reorderGeneralCustomerBrands(ids: number[]) {
  return request<{ message: string }>(
    "/inventory/general-customer-brands/order",
    {
      method: "PUT",
      body: JSON.stringify({ ids }),
    }
  )
}

export function listGeneralCustomerUnits() {
  return request<GeneralCustomerUnitListResponse>(
    "/inventory/general-customer-units"
  )
}

export function createGeneralCustomerUnit(payload: {
  shop_id: number
  unit_name: string
}) {
  return request<{ item: GeneralCustomerUnitItem; message: string }>(
    "/inventory/general-customer-units",
    { method: "POST", body: JSON.stringify(payload) }
  )
}

export function updateGeneralCustomerUnit(
  id: number,
  payload: { shop_id: number; unit_name: string }
) {
  return request<{ item: GeneralCustomerUnitItem; message: string }>(
    `/inventory/general-customer-units/${id}`,
    { method: "PUT", body: JSON.stringify(payload) }
  )
}

export function deleteGeneralCustomerUnit(id: number) {
  return request<{ message: string }>(
    `/inventory/general-customer-units/${id}`,
    {
      method: "DELETE",
    }
  )
}

export function reorderGeneralCustomerUnits(shop_id: number, ids: number[]) {
  return request<{ message: string }>(
    "/inventory/general-customer-units/order",
    {
      method: "PUT",
      body: JSON.stringify({ shop_id, ids }),
    }
  )
}

export function listDetails(
  documentId: number,
  params?: { page?: number; pageSize?: number }
) {
  const search = new URLSearchParams()
  if (params?.page) search.set("page", String(params.page))
  if (params?.pageSize) search.set("page_size", String(params.pageSize))
  const suffix = search.size > 0 ? `?${search.toString()}` : ""
  return request<{
    items: InventoryDetail[]
    total: number
    page: number
    page_size: number
  }>(`/inventory/${documentId}/details${suffix}`)
}

export function replaceDetailsFromExcel(payload: {
  documentId: number
  file: File
  brand?: string
}) {
  const formData = new FormData()
  formData.append("file", payload.file)
  formData.append("brand", payload.brand ?? "")
  const controller = new AbortController()
  const timeout = window.setTimeout(() => controller.abort(), 120_000)
  return fetch(
    `${API_PREFIX}/inventory/${payload.documentId}/details/import-replace`,
    {
      method: "POST",
      body: formData,
      signal: controller.signal,
      credentials: "include",
    }
  )
    .then(async (response) => {
      if (!response.ok) {
        throw new ApiError(response.status, await response.text())
      }
      return (await response.json()) as {
        updated: number
        details: number
        message: string
      }
    })
    .catch((error) => {
      if (error instanceof DOMException && error.name === "AbortError") {
        throw new ApiError(
          408,
          "导入超过 2 分钟未返回，请检查 Excel 行数或稍后刷新确认是否已导入"
        )
      }
      throw error
    })
    .finally(() => window.clearTimeout(timeout))
}

export function lookupInventoryDetail(params: {
  productCode: string
  quantity?: string
  brand?: string
}) {
  const search = new URLSearchParams({ product_code: params.productCode })
  if (params.quantity) search.set("quantity", params.quantity)
  if (params.brand) search.set("brand", params.brand)
  return request<{ item: InventoryDetailLookupResult }>(
    `/inventory/detail-lookup?${search.toString()}`
  )
}

export function listInventoryDetailCandidates(params: {
  query: string
  brand?: string
  limit?: number
}) {
  const search = new URLSearchParams({ query: params.query })
  if (params.brand) search.set("brand", params.brand)
  if (params.limit) search.set("limit", String(params.limit))
  return request<{ items: InventoryDetailCandidate[] }>(
    `/inventory/detail-candidates?${search.toString()}`
  )
}

export function createDetail(
  documentId: number,
  payload: Record<string, unknown>
) {
  return request<{ item: InventoryDetail; message: string }>(
    `/inventory/${documentId}/details`,
    {
      method: "POST",
      body: JSON.stringify(payload),
    }
  )
}

export function updateDetail(
  documentId: number,
  detailId: number,
  payload: Record<string, unknown>
) {
  return request<{ item: InventoryDetail; message: string }>(
    `/inventory/${documentId}/details/${detailId}`,
    {
      method: "PUT",
      body: JSON.stringify(payload),
    }
  )
}

export function deleteDetail(documentId: number, detailId: number) {
  return request<{ message: string }>(
    `/inventory/${documentId}/details/${detailId}`,
    {
      method: "DELETE",
    }
  )
}

export function batchDeleteDetails(documentId: number, ids: number[]) {
  return request<{ deleted: number; message: string }>(
    `/inventory/${documentId}/details/batch-delete`,
    {
      method: "POST",
      body: JSON.stringify({ ids }),
    }
  )
}

// ── Ending Inventory ──────────────────────────────────────────────

export type EndingInventoryItem = {
  product_code: string | null
  product_name: string | null
  color_spec: string | null
  beginning_qty: string | null
  inbound_qty: string | null
  return_qty: string | null
  ending_qty: string | null
}

export type EndingInventoryResponse = {
  items: EndingInventoryItem[]
  total: number
  page: number
  page_size: number
}

export type PurchaseInboundDetailItem = {
  row_number: number
  detail_id: number
  document_id: number
  product_code: string | null
  product_name: string | null
  document_type: string | null
  document_number: string | null
  date: string | null
  purchase_quantity: string | null
  purchase_amount: string | null
  retail_amount: string | null
  factory_code: string | null
  unit_code: string | null
  unit_name: string | null
  warehouse_name: string | null
  color_name: string | null
}

export type PurchaseInboundDetailResponse = {
  items: PurchaseInboundDetailItem[]
  total: number
  page: number
  page_size: number
  totals: {
    purchase_quantity: string
    purchase_amount: string
    retail_amount: string
  }
}

export function importJstStock(stockDate?: string) {
  const search = stockDate ? `?stock_date=${stockDate}` : ""
  return request<{ imported: number; message: string }>(
    `/inventory/import-jst-stock${search}`,
    {
      method: "POST",
    }
  )
}

export function listEndingInventory(params: {
  stock_date: string
  date_start?: string
  date_end?: string
  product_code?: string
  page: number
  pageSize: number
}) {
  const search = new URLSearchParams({
    stock_date: params.stock_date,
    page: String(params.page),
    page_size: String(params.pageSize),
  })
  if (params.date_start) search.set("date_start", params.date_start)
  if (params.date_end) search.set("date_end", params.date_end)
  if (params.product_code) search.set("product_code", params.product_code)
  return request<EndingInventoryResponse>(
    `/inventory/ending-balance?${search.toString()}`
  )
}

export function listPurchaseInboundDetails(params: {
  date_start?: string
  date_end?: string
  document_type?: string
  supplier?: string
  warehouse?: string[]
  product_code?: string
  product_name?: string
  color_name?: string
  size_name?: string
  page: number
  pageSize: number
}) {
  const search = new URLSearchParams({
    page: String(params.page),
    page_size: String(params.pageSize),
  })
  if (params.date_start) search.set("date_start", params.date_start)
  if (params.date_end) search.set("date_end", params.date_end)
  if (params.document_type) search.set("document_type", params.document_type)
  if (params.supplier) search.set("supplier", params.supplier)
  for (const warehouse of params.warehouse ?? []) {
    if (warehouse) search.append("warehouse", warehouse)
  }
  if (params.product_code) search.set("product_code", params.product_code)
  if (params.product_name) search.set("product_name", params.product_name)
  if (params.color_name) search.set("color_name", params.color_name)
  if (params.size_name) search.set("size_name", params.size_name)
  return request<PurchaseInboundDetailResponse>(
    `/inventory-reports/purchase-inbound-details?${search.toString()}`
  )
}

export function listWarehouseBrands() {
  return request<{ items: WarehouseBrandItem[] }>("/warehouse-brands")
}

export function createWarehouseBrand(payload: { name: string }) {
  return request<{ item: WarehouseBrandItem; message: string }>(
    "/warehouse-brands",
    {
      method: "POST",
      body: JSON.stringify(payload),
    }
  )
}

export function updateWarehouseBrand(id: number, payload: { name: string }) {
  return request<{ item: WarehouseBrandItem; message: string }>(
    `/warehouse-brands/${id}`,
    {
      method: "PUT",
      body: JSON.stringify(payload),
    }
  )
}

export function deleteWarehouseBrand(id: number) {
  return request<{ message: string }>(`/warehouse-brands/${id}`, {
    method: "DELETE",
  })
}

export function reorderWarehouseBrands(ids: number[]) {
  return request<{ message: string }>("/warehouse-brands/order", {
    method: "PUT",
    body: JSON.stringify({ ids }),
  })
}

export function buildPurchaseInboundDetailExportUrl(
  params: {
    date_start?: string
    date_end?: string
    document_type?: string
    supplier?: string
    warehouse?: string[]
    product_code?: string
    product_name?: string
    color_name?: string
    size_name?: string
  } = {}
) {
  const search = new URLSearchParams()
  if (params.date_start) search.set("date_start", params.date_start)
  if (params.date_end) search.set("date_end", params.date_end)
  if (params.document_type) search.set("document_type", params.document_type)
  if (params.supplier) search.set("supplier", params.supplier)
  for (const warehouse of params.warehouse ?? []) {
    if (warehouse) search.append("warehouse", warehouse)
  }
  if (params.product_code) search.set("product_code", params.product_code)
  if (params.product_name) search.set("product_name", params.product_name)
  if (params.color_name) search.set("color_name", params.color_name)
  if (params.size_name) search.set("size_name", params.size_name)
  const suffix = search.toString() ? `?${search.toString()}` : ""
  return `${API_PREFIX}/inventory-reports/purchase-inbound-details/export${suffix}`
}

// ── Suppliers ────────────────────────────────────────────────────

export function listSuppliers(params?: {
  page?: number
  pageSize?: number
  query?: string
  brand?: string
}) {
  if (!params) {
    return request<SupplierListResponse>("/suppliers")
  }
  const search = new URLSearchParams({
    page: String(params.page ?? 1),
    page_size: String(params.pageSize ?? 50),
  })
  if (params.query) search.set("query", params.query)
  if (params.brand) search.set("brand", params.brand)
  return request<SupplierListResponse>(`/suppliers?${search.toString()}`)
}

export function listSuppliersByBrand(brand: ProductArchiveRecordBrandKey) {
  const search = new URLSearchParams({ brand })
  return request<SupplierListResponse>(`/suppliers?${search.toString()}`)
}

export async function exportSuppliers(params?: {
  query?: string
  brand?: string
}) {
  const search = new URLSearchParams()
  if (params?.query?.trim()) search.set("query", params.query.trim())
  if (params?.brand && params.brand !== "all") search.set("brand", params.brand)
  const suffix = search.size ? `?${search.toString()}` : ""
  const response = await fetch(`${API_PREFIX}/suppliers/export${suffix}`, {
    credentials: "include",
  })
  if (!response.ok)
    throw new ApiError(response.status, await readApiError(response))
  return response.blob()
}

export function listSupplierBrands() {
  return request<{ items: SupplierBrandItem[] }>("/supplier-brands")
}

export function createSupplierBrand(payload: { name: string }) {
  return request<{ item: SupplierBrandItem; message: string }>(
    "/supplier-brands",
    {
      method: "POST",
      body: JSON.stringify(payload),
    }
  )
}

export function updateSupplierBrand(id: number, payload: { name: string }) {
  return request<{ item: SupplierBrandItem; message: string }>(
    `/supplier-brands/${id}`,
    {
      method: "PUT",
      body: JSON.stringify(payload),
    }
  )
}

export function deleteSupplierBrand(id: number) {
  return request<{ message: string }>(`/supplier-brands/${id}`, {
    method: "DELETE",
  })
}

export function createSupplier(payload: Record<string, unknown>) {
  return request<{ item: SupplierItem; message: string }>("/suppliers", {
    method: "POST",
    body: JSON.stringify(payload),
  })
}

export function updateSupplier(id: number, payload: Record<string, unknown>) {
  return request<{ item: SupplierItem; message: string }>(`/suppliers/${id}`, {
    method: "PUT",
    body: JSON.stringify(payload),
  })
}

export function deleteSupplier(id: number) {
  return request<{ message: string }>(`/suppliers/${id}`, {
    method: "DELETE",
  })
}

// ── Warehouses ───────────────────────────────────────────────────

export function listWarehouses() {
  return request<{ items: WarehouseItem[] }>("/warehouses")
}

export function getWarehouseInventory(
  warehouseId: number,
  params: {
    date_start?: string
    date_end?: string
    product_code?: string
    page: number
    pageSize: number
  }
) {
  const search = new URLSearchParams({
    page: String(params.page),
    page_size: String(params.pageSize),
  })
  if (params.date_start) search.set("date_start", params.date_start)
  if (params.date_end) search.set("date_end", params.date_end)
  if (params.product_code) search.set("product_code", params.product_code)
  return request<WarehouseInventoryResponse>(
    `/warehouses/${warehouseId}/inventory?${search.toString()}`
  )
}

export function listWarehouseInventoryMovements(
  warehouseId: number,
  params: {
    date_start?: string
    date_end?: string
    product_code?: string
    color_name?: string
    color_spec?: string
    page: number
    pageSize: number
  }
) {
  const search = new URLSearchParams({
    page: String(params.page),
    page_size: String(params.pageSize),
  })
  if (params.date_start) search.set("date_start", params.date_start)
  if (params.date_end) search.set("date_end", params.date_end)
  if (params.product_code) search.set("product_code", params.product_code)
  if (params.color_name) search.set("color_name", params.color_name)
  if (params.color_spec) search.set("color_spec", params.color_spec)
  return request<WarehouseInventoryMovementResponse>(
    `/warehouses/${warehouseId}/inventory/movements?${search.toString()}`
  )
}

export function createWarehouse(payload: Record<string, unknown>) {
  return request<{ item: WarehouseItem; message: string }>("/warehouses", {
    method: "POST",
    body: JSON.stringify(payload),
  })
}

export function updateWarehouse(id: number, payload: Record<string, unknown>) {
  return request<{ item: WarehouseItem; message: string }>(
    `/warehouses/${id}`,
    {
      method: "PUT",
      body: JSON.stringify(payload),
    }
  )
}

export function deleteWarehouse(id: number) {
  return request<{ message: string }>(`/warehouses/${id}`, {
    method: "DELETE",
  })
}

export function reorderWarehouses(brand: string, ids: number[]) {
  return request<{ message: string }>("/warehouses/order", {
    method: "PUT",
    body: JSON.stringify({ brand, ids }),
  })
}
