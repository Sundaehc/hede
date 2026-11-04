import { act, cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { afterEach, beforeEach, expect, test, vi } from "vitest"

import { ProductAdminPage } from "@/components/product-admin/product-admin-page"

const { listMock, selectionMock, exportMock, yearsMock } = vi.hoisted(() => ({
  listMock: vi.fn(), selectionMock: vi.fn(), exportMock: vi.fn(), yearsMock: vi.fn(),
}))
vi.mock("@/components/auth/auth-provider", () => ({
  useAuth: () => ({ user: { role_code: "super_admin" }, hasPermission: () => true }),
}))
vi.mock("@/components/operation-log-dialog", () => ({ OperationLogDialog: () => null }))
vi.mock("@/components/product-admin/product-form-dialog", () => ({ ProductFormDialog: () => null }))
vi.mock("@/components/product-admin/product-detail-dialog", () => ({ ProductDetailDialog: () => null }))
vi.mock("@/components/product-admin/product-copywriting-dialog", () => ({ ProductCopywritingDialog: () => null }))
vi.mock("@/lib/api", async () => ({
  ...(await vi.importActual<typeof import("@/lib/api")>("@/lib/api")),
  listProducts: listMock,
  listProductSelectionIds: selectionMock,
  getProductSearchOptions: yearsMock,
  listProductArchiveBrands: async () => ({ items: [] }),
  getProductImageRefreshStatus: async () => ({ in_progress: false }),
  assertProductExportAllowed: async () => undefined,
  downloadProductExport: exportMock,
}))

beforeEach(() => {
  vi.resetAllMocks()
  window.history.replaceState({}, "", "/products")
  listMock.mockResolvedValue({ items: [], total: 30, page: 1, page_size: 10 })
  yearsMock.mockResolvedValue({ years: ["2025", "26年秋季款"], seasons: ["春秋", "秋冬"], product_names: ["牛皮皮鞋", "羊皮皮鞋", "运动鞋"] })
  selectionMock.mockResolvedValue({ items: [], total: 0 })
  exportMock.mockResolvedValue({ filename: "商品档案.xlsx", size: 100 })
})
afterEach(cleanup)

async function openPage() {
  const user = userEvent.setup()
  const rendered = render(<ProductAdminPage />)
  await waitFor(() => expect(screen.getByRole("button", { name: "搜索" })).toBeEnabled())
  return { user, ...rendered }
}

test("combines submitted year, season and product name in overview, pagination, selection and export", async () => {
  const { user } = await openPage()
  expect(yearsMock).toHaveBeenCalledWith("all")
  const calls = listMock.mock.calls.length
  await user.type(screen.getByLabelText("年份"), "2026")
  await user.type(screen.getByLabelText("季节"), "秋")
  await user.type(screen.getByLabelText("品名"), "  皮鞋  ")
  expect(listMock).toHaveBeenCalledTimes(calls)
  await user.click(screen.getByRole("button", { name: "搜索" }))
  await waitFor(() => expect(listMock).toHaveBeenLastCalledWith(expect.objectContaining({
    brand: "all", year: "2026", season: "秋", productName: "皮鞋", page: 1,
  })))
  await user.click(screen.getByLabelText("Go to next page"))
  await waitFor(() => expect(listMock).toHaveBeenLastCalledWith(expect.objectContaining({
    year: "2026", season: "秋", productName: "皮鞋", page: 2,
  })))
  await user.type(screen.getByLabelText("品名"), "未提交")
  await user.click(screen.getByRole("button", { name: "全选筛选结果" }))
  expect(selectionMock).toHaveBeenCalledWith(expect.objectContaining({
    brand: "all", year: "2026", season: "秋", productName: "皮鞋",
  }))
  await user.click(screen.getByRole("button", { name: "导出搜索结果" }))
  await waitFor(() => expect(exportMock).toHaveBeenCalledWith(
    "all", undefined, undefined, expect.any(Function), undefined, undefined, "2026", undefined, undefined,
    { season: "秋", productName: "皮鞋" },
  ))
})

test("Enter submits attributes, collapsed summary shows applied values, and clear resets every condition", async () => {
  const { user } = await openPage()
  await user.type(screen.getByLabelText("年份"), "2025")
  await user.type(screen.getByLabelText("季节"), "春")
  await user.type(screen.getByLabelText("品名"), "运动鞋{Enter}")
  await waitFor(() => expect(listMock).toHaveBeenLastCalledWith(expect.objectContaining({ year: "2025", season: "春", productName: "运动鞋" })))
  await user.type(screen.getByLabelText("品名"), "草稿")
  await user.click(screen.getByRole("button", { name: "收起搜索区" }))
  const summary = within(screen.getByRole("group", { name: "当前搜索条件" }))
  expect(summary.getByText("2025")).toBeInTheDocument()
  expect(summary.getByText("春")).toBeInTheDocument()
  expect(summary.getByText("运动鞋")).toBeInTheDocument()
  expect(summary.queryByText("运动鞋草稿")).not.toBeInTheDocument()
  await user.click(screen.getByRole("button", { name: "展开搜索区" }))
  await user.click(screen.getByRole("button", { name: "清空" }))
  await waitFor(() => expect(listMock).toHaveBeenLastCalledWith(expect.objectContaining({ year: undefined, season: undefined, productName: undefined, page: 1 })))
  for (const label of ["年份", "季节", "品名"]) expect(screen.getByLabelText(label)).toHaveValue("")
})

test("remount restores submitted attributes separately from drafts and brand year shortcuts stay in sync", async () => {
  const { user, unmount } = await openPage()
  await user.type(screen.getByLabelText("年份"), "2026")
  await user.type(screen.getByLabelText("季节"), "冬")
  await user.type(screen.getByLabelText("品名"), "短靴{Enter}")
  await waitFor(() => expect(listMock).toHaveBeenLastCalledWith(expect.objectContaining({ productName: "短靴" })))
  await user.type(screen.getByLabelText("品名"), "草稿")
  unmount()
  render(<ProductAdminPage />)
  await waitFor(() => expect(screen.getByRole("button", { name: "搜索" })).toBeEnabled())
  expect(screen.getByLabelText("品名")).toHaveValue("草稿")
  expect(screen.getByRole("button", { name: "移除品名：短靴" })).toBeInTheDocument()
  expect(listMock).toHaveBeenLastCalledWith(expect.objectContaining({ year: "2026", season: "冬", productName: "短靴" }))
  await user.click(screen.getByRole("tab", { name: "千百度男鞋" }))
  await user.click(await screen.findByRole("button", { name: "2025" }))
  await waitFor(() => expect(listMock).toHaveBeenLastCalledWith(expect.objectContaining({ brand: "cbanner_mens", year: "2025", season: "冬", productName: "短靴" })))
  expect(screen.getByLabelText("年份")).toHaveValue("")
  expect(screen.getByRole("button", { name: "移除年份：2025" })).toBeInTheDocument()
})

test("all attribute dropdowns use existing product values and narrow candidates by substring", async () => {
  const { user } = await openPage()
  await user.click(screen.getByLabelText("年份"))
  expect(screen.getByRole("option", { name: "26年秋季款" })).toBeInTheDocument()
  await user.type(screen.getByLabelText("年份"), "2026")
  expect(screen.getByRole("option", { name: "26年秋季款" })).toBeInTheDocument()
  await user.clear(screen.getByLabelText("年份"))
  await user.type(screen.getByLabelText("年份"), "秋季")
  expect(screen.queryByRole("option", { name: "2025" })).not.toBeInTheDocument()
  await user.click(screen.getByRole("option", { name: "26年秋季款" }))
  expect(screen.getByLabelText("年份")).toHaveValue("")
  expect(screen.getByRole("button", { name: "移除年份：26年秋季款" })).toBeInTheDocument()
  await user.click(screen.getByLabelText("季节"))
  expect(within(screen.getByRole("listbox", { name: "季节选项" })).getAllByRole("option").map((item) => item.textContent)).toEqual(["春秋", "秋冬"])
  await user.type(screen.getByLabelText("季节"), "冬")
  expect(within(screen.getByRole("listbox", { name: "季节选项" })).getAllByRole("option")).toHaveLength(1)
  await user.click(screen.getByRole("option", { name: "秋冬" }))
  await user.type(screen.getByLabelText("品名"), "皮鞋")
  expect(within(screen.getByRole("listbox", { name: "品名选项" })).getAllByRole("option")).toHaveLength(2)
  expect(screen.queryByRole("option", { name: "运动鞋" })).not.toBeInTheDocument()
  await user.click(screen.getByRole("button", { name: "搜索" }))
  await waitFor(() => expect(listMock).toHaveBeenLastCalledWith(expect.objectContaining({ year: "26年秋季款", season: "秋冬", productName: "皮鞋" })))
  await user.click(screen.getByLabelText("品名"))
  expect(screen.getByLabelText("品名")).toHaveValue("")
  expect(screen.getByRole("button", { name: "移除品名：皮鞋" })).toBeInTheDocument()
  await user.type(screen.getByLabelText("品名"), "未匹配{Enter}")
  await waitFor(() => expect(listMock).toHaveBeenLastCalledWith(expect.objectContaining({ productName: JSON.stringify(["皮鞋", "未匹配"]) })))
})

test("keyboard candidate selection submits the selected value and ignores Chinese composition confirmation", async () => {
  const { user } = await openPage()
  const input = screen.getByLabelText("品名")
  await user.type(input, "皮鞋")
  const calls = listMock.mock.calls.length
  fireEvent.keyDown(input, { key: "Enter", isComposing: true })
  expect(listMock).toHaveBeenCalledTimes(calls)
  await user.keyboard("{Home}{ArrowDown}{Enter}")
  expect(input).toHaveValue("")
  expect(screen.getByRole("button", { name: "移除品名：羊皮皮鞋" })).toBeInTheDocument()
  expect(listMock).toHaveBeenCalledTimes(calls)
  await user.keyboard("{Enter}")
  await waitFor(() => expect(listMock).toHaveBeenLastCalledWith(expect.objectContaining({ productName: "羊皮皮鞋" })))
})

test("brand switches discard stale option responses and refresh reloads candidates", async () => {
  let resolveOverview!: (value: { years: string[]; seasons: string[]; product_names: string[] }) => void
  yearsMock.mockImplementation((brand: string) => brand === "all"
    ? new Promise((resolve) => { resolveOverview = resolve })
    : Promise.resolve({ years: ["2024"], seasons: ["夏季"], product_names: ["品牌专属鞋"] }))
  const { user } = await openPage()
  await user.click(screen.getByRole("tab", { name: "千百度男鞋" }))
  await waitFor(() => expect(yearsMock).toHaveBeenCalledWith("cbanner_mens"))
  await act(async () => resolveOverview({ years: ["2099"], seasons: ["过期季节"], product_names: ["过期品名"] }))
  await user.click(screen.getByLabelText("品名"))
  expect(screen.getByRole("option", { name: "品牌专属鞋" })).toBeInTheDocument()
  expect(screen.queryByRole("option", { name: "过期品名" })).not.toBeInTheDocument()
  const calls = yearsMock.mock.calls.length
  await user.click(screen.getByRole("button", { name: "刷新" }))
  await waitFor(() => expect(yearsMock).toHaveBeenCalledTimes(calls + 1))
})

test("multiple values in all three attributes survive search, pagination, selection and export", async () => {
  const { user } = await openPage()
  const initialCalls = listMock.mock.calls.length
  for (const [label, values] of [["年份", ["2025", "26年秋季款"]], ["季节", ["春秋", "秋冬"]], ["品名", ["牛皮皮鞋", "羊皮皮鞋"]]] as const) {
    await user.click(screen.getByLabelText(label))
    for (const value of values) {
      await user.click(screen.getByRole("option", { name: value }))
      expect(screen.getByRole("option", { name: value })).toHaveAttribute("aria-selected", "true")
    }
    expect(screen.getByRole("listbox", { name: `${label}选项` })).toHaveAttribute("aria-multiselectable", "true")
  }
  expect(listMock).toHaveBeenCalledTimes(initialCalls)
  await user.click(screen.getByRole("button", { name: "搜索" }))
  const filters = { year: JSON.stringify(["2025", "26年秋季款"]), season: JSON.stringify(["春秋", "秋冬"]), productName: JSON.stringify(["牛皮皮鞋", "羊皮皮鞋"]) }
  await waitFor(() => expect(listMock).toHaveBeenLastCalledWith(expect.objectContaining({ ...filters, page: 1 })))
  await user.click(screen.getByLabelText("Go to next page"))
  await waitFor(() => expect(listMock).toHaveBeenLastCalledWith(expect.objectContaining({ ...filters, page: 2 })))
  await user.click(screen.getByRole("button", { name: "全选筛选结果" }))
  expect(selectionMock).toHaveBeenCalledWith(expect.objectContaining(filters))
  await user.click(screen.getByRole("button", { name: "导出搜索结果" }))
  await waitFor(() => expect(exportMock).toHaveBeenCalledWith(
    "all", undefined, undefined, expect.any(Function), undefined, undefined, filters.year, undefined, undefined,
    { season: filters.season, productName: filters.productName },
  ))
  await user.click(screen.getByRole("button", { name: "收起搜索区" }))
  const summary = within(screen.getByRole("group", { name: "当前搜索条件" }))
  expect(summary.getByText("牛皮皮鞋、羊皮皮鞋")).toBeInTheDocument()
})

test("toggle, remove and clear modify draft values before submitting", async () => {
  const { user } = await openPage()
  const input = screen.getByLabelText("品名")
  await user.type(input, "皮鞋")
  await user.click(screen.getByRole("option", { name: "牛皮皮鞋" }))
  await user.click(screen.getByRole("option", { name: "羊皮皮鞋" }))
  await user.click(screen.getByRole("option", { name: "牛皮皮鞋" }))
  expect(screen.queryByRole("button", { name: "移除品名：牛皮皮鞋" })).not.toBeInTheDocument()
  await user.click(screen.getByRole("option", { name: "运动鞋" }))
  await user.click(screen.getByRole("button", { name: "移除品名：羊皮皮鞋" }))
  await user.click(screen.getByRole("button", { name: "搜索" }))
  await waitFor(() => expect(listMock).toHaveBeenLastCalledWith(expect.objectContaining({ productName: "运动鞋" })))
  await user.click(screen.getByRole("button", { name: "清空品名" }))
  await user.click(screen.getByRole("button", { name: "搜索" }))
  await waitFor(() => expect(listMock).toHaveBeenLastCalledWith(expect.objectContaining({ productName: undefined })))
})

test("a candidate beyond the display limit can be found and added alongside another selection", async () => {
  yearsMock.mockResolvedValue({ years: [], seasons: [], product_names: Array.from({ length: 90 }, (_, index) => `鞋款${index}`) })
  const { user } = await openPage()
  const input = screen.getByLabelText("品名")
  await user.click(input)
  expect(within(screen.getByRole("listbox", { name: "品名选项" })).getAllByRole("option")).toHaveLength(80)
  await user.click(screen.getByRole("option", { name: "鞋款0" }))
  await user.type(input, "鞋款89")
  await user.click(screen.getByRole("option", { name: "鞋款89" }))
  await user.click(screen.getByRole("button", { name: "搜索" }))
  await waitFor(() => expect(listMock).toHaveBeenLastCalledWith(expect.objectContaining({ productName: JSON.stringify(["鞋款0", "鞋款89"]) })))
})

test("reopening the page restores selected values separately from an unsubmitted search", async () => {
  const { user, unmount } = await openPage()
  await user.click(screen.getByLabelText("品名"))
  await user.click(screen.getByRole("option", { name: "牛皮皮鞋" }))
  await user.click(screen.getByRole("option", { name: "羊皮皮鞋" }))
  await user.click(screen.getByRole("button", { name: "搜索" }))
  await user.type(screen.getByLabelText("品名"), "草稿")
  unmount()
  render(<ProductAdminPage />)
  await waitFor(() => expect(screen.getByRole("button", { name: "搜索" })).toBeEnabled())
  expect(screen.getByLabelText("品名")).toHaveValue("草稿")
  expect(screen.getByRole("button", { name: "移除品名：牛皮皮鞋" })).toBeInTheDocument()
  expect(screen.getByRole("button", { name: "移除品名：羊皮皮鞋" })).toBeInTheDocument()
  expect(listMock).toHaveBeenLastCalledWith(expect.objectContaining({ productName: JSON.stringify(["牛皮皮鞋", "羊皮皮鞋"]) }))
})
