import { beforeEach, expect, test, vi } from "vitest"

import { ApiError, createProduct, deleteProduct, listProducts, lookupImage, updateProduct } from "@/lib/api"

beforeEach(() => {
  vi.restoreAllMocks()
})

test("listProducts serializes brand query and pagination into the request URL", async () => {
  const fetchMock = vi.spyOn(global, "fetch").mockResolvedValue(
    new Response(JSON.stringify({ items: [], total: 0, page: 1, page_size: 20 }), {
      status: 200,
      headers: { "Content-Type": "application/json" },
    }),
  )

  await listProducts({ brand: "cbanner_mens", query: "OA", page: 1, pageSize: 20 })

  expect(fetchMock).toHaveBeenCalledWith(
    "http://127.0.0.1:8000/products?brand=cbanner_mens&page=1&page_size=20&query=OA",
    expect.objectContaining({
      headers: {
        "Content-Type": "application/json",
      },
    }),
  )
})

test("createProduct sends POST to /products with the expected JSON body", async () => {
  const fetchMock = vi.spyOn(global, "fetch").mockResolvedValue(
    new Response(JSON.stringify({ item: { id: 1 }, message: "created" }), {
      status: 200,
      headers: { "Content-Type": "application/json" },
    }),
  )

  await createProduct("cbanner_mens", { sku: "ABC123", title: "Oxford" })

  expect(fetchMock).toHaveBeenCalledWith(
    "http://127.0.0.1:8000/products",
    expect.objectContaining({
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        brand: "cbanner_mens",
        payload: { sku: "ABC123", title: "Oxford" },
      }),
    }),
  )
})

test("updateProduct sends PUT to /products/{brand}/{id} with the expected JSON body", async () => {
  const fetchMock = vi.spyOn(global, "fetch").mockResolvedValue(
    new Response(JSON.stringify({ item: { id: 42 }, message: "updated" }), {
      status: 200,
      headers: { "Content-Type": "application/json" },
    }),
  )

  await updateProduct("cbanner_mens", 42, { sku: "ABC123", title: "Derby" })

  expect(fetchMock).toHaveBeenCalledWith(
    "http://127.0.0.1:8000/products/cbanner_mens/42",
    expect.objectContaining({
      method: "PUT",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        brand: "cbanner_mens",
        payload: { sku: "ABC123", title: "Derby" },
      }),
    }),
  )
})

test("deleteProduct sends DELETE to /products/{brand}/{id}", async () => {
  const fetchMock = vi.spyOn(global, "fetch").mockResolvedValue(
    new Response(JSON.stringify({ message: "deleted" }), {
      status: 200,
      headers: { "Content-Type": "application/json" },
    }),
  )

  await deleteProduct("cbanner_mens", 42)

  expect(fetchMock).toHaveBeenCalledWith(
    "http://127.0.0.1:8000/products/cbanner_mens/42",
    expect.objectContaining({
      method: "DELETE",
      headers: {
        "Content-Type": "application/json",
      },
    }),
  )
})

test("lookupImage sends POST to /images/lookup with original_sku and sku mapped correctly", async () => {
  const fetchMock = vi.spyOn(global, "fetch").mockResolvedValue(
    new Response(JSON.stringify({ result: null, message: "ok" }), {
      status: 200,
      headers: { "Content-Type": "application/json" },
    }),
  )

  await lookupImage({ brand: "cbanner_mens", originalSku: "ABC123", sku: "ABC-123" })

  expect(fetchMock).toHaveBeenCalledWith(
    "http://127.0.0.1:8000/images/lookup",
    expect.objectContaining({
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        brand: "cbanner_mens",
        original_sku: "ABC123",
        sku: "ABC-123",
      }),
    }),
  )
})

test("lookupImage throws ApiError on non-2xx response", async () => {
  vi.spyOn(global, "fetch").mockResolvedValue(new Response("boom", { status: 500 }))

  await expect(lookupImage({ brand: "cbanner_mens", originalSku: "ABC123", sku: null })).rejects.toBeInstanceOf(
    ApiError,
  )
})
