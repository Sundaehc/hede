import { afterEach, expect, test, vi } from "vitest"

import { buildSalesDetailExportUrl, getSalesDetailOptions, listSalesDetails } from "@/lib/api"

afterEach(() => vi.unstubAllGlobals())

test("sales list and export serialize the same applied filters with multiple brands and warehouses", async () => {
  const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify({ items: [] }), { status: 200 }))
  vi.stubGlobal("fetch", fetchMock)
  const filters = {
    date_start: "2026-11-01", date_end: "2026-11-09", document_type: "批发销售退货单",
    brands: ["yandou", "ni"], warehouse: ["总仓", "仙岩仓"], supplier: "杭州客户",
    product_code: "000SKU", product_name: "鞋", color_name: "黑", size_name: "240",
  }
  const controller = new AbortController()
  await listSalesDetails({ ...filters, page: 2, pageSize: 100 }, controller.signal)
  const [path, options] = fetchMock.mock.calls[0]
  const listUrl = new URL(path, "http://localhost")
  expect(listUrl.pathname).toBe("/api/inventory-reports/sales-details")
  expect(options).toEqual(expect.objectContaining({ signal: controller.signal, credentials: "include" }))
  expect(listUrl.searchParams.get("page")).toBe("2")
  expect(listUrl.searchParams.get("page_size")).toBe("100")
  expect(listUrl.searchParams.getAll("brands")).toEqual(["yandou", "ni"])
  expect(listUrl.searchParams.getAll("warehouse")).toEqual(["总仓", "仙岩仓"])
  listUrl.searchParams.delete("page")
  listUrl.searchParams.delete("page_size")
  const exported = new URL(buildSalesDetailExportUrl(filters), "http://localhost")
  expect(exported.pathname).toBe("/api/inventory-reports/sales-details/export")
  expect(exported.searchParams.toString()).toBe(listUrl.searchParams.toString())
  expect(exported.searchParams.get("product_code")).toBe("000SKU")
})

test("loads sales customer options from the sales report endpoint", async () => {
  const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify({ brands: [], customers: [], warehouses: [] }), { status: 200 }))
  vi.stubGlobal("fetch", fetchMock)
  await getSalesDetailOptions()
  expect(fetchMock).toHaveBeenCalledWith("/api/inventory-reports/sales-details/options", expect.objectContaining({ credentials: "include" }))
})
