import { afterEach, expect, test, vi } from "vitest"
import { downloadSelectedDetailExport } from "@/lib/api"

afterEach(() => { vi.restoreAllMocks(); vi.unstubAllGlobals(); vi.useRealTimers() })

test.each([
  ["orders", "/api/purchase-order-details/export"],
  ["inbound", "/api/inventory-reports/purchase-inbound-details/export"],
  ["sales", "/api/inventory-reports/sales-details/export"],
] as const)("%s posts large cross-page selections as JSON and uses the server filename", async (mode, path) => {
  vi.useFakeTimers()
  const fetchMock = vi.spyOn(global, "fetch").mockResolvedValue(new Response("xlsx", { headers: {
    "Content-Disposition": "attachment; filename*=UTF-8''" + encodeURIComponent("所选明细.xlsx"),
  } }))
  const create = vi.fn(() => "blob:selected")
  vi.stubGlobal("URL", class extends URL { static createObjectURL = create; static revokeObjectURL = vi.fn() })
  const click = vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(function (this: HTMLAnchorElement) {
    expect(this.download).toBe("所选明细.xlsx")
  })
  const rows = Array.from({ length: 20_000 }, (_, index) => String(index + 1))
  const controller = new AbortController()
  await downloadSelectedDetailExport(mode, { brands: ["ns"], product_code: "001", sort_direction: "desc" }, rows, controller.signal)
  const [raw, init] = fetchMock.mock.calls[0]
  const url = new URL(String(raw), "http://local")
  expect(url.pathname).toBe(path)
  expect(Object.fromEntries(url.searchParams)).toEqual({ brands: "ns", product_code: "001", sort_direction: "desc" })
  expect(init).toMatchObject({ method: "POST", credentials: "include", signal: controller.signal, cache: "no-store" })
  expect(JSON.parse(String(init?.body))).toEqual({ rows })
  expect(click).toHaveBeenCalledOnce()
  vi.runAllTimers()
})

test("failed, cancelled and empty selected exports do not download", async () => {
  const click = vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(() => undefined)
  const fetchMock = vi.spyOn(global, "fetch").mockResolvedValueOnce(new Response(JSON.stringify({ detail: "所选明细已变更" }), { status: 409 }))
  await expect(downloadSelectedDetailExport("inbound", {}, ["1"])).rejects.toMatchObject({ status: 409, message: "所选明细已变更" })
  fetchMock.mockResolvedValueOnce(new Response("xlsx"))
  const controller = new AbortController(); controller.abort()
  await expect(downloadSelectedDetailExport("sales", { display_mode: "barcode" }, ["1:0:035"], controller.signal)).rejects.toMatchObject({ name: "AbortError" })
  await expect(downloadSelectedDetailExport("orders", {}, [])).rejects.toThrow("请先选择")
  expect(fetchMock).toHaveBeenCalledTimes(2)
  expect(click).not.toHaveBeenCalled()
})
