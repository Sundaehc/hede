import { cleanup, render, screen, waitFor } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { afterEach, beforeEach, expect, test, vi } from "vitest"

import { FineTablePage } from "@/components/fine-table/fine-table-page"
import { ProductGoodsPage } from "@/components/product-goods/product-goods-page"

const { mockFineTable, mockProductGoods } = vi.hoisted(() => ({
  mockFineTable: vi.fn(), mockProductGoods: vi.fn(),
}))

vi.mock("@/components/auth/auth-provider", () => ({ useAuth: () => ({ hasPermission: () => false }) }))
vi.mock("@/components/operation-log-dialog", () => ({ OperationLogDialog: () => null }))
vi.mock("@/components/product-goods/product-goods-detail-drawer", () => ({ ProductGoodsDetailDrawer: () => null }))
vi.mock("@/lib/api", async () => ({
  ...(await vi.importActual<typeof import("@/lib/api")>("@/lib/api")),
  listFineTable: mockFineTable,
  listProductGoods: mockProductGoods,
}))

beforeEach(() => {
  vi.clearAllMocks()
  window.history.replaceState(null, "", "/")
  mockFineTable.mockResolvedValue({ items: [], total: 200, page: 1, page_size: 50, latest_order_date: "2026-10-08" })
  mockProductGoods.mockResolvedValue({
    items: [], total: 200, page: 1, page_size: 50, daily_dates: [],
    annual_sales_columns: [], monthly_sales_columns: [], size_columns: [], platform_columns: [],
    snapshot_date: null, snapshot_dates: [],
  })
})

afterEach(cleanup)

function remember(page: string, field: string, value: unknown) {
  window.sessionStorage.setItem("hede:session-query:v1:anonymous:" + page + ":" + field, JSON.stringify(value))
}

test("fine-table restores submitted and draft queries, prefixes, filters and page", async () => {
  remember("fine-table", "query", "FT-SUBMITTED")
  remember("fine-table", "queryInput", "FT-DRAFT")
  remember("fine-table", "skuPrefix", "FT-PREFIX")
  remember("fine-table", "skuPrefixInput", "FT-PREFIX-DRAFT")
  remember("fine-table", "brand", "cbanner_womens")
  remember("fine-table", "page", 3)
  const filters = [{ field: "season", operator: "in", values: ["春"] }]
  remember("fine-table", "filters", filters)
  const first = render(<FineTablePage />)
  expect(screen.getByLabelText("搜索货号、原始货号")).toHaveValue("FT-DRAFT")
  expect(screen.getByLabelText("货号前缀筛选")).toHaveValue("FT-PREFIX-DRAFT")
  await waitFor(() => expect(mockFineTable).toHaveBeenCalledWith(expect.objectContaining({
    brand: "cbanner_womens", query: "FT-SUBMITTED", skuPrefix: "FT-PREFIX", page: 3, filters,
  })))
  first.unmount()
  render(<FineTablePage />)
  expect(screen.getByLabelText("搜索货号、原始货号")).toHaveValue("FT-DRAFT")
  expect(screen.getByLabelText("货号前缀筛选")).toHaveValue("FT-PREFIX-DRAFT")
})

test("product-goods requests the saved page rather than clamping to unloaded totals", async () => {
  remember("product-goods", "query", "GOODS-SUBMITTED")
  remember("product-goods", "queryInput", "GOODS-DRAFT")
  remember("product-goods", "page", 3)
  const filters = [{ field: "season", operator: "in", values: ["秋"] }]
  remember("product-goods", "filters", filters)
  const first = render(<ProductGoodsPage />)
  expect(screen.getByPlaceholderText("货号、款号、工厂货号、颜色")).toHaveValue("GOODS-DRAFT")
  await waitFor(() => expect(mockProductGoods).toHaveBeenCalledWith(expect.objectContaining({ query: "GOODS-SUBMITTED", page: 3, filters })))
  expect(mockProductGoods.mock.calls[0][0].page).toBe(3)
  first.unmount()
  const restored = render(<ProductGoodsPage />)
  expect(screen.getByPlaceholderText("货号、款号、工厂货号、颜色")).toHaveValue("GOODS-DRAFT")
  const user = userEvent.setup()
  await user.click(screen.getByRole("button", { name: "清除" }))
  await waitFor(() => expect(mockProductGoods).toHaveBeenCalledWith(expect.objectContaining({ query: undefined, filters: undefined, page: 1 })))
  restored.unmount()
  render(<ProductGoodsPage />)
  expect(screen.getByPlaceholderText("货号、款号、工厂货号、颜色")).toHaveValue("")
})
