import { afterEach, expect, test, vi } from "vitest"
import { listDetails, listInventory, listProducts } from "@/lib/api"

afterEach(() => vi.restoreAllMocks())

test("lists affected by imports always query fresh results with the existing filters", async () => {
  const fetchMock = vi.spyOn(globalThis, "fetch").mockImplementation(async () => new Response(JSON.stringify({ items: [], total: 0 })))
  await listProducts({ brand: "cbanner_womens", query: "IMPORTED", page: 1, pageSize: 10 })
  await listInventory({ document_type: "进货订单", page: 1, pageSize: 10 })
  await listDetails(88, { page: 1, pageSize: 100 })
  expect(fetchMock.mock.calls.map(([url]) => url)).toEqual([
    "/api/products?brand=cbanner_womens&page=1&page_size=10&query=IMPORTED",
    "/api/inventory?page=1&page_size=10&document_type=%E8%BF%9B%E8%B4%A7%E8%AE%A2%E5%8D%95",
    "/api/inventory/88/details?page=1&page_size=100",
  ])
  for (const [, options] of fetchMock.mock.calls) expect(options).toMatchObject({ cache: "no-store", credentials: "include" })
})
