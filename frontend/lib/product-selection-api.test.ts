import { afterEach, expect, test, vi } from "vitest"

import { batchDeleteProducts, listProductSelectionIds } from "@/lib/api"

afterEach(() => vi.restoreAllMocks())

test("selects matching product identities using applied filters without pagination", async () => {
  const items = [{ brand: "cbanner_mens", id: 1 }, { brand: "new_brand", id: 1 }]
  const fetchMock = vi.spyOn(global, "fetch").mockResolvedValue(new Response(JSON.stringify({ items, total: 2 })))
  await expect(listProductSelectionIds({ brand: "all", query: "AA,BB", skuPrefix: "A", year: "2026" })).resolves.toEqual({ items, total: 2 })
  expect(fetchMock).toHaveBeenCalledExactlyOnceWith("/api/products/selection-ids", expect.objectContaining({
    method: "POST", cache: "no-store", credentials: "include",
    body: JSON.stringify({ brand: "all", query: "AA,BB", year: "2026", sku_prefix: "A" }),
  }))
})

test("deletes only the confirmed brand and ID snapshot", async () => {
  const items = [{ brand: "cbanner_mens", id: 1 }, { brand: "new_brand", id: 1 }]
  const fetchMock = vi.spyOn(global, "fetch").mockResolvedValue(new Response(JSON.stringify({ deleted: 2, message: "已移入回收站" })))
  await batchDeleteProducts(items)
  expect(fetchMock).toHaveBeenCalledExactlyOnceWith("/api/products/batch-delete", expect.objectContaining({ method: "POST", body: JSON.stringify({ items }) }))
})

test("selection failures propagate instead of claiming a successful selection", async () => {
  vi.spyOn(global, "fetch").mockResolvedValue(new Response(JSON.stringify({ detail: "权限不足" }), { status: 403 }))
  await expect(listProductSelectionIds({ brand: "all" })).rejects.toMatchObject({ status: 403, message: "权限不足" })
})
