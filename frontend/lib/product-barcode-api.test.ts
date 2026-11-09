import { afterEach, expect, test, vi } from "vitest"
import { downloadProductBarcodes, listProductBarcodes } from "@/lib/api"

afterEach(() => { vi.restoreAllMocks(); vi.unstubAllGlobals() })

test("queries generated barcodes with brand and pagination, no cache and cancellation", async () => {
  const fetchMock = vi.spyOn(global, "fetch").mockResolvedValue(new Response(JSON.stringify({ items: [], total: 0 })))
  const controller = new AbortController()
  await listProductBarcodes({ brand: "custom", query: "货号,ABC", page: 2, pageSize: 50 }, controller.signal)
  const [url, init] = fetchMock.mock.calls[0]
  const parsed = new URL(String(url), "http://local")
  expect(parsed.pathname).toBe("/api/products/barcodes")
  expect(Object.fromEntries(parsed.searchParams)).toEqual({ brand: "custom", query: "货号,ABC", page: "2", page_size: "50" })
  expect(init).toMatchObject({ credentials: "include", cache: "no-store", signal: controller.signal })
})

test("downloads all query rows with credentials and preserves the server filename", async () => {
  vi.useFakeTimers()
  const fetchMock = vi.spyOn(global, "fetch").mockResolvedValue(new Response("xlsx", { headers: {
    "Content-Disposition": "attachment; filename*=UTF-8''" + encodeURIComponent("条码搜索.xlsx"),
  } }))
  const create = vi.fn(() => "blob:barcodes")
  vi.stubGlobal("URL", class extends URL {
    static createObjectURL = create
    static revokeObjectURL = vi.fn()
  })
  const click = vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(function (this: HTMLAnchorElement) {
    expect(this.download).toBe("条码搜索.xlsx")
  })
  const controller = new AbortController()
  expect(await downloadProductBarcodes({ brand: "all", query: "001,ABC" }, controller.signal)).toEqual({ filename: "条码搜索.xlsx", size: 4 })
  const [url, init] = fetchMock.mock.calls[0]
  const parsed = new URL(String(url), "http://local")
  expect(parsed.pathname).toBe("/api/products/barcodes/export")
  expect(Object.fromEntries(parsed.searchParams)).toEqual({ brand: "all", query: "001,ABC" })
  expect(init).toMatchObject({ credentials: "include", cache: "no-store", signal: controller.signal })
  expect(click).toHaveBeenCalledOnce()
  expect(create).toHaveBeenCalledOnce()
  vi.runAllTimers()
  vi.useRealTimers()
})

test("surfaces export errors and avoids downloads after cancellation", async () => {
  vi.spyOn(global, "fetch").mockResolvedValueOnce(new Response(JSON.stringify({ detail: "权限不足" }), { status: 403 }))
  await expect(downloadProductBarcodes({ brand: "all", query: "ABC" })).rejects.toMatchObject({ status: 403, message: "权限不足" })
  const controller = new AbortController()
  vi.mocked(fetch).mockResolvedValueOnce(new Response("xlsx"))
  controller.abort()
  await expect(downloadProductBarcodes({ brand: "all", query: "ABC" }, controller.signal)).rejects.toMatchObject({ name: "AbortError" })
})
