import { afterEach, expect, test, vi } from "vitest"
import { listInventoryPrintLabels } from "@/lib/api"

afterEach(() => vi.restoreAllMocks())

test("loads current document print labels without caching and forwards cancellation", async () => {
  const controller = new AbortController()
  const fetchMock = vi.spyOn(global, "fetch").mockImplementation((_input, init) => new Promise((_resolve, reject) => {
    init?.signal?.addEventListener("abort", () => reject(new DOMException("Aborted", "AbortError")), { once: true })
  }))
  const result = listInventoryPrintLabels(77, controller.signal)
  expect(fetchMock).toHaveBeenCalledWith("/api/inventory/77/print-labels", expect.objectContaining({
    signal: controller.signal, cache: "no-store", credentials: "include",
  }))
  controller.abort()
  await expect(result).rejects.toMatchObject({ name: "AbortError" })
})
