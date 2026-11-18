import { cleanup, render, screen, within } from "@testing-library/react"
import { afterEach, describe, expect, it, vi } from "vitest"

import { ProductDetailDialog } from "@/components/product-admin/product-detail-dialog"
import { ProductTable } from "@/components/product-admin/product-table"
import { ALL_PRODUCT_FIELDS } from "@/lib/fields"
import type { ProductListItem } from "@/lib/types"

afterEach(cleanup)

const sampleItem = {
  ...Object.fromEntries(ALL_PRODUCT_FIELDS.map((field) => [field, null])),
  id: 1,
  brand: "smiley",
  sku: "MARKET-001",
  cost: "118.00",
  cost_price: "136.50",
  gender_costs: { female: "111.11", male: "222.22" },
  market_price: "299.90",
  factory_code: "FACTORY-001",
  barcode: "BARCODE-001",
  accessories: "鞋带",
} as ProductListItem

function table(item: ProductListItem, showCost: boolean) {
  return <ProductTable
    items={[item]}
    total={1}
    page={1}
    pageSize={20}
    pageSizes={[20]}
    isLoading={false}
    error={null}
    showCost={showCost}
    selectedKeys={new Set()}
    onToggleSelect={vi.fn()}
    onToggleSelectAll={vi.fn()}
    onPageChange={vi.fn()}
    onPageSizeChange={vi.fn()}
  />
}

describe.each(["smiley", "ni"])("%s archive market price display", (brand) => {
  it.each([false, true])("groups detail prices without duplicating market price, showCost=%s", (showCost) => {
    render(<ProductDetailDialog item={{ ...sampleItem, brand }} showCost={showCost} onClose={vi.fn()} />)
    const section = screen.getByRole("heading", { name: "物价信息" }).closest("section")!
    expect(within(section).getByText("市场价")).toBeInTheDocument()
    expect(within(section).getByText("299.90")).toBeInTheDocument()
    expect(screen.getAllByText("市场价")).toHaveLength(1)
    expect(screen.getAllByRole("heading", { level: 3 }).slice(0, 3).map((heading) => heading.textContent)).toEqual(["基础信息", "物价信息", "材质信息"])
    if (showCost) {
      expect(within(section).getByText("工厂出货价")).toBeInTheDocument()
      expect(within(section).getByText("成本价")).toBeInTheDocument()
      expect(within(section).getByText("女码 111.11 / 男码 222.22")).toBeInTheDocument()
      expect(within(section).getByText("136.50")).toBeInTheDocument()
    } else {
      expect(screen.getByRole("dialog")).not.toHaveTextContent(/工厂出货价|成本价|118\.00|136\.50|111\.11|222\.22/)
    }
    if (brand === "smiley") {
      const extras = screen.getByRole("heading", { name: "笑脸商品信息" }).closest("section")!
      expect(within(extras).queryByText("市场价")).not.toBeInTheDocument()
      for (const value of ["FACTORY-001", "BARCODE-001", "鞋带"]) expect(within(extras).getByText(value)).toBeInTheDocument()
    }
  })

  it.each([false, true])("groups card prices without duplicating market price, showCost=%s", (showCost) => {
    render(table({ ...sampleItem, brand }, showCost))
    const card = screen.getByRole("group", { name: "商品信息 MARKET-001" })
    const section = within(card).getByText("物价信息").parentElement!
    expect(within(section).getByText("市场价:")).toBeInTheDocument()
    expect(within(section).getByText("299.90")).toBeInTheDocument()
    expect(within(card).getAllByText("市场价:")).toHaveLength(1)
    if (showCost) {
      expect(within(section).getByText("工厂出货价:")).toBeInTheDocument()
      expect(within(section).getByText("成本价:")).toBeInTheDocument()
      expect(within(section).getByText("女码 111.11 / 男码 222.22")).toBeInTheDocument()
      expect(within(section).getByText("136.50")).toBeInTheDocument()
    } else {
      expect(card).not.toHaveTextContent(/工厂出货价|成本价|118\.00|136\.50|111\.11|222\.22/)
    }
    if (brand === "smiley") {
      for (const label of ["工厂代码:", "商品条码:", "配件:"]) expect(within(card).getByText(label)).toBeInTheDocument()
    }
  })

  it.each([0, "0.00", "99999999.99", null, undefined])("preserves zero and empty market prices without cost permission: %s", (market_price) => {
    const item = { ...sampleItem, brand, market_price }
    render(<>{table(item, false)}<ProductDetailDialog item={item} onClose={vi.fn()} /></>)
    const detailPriceSection = screen.getByRole("heading", { name: "物价信息" }).closest("section")!
    const cardPriceSection = screen.getByText("物价信息", { selector: "p" }).parentElement!
    for (const section of [detailPriceSection, cardPriceSection]) {
      expect(within(section).getByText(market_price == null ? "—" : String(market_price))).toBeInTheDocument()
      expect(section).not.toHaveTextContent(/工厂出货价|成本价|118\.00|136\.50|111\.11|222\.22/)
    }
  })
})

it.each(["cbanner_mens", "cbanner_womens", "supplier_brand_33aa8a0c3b6a", "yandou", "eblan", "ns", "custom"])("keeps market price out of details and cards for %s", (brand) => {
  const item = { ...sampleItem, brand }
  const { rerender } = render(<>{table(item, true)}<ProductDetailDialog item={item} showCost onClose={vi.fn()} /></>)
  expect(screen.queryByText(/市场价/)).not.toBeInTheDocument()
  expect(screen.queryByText("299.90")).not.toBeInTheDocument()
  expect(screen.getAllByText("物价信息")).toHaveLength(2)
  rerender(<>{table(item, false)}<ProductDetailDialog item={item} onClose={vi.fn()} /></>)
  expect(screen.queryByText(/市场价|物价信息|工厂出货价|成本价|111\.11|222\.22/)).not.toBeInTheDocument()
})
