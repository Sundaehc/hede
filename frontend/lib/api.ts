import type { BrandKey } from "@/lib/brands"
import type {
  ImageLookupResult,
  ProductListItem,
  ProductListResponse,
  ProductMutationPayload,
  ProductColorBarcodeListResponse,
  ProductImageRefreshStatus,
  RefreshProductImagesResult,
  FineTableResponse,
  FineTableSnapshotListResponse,
  FineTableSnapshotResponse,
  GeneralCustomerBrandItem,
  GeneralCustomerBrandListResponse,
  GeneralCustomerShopItem,
  GeneralCustomerShopListResponse,
} from "@/lib/types"

const API_PREFIX = "/api"

export class ApiError extends Error {
  constructor(
    public readonly status: number,
    message: string,
  ) {
    super(message)
    this.name = "ApiError"
  }
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const response = await fetch(`${API_PREFIX}${path}`, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...(init.headers ?? {}),
    },
  })

  if (!response.ok) {
    throw new ApiError(response.status, await response.text())
  }

  return (await response.json()) as T
}

export function getProductYears(brand: BrandKey) {
  return request<{ years: string[] }>(`/products/${brand}/years`)
}

export function listProductColorBarcodes(brand: Exclude<BrandKey, "all">) {
  const search = new URLSearchParams({ brand })
  return request<ProductColorBarcodeListResponse>(`/products/color-barcodes?${search.toString()}`)
}

