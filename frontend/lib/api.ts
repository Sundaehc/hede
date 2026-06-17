import type { BrandKey } from "@/lib/brands"
import type {
  ImageLookupResult,
  ProductListItem,
  ProductListResponse,
  ProductMutationPayload,
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

export function exportProducts(brand: BrandKey, ids?: number[]) {
  const params = new URLSearchParams({ brand })
  if (ids && ids.length > 0) {
    params.set("ids", ids.join(","))
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
  quantity: string | null
  unit_price: string | null
  amount: string | null
  created_at: string | null
  updated_at: string | null
}

export type InventoryListResponse = {
  items: InventoryRecord[]
  total: number
  page: number
  page_size: number
}

export type SupplierItem = {
  id: number
  brand: Exclude<BrandKey, "all"> | "smiley"
  name: string
  factory_code: string | null
  contact: string | null
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

export function listInventory(params: {
  date_start?: string
  date_end?: string
  supplier?: string
  warehouse?: string
  document_type?: string
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

export function exportInventory() {
  return fetch(`${API_PREFIX}/inventory/export`).then(async (response) => {
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
  formData.append("supplier", payload.supplier)
  formData.append("warehouse", payload.warehouse)
  formData.append("document_type", payload.document_type)
  formData.append("handler", payload.handler)
  formData.append("summary", payload.summary)
  formData.append("brand", payload.brand ?? "")
  return fetch(`${API_PREFIX}/inventory/import-purchase`, {
    method: "POST",
    body: formData,
  }).then(async (response) => {
    if (!response.ok) {
      throw new ApiError(response.status, await response.text())
    }
    return (await response.json()) as InventoryImportResult
  })
}

export function listGeneralCustomerBrands() {
  return request<GeneralCustomerBrandListResponse>("/inventory/general-customer-brands")
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

// ── Suppliers ────────────────────────────────────────────────────

export function listSuppliers(params?: { page?: number; pageSize?: number; query?: string; brand?: BrandKey | "smiley" }) {
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
