import type { BrandKey } from "@/lib/brands"
import type { ImageLookupResult, ProductListItem, ProductListResponse, ProductMutationPayload } from "@/lib/types"

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

export function listProducts(params: {
  brand: BrandKey
  query?: string
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

  return request<ProductListResponse>(`/products?${search.toString()}`)
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