export function listProducts(params: {
  brand: BrandKey | "all"
  query?: string
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
  if (params.year) {
    search.set("year", params.year)
  }

  return request<ProductListResponse>(`/products?${search.toString()}`)
}

export function listFineTable(params: {
  brand: Exclude<BrandKey, "all">
  query?: string
  skuPrefix?: string
  page: number
  pageSize: number
}) {
  const search = new URLSearchParams({
    brand: params.brand,
    page: String(params.page),
    page_size: String(params.pageSize),
  })
  if (params.query) search.set("query", params.query)
  if (params.skuPrefix) search.set("sku_prefix", params.skuPrefix)
  return request<FineTableResponse>(`/fine-table?${search.toString()}`)
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
  return request<FineTableSnapshotListResponse>(`/fine-table/snapshots?${search.toString()}`)
}

export function getFineTableSnapshot(params: {
  id: number
  query?: string
  skuPrefix?: string
  page: number
  pageSize: number
}) {
  const search = new URLSearchParams({
    page: String(params.page),
    page_size: String(params.pageSize),
  })
  if (params.query) search.set("query", params.query)
  if (params.skuPrefix) search.set("sku_prefix", params.skuPrefix)
  return request<FineTableSnapshotResponse>(`/fine-table/snapshots/${params.id}?${search.toString()}`)
}

export function getFineTableSnapshotByDate(params: {
  brand: Exclude<BrandKey, "all">
  snapshotDate: string
  query?: string
  skuPrefix?: string
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
  return request<FineTableSnapshotResponse>(`/fine-table/snapshots/by-date?${search.toString()}`)
}

export function getProduct(brand: BrandKey, id: number) {
  return request<ProductListItem>(`/products/${brand}/${id}`)
}

export function createProduct(brand: BrandKey, payload: ProductMutationPayload) {
  return request<{ item: ProductListItem; message: string }>("/products", {
    method: "POST",
    body: JSON.stringify({ brand, payload }),
  })
}

export function updateProduct(brand: BrandKey, id: number, payload: ProductMutationPayload) {
  return request<{ item: ProductListItem; message: string }>(`/products/${brand}/${id}`, {
    method: "PUT",
    body: JSON.stringify({ brand, payload }),
  })
}

export function deleteProduct(brand: BrandKey, id: number) {
  return request<{ message: string }>(`/products/${brand}/${id}`, {
    method: "DELETE",
  })
}

export type BatchDeleteResult = {
  deleted: number
  message: string
}

export function batchDeleteProducts(brand: BrandKey, ids: number[]) {
  return request<BatchDeleteResult>("/products/batch-delete", {
    method: "POST",
    body: JSON.stringify({ brand, ids }),
  })
}

export function lookupImage(params: {
  brand: BrandKey
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

export function refreshProductImages(brand: BrandKey | "all") {
  const search = new URLSearchParams()
  if (brand !== "all") {
    search.set("brand", brand)
  }
  const suffix = search.toString() ? `?${search.toString()}` : ""
  return request<RefreshProductImagesResult>(`/images/refresh-product-images${suffix}`, {
    method: "POST",
  })
}

export function getProductImageRefreshStatus() {
  return request<ProductImageRefreshStatus>("/images/refresh-product-images/status")
}

export function exportProducts(brand: BrandKey, ids?: number[], mode?: "with_sizes") {
  const params = new URLSearchParams({ brand })
  if (ids && ids.length > 0) {
    params.set("ids", ids.join(","))
  }
  if (mode) {
    params.set("mode", mode)
  }
  return fetch(`${API_PREFIX}/export?${params.toString()}`).then(async (response) => {
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

export function importProducts(brand: BrandKey, file: File) {
  const formData = new FormData()
  formData.append("file", file)

  return fetch(`${API_PREFIX}/import?brand=${brand}`, {
    method: "POST",
    body: formData,
  }).then(async (response) => {
    if (!response.ok) {
      throw new ApiError(response.status, await response.text())
    }
    return (await response.json()) as ImportResult
  })
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
  product_code: string | null
  product_name: string | null
  color_spec: string | null
  color_barcode: string | null
  color_name: string | null
  quantity: string | null
  unit_price: string | null
  amount: string | null
  size_quantities: Record<string, string> | null
  extra_fields: Record<string, string> | null
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
  brand: Exclude<BrandKey, "all"> | "smiley" | "ni"
  name: string
  factory_code: string | null
  contact: string | null
  wechat: string | null
  cooperation_status: string | null
  factory_grade: "A" | "B" | "C" | "D" | null
  factory_suggestion: string | null
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
  name: string
  address: string | null
  notes: string | null
}

export type InventoryAccountSubject = {
  id: number
  code: string | null
  name: string
  created_at: string | null
  updated_at: string | null
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
  if (params.exclude_document_type) search.set("exclude_document_type", params.exclude_document_type)
  if (params.summary) search.set("summary", params.summary)
  if (params.original_sku) search.set("original_sku", params.original_sku)
  if (params.product_code) search.set("product_code", params.product_code)
  if (params.handler) search.set("handler", params.handler)
  if (params.completion_status) search.set("completion_status", params.completion_status)
  return request<InventoryListResponse>(`/inventory?${search.toString()}`)
}

export function createInventoryRecord(payload: Record<string, unknown>) {
  return request<{ item: InventoryRecord; message: string }>("/inventory", {
    method: "POST",
    body: JSON.stringify(payload),
  })
}

export function updateInventoryRecord(id: number, payload: Record<string, unknown>) {
  return request<{ item: InventoryRecord; message: string }>(`/inventory/${id}`, {
    method: "PUT",
    body: JSON.stringify(payload),
  })
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
  if (params.exclude_document_type) search.set("exclude_document_type", params.exclude_document_type)
  return request<InventoryListResponse>(`/inventory/recycle-bin?${search.toString()}`)
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
  return request<CounterpartyLedgerResponse>(`/inventory/counterparty-ledger?${search.toString()}`)
}

export function restoreInventoryRecord(id: number) {
  return request<{ item: InventoryRecord; message: string }>(`/inventory/${id}/restore`, {
    method: "POST",
  })
}

export function batchRestoreInventory(ids: number[]) {
  return request<{ restored: number; message: string }>("/inventory/batch-restore", {
    method: "POST",
    body: JSON.stringify({ ids }),
  })
}

export function batchPermanentlyDeleteInventory(ids: number[]) {
  return request<{ deleted: number; message: string }>("/inventory/recycle-bin/batch-delete", {
    method: "POST",
    body: JSON.stringify({ ids }),
  })
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
  return request<BatchUpdateInventoryCostsResult>("/inventory/batch-update-costs", {
    method: "POST",
    body: JSON.stringify(payload),
  })
}

export function batchDeleteInventory(ids: number[]) {
  return request<{ deleted: number; message: string }>("/inventory/batch-delete", {
    method: "POST",
    body: JSON.stringify({ ids }),
  })
}

export type InventoryImportResult = {
  created: number
  message: string
}

export function importInventory(file: File) {
  const formData = new FormData()
  formData.append("file", file)
  return fetch(`${API_PREFIX}/inventory/import`, {
    method: "POST",
    body: formData,
  }).then(async (response) => {
    if (!response.ok) {
      throw new ApiError(response.status, await response.text())
    }
    return (await response.json()) as InventoryImportResult
  })
}

export function buildInventoryExportUrl(params: {
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
} = {}) {
  const search = new URLSearchParams()
  if (params.date_start) search.set("date_start", params.date_start)
  if (params.date_end) search.set("date_end", params.date_end)
  if (params.supplier) search.set("supplier", params.supplier)
  if (params.warehouse) search.set("warehouse", params.warehouse)
  if (params.document_type) search.set("document_type", params.document_type)
  if (params.exclude_document_type) search.set("exclude_document_type", params.exclude_document_type)
  if (params.summary) search.set("summary", params.summary)
  if (params.original_sku) search.set("original_sku", params.original_sku)
  if (params.product_code) search.set("product_code", params.product_code)
  if (params.handler) search.set("handler", params.handler)
  if (params.completion_status) search.set("completion_status", params.completion_status)
  if (params.purchase_export_mode) search.set("purchase_export_mode", params.purchase_export_mode)
  const suffix = search.toString() ? `?${search.toString()}` : ""
  return `${API_PREFIX}/inventory/export${suffix}`
}

export function exportInventory(params: {
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
} = {}) {
  return fetch(buildInventoryExportUrl(params)).then(async (response) => {
    if (!response.ok) {
      throw new ApiError(response.status, await response.text())
    }
    return response
  })
}

export function listGeneralCustomerShops() {
  return request<GeneralCustomerShopListResponse>("/inventory/general-customer-shops")
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
  })
    .then(async (response) => {
      if (!response.ok) {
        throw new ApiError(response.status, await response.text())
      }
      return (await response.json()) as InventoryImportResult
    })
    .catch((error) => {
      if (error instanceof DOMException && error.name === "AbortError") {
        throw new ApiError(408, "导入超过 2 分钟未返回，请检查 Excel 行数或稍后刷新确认是否已导入")
      }
      throw error
    })
    .finally(() => window.clearTimeout(timeout))
}

export function listGeneralCustomerBrands() {
  return request<GeneralCustomerBrandListResponse>("/inventory/general-customer-brands")
}

export function listInventoryAccountSubjects() {
  return request<{ items: InventoryAccountSubject[] }>("/inventory/account-subjects")
}

export function createInventoryAccountSubject(payload: Record<string, unknown>) {
  return request<{ item: InventoryAccountSubject; message: string }>("/inventory/account-subjects", {
    method: "POST",
    body: JSON.stringify(payload),
  })
}

export function deleteInventoryAccountSubject(id: number) {
  return request<{ message: string }>(`/inventory/account-subjects/${id}`, {
    method: "DELETE",
  })
}

export function createGeneralCustomerBrand(payload: Record<string, unknown>) {
  return request<{ item: GeneralCustomerBrandItem; message: string }>("/inventory/general-customer-brands", {
    method: "POST",
    body: JSON.stringify(payload),
  })
}

export function updateGeneralCustomerBrand(id: number, payload: Record<string, unknown>) {
  return request<{ item: GeneralCustomerBrandItem; message: string }>(`/inventory/general-customer-brands/${id}`, {
    method: "PUT",
    body: JSON.stringify(payload),
  })
}

export function deleteGeneralCustomerBrand(id: number) {
  return request<{ message: string }>(`/inventory/general-customer-brands/${id}`, {
    method: "DELETE",
  })
}

export function createGeneralCustomerShop(payload: Record<string, unknown>) {
  return request<{ item: GeneralCustomerShopItem; message: string }>("/inventory/general-customer-shops", {
    method: "POST",
    body: JSON.stringify(payload),
  })
}

export function updateGeneralCustomerShop(id: number, payload: Record<string, unknown>) {
  return request<{ item: GeneralCustomerShopItem; message: string }>(`/inventory/general-customer-shops/${id}`, {
    method: "PUT",
    body: JSON.stringify(payload),
  })
}

export function deleteGeneralCustomerShop(id: number) {
  return request<{ message: string }>(`/inventory/general-customer-shops/${id}`, {
    method: "DELETE" })
}

export function listDetails(documentId: number) {
  return request<{ items: InventoryDetail[] }>(`/inventory/${documentId}/details`)
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
  return fetch(`${API_PREFIX}/inventory/${payload.documentId}/details/import-replace`, {
    method: "POST",
    body: formData,
    signal: controller.signal,
  })
    .then(async (response) => {
      if (!response.ok) {
        throw new ApiError(response.status, await response.text())
      }
      return (await response.json()) as { updated: number; details: number; message: string }
    })
    .catch((error) => {
      if (error instanceof DOMException && error.name === "AbortError") {
        throw new ApiError(408, "导入超过 2 分钟未返回，请检查 Excel 行数或稍后刷新确认是否已导入")
      }
      throw error
    })
    .finally(() => window.clearTimeout(timeout))
}

export function lookupInventoryDetail(params: { productCode: string; quantity?: string; brand?: string }) {
  const search = new URLSearchParams({ product_code: params.productCode })
  if (params.quantity) search.set("quantity", params.quantity)
  if (params.brand) search.set("brand", params.brand)
  return request<{ item: InventoryDetailLookupResult }>(`/inventory/detail-lookup?${search.toString()}`)
}

export function createDetail(documentId: number, payload: Record<string, unknown>) {
  return request<{ item: InventoryDetail; message: string }>(`/inventory/${documentId}/details`, {
    method: "POST",
    body: JSON.stringify(payload),
  })
}

export function updateDetail(documentId: number, detailId: number, payload: Record<string, unknown>) {
  return request<{ item: InventoryDetail; message: string }>(`/inventory/${documentId}/details/${detailId}`, {
    method: "PUT",
    body: JSON.stringify(payload),
  })
}

export function deleteDetail(documentId: number, detailId: number) {
  return request<{ message: string }>(`/inventory/${documentId}/details/${detailId}`, {
    method: "DELETE",
  })
}

export function batchDeleteDetails(documentId: number, ids: number[]) {
  return request<{ deleted: number; message: string }>(`/inventory/${documentId}/details/batch-delete`, {
    method: "POST",
    body: JSON.stringify({ ids }),
  })
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
  return request<{ imported: number; message: string }>(`/inventory/import-jst-stock${search}`, {
    method: "POST",
  })
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
  return request<EndingInventoryResponse>(`/inventory/ending-balance?${search.toString()}`)
}

export function listPurchaseInboundDetails(params: {
  date_start?: string
  date_end?: string
  document_type?: string
  supplier?: string
  warehouse?: string
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
  if (params.warehouse) search.set("warehouse", params.warehouse)
  if (params.product_code) search.set("product_code", params.product_code)
  if (params.product_name) search.set("product_name", params.product_name)
  if (params.color_name) search.set("color_name", params.color_name)
  if (params.size_name) search.set("size_name", params.size_name)
  return request<PurchaseInboundDetailResponse>(`/inventory-reports/purchase-inbound-details?${search.toString()}`)
}

// ── Suppliers ────────────────────────────────────────────────────

export function listSuppliers(params?: { page?: number; pageSize?: number; query?: string; brand?: BrandKey | "smiley" | "ni"; sort?: "grade_asc" | "grade_desc" | "" }) {
  if (!params) {
    return request<SupplierListResponse>("/suppliers")
  }
  const search = new URLSearchParams({
    page: String(params.page ?? 1),
    page_size: String(params.pageSize ?? 50),
  })
  if (params.query) search.set("query", params.query)
  if (params.brand) search.set("brand", params.brand)
  if (params.sort) search.set("sort", params.sort)
  return request<SupplierListResponse>(`/suppliers?${search.toString()}`)
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

export function createWarehouse(payload: Record<string, unknown>) {
  return request<{ item: WarehouseItem; message: string }>("/warehouses", {
    method: "POST",
    body: JSON.stringify(payload),
  })
}

export function updateWarehouse(id: number, payload: Record<string, unknown>) {
  return request<{ item: WarehouseItem; message: string }>(`/warehouses/${id}`, {
    method: "PUT",
    body: JSON.stringify(payload),
  })
}

export function deleteWarehouse(id: number) {
  return request<{ message: string }>(`/warehouses/${id}`, {
    method: "DELETE",
  })
}
