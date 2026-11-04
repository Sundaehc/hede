import { cleanup, render, screen, waitFor, within } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { afterEach, beforeEach, expect, test, vi } from "vitest"

import { FineTablePage } from "@/components/fine-table/fine-table-page"
import type { FineTableFilter } from "@/lib/api"

const { listMock, optionsMock, snapshotMock } = vi.hoisted(() => ({
  listMock: vi.fn(), optionsMock: vi.fn(), snapshotMock: vi.fn(),
}))

vi.mock("@/components/auth/auth-provider", () => ({ useAuth: () => ({ hasPermission: () => false }) }))
vi.mock("@/components/operation-log-dialog", () => ({ OperationLogDialog: () => null }))
vi.mock("@/lib/api", async () => ({
  ...(await vi.importActual<typeof import("@/lib/api")>("@/lib/api")),
  listFineTable: listMock,
  listFineTableFilterOptions: optionsMock,
  getFineTableSnapshotByDate: snapshotMock,
}))

const options = ["烟筒靴", "雪地靴", "棉靴", "短靴", "运动鞋", ""].map((value) => ({ value, count: 1 }))
const bootValues = options.filter((item) => item.value.includes("靴")).map((item) => item.value)
let caseNumber = 0

function remember(field: string, value: unknown) {
  window.sessionStorage.setItem(`hede:session-query:v1:anonymous:fine-table:${field}`, JSON.stringify(value))
}

function savedFilters(): FineTableFilter[] {
  return JSON.parse(window.sessionStorage.getItem("hede:session-query:v1:anonymous:fine-table:filters") ?? "[]")
}

beforeEach(() => {
  vi.resetAllMocks()
  window.history.replaceState({}, "", "/fine-table")
  // Keep this test's page and option caches independent of previous cases.
  remember("query", `FILTER-CASE-${++caseNumber}`)
  listMock.mockResolvedValue({ items: [], total: 0, page: 1, page_size: 50, latest_order_date: null })
  optionsMock.mockImplementation(async ({ field }: { field: string }) => ({ field, total: options.length, truncated: false, options }))
  snapshotMock.mockResolvedValue({
    items: [], total: 0, page: 1, page_size: 50,
    snapshot: { snapshot_date: "2026-11-01", latest_order_date: null },
  })
})

afterEach(cleanup)

async function openFilter(active = false) {
  const user = userEvent.setup()
  render(<FineTablePage />)
  await waitFor(() => expect(screen.getByRole("button", { name: active ? "主款式已筛选" : "筛选主款式" })).toBeEnabled())
  await user.click(screen.getByRole("button", { name: active ? "主款式已筛选" : "筛选主款式" }))
  const dialog = within(screen.getByRole("dialog", { name: "主款式筛选" }))
  await waitFor(() => expect(dialog.getByRole("button", { name: "确定" })).toBeEnabled())
  return { user, dialog, search: dialog.getByRole("textbox", { name: "搜索主款式筛选项" }) }
}

test("search and confirm applies only checked matching values, resets the page and preserves other columns", async () => {
  const otherFilter: FineTableFilter = { field: "year", operator: "in", values: ["2026"] }
  remember("filters", [otherFilter])
  remember("page", 3)
  const { user, dialog, search } = await openFilter()
  const initialCalls = listMock.mock.calls.length
  await user.type(search, " 靴 ")
  expect(dialog.getByText("已选 4 / 6")).toBeInTheDocument()
  expect(dialog.queryByLabelText("选择运动鞋")).not.toBeInTheDocument()
  expect(listMock).toHaveBeenCalledTimes(initialCalls)
  await user.click(dialog.getByRole("button", { name: "确定" }))
  const filters = [otherFilter, { field: "main_style", operator: "in", values: bootValues }]
  await waitFor(() => expect(listMock).toHaveBeenCalledWith(expect.objectContaining({ page: 1, filters })))
  expect(savedFilters()).toEqual(filters)
  expect(screen.queryByRole("dialog", { name: "主款式筛选" })).not.toBeInTheDocument()
})

test("unchecking a search result excludes it without keeping invisible selected values", async () => {
  const { user, dialog, search } = await openFilter()
  await user.type(search, "靴")
  await user.click(dialog.getByLabelText("选择雪地靴"))
  expect(dialog.getByText("已选 3 / 6")).toBeInTheDocument()
  await user.click(dialog.getByRole("button", { name: "确定" }))
  expect(savedFilters()).toEqual([{ field: "main_style", operator: "in", values: bootValues.filter((value) => value !== "雪地靴") }])
})

