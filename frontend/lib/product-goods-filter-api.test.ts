import { afterEach, expect, test, vi } from "vitest"
import { listProductGoodsFilterOptions } from "@/lib/api"

afterEach(() => vi.restoreAllMocks())

test("product goods filter options include snapshot date and other filters", async () => {
  const fetchMock = vi.spyOn(global, "fetch").mockResolvedValue(new Response(JSON.stringify({ field: "year", options: [], total: 0, truncated: false }), {
    headers: { "Content-Type": "application/json" },
  }))
  const filters = [{ field: "season", operator: "in", values: ["冬"] }] as const
  await listProductGoodsFilterOptions({ brand: "cbanner_mens", field: "year", snapshotDate: "2026-11-01", query: "鞋", filters: [...filters].map((item) => ({ ...item, values: [...item.values] })) })
  const url = new URL(String(fetchMock.mock.calls[0][0]), "http://localhost")
  expect(url.pathname).toBe("/api/product-goods/filter-options")
  expect(Object.fromEntries(url.searchParams)).toEqual({ brand: "cbanner_mens", field: "year", snapshot_date: "2026-11-01", query: "鞋", filters: JSON.stringify(filters) })
})
