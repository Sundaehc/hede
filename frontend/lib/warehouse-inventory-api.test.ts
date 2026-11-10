import { afterEach, expect, test, vi } from "vitest"

import { downloadWarehouseEndingInventory, getWarehouseInventory, listWarehouseInventoryMovements, listWarehouseInventorySummary } from "@/lib/api"

afterEach(() => { vi.restoreAllMocks(); vi.unstubAllGlobals(); vi.useRealTimers() })

test("barcode inventory and movements preserve mode, identity and the empty unallocated key", async () => {
  const fetchMock = vi.spyOn(global, "fetch").mockImplementation(async () => new Response(JSON.stringify({ items: [], total: 0 })))
  await getWarehouseInventory(22, { display_mode: "barcode", page: 1, pageSize: 20 })
  await listWarehouseInventoryMovements(22, { display_mode: "barcode", product_identity_id: 456, inventory_size_key: "35", unallocated: false, exact_match: true, page: 1, pageSize: 50 })
  await listWarehouseInventoryMovements(22, { display_mode: "barcode", product_identity_id: null, inventory_size_key: "", unallocated: true, exact_match: true, page: 1, pageSize: 50 })
  const urls = fetchMock.mock.calls.map(([url]) => new URL(String(url), "http://local"))
  expect(urls[0].searchParams.get("display_mode")).toBe("barcode")
  expect(urls[1].searchParams.get("product_identity_id")).toBe("456")
  expect(urls[1].searchParams.get("inventory_size_key")).toBe("35")
  expect(urls[1].searchParams.get("unallocated")).toBe("false")
  expect(urls[2].searchParams.has("product_identity_id")).toBe(false)
  expect(urls[2].searchParams.get("inventory_size_key")).toBe("")
  expect(urls[2].searchParams.get("unallocated")).toBe("true")
})

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

test("ending inventory filters on the server with the submitted dates and product", async () => {
  const fetchMock = vi.spyOn(global, "fetch").mockImplementation(async () => new Response(JSON.stringify({ items: [], total: 0 })))
  await getWarehouseInventory(22, {
    date_start: "2026-10-01", date_end: "2026-10-31", product_code: "001",
    ending_nonzero: true, page: 2, pageSize: 50,
  })
  const url = new URL(String(fetchMock.mock.calls[0][0]), "http://localhost")
  expect(url.pathname).toBe("/api/warehouses/22/inventory")
  expect(Object.fromEntries(url.searchParams)).toEqual({
    date_start: "2026-10-01", date_end: "2026-10-31", product_code: "001",
    ending_nonzero: "true", page: "2", page_size: "50",
  })
  await getWarehouseInventory(22, { ending_nonzero: false, page: 1, pageSize: 20 })
  expect(String(fetchMock.mock.calls[1][0])).not.toContain("ending_nonzero")
})

test("ending inventory downloads every page with submitted filters and server filename", async () => {
  vi.useFakeTimers()
  const fetchMock = vi.spyOn(global, "fetch").mockResolvedValue(new Response("xlsx", { headers: {
    "Content-Disposition": "attachment; filename*=UTF-8''" + encodeURIComponent("期末库存_主仓_2026-10-31.xlsx"),
  } }))
  const create = vi.fn(() => "blob:inventory")
  const revoke = vi.fn()
  vi.stubGlobal("URL", class extends URL { static createObjectURL = create; static revokeObjectURL = revoke })
  const click = vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(function (this: HTMLAnchorElement) {
    expect(this.download).toBe("期末库存_主仓_2026-10-31.xlsx")
  })
  const controller = new AbortController()
  expect(await downloadWarehouseEndingInventory(22, { date_start: "2026-10-01", date_end: "2026-10-31", product_code: "001" }, controller.signal)).toEqual({ filename: "期末库存_主仓_2026-10-31.xlsx", size: 4 })
  const [url, init] = fetchMock.mock.calls[0]
  const parsed = new URL(String(url), "http://local")
  expect(parsed.pathname).toBe("/api/warehouses/22/inventory/export")
  expect(Object.fromEntries(parsed.searchParams)).toEqual({ date_start: "2026-10-01", date_end: "2026-10-31", product_code: "001" })
  expect(init).toMatchObject({ credentials: "include", cache: "no-store", signal: controller.signal })
  expect(click).toHaveBeenCalledOnce()
  expect(create).toHaveBeenCalledOnce()
  vi.runAllTimers()
  expect(revoke).toHaveBeenCalledWith("blob:inventory")
})

test("ending export surfaces failures and avoids downloading a cancelled request", async () => {
  const click = vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(() => undefined)
  vi.spyOn(global, "fetch").mockResolvedValueOnce(new Response(JSON.stringify({ detail: "权限不足" }), { status: 403 }))
  await expect(downloadWarehouseEndingInventory(1, {})).rejects.toMatchObject({ status: 403, message: "权限不足" })
  vi.mocked(fetch).mockResolvedValueOnce(new Response("xlsx"))
  const controller = new AbortController()
  controller.abort()
  await expect(downloadWarehouseEndingInventory(1, {}, controller.signal)).rejects.toMatchObject({ name: "AbortError" })
  expect(click).not.toHaveBeenCalled()
})
