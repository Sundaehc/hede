import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { afterEach, beforeEach, expect, test, vi } from "vitest"

import { ProductToolbar } from "@/components/product-admin/product-toolbar"
import { buildProductExportUrl } from "@/lib/api"

const { mockPreflight, mockDownload } = vi.hoisted(() => ({
  mockPreflight: vi.fn(),
  mockDownload: vi.fn(),
}))

vi.mock("@/lib/api", async () => ({
  ...(await vi.importActual<typeof import("@/lib/api")>("@/lib/api")),
  assertProductExportAllowed: mockPreflight,
  downloadProductExport: mockDownload,
  getProductImageRefreshStatus: vi.fn().mockResolvedValue({ in_progress: false }),
}))

function toolbarProps() {
  return {
    brand: "eblan" as const,
    year: "2026",
    value: "ER",
    query: "ER",
    prefixValue: "ER7",
    skuPrefix: "ER7",
    isLoading: false,
    canExport: true,
    canExportPrices: true,
    canImport: false,
    canRefreshImages: false,
    onValueChange: vi.fn(),
    onPrefixValueChange: vi.fn(),
    onSearch: vi.fn(),
    onClear: vi.fn(),
    onRefresh: vi.fn(),
    onImportComplete: vi.fn(),
    onMessage: vi.fn(),
  }
}

beforeEach(() => {
  vi.clearAllMocks()
  mockPreflight.mockResolvedValue(undefined)
  mockDownload.mockResolvedValue({ filename: "伊伴物价.xlsx", size: 100 })
})

afterEach(cleanup)

test("price export sends current filters without size expansion", async () => {
  const user = userEvent.setup()
  render(<ProductToolbar {...toolbarProps()} />)
  await user.click(screen.getByRole("button", { name: "物价导出" }))

  await waitFor(() => expect(mockDownload).toHaveBeenCalledWith(
    "eblan", undefined, "price", expect.any(Function), undefined, undefined, "2026", "ER", "ER7",
  ))
  expect(mockPreflight).toHaveBeenCalledWith("eblan", undefined, "price", undefined, undefined, "2026", "ER", "ER7")
})

test("price export prefers selected product IDs", async () => {
  const user = userEvent.setup()
  render(<ProductToolbar {...toolbarProps()} selectedIds={new Set([7, 9])} />)
  await user.click(screen.getByRole("button", { name: "物价导出" }))

  await waitFor(() => expect(mockDownload).toHaveBeenCalledWith(
    "eblan", [7, 9], "price", expect.any(Function), undefined, undefined, "2026", undefined, undefined,
  ))
})

test.each([
  { canExport: false, canExportPrices: false },
  { canExport: true, canExportPrices: false },
])("price export is hidden without price permission: %o", async (permissions) => {
  render(<ProductToolbar {...toolbarProps()} {...permissions} />)
  await waitFor(() => expect(screen.queryByRole("button", { name: "物价导出" })).not.toBeInTheDocument())
})

test("price-only permission allows selected export without general export controls", async () => {
  const user = userEvent.setup()
  render(<ProductToolbar {...toolbarProps()} canExport={false} selectedIds={new Set([7])} />)
  expect(screen.queryByRole("button", { name: /^(导出 Excel|导出搜索结果|导出选中|带尺码导出)/ })).not.toBeInTheDocument()
  expect(screen.queryByLabelText("导出开始日期")).not.toBeInTheDocument()
  expect(screen.queryByRole("button", { name: "新增商品" })).not.toBeInTheDocument()
  await user.click(screen.getByRole("button", { name: "物价导出" }))

  await waitFor(() => expect(mockDownload).toHaveBeenCalledWith(
    "eblan", [7], "price", expect.any(Function), undefined, undefined, "2026", undefined, undefined,
  ))
})

