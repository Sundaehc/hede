import { afterEach, expect, test, vi } from "vitest"

import {
  buildPurchaseInboundDetailExportUrl,
  listPurchaseInboundDetails,
} from "@/lib/api"

afterEach(() => vi.restoreAllMocks())

test.each(["asc", "desc"] as const)("passes brands and %s date ordering to the inbound detail list and export", async sort_direction => {
  const fetchMock = vi
    .spyOn(global, "fetch")
    .mockResolvedValue(new Response(JSON.stringify({ items: [], total: 0 })))
  const filters = {
    brands: ["cbanner_mens", "yandou"],
    warehouse: ["总仓"],
    supplier: "供应商",
    product_code: "SKU",
    sort_direction,
    display_mode: "barcode" as const,
  }
  const controller = new AbortController()
  await listPurchaseInboundDetails({ ...filters, page: 2, pageSize: 50 }, controller.signal)
  expect(fetchMock.mock.calls[0][1]?.signal).toBe(controller.signal)
  const listUrl = new URL(
    String(fetchMock.mock.calls[0][0]),
    "http://localhost"
  )
  const exportUrl = new URL(
    buildPurchaseInboundDetailExportUrl(filters),
    "http://localhost"
  )
  for (const url of [listUrl, exportUrl]) {
    expect(url.searchParams.getAll("brands")).toEqual(filters.brands)
    expect(url.searchParams.getAll("warehouse")).toEqual(filters.warehouse)
    expect(url.searchParams.get("supplier")).toBe("供应商")
    expect(url.searchParams.get("product_code")).toBe("SKU")
    expect(url.searchParams.get("sort_direction")).toBe(sort_direction)
    expect(url.searchParams.get("display_mode")).toBe("barcode")
  }
  expect(listUrl.searchParams.get("page")).toBe("2")
  expect(exportUrl.searchParams.has("page")).toBe(false)
})

test("empty brand selections preserve the unfiltered list and export", async () => {
  const fetchMock = vi
    .spyOn(global, "fetch")
    .mockResolvedValue(new Response(JSON.stringify({ items: [], total: 0 })))
  await listPurchaseInboundDetails({ brands: [], page: 1, pageSize: 50 })
  expect(
    new URL(
      String(fetchMock.mock.calls[0][0]),
      "http://localhost"
    ).searchParams.has("brands")
  ).toBe(false)
  expect(
    new URL(
      buildPurchaseInboundDetailExportUrl({ brands: [""] }),
      "http://localhost"
    ).searchParams.has("brands")
  ).toBe(false)
})
