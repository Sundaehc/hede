import { afterEach, expect, test, vi } from "vitest"
import {
  downloadCounterpartyLedger,
  getSupplier,
  listCounterpartyLedger,
} from "./api"

afterEach(() => vi.restoreAllMocks())

test("ledger requests send the submitted dates, selected sorting and cancellation signal", async () => {
  const fetchMock = vi
    .spyOn(global, "fetch")
    .mockResolvedValue(new Response(JSON.stringify({ items: [] })))
  const controller = new AbortController()
  await listCounterpartyLedger(
    {
      counterpartyType: "supplier",
      name: "测试 & 供应商",
      dateStart: "2025-01-01",
      dateEnd: "2026-08-31",
      sortBy: "increase_amount",
      sortDirection: "desc",
    },
    controller.signal
  )
  const [input, options] = fetchMock.mock.calls[0]
  const url = new URL(String(input), "http://localhost")
  expect(url.pathname).toBe("/api/inventory/counterparty-ledger")
  expect(Object.fromEntries(url.searchParams)).toEqual({
    counterparty_type: "supplier",
    name: "测试 & 供应商",
    date_start: "2025-01-01",
    date_end: "2026-08-31",
    sort_by: "increase_amount",
    sort_direction: "desc",
  })
  expect(options).toMatchObject({
    cache: "no-store",
    credentials: "include",
    signal: controller.signal,
  })
})

test.each(["supplier", "customer"] as const)(
  "exports %s using the correct endpoint and selected order",
  async (counterpartyType) => {
    vi.useFakeTimers({ toFake: ["setTimeout", "clearTimeout"] })
    const fetchMock = vi
      .spyOn(global, "fetch")
      .mockResolvedValue(
        new Response("test-xlsx", {
          headers: {
            "content-disposition": "attachment; filename=ledger.xlsx",
          },
        })
      )
    const create = vi.fn().mockReturnValue("blob:test")
    vi.stubGlobal(
      "URL",
      class extends URL {
        static createObjectURL = create
        static revokeObjectURL = vi.fn()
      }
    )
    const click = vi
      .spyOn(HTMLAnchorElement.prototype, "click")
      .mockImplementation(() => {})
    try {
      const result = await downloadCounterpartyLedger(counterpartyType, {
        name: "测试单位",
        dateStart: "2025-01-01",
        dateEnd: "2026-08-31",
        sortBy: "balance",
        sortDirection: "asc",
      })
      const url = new URL(
        String(fetchMock.mock.calls[0][0]),
        "http://localhost"
      )
      expect(url.pathname).toBe(
        `/api/inventory/${counterpartyType === "supplier" ? "supplier-ledger" : "counterparty-ledger"}/export`
      )
      expect(url.searchParams.get("sort_by")).toBe("balance")
      expect(url.searchParams.get("sort_direction")).toBe("asc")
      expect(url.searchParams.get("date_start")).toBe("2025-01-01")
      expect(result?.filename).toBe("ledger.xlsx")
      expect(click).toHaveBeenCalledOnce()
    } finally {
      vi.runAllTimers()
      vi.useRealTimers()
      vi.unstubAllGlobals()
    }
  }
)

test("supplier lookup uses its stable ID and reads the latest record", async () => {
  const fetchMock = vi
    .spyOn(global, "fetch")
    .mockResolvedValue(new Response(JSON.stringify({ item: { id: 42 } })))
  const controller = new AbortController()
  await expect(getSupplier(42, controller.signal)).resolves.toEqual({
    item: { id: 42 },
  })
  expect(fetchMock).toHaveBeenCalledWith(
    "/api/suppliers/42",
    expect.objectContaining({ signal: controller.signal, cache: "no-store" })
  )
})
