import { afterEach, expect, test, vi } from "vitest"

import { buildPurchaseOrderDetailExportUrl, getPurchaseOrderDetailOptions, listPurchaseOrderDetails } from "@/lib/api"

afterEach(() => vi.restoreAllMocks())

test("purchase list and export preserve all applied filters and multiple brands and warehouses", async () => {
  const fetchMock = vi.spyOn(global, "fetch").mockResolvedValue(new Response(JSON.stringify({ items: [], total: 0 })))
  const filters = {
    date_start: "2026-11-01", date_end: "2026-11-06", brands: ["cbanner_womens", "custom"],
    supplier: "女鞋厂", warehouse: ["仙岩仓", "总仓"], product_code: "SKU-A", product_name: "休闲",
    color_name: "黑", size_name: "230",
  }
  const controller = new AbortController()
  await listPurchaseOrderDetails({ ...filters, page: 2, pageSize: 100 }, controller.signal)
  const listUrl = new URL(String(fetchMock.mock.calls[0][0]), "http://localhost")
  const exportUrl = new URL(buildPurchaseOrderDetailExportUrl(filters), "http://localhost")
  expect(listUrl.pathname).toBe("/api/purchase-order-details")
  expect(exportUrl.pathname).toBe("/api/purchase-order-details/export")
  for (const url of [listUrl, exportUrl]) {
    expect(url.searchParams.getAll("brands")).toEqual(filters.brands)
    expect(url.searchParams.getAll("warehouse")).toEqual(filters.warehouse)
    for (const key of ["date_start", "date_end", "supplier", "product_code", "product_name", "color_name", "size_name"] as const) {
      expect(url.searchParams.get(key)).toBe(filters[key])
    }
  }
  expect(fetchMock.mock.calls[0][1]).toEqual(expect.objectContaining({ credentials: "include", signal: controller.signal }))
  expect(listUrl.searchParams.get("page")).toBe("2")
  expect(listUrl.searchParams.get("page_size")).toBe("100")
  expect(exportUrl.searchParams.has("page")).toBe(false)
  expect(exportUrl.searchParams.has("page_size")).toBe(false)
})

test("purchase options use the purchase permission endpoint and empty filters are omitted", async () => {
  const fetchMock = vi.spyOn(global, "fetch").mockImplementation(async () => new Response(JSON.stringify({ items: [] })))
  await getPurchaseOrderDetailOptions()
  expect(String(fetchMock.mock.calls[0][0])).toBe("/api/purchase-order-details/options")
  await listPurchaseOrderDetails({ brands: [""], warehouse: [], page: 1, pageSize: 50 })
  const url = new URL(String(fetchMock.mock.calls[1][0]), "http://localhost")
  expect(url.searchParams.has("brands")).toBe(false)
  expect(url.searchParams.has("warehouse")).toBe(false)
  expect(new URL(buildPurchaseOrderDetailExportUrl(), "http://localhost").search).toBe("")
})
