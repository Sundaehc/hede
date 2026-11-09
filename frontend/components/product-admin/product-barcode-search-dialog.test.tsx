import { act, cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { afterEach, beforeEach, expect, test, vi } from "vitest"
import { ProductBarcodeSearchDialog } from "@/components/product-admin/product-barcode-search-dialog"
import type { ProductBarcodeItem, ProductBarcodeResponse } from "@/lib/api"

const { listMock, exportMock } = vi.hoisted(() => ({ listMock: vi.fn(), exportMock: vi.fn() }))
vi.mock("@/lib/api", async () => ({
  ...(await vi.importActual<typeof import("@/lib/api")>("@/lib/api")),
  listProductBarcodes: listMock,
  downloadProductBarcodes: exportMock,
}))
const brands = [{ key: "all", label: "总览" }, { key: "custom", label: "自定义品牌" }]
const row: ProductBarcodeItem = {
  id: 1, brand: "custom", sku: "SHOE", original_sku: "OLD", product_name: "女鞋", color: "黑色",
  color_code: "01", size_range: "测试尺码", barcode_build_rule: "货号+颜色代码+尺码", size_name: "35",
  size_barcode: "225", barcode: "SHOE01225", issue: "",
}
const result = (items: ProductBarcodeItem[] = [row], total = items.length): ProductBarcodeResponse => ({ items, total, page: 1, page_size: 50 })

beforeEach(() => { vi.resetAllMocks(); listMock.mockResolvedValue(result()); exportMock.mockResolvedValue({ filename: "条码搜索.xlsx", size: 10 }) })
afterEach(() => { cleanup(); vi.restoreAllMocks() })

test("waits for a query, submits with Enter, renders full barcode and copies its exact value", async () => {
  const user = userEvent.setup()
  const copy = vi.spyOn(navigator.clipboard, "writeText").mockResolvedValue()
  render(<ProductBarcodeSearchDialog brand="custom" brands={brands} onClose={vi.fn()} />)
  expect(listMock).not.toHaveBeenCalled()
  expect(screen.getByRole("button", { name: "查询条码" })).toBeDisabled()
  await user.type(screen.getByLabelText("货号 / 原始货号"), " SHOE{Enter}")
  expect(listMock).toHaveBeenLastCalledWith({ brand: "custom", query: "SHOE", page: 1, pageSize: 50 }, expect.any(AbortSignal))
  const table = await screen.findByRole("table", { name: "商品条码查询结果" })
  expect(within(table).getByText("SHOE01225")).toHaveClass("select-all")
  expect(within(table).getByText("货号+颜色代码+尺码")).toBeInTheDocument()
  expect(within(table).getByText("35")).toBeInTheDocument()
  await user.click(within(table).getByRole("button", { name: "复制条码 SHOE01225" }))
  expect(copy).toHaveBeenCalledWith("SHOE01225")
  expect(screen.getByRole("status")).toHaveTextContent("已复制条码 SHOE01225")
})

test("paginates submitted query independently of edits and a new search resets page", async () => {
  const user = userEvent.setup()
  listMock.mockResolvedValue(result([row], 70))
  render(<ProductBarcodeSearchDialog brand="all" brands={brands} initialQuery="SHOE" onClose={vi.fn()} />)
  await screen.findByText("SHOE01225")
  await user.clear(screen.getByLabelText("货号 / 原始货号"))
  await user.type(screen.getByLabelText("货号 / 原始货号"), "NEXT")
  await user.click(screen.getByRole("button", { name: "下一页" }))
  await waitFor(() => expect(listMock).toHaveBeenLastCalledWith(expect.objectContaining({ query: "SHOE", page: 2 }), expect.any(AbortSignal)))
  await screen.findByRole("button", { name: "查询条码" })
  await user.click(screen.getByRole("button", { name: "查询条码" }))
  await waitFor(() => expect(listMock).toHaveBeenLastCalledWith(expect.objectContaining({ query: "NEXT", page: 1 }), expect.any(AbortSignal)))
})

test("aborts closed requests and ignores late results after changing brand", async () => {
  let resolve!: (value: ProductBarcodeResponse) => void
  listMock.mockImplementationOnce(() => new Promise((done) => { resolve = done }))
  const { rerender, unmount } = render(<ProductBarcodeSearchDialog brand="all" brands={brands} initialQuery="SHOE" onClose={vi.fn()} />)
  const signal = listMock.mock.calls[0][1] as AbortSignal
  rerender(<ProductBarcodeSearchDialog brand="custom" brands={brands} initialQuery="SHOE" onClose={vi.fn()} />)
  await screen.findByText("SHOE01225")
  await act(async () => resolve(result([{ ...row, barcode: "OLD-RESPONSE" }])))
  expect(signal.aborted).toBe(true)
  expect(screen.queryByText("OLD-RESPONSE")).not.toBeInTheDocument()
  const latestSignal = listMock.mock.lastCall![1] as AbortSignal
  unmount()
  expect(latestSignal.aborted).toBe(true)
})

test("reports configuration problems without copy actions and explains clipboard failure", async () => {
  const user = userEvent.setup()
  vi.spyOn(navigator.clipboard, "writeText").mockRejectedValue(new Error("denied"))
  listMock.mockResolvedValue(result([row, { ...row, id: 2, barcode: null, issue: "请维护颜色代码" }]))
  render(<ProductBarcodeSearchDialog brand="custom" brands={brands} initialQuery="SHOE" onClose={vi.fn()} />)
  await screen.findByText("请维护颜色代码")
  expect(screen.getAllByRole("button", { name: /^复制条码/ })).toHaveLength(1)
  await user.click(screen.getByRole("button", { name: "复制条码 SHOE01225" }))
  expect(screen.getByRole("status")).toHaveTextContent("复制失败，请选中完整条码手动复制")
})

test("separates API errors and empty results and retries the submitted query", async () => {
  const user = userEvent.setup()
  listMock.mockRejectedValueOnce(new Error("服务连接中断"))
  render(<ProductBarcodeSearchDialog brand="custom" brands={brands} initialQuery="SHOE" onClose={vi.fn()} />)
  expect(await screen.findByRole("alert")).toHaveTextContent("服务连接中断")
  expect(screen.queryByText(/未找到匹配的商品/)).not.toBeInTheDocument()
  listMock.mockResolvedValueOnce(result([]))
  await user.click(screen.getByRole("button", { name: "重新查询" }))
  expect(await screen.findByText(/未找到匹配的商品/)).toBeInTheDocument()
})

test("does not submit Chinese composition confirmation and closes with Escape", async () => {
  const close = vi.fn()
  render(<ProductBarcodeSearchDialog brand="custom" brands={brands} onClose={close} />)
  const input = screen.getByLabelText("货号 / 原始货号")
  fireEvent.change(input, { target: { value: "SHOE" } })
  fireEvent.keyDown(input, { key: "Enter", isComposing: true })
  expect(listMock).not.toHaveBeenCalled()
  fireEvent.keyDown(input, { key: "Escape" })
  expect(close).toHaveBeenCalledOnce()
})

test("exports every result for the submitted query rather than drafts or the current page", async () => {
  const user = userEvent.setup()
  listMock.mockResolvedValue(result([row], 70))
  render(<ProductBarcodeSearchDialog brand="custom" brands={brands} initialQuery="SHOE" canExport onClose={vi.fn()} />)
  await screen.findByText("SHOE01225")
  await user.click(screen.getByRole("button", { name: "下一页" }))
  await waitFor(() => expect(listMock).toHaveBeenLastCalledWith(expect.objectContaining({ page: 2 }), expect.any(AbortSignal)))
  await user.clear(screen.getByLabelText("货号 / 原始货号"))
  await user.type(screen.getByLabelText("货号 / 原始货号"), "未提交")
  await user.click(screen.getByRole("button", { name: "导出 Excel" }))
  expect(exportMock).toHaveBeenCalledExactlyOnceWith({ brand: "custom", query: "SHOE" }, expect.any(AbortSignal))
  expect(screen.getByRole("status")).toHaveTextContent("已导出当前查询的全部条码结果")
  expect(screen.getByLabelText("货号 / 原始货号")).toHaveValue("未提交")
  expect(screen.getByText("2 / 2")).toBeInTheDocument()
})

test("requires export permission and disables exports before a query and for empty results", async () => {
  const { rerender } = render(<ProductBarcodeSearchDialog brand="custom" brands={brands} onClose={vi.fn()} />)
  expect(screen.queryByRole("button", { name: "导出 Excel" })).not.toBeInTheDocument()
  rerender(<ProductBarcodeSearchDialog brand="custom" brands={brands} canExport onClose={vi.fn()} />)
  expect(screen.getByRole("button", { name: "导出 Excel" })).toBeDisabled()
  listMock.mockResolvedValue(result([]))
  fireEvent.change(screen.getByLabelText("货号 / 原始货号"), { target: { value: "NONE" } })
  fireEvent.submit(screen.getByLabelText("货号 / 原始货号").closest("form")!)
  await screen.findByText(/未找到匹配的商品/)
  expect(screen.getByRole("button", { name: "导出 Excel" })).toBeDisabled()
})

test("shows an export error without losing results and supports retry", async () => {
  const user = userEvent.setup()
  exportMock.mockRejectedValueOnce(new Error("导出权限不足"))
  render(<ProductBarcodeSearchDialog brand="custom" brands={brands} initialQuery="SHOE" canExport onClose={vi.fn()} />)
  await screen.findByText("SHOE01225")
  await user.click(screen.getByRole("button", { name: "导出 Excel" }))
  expect(await screen.findByRole("alert")).toHaveTextContent("导出权限不足")
  expect(screen.getByText("SHOE01225")).toBeInTheDocument()
  await user.click(screen.getByRole("button", { name: "导出 Excel" }))
  expect(screen.queryByRole("alert")).not.toBeInTheDocument()
  expect(exportMock).toHaveBeenCalledTimes(2)
})

test("prevents duplicate export and aborts the download when the dialog closes", async () => {
  const user = userEvent.setup()
  exportMock.mockImplementationOnce(() => new Promise(() => {}))
  const { unmount } = render(<ProductBarcodeSearchDialog brand="custom" brands={brands} initialQuery="SHOE" canExport onClose={vi.fn()} />)
  await screen.findByText("SHOE01225")
  await user.click(screen.getByRole("button", { name: "导出 Excel" }))
  expect(screen.getByRole("button", { name: "导出中…" })).toBeDisabled()
  expect(screen.getByRole("button", { name: "查询条码" })).toBeDisabled()
  expect(exportMock).toHaveBeenCalledOnce()
  const signal = exportMock.mock.calls[0][1] as AbortSignal
  unmount()
  expect(signal.aborted).toBe(true)
})