test("select-all toggles only matches and Enter submits the resulting search selection", async () => {
  const { user, dialog, search } = await openFilter()
  await user.type(search, "靴")
  await user.click(dialog.getByLabelText("全选/反选"))
  expect(dialog.getByText("已选 0 / 6")).toBeInTheDocument()
  await user.click(dialog.getByLabelText("全选/反选"))
  expect(dialog.getByText("已选 4 / 6")).toBeInTheDocument()
  await user.type(search, "{Enter}")
  expect(savedFilters()).toEqual([{ field: "main_style", operator: "in", values: bootValues }])
})

test("a search without matches applies an empty selection rather than all rows", async () => {
  const { user, dialog, search } = await openFilter()
  await user.type(search, "不存在的款式")
  expect(dialog.getByText("没有匹配的筛选项")).toBeInTheDocument()
  await user.click(dialog.getByRole("button", { name: "确定" }))
  await waitFor(() => expect(listMock).toHaveBeenCalledWith(expect.objectContaining({
    filters: [{ field: "main_style", operator: "in", values: [] }],
  })))
})

test("clearing the search restores the full draft and cancel leaves the applied filter unchanged", async () => {
  const original: FineTableFilter = { field: "main_style", operator: "not_in", values: ["短靴"] }
  remember("filters", [original])
  const { user, dialog, search } = await openFilter(true)
  await user.type(search, "靴")
  expect(dialog.getByText("已选 3 / 6")).toBeInTheDocument()
  expect(dialog.getByLabelText("选择短靴")).not.toBeChecked()
  await user.clear(search)
  expect(dialog.getByText("已选 5 / 6")).toBeInTheDocument()
  expect(dialog.getByLabelText("选择运动鞋")).toBeChecked()
  await user.click(dialog.getByRole("button", { name: "取消" }))
  expect(savedFilters()).toEqual([original])
})

test("without a search, manual exclusions and clearing the column still work", async () => {
  const { user, dialog } = await openFilter()
  await user.click(dialog.getByLabelText("选择空白"))
  await user.click(dialog.getByRole("button", { name: "确定" }))
  expect(savedFilters()).toEqual([{ field: "main_style", operator: "not_in", values: [""] }])
  await user.click(screen.getByRole("button", { name: "主款式已筛选" }))
  const reopened = within(screen.getByRole("dialog", { name: "主款式筛选" }))
  await user.click(reopened.getByRole("button", { name: "清除此列" }))
  expect(savedFilters()).toEqual([])
})

test("history snapshots receive the same searched column selection", async () => {
  remember("historyDate", "2026-11-01")
  const { user, dialog, search } = await openFilter()
  await user.type(search, "靴")
  await user.click(dialog.getByRole("button", { name: "确定" }))
  await waitFor(() => expect(snapshotMock).toHaveBeenCalledWith(expect.objectContaining({
    snapshotDate: "2026-11-01", page: 1,
    filters: [{ field: "main_style", operator: "in", values: bootValues }],
  })))
})

test("a search matching every loaded option still uses inclusion when the option list is truncated", async () => {
  optionsMock.mockResolvedValue({ field: "main_style", total: 12_000, truncated: true, options: options.slice(0, 4) })
  const { user, dialog, search } = await openFilter()
  await user.type(search, "靴")
  await user.click(dialog.getByRole("button", { name: "确定" }))
  expect(savedFilters()).toEqual([{ field: "main_style", operator: "in", values: bootValues }])
})

test("date tree year and month selection includes dates beyond 300 choices", async () => {
  const dateOptions = Array.from({ length: 365 }, (_, index) => ({
    value: new Date(Date.UTC(2025, 0, index + 1)).toISOString().slice(0, 10), count: 1,
  }))
  optionsMock.mockResolvedValue({ field: "first_order_time", total: 365, truncated: false, options: dateOptions })
  const user = userEvent.setup()
  render(<FineTablePage />)
  await user.click(await screen.findByRole("button", { name: "筛选首单日期" }))
  const dialog = within(screen.getByRole("dialog", { name: "首单日期筛选" }))
  await waitFor(() => expect(dialog.getByLabelText("选择2025年")).toBeChecked())
  await user.click(dialog.getByLabelText("选择2025年"))
  expect(dialog.getByText("已选 0 / 365")).toBeInTheDocument()
  await user.click(dialog.getByRole("button", { name: "2025年展开" }))
  await user.click(dialog.getByLabelText("选择2025年1月"))
  expect(dialog.getByText("已选 31 / 365")).toBeInTheDocument()
  await user.click(dialog.getByRole("button", { name: "确定" }))
  expect(savedFilters()).toEqual([{ field: "first_order_time", operator: "in", values: dateOptions.slice(0, 31).map((item) => item.value) }])
})
