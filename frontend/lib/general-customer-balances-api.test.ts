import { afterEach, expect, test, vi } from "vitest"

import {
  getGeneralCustomerBalances,
  listGeneralCustomerBrands,
  listGeneralCustomerShops,
  listGeneralCustomerUnits,
} from "./api"

afterEach(() => vi.restoreAllMocks())

test.each([
  [{ dateStart: "2026-11-01", dateEnd: "2026-11-19" }, { date_start: "2026-11-01", date_end: "2026-11-19" }],
  [{ dateEnd: "2026-11-19" }, { date_end: "2026-11-19" }],
  [{ dateStart: "2026-11-01" }, { date_start: "2026-11-01" }],
  [{ dateStart: "", dateEnd: "" }, {}],
])("balance queries send only selected dates: %j", async (params, expected) => {
  const response = { items: [{ name: "零余额店", ending_balance: "0" }] }
  const fetchMock = vi.spyOn(global, "fetch").mockResolvedValue(new Response(JSON.stringify(response)))
  const controller = new AbortController()
  await expect(getGeneralCustomerBalances(params, controller.signal)).resolves.toEqual(response)
  const [input, options] = fetchMock.mock.calls[0]
  const url = new URL(String(input), "http://localhost")
  expect(url.pathname).toBe("/api/inventory/general-customer-balances")
  expect(Object.fromEntries(url.searchParams)).toEqual(expected)
  expect(options).toMatchObject({ signal: controller.signal, cache: "no-store", credentials: "include" })
})

test.each([
  [listGeneralCustomerBrands, "general-customer-brands"],
  [listGeneralCustomerShops, "general-customer-shops"],
  [listGeneralCustomerUnits, "general-customer-units"],
] as const)("customer archive requests forward cancellation and bypass old cached data: %s", async (list, path) => {
  const fetchMock = vi.spyOn(global, "fetch").mockResolvedValue(new Response(JSON.stringify({ items: [] })))
  const controller = new AbortController()
  await list(controller.signal)
  expect(fetchMock).toHaveBeenCalledWith(`/api/inventory/${path}`, expect.objectContaining({ signal: controller.signal, cache: "no-store" }))
})

test("balance request errors propagate instead of producing a zero balance", async () => {
  vi.spyOn(global, "fetch").mockResolvedValue(new Response(JSON.stringify({ detail: "余额读取失败" }), { status: 500 }))
  await expect(getGeneralCustomerBalances({})).rejects.toThrow("余额读取失败")
})
