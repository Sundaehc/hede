import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { afterEach, beforeEach, expect, test, vi } from "vitest"

import { ProductGoodsPage } from "@/components/product-goods/product-goods-page"
import type { ProductGoodsFilter } from "@/lib/api"

const { listMock, optionsMock } = vi.hoisted(() => ({ listMock: vi.fn(), optionsMock: vi.fn() }))
vi.mock("@/components/auth/auth-provider", () => ({ useAuth: () => ({ hasPermission: () => false }) }))
vi.mock("@/components/operation-log-dialog", () => ({ OperationLogDialog: () => null }))
vi.mock("@/lib/api", async () => ({
  ...(await vi.importActual<typeof import("@/lib/api")>("@/lib/api")),
  listProductGoods: listMock,
  listProductGoodsFilterOptions: optionsMock,
}))

const options = ["烟筒靴", "雪地靴", "运动鞋", ""].map((value) => ({ value, count: 1 }))
let caseNumber = 0
function remember(field: string, value: unknown) {
  window.sessionStorage.setItem(`hede:session-query:v1:anonymous:product-goods:${field}`, JSON.stringify(value))
}
function savedFilters(): ProductGoodsFilter[] {
  return JSON.parse(window.sessionStorage.getItem("hede:session-query:v1:anonymous:product-goods:filters") ?? "[]")
}

beforeEach(() => {
  vi.resetAllMocks()
  window.history.replaceState({}, "", "/product-goods")
  remember("query", `GOODS-FILTER-${++caseNumber}`)
  listMock.mockResolvedValue({
    items: [], total: 0, page: 1, page_size: 50, daily_dates: [], annual_sales_columns: [],
    monthly_sales_columns: [], size_columns: [], platform_columns: [], snapshot_date: null, snapshot_dates: [],
  })
  optionsMock.mockImplementation(async ({ field }: { field: string }) => ({ field, total: options.length, truncated: false, options }))
})
afterEach(cleanup)

async function openFilter() {
  const user = userEvent.setup()
  render(<ProductGoodsPage />)
  await user.click(await screen.findByRole("button", { name: "筛选货号" }))
  const dialog = within(screen.getByRole("dialog", { name: "货号筛选" }))
  await waitFor(() => expect(dialog.getByRole("button", { name: "确定" })).toBeEnabled())
  return { user, dialog, search: dialog.getByRole("textbox", { name: "搜索货号筛选项" }) }
}

test("searched selection excludes hidden values and preserves other columns", async () => {
  const other: ProductGoodsFilter = { field: "year", operator: "in", values: ["2026"] }
  remember("filters", [other])
  const { user, dialog, search } = await openFilter()
  await user.type(search, " 靴 ")
  expect(dialog.getByText("已选 2")).toBeInTheDocument()
  await user.click(dialog.getByLabelText("选择雪地靴"))
  await user.click(dialog.getByRole("button", { name: "确定" }))
  expect(savedFilters()).toEqual([other, { field: "goods_code", operator: "in", values: ["烟筒靴"] }])
})

test("select-all includes every match beyond the 300 rendered choices", async () => {
  const manyOptions = Array.from({ length: 350 }, (_, index) => ({ value: `靴-${index}`, count: 1 }))
  optionsMock.mockResolvedValue({ field: "goods_code", total: 350, truncated: false, options: manyOptions })
  const { user, dialog, search } = await openFilter()
  expect(dialog.getAllByRole("checkbox")).toHaveLength(301)
  await user.type(search, "靴")
  await user.click(dialog.getByLabelText("全选/反选"))
  expect(dialog.getByText("已选 0")).toBeInTheDocument()
  await user.click(dialog.getByLabelText("全选/反选"))
  expect(dialog.getByText("已选 350")).toBeInTheDocument()
  await user.type(search, "{Enter}")
  expect(savedFilters()).toEqual([{ field: "goods_code", operator: "in", values: manyOptions.map((item) => item.value) }])
})

test("a search without matches submits an empty selection", async () => {
  const { user, dialog, search } = await openFilter()
  await user.type(search, "不存在")
  await user.click(dialog.getByRole("button", { name: "确定" }))
  expect(savedFilters()).toEqual([{ field: "goods_code", operator: "in", values: [] }])
})

test("cancel preserves filters and clearing the column removes only that column", async () => {
  const original: ProductGoodsFilter = { field: "goods_code", operator: "not_in", values: ["运动鞋"] }
  remember("filters", [original])
  const { user, dialog, search } = await openFilter()
  await user.type(search, "靴")
  await user.click(dialog.getByRole("button", { name: "取消" }))
  expect(savedFilters()).toEqual([original])
  await user.click(screen.getByRole("button", { name: "筛选货号" }))
  const reopened = within(screen.getByRole("dialog", { name: "货号筛选" }))
  await user.click(reopened.getByRole("button", { name: "清除此列" }))
  expect(savedFilters()).toEqual([])
})

test("snapshot context is passed to options and Chinese composition does not submit", async () => {
  remember("snapshotDate", "2026-11-01")
  const { user, dialog, search } = await openFilter()
  expect(optionsMock).toHaveBeenCalledWith(expect.objectContaining({ snapshotDate: "2026-11-01" }))
  await user.type(search, "靴")
  fireEvent.keyDown(search, { key: "Enter", isComposing: true })
  expect(dialog.getByRole("button", { name: "确定" })).toBeInTheDocument()
  expect(savedFilters()).toEqual([])
  fireEvent.keyDown(search, { key: "Enter", isComposing: false })
  await waitFor(() => expect(listMock).toHaveBeenCalledWith(expect.objectContaining({
    snapshotDate: "2026-11-01", page: 1,
    filters: [{ field: "goods_code", operator: "in", values: ["烟筒靴", "雪地靴"] }],
  })))
})

test("truncated search results stay an explicit inclusion even when all loaded values match", async () => {
  optionsMock.mockResolvedValue({ field: "goods_code", total: 12000, truncated: true, options: options.slice(0, 2) })
  const { user, dialog, search } = await openFilter()
  expect(dialog.getByText(/仅加载前 10000 项/)).toBeInTheDocument()
  await user.type(search, "靴")
  await user.click(dialog.getByRole("button", { name: "确定" }))
  expect(savedFilters()).toEqual([{ field: "goods_code", operator: "in", values: ["烟筒靴", "雪地靴"] }])
})
