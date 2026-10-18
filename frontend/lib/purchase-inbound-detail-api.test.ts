import { afterEach, expect, test, vi } from "vitest"

import {
  buildPurchaseInboundDetailExportUrl,
  listPurchaseInboundDetails,
} from "@/lib/api"

afterEach(() => vi.restoreAllMocks())

test("passes every selected brand to the inbound detail list and export", async () => {
  const fetchMock = vi
    .spyOn(global, "fetch")
    .mockResolvedValue(new Response(JSON.stringify({ items: [], total: 0 })))
  const filters = {
    brands: ["cbanner_mens", "yandou"],
    warehouse: ["总仓"],
    supplier: "供应商",
    product_code: "SKU",
  }
  await listPurchaseInboundDetails({ ...filters, page: 2, pageSize: 50 })
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
