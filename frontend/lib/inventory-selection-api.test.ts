import { afterEach, expect, test, vi } from "vitest"

import { batchDeleteInventory, buildInventoryExportUrl, listInventory, listInventorySelectionIds } from "@/lib/api"

afterEach(() => vi.restoreAllMocks())

test("cancels inventory fetches through the signal without adding it to the query", async () => {
  const controller = new AbortController()
  const fetchMock = vi.spyOn(global, "fetch").mockImplementation((_input, init) => new Promise((_resolve, reject) => {
    init?.signal?.addEventListener("abort", () => reject(new DOMException("Aborted", "AbortError")), { once: true })
  }))
  const pending = listInventory({ page: 1, pageSize: 10, completion_status: "completed", signal: controller.signal })
  const url = new URL(String(fetchMock.mock.calls[0][0]), "http://localhost")
  expect(url.searchParams.get("completion_status")).toBe("completed")
  expect(url.searchParams.has("signal")).toBe(false)
  expect(fetchMock.mock.calls[0][1]?.signal).toBe(controller.signal)

  controller.abort()
  await expect(pending).rejects.toMatchObject({ name: "AbortError" })
})

test("requests matching IDs with exactly the applied scope and no pagination", async () => {
  const fetchMock = vi
    .spyOn(global, "fetch")
    .mockResolvedValue(
      new Response(JSON.stringify({ ids: [1, 20, 100001], total: 3 }))
    )
  const filters = {
    summary: "批次",
    brands: ["cbanner_mens"],
    completion_status: "completed",
    exclude_document_type: "进货订单",
  }
  await expect(listInventorySelectionIds(filters)).resolves.toEqual({
    ids: [1, 20, 100001],
    total: 3,
  })
  expect(fetchMock).toHaveBeenCalledWith(
    "/api/inventory/selection-ids",
    expect.objectContaining({
      method: "POST",
      cache: "no-store",
      credentials: "include",
      body: JSON.stringify(filters),
    })
  )
})

test("deletes the confirmed cross-page snapshot without fetching again", async () => {
  const fetchMock = vi
    .spyOn(global, "fetch")
    .mockResolvedValue(
      new Response(JSON.stringify({ deleted: 3, message: "已移入回收站" }))
    )
  await batchDeleteInventory([1, 20, 100001])
  expect(fetchMock).toHaveBeenCalledExactlyOnceWith(
    "/api/inventory/batch-delete",
    expect.objectContaining({
      method: "POST",
      body: JSON.stringify({ ids: [1, 20, 100001] }),
    })
  )
})

test("propagates failed selection requests without reporting successful selection", async () => {
  vi.spyOn(global, "fetch").mockResolvedValue(
    new Response(JSON.stringify({ detail: "权限不足" }), { status: 403 })
  )
  await expect(listInventorySelectionIds({})).rejects.toMatchObject({
    status: 403,
    message: "权限不足",
  })
})

test("preserves multiple typed handler names in list, export and selection requests", async () => {
  const fetchMock = vi.spyOn(global, "fetch").mockImplementation(async () => new Response(JSON.stringify({ items: [], ids: [], total: 0 })))
  const handler = "张三，李四;Alice Smith\n王五"
  await listInventory({ handler, page: 2, pageSize: 10 })
  const listUrl = new URL(String(fetchMock.mock.calls[0][0]), "http://localhost")
  expect(listUrl.searchParams.get("handler")).toBe(handler)
  expect(new URL(buildInventoryExportUrl({ handler }), "http://localhost").searchParams.get("handler")).toBe(handler)

  await listInventorySelectionIds({ handler })
  expect(fetchMock).toHaveBeenLastCalledWith("/api/inventory/selection-ids", expect.objectContaining({
    body: JSON.stringify({ handler }),
    cache: "no-store",
  }))
})
