import { afterEach, expect, test, vi } from "vitest"
import { buildProductExportUrl, getProductSearchOptions, listProducts, listProductSelectionIds } from "@/lib/api"
import { productAttributeFilter, productAttributeSummary, productAttributeValues } from "@/lib/product-attribute-filters"

afterEach(() => vi.restoreAllMocks())

test("list, selection and export serialize the same product attributes", async () => {
  const fetchMock = vi.spyOn(global, "fetch").mockImplementation(async () => new Response(JSON.stringify({ items: [], total: 0 }), {
    headers: { "Content-Type": "application/json" },
  }))
  const filters = { brand: "all", year: "2026", season: "秋", productName: "皮鞋" }
  await listProducts({ ...filters, page: 2, pageSize: 50 })
  const url = new URL(String(fetchMock.mock.calls[0][0]), "http://localhost")
  expect(Object.fromEntries(url.searchParams)).toEqual({ brand: "all", year: "2026", season: "秋", product_name: "皮鞋", page: "2", page_size: "50" })
  await listProductSelectionIds(filters)
  expect(JSON.parse(String(fetchMock.mock.calls[1][1]?.body))).toEqual({ brand: "all", year: "2026", season: "秋", product_name: "皮鞋" })
  const exportUrl = new URL(buildProductExportUrl("all", undefined, undefined, undefined, undefined, "2026", undefined, undefined, { season: " 秋 ", productName: " 皮鞋 " }), "http://localhost")
  expect(Object.fromEntries(exportUrl.searchParams)).toEqual({ brand: "all", year: "2026", season: "秋", product_name: "皮鞋" })
})

test("attribute candidates are requested for the selected brand without caching", async () => {
  const options = { years: ["26年秋季款"], seasons: ["秋冬"], product_names: ["短靴"] }
  const fetchMock = vi.spyOn(global, "fetch").mockResolvedValue(new Response(JSON.stringify(options), { headers: { "Content-Type": "application/json" } }))
  expect(await getProductSearchOptions("all")).toEqual(options)
  expect(fetchMock).toHaveBeenCalledWith("/api/products/all/search-options", expect.objectContaining({ cache: "no-store" }))
})

test("multiple values serialize identically for listing, selection and export without splitting punctuation", async () => {
  const fetchMock = vi.spyOn(global, "fetch").mockImplementation(async () => new Response(JSON.stringify({ items: [], total: 0 }), { headers: { "Content-Type": "application/json" } }))
  const filters = { brand: "all", year: productAttributeFilter(["2025", "2026"]), season: productAttributeFilter(["春秋", "秋冬"]), productName: productAttributeFilter(["鞋,靴", "鞋、凉鞋"]) }
  await listProducts({ ...filters, page: 1, pageSize: 20 })
  const listUrl = new URL(String(fetchMock.mock.calls[0][0]), "http://localhost")
  await listProductSelectionIds(filters)
  const selection = JSON.parse(String(fetchMock.mock.calls[1][1]?.body))
  const exportUrl = new URL(buildProductExportUrl("all", undefined, undefined, undefined, undefined, filters.year, undefined, undefined, filters), "http://localhost")
  for (const field of ["year", "season", "product_name"]) {
    expect(listUrl.searchParams.get(field)).toBe(selection[field])
    expect(exportUrl.searchParams.get(field)).toBe(selection[field])
  }
  expect(productAttributeValues(filters.productName)).toEqual(["鞋,靴", "鞋、凉鞋"])
})

test("normalization preserves single values, removes duplicates and formats multi-value summaries", () => {
  expect(productAttributeFilter([" 2026 ", "2026", ""], "2025")).toBe('["2026","2025"]')
  expect(productAttributeFilter(["半拖鞋"])).toBe("半拖鞋")
  expect(productAttributeValues("2026")).toEqual(["2026"])
  expect(productAttributeValues("[特殊鞋]")).toEqual(["[特殊鞋]"])
  expect(productAttributeSummary(productAttributeFilter(["2026", "2025"]))).toBe("2026、2025")
  expect(productAttributeFilter([])).toBe("")
})
