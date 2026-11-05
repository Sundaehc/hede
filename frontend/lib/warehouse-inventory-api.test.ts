import { afterEach, expect, test, vi } from "vitest"

import { getWarehouseInventory, listWarehouseInventoryMovements, listWarehouseInventorySummary } from "@/lib/api"

afterEach(() => vi.restoreAllMocks())

test("inventory drilldown preserves empty grouping fields and omits null fields", async () => {
  const fetchMock = vi.spyOn(global, "fetch").mockResolvedValue(new Response(JSON.stringify({ items: [], total: 0 })))
  await listWarehouseInventoryMovements(22, {
    product_code: "P_%", product_name: null, color_name: null, color_spec: "", exact_match: true,
    date_start: "2026-10-01", date_end: "2026-10-31", page: 2, pageSize: 50,
  })
  const url = new URL(String(fetchMock.mock.calls[0][0]), "http://localhost")
  expect(url.pathname).toBe("/api/warehouses/22/inventory/movements")
  expect(url.searchParams.get("product_code")).toBe("P_%")
  expect(url.searchParams.has("product_name")).toBe(false)
  expect(url.searchParams.has("color_name")).toBe(false)
  expect(url.searchParams.get("color_spec")).toBe("")
  expect(url.searchParams.get("exact_match")).toBe("true")
  expect(url.searchParams.get("date_start")).toBe("2026-10-01")
  expect(url.searchParams.get("date_end")).toBe("2026-10-31")
  expect(url.searchParams.get("page")).toBe("2")
})

test("warehouse statistics always request fresh data without browser caching", async () => {
  const fetchMock = vi.spyOn(global, "fetch").mockImplementation(async () => new Response(JSON.stringify({ items: [], total: 0 })))
  await listWarehouseInventorySummary({})
  await getWarehouseInventory(22, { page: 1, pageSize: 20 })
  await listWarehouseInventoryMovements(22, { page: 1, pageSize: 50 })
  expect(fetchMock).toHaveBeenCalledTimes(3)
  for (const [, options] of fetchMock.mock.calls) {
    expect(options?.cache).toBe("no-store")
  }
})