test("price export surfaces server permission errors without downloading", async () => {
  const user = userEvent.setup()
  const props = toolbarProps()
  mockPreflight.mockRejectedValue(new Error("无权查看商品成本，不能导出物价"))
  render(<ProductToolbar {...props} />)
  await user.click(screen.getByRole("button", { name: "物价导出" }))

  await waitFor(() => expect(props.onMessage).toHaveBeenCalledWith("导出失败", "无权查看商品成本，不能导出物价"))
  expect(mockDownload).not.toHaveBeenCalled()
  expect(screen.getByRole("button", { name: "物价导出" })).toBeEnabled()
})

test("price export supports overview and disables duplicate downloads", async () => {
  const user = userEvent.setup()
  let finishDownload: (value: { filename: string; size: number }) => void = () => undefined
  mockDownload.mockImplementation(() => new Promise((resolve) => { finishDownload = resolve }))
  render(<ProductToolbar {...toolbarProps()} brand="all" />)
  await user.click(screen.getByRole("button", { name: "物价导出" }))

  await waitFor(() => expect(mockDownload).toHaveBeenCalledWith(
    "all", undefined, "price", expect.any(Function), undefined, undefined, "2026", "ER", "ER7",
  ))
  expect(screen.getByRole("button", { name: "准备导出..." })).toBeDisabled()
  finishDownload({ filename: "总览物价.xlsx", size: 100 })
  await waitFor(() => expect(screen.getByRole("button", { name: "物价导出" })).toBeEnabled())
})

test("price export URL serializes price mode and filters", () => {
  const url = new URL(buildProductExportUrl("eblan", undefined, "price", undefined, undefined, "2026", " ER ", " ER7 "), "http://localhost")
  expect(Object.fromEntries(url.searchParams)).toEqual({ brand: "eblan", mode: "price", year: "2026", query: "ER", sku_prefix: "ER7" })
})

test("groups exports, product maintenance, and activity dates without changing actions", async () => {
  const user = userEvent.setup()
  const onCreate = vi.fn()
  render(<ProductToolbar {...toolbarProps()} canImport onCreate={onCreate} />)

  const exports = within(screen.getByRole("group", { name: "数据导出" }))
  expect(exports.getByRole("button", { name: "导出搜索结果" })).toBeInTheDocument()
  expect(exports.getByRole("button", { name: "物价导出" })).toBeInTheDocument()
  expect(exports.getByRole("button", { name: "带尺码导出" })).toBeInTheDocument()

  const maintenance = within(screen.getByRole("group", { name: "商品维护" }))
  expect(maintenance.getByRole("button", { name: "下载导入模板" })).toBeInTheDocument()
  expect(maintenance.getByRole("button", { name: "导入 Excel" })).toBeInTheDocument()
  await user.click(maintenance.getByRole("button", { name: "新增商品" }))
  expect(onCreate).toHaveBeenCalledOnce()

  const activity = within(screen.getByRole("group", { name: "按时间导出" }))
  expect(activity.getByText("仅包含所选时间内导入或新增的商品")).toBeInTheDocument()
  expect(activity.getByRole("button", { name: /^导出时间段：/ })).toBeInTheDocument()
  expect(activity.getByRole("button", { name: "导出记录" })).toBeInTheDocument()
  expect(activity.getByRole("button", { name: "导出记录（含尺码）" })).toBeInTheDocument()
})

test.each([
  ["导出记录", undefined],
  ["导出记录（含尺码）", "with_sizes"],
])("%s exports the selected activity range independently of search filters", async (label, mode) => {
  const user = userEvent.setup()
  render(<ProductToolbar {...toolbarProps()} onCreate={vi.fn()} />)
  const activity = within(screen.getByRole("group", { name: "按时间导出" }))
  await user.click(activity.getByRole("button", { name: /^导出时间段：/ }))
  fireEvent.change(activity.getByLabelText("开始日期"), { target: { value: "2026-01-05" } })
  fireEvent.change(activity.getByLabelText("结束日期"), { target: { value: "2026-01-08" } })
  await user.click(activity.getByRole("button", { name: label }))

  await waitFor(() => expect(mockDownload).toHaveBeenCalledWith(
    "eblan", undefined, mode, expect.any(Function), "2026-01-05", "2026-01-08", undefined, undefined, undefined,
  ))
})
