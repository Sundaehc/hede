import { expect, test } from "vitest"

import { PRODUCT_ARCHIVE_BRANDS, resolveProductArchiveBrands } from "@/lib/brands"

test("keeps the shared Eblan product archive label independent of supplier gender labels", () => {
  const managedBrands = [{ code: "eblan", name: "伊伴男鞋" }]

  const brands = resolveProductArchiveBrands(managedBrands)

  expect(brands.find((brand) => brand.key === "eblan")).toEqual({
    key: "eblan",
    label: "伊伴",
  })
  expect(brands.some((brand) => brand.label === "伊伴男鞋")).toBe(false)
  expect(managedBrands).toEqual([{ code: "eblan", name: "伊伴男鞋" }])
})

test("preserves configured names, order and deduplication for other archive brands", () => {
  const brands = resolveProductArchiveBrands([
    { code: "supplier_brand_ns", name: "NS" },
    { code: "cbanner_mens", name: "千百度男鞋新名称" },
    { code: "eblan", name: "伊伴男鞋" },
    { code: "eblan", name: "重复名称" },
  ])

  expect(brands.slice(0, 4)).toEqual([
    { key: "all", label: "总览" },
    { key: "supplier_brand_ns", label: "NS" },
    { key: "cbanner_mens", label: "千百度男鞋新名称" },
    { key: "eblan", label: "伊伴" },
  ])
  expect(brands.filter((brand) => brand.key === "eblan")).toHaveLength(1)
  expect(brands.find((brand) => brand.key === "cbanner_womens")).toEqual({
    key: "cbanner_womens",
    label: "千百度女鞋",
  })
})

test("retains the original archive labels before configured brands load", () => {
  expect(resolveProductArchiveBrands([])).toEqual(PRODUCT_ARCHIVE_BRANDS)
})
