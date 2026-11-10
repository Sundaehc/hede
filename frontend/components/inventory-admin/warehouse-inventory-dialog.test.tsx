import { act, cleanup, render, screen, waitFor, within } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { afterEach, beforeEach, expect, test, vi } from "vitest"

import { WarehouseInventoryDialog } from "@/components/inventory-admin/warehouse-inventory-dialog"
import type { WarehouseInventoryMovementResponse, WarehouseInventoryResponse, WarehouseItem } from "@/lib/api"

const { inventoryMock, movementsMock, exportMock } = vi.hoisted(() => ({ inventoryMock: vi.fn(), movementsMock: vi.fn(), exportMock: vi.fn() }))
vi.mock("@/lib/api", async () => ({
  ...(await vi.importActual<typeof import("@/lib/api")>("@/lib/api")),
  getWarehouseInventory: inventoryMock,
  listWarehouseInventoryMovements: movementsMock,
  downloadWarehouseEndingInventory: exportMock,
}))

const warehouse: WarehouseItem = { id: 1, name: "主仓", brand: "甲", address: null, notes: null, sort_order: 0 }
const range = { start: "2026-10-01", end: "2026-10-31" }
function response(productCode = "P001"): WarehouseInventoryResponse {
  return {
    items: [{ product_code: productCode, product_name: "商品", color_name: "黑色", color_spec: "黑",
      beginning_qty: "10", inbound_qty: "2", outbound_qty: "1", ending_qty: "11" }],
    total: 51, page: 1, page_size: 20,
    totals: { beginning_qty: "10", inbound_qty: "2", outbound_qty: "1", ending_qty: "11" },
  }
}
beforeEach(() => {
  vi.resetAllMocks()
  inventoryMock.mockResolvedValue(response())
  movementsMock.mockResolvedValue({ items: [], total: 0, page: 1, page_size: 50, totals: response().totals })
  exportMock.mockResolvedValue({ filename: "期末库存.xlsx", size: 4 })
})
afterEach(cleanup)

test("returning from movements refreshes the inventory page after source data changes", async () => {
  const user = userEvent.setup()
  render(<WarehouseInventoryDialog warehouse={warehouse} open initialDateRange={range} onOpenChange={() => undefined} />)
  await screen.findByText("P001")
  expect(inventoryMock).toHaveBeenCalledOnce()
  await user.click(screen.getByRole("button", { name: "查看库存明细" }))
  await waitFor(() => expect(movementsMock).toHaveBeenCalledOnce())
  const refreshed = response()
  refreshed.items[0].outbound_qty = "2"
  refreshed.items[0].ending_qty = "10"
  refreshed.totals = { beginning_qty: "10", inbound_qty: "2", outbound_qty: "2", ending_qty: "10" }
  inventoryMock.mockResolvedValueOnce(refreshed)
  await user.click(screen.getByRole("button", { name: "返回汇总" }))
  await screen.findByText("P001")
  expect(inventoryMock).toHaveBeenCalledTimes(2)
  expect(screen.queryByText("11")).not.toBeInTheDocument()
  expect(movementsMock.mock.calls[0][2].aborted).toBe(true)
  await user.click(screen.getByRole("button", { name: "查询" }))
  await waitFor(() => expect(inventoryMock).toHaveBeenCalledTimes(3))
})

test("rerendering the same warehouse does not query again and pagination still works", async () => {
  const user = userEvent.setup()
  const rendered = render(<WarehouseInventoryDialog warehouse={warehouse} open initialDateRange={range} onOpenChange={() => undefined} />)
  await screen.findByText("P001")
  rendered.rerender(<WarehouseInventoryDialog warehouse={{ ...warehouse }} open initialDateRange={{ ...range }} onOpenChange={() => undefined} />)
  expect(inventoryMock).toHaveBeenCalledOnce()
  await user.click(screen.getByRole("button", { name: "下一页" }))
  await waitFor(() => expect(inventoryMock).toHaveBeenLastCalledWith(1, expect.objectContaining({ page: 2 }), expect.any(AbortSignal)))
  expect(inventoryMock).toHaveBeenCalledTimes(2)
})

test("cancels old requests on query changes and ignores their late results", async () => {
  let resolveOld!: (value: WarehouseInventoryResponse) => void
  inventoryMock.mockReturnValueOnce(new Promise((resolve) => { resolveOld = resolve }))
  const user = userEvent.setup()
  const rendered = render(<WarehouseInventoryDialog warehouse={warehouse} open initialDateRange={range} onOpenChange={() => undefined} />)
  await waitFor(() => expect(inventoryMock).toHaveBeenCalledOnce())
  await user.type(screen.getByPlaceholderText("输入商品货号"), "P002{Enter}")
  await waitFor(() => expect(inventoryMock).toHaveBeenCalledTimes(2))
  expect(inventoryMock.mock.calls[0][2].aborted).toBe(true)
  await screen.findByText("P001")
  await act(async () => { resolveOld(response("OLD")) })
  expect(screen.queryByText("OLD")).not.toBeInTheDocument()
  rendered.unmount()
  expect(inventoryMock.mock.calls[1][2].aborted).toBe(true)
})

test("movement cards use current server totals and preserve the selected row identity", async () => {
  const stale = response("Q7841771W52")
  stale.items[0] = { ...stale.items[0], product_name: null, color_name: null, color_spec: "",
    beginning_qty: "0", inbound_qty: "6", outbound_qty: "5", ending_qty: "1" }
  inventoryMock.mockResolvedValue(stale)
  let resolveMovements!: (value: WarehouseInventoryMovementResponse) => void
  movementsMock.mockReturnValueOnce(new Promise((resolve) => { resolveMovements = resolve }))
  const user = userEvent.setup()
  render(<WarehouseInventoryDialog warehouse={warehouse} open initialDateRange={range} onOpenChange={() => undefined} />)
  await screen.findByText("Q7841771W52")
  await user.click(screen.getByRole("button", { name: "查看库存明细" }))
  await waitFor(() => expect(movementsMock).toHaveBeenCalledWith(1, expect.objectContaining({
    product_code: "Q7841771W52", product_name: null, color_name: null, color_spec: "", exact_match: true,
  }), expect.any(AbortSignal)))
  expect(screen.getByText("出库", { selector: "span" }).parentElement).toHaveTextContent("—")
  await act(async () => resolveMovements({ items: [], total: 10, page: 1, page_size: 50,
    totals: { beginning_qty: "0", inbound_qty: "6", outbound_qty: "6", ending_qty: "0" } }))
  expect(screen.getByText("出库", { selector: "span" }).parentElement).toHaveTextContent("出库6")
  expect(screen.getByText("期末", { selector: "span" }).parentElement).toHaveTextContent("期末0")
  expect(screen.getByText("库存流水 10 条")).toBeInTheDocument()
})

test("failed movement requests do not fall back to stale summary cards", async () => {
  movementsMock.mockRejectedValueOnce(new Error("查询失败"))
  const user = userEvent.setup()
  render(<WarehouseInventoryDialog warehouse={warehouse} open initialDateRange={range} onOpenChange={() => undefined} />)
  await screen.findByText("P001")
  await user.click(screen.getByRole("button", { name: "查看库存明细" }))
  await screen.findByText("查询失败")
  expect(screen.getByText("期末", { selector: "span" }).parentElement).toHaveTextContent("—")
})

test("inventory cards hide previous quantities during a refresh and on error", async () => {
  const user = userEvent.setup()
  render(<WarehouseInventoryDialog warehouse={warehouse} open initialDateRange={range} onOpenChange={() => undefined} />)
  await screen.findByText("P001")
  expect(screen.getAllByText("11")).toHaveLength(2)
  let rejectRefresh!: (reason: Error) => void
  inventoryMock.mockReturnValueOnce(new Promise((_resolve, reject) => { rejectRefresh = reject }))
  await user.click(screen.getByRole("button", { name: "查询" }))
  expect(screen.queryByText("11")).not.toBeInTheDocument()
  await act(async () => rejectRefresh(new Error("库存查询失败")))
  await screen.findByText("库存查询失败")
  expect(screen.getAllByText("—", { selector: "p" })).toHaveLength(4)
})

test("ending inventory card opens the composition at page one using submitted filters", async () => {
  const user = userEvent.setup()
  render(<WarehouseInventoryDialog warehouse={warehouse} open initialDateRange={range} onOpenChange={() => undefined} />)
  await screen.findByText("P001")
  await user.type(screen.getByPlaceholderText("输入商品货号"), "P{Enter}")
  await waitFor(() => expect(inventoryMock).toHaveBeenCalledTimes(2))
  await user.click(screen.getByRole("button", { name: "下一页" }))
  await waitFor(() => expect(inventoryMock).toHaveBeenCalledTimes(3))
  await user.type(screen.getByPlaceholderText("输入商品货号"), "UNSUBMITTED")
  const nonzero = response("NEGATIVE")
  nonzero.items[0].ending_qty = "-3"
  nonzero.total = 25
  inventoryMock.mockResolvedValue(nonzero)
  await user.click(screen.getByRole("button", { name: "查看期末库存商品" }))
  await screen.findByText("NEGATIVE")
  expect(inventoryMock).toHaveBeenLastCalledWith(1, {
    date_start: range.start, date_end: range.end, product_code: "P", ending_nonzero: true, page: 1, pageSize: 20,
  }, expect.any(AbortSignal))
  expect(screen.getByRole("heading", { name: "期末库存商品" })).toBeInTheDocument()
  expect(screen.getByRole("button", { name: "查看期末库存商品" })).toHaveAttribute("aria-pressed", "true")
  expect(screen.getByText("-3")).toBeInTheDocument()
  expect(screen.getByText(/跨页期末合计与上方一致/)).toHaveTextContent("2026-10-31")
  await user.click(screen.getByRole("button", { name: "下一页" }))
  await waitFor(() => expect(inventoryMock).toHaveBeenLastCalledWith(1, expect.objectContaining({ ending_nonzero: true, product_code: "P", page: 2 }), expect.any(AbortSignal)))
  await user.click(screen.getByRole("button", { name: "查看库存明细" }))
  await waitFor(() => expect(movementsMock).toHaveBeenCalledWith(1, expect.objectContaining({ product_code: "NEGATIVE", date_end: range.end, exact_match: true }), expect.any(AbortSignal)))
  await user.click(screen.getByRole("button", { name: "返回汇总" }))
  await screen.findByText("NEGATIVE")
  expect(inventoryMock).toHaveBeenLastCalledWith(1, expect.objectContaining({ ending_nonzero: true, page: 2 }), expect.any(AbortSignal))
  await user.click(screen.getByRole("button", { name: "查看全部商品" }))
  await waitFor(() => expect(inventoryMock).toHaveBeenLastCalledWith(1, expect.objectContaining({ ending_nonzero: false, product_code: "P", page: 1 }), expect.any(AbortSignal)))
  expect(screen.queryByText("期末库存商品清单")).not.toBeInTheDocument()
})

test("ending stock search, empty results and clearing retain predictable scope", async () => {
  const user = userEvent.setup()
  render(<WarehouseInventoryDialog warehouse={warehouse} open initialDateRange={range} onOpenChange={() => undefined} />)
  await screen.findByText("P001")
  await user.click(screen.getByRole("button", { name: "查看期末库存商品" }))
  await screen.findByText("期末库存商品清单")
  const empty = response()
  empty.items = []
  empty.total = 0
  empty.totals.ending_qty = "0"
  inventoryMock.mockResolvedValueOnce(empty)
  await user.type(screen.getByPlaceholderText("输入商品货号"), "NO-MATCH{Enter}")
  await screen.findByText("当前条件下没有期末库存非零的商品")
  expect(inventoryMock).toHaveBeenLastCalledWith(1, expect.objectContaining({ ending_nonzero: true, product_code: "NO-MATCH", page: 1 }), expect.any(AbortSignal))
  await user.click(screen.getByRole("button", { name: "清空" }))
  await screen.findByText("P001")
  expect(inventoryMock).toHaveBeenLastCalledWith(1, { ending_nonzero: false, page: 1, pageSize: 20 }, expect.any(AbortSignal))
  expect(screen.getByRole("heading", { name: "仓库库存" })).toBeInTheDocument()
})

test("failed ending inventory query hides old rows and permits retry", async () => {
  const user = userEvent.setup()
  render(<WarehouseInventoryDialog warehouse={warehouse} open initialDateRange={range} onOpenChange={() => undefined} />)
  await screen.findByText("P001")
  inventoryMock.mockRejectedValueOnce(new Error("期末商品加载失败"))
  await user.click(screen.getByRole("button", { name: "查看期末库存商品" }))
  await screen.findByText("期末商品加载失败")
  expect(screen.queryByText("P001")).not.toBeInTheDocument()
  expect(screen.getByRole("button", { name: "查看期末库存商品" })).toBeDisabled()
  await user.click(screen.getByRole("button", { name: "查询" }))
  await screen.findByText("P001")
  expect(screen.getByRole("button", { name: "查看期末库存商品" })).toBeEnabled()
  expect(inventoryMock).toHaveBeenLastCalledWith(1, expect.objectContaining({ ending_nonzero: true }), expect.any(AbortSignal))
})

test.each([false, true])("inventory pagination keeps navigation mounted without presenting old rows (ending only: %s)", async (endingOnly) => {
  const user = userEvent.setup()
  render(<WarehouseInventoryDialog warehouse={warehouse} open initialDateRange={range} onOpenChange={() => undefined} />)
  await screen.findByText("P001")
  if (endingOnly) {
    await user.click(screen.getByRole("button", { name: "查看期末库存商品" }))
    await waitFor(() => expect(inventoryMock).toHaveBeenCalledTimes(2))
  }
  let resolveNext!: (value: WarehouseInventoryResponse) => void
  inventoryMock.mockReturnValueOnce(new Promise(resolve => { resolveNext = resolve }))
  const next = screen.getByRole("button", { name: "下一页" })
  const previous = screen.getByRole("button", { name: "上一页" })
  await user.click(next)
  const table = screen.getByRole("region", { name: "仓库商品库存表" })
  expect(table).toHaveAttribute("aria-busy", "true")
  expect(within(table).getByText("加载中...")).toBeInTheDocument()
  expect(screen.queryByText("P001")).not.toBeInTheDocument()
  expect(screen.getByRole("button", { name: "下一页" })).toBe(next)
  expect(screen.getByRole("button", { name: "上一页" })).toBe(previous)
  expect(next).toBeDisabled()
  expect(previous).toBeDisabled()
  expect(inventoryMock).toHaveBeenLastCalledWith(1, expect.objectContaining({ ending_nonzero: endingOnly, page: 2 }), expect.any(AbortSignal))
  await act(async () => resolveNext(response("P021")))
  expect(table).toHaveAttribute("aria-busy", "false")
  expect(within(table).getByText("P021")).toBeInTheDocument()
  expect(previous).toBeEnabled()
  await user.click(previous)
  await screen.findByText("P001")
  expect(inventoryMock).toHaveBeenLastCalledWith(1, expect.objectContaining({ ending_nonzero: endingOnly, page: 1 }), expect.any(AbortSignal))
})

test("movement pagination keeps navigation mounted, hides old results and separates failure from empty data", async () => {
  const user = userEvent.setup()
  const movement: WarehouseInventoryMovementResponse["items"][number] = {
    detail_id: 1, document_id: 1, document_number: "DOC001", date: "2026-10-31", date_value: "2026-10-31",
    document_type: "进货单", supplier: null, warehouse: "主仓", summary: "入库测试", handler: "测试经手人",
    product_code: "P001", product_name: "测试鞋", color_name: "黑色", color_spec: "黑",
    inbound_qty: "2", outbound_qty: "0", change_qty: "2",
  }
  const movementResponse = { items: [movement], total: 51, page: 1, page_size: 50, totals: response().totals }
  movementsMock.mockResolvedValueOnce(movementResponse)
  render(<WarehouseInventoryDialog warehouse={warehouse} open initialDateRange={range} onOpenChange={() => undefined} />)
  await screen.findByText("P001")
  await user.click(screen.getByRole("button", { name: "查看库存明细" }))
  await screen.findByText("DOC001")
  let resolveNext!: (value: WarehouseInventoryMovementResponse) => void
  movementsMock.mockReturnValueOnce(new Promise(resolve => { resolveNext = resolve }))
  const next = screen.getByRole("button", { name: "下一页" })
  const previous = screen.getByRole("button", { name: "上一页" })
  await user.click(next)
  const table = screen.getByRole("region", { name: "商品库存流水表" })
  expect(table).toHaveAttribute("aria-busy", "true")
  expect(screen.queryByText("DOC001")).not.toBeInTheDocument()
  expect(next).toBeDisabled()
  expect(previous).toBeDisabled()
  expect(screen.getByRole("button", { name: "下一页" })).toBe(next)
  await act(async () => resolveNext({ ...movementResponse, page: 2, items: [{ ...movement, detail_id: 51, document_number: "DOC051" }] }))
  expect(within(table).getByText("DOC051")).toBeInTheDocument()
  expect(table).toHaveAttribute("aria-busy", "false")
  expect(next).toBeDisabled()
  expect(previous).toBeEnabled()
  expect(movementsMock).toHaveBeenLastCalledWith(1, expect.objectContaining({ page: 2, product_code: "P001", exact_match: true }), expect.any(AbortSignal))
  movementsMock.mockRejectedValueOnce(new Error("流水翻页失败"))
  await user.click(previous)
  await screen.findByText("流水翻页失败")
  expect(screen.queryByText("DOC051")).not.toBeInTheDocument()
  expect(screen.queryByText("暂无库存流水")).not.toBeInTheDocument()
})

test("ending export uses submitted filters across pages, prevents duplicate requests and keeps results on failure", async () => {
  const user = userEvent.setup()
  render(<WarehouseInventoryDialog warehouse={warehouse} open canExport initialDateRange={range} onOpenChange={() => undefined} />)
  await screen.findByText("P001")
  expect(screen.queryByRole("button", { name: "导出 Excel" })).not.toBeInTheDocument()
  await user.type(screen.getByPlaceholderText("输入商品货号"), "P{Enter}")
  await waitFor(() => expect(inventoryMock).toHaveBeenCalledTimes(2))
  await user.click(screen.getByRole("button", { name: "查看期末库存商品" }))
  await screen.findByText("期末库存商品清单")
  await user.click(screen.getByRole("button", { name: "下一页" }))
  await waitFor(() => expect(inventoryMock).toHaveBeenLastCalledWith(1, expect.objectContaining({ page: 2 }), expect.any(AbortSignal)))
  await user.type(screen.getByPlaceholderText("输入商品货号"), "UNSUBMITTED")
  let rejectExport!: (reason: Error) => void
  exportMock.mockReturnValueOnce(new Promise((_resolve, reject) => { rejectExport = reject }))
  await user.dblClick(screen.getByRole("button", { name: "导出 Excel" }))
  expect(exportMock).toHaveBeenCalledOnce()
  expect(exportMock).toHaveBeenCalledWith(1, { date_start: range.start, date_end: range.end, product_code: "P" }, expect.any(AbortSignal))
  expect(screen.getByRole("button", { name: "导出中…" })).toBeDisabled()
  await act(async () => rejectExport(new Error("导出查询失败")))
  expect(screen.getByRole("alert")).toHaveTextContent("导出查询失败")
  expect(screen.getByText("P001")).toBeInTheDocument()
  await user.click(screen.getByRole("button", { name: "导出 Excel" }))
  await screen.findByText("期末库存文件已生成，已开始下载")
  expect(exportMock).toHaveBeenCalledTimes(2)
})

test("ending export is hidden without permission and disabled when there are no rows", async () => {
  const user = userEvent.setup()
  const rendered = render(<WarehouseInventoryDialog warehouse={warehouse} open initialDateRange={range} onOpenChange={() => undefined} />)
  await screen.findByText("P001")
  await user.click(screen.getByRole("button", { name: "查看期末库存商品" }))
  expect(screen.queryByRole("button", { name: "导出 Excel" })).not.toBeInTheDocument()
  rendered.rerender(<WarehouseInventoryDialog warehouse={warehouse} open canExport initialDateRange={range} onOpenChange={() => undefined} />)
  expect(screen.getByRole("button", { name: "导出 Excel" })).toBeEnabled()
  inventoryMock.mockResolvedValueOnce({ ...response(), items: [], total: 0 })
  await user.click(screen.getByRole("button", { name: "查询" }))
  await screen.findByText("当前条件下没有期末库存非零的商品")
  expect(screen.getByRole("button", { name: "导出 Excel" })).toBeDisabled()
  expect(exportMock).not.toHaveBeenCalled()
})

test.each(["unmount", "close", "filters"])("cancels ending export on %s and ignores late completion", async (action) => {
  const user = userEvent.setup()
  let resolveExport!: (value: { filename: string; size: number }) => void
  exportMock.mockReturnValueOnce(new Promise(resolve => { resolveExport = resolve }))
  const rendered = render(<WarehouseInventoryDialog warehouse={warehouse} open canExport initialDateRange={range} onOpenChange={() => undefined} />)
  await screen.findByText("P001")
  await user.click(screen.getByRole("button", { name: "查看期末库存商品" }))
  await user.click(screen.getByRole("button", { name: "导出 Excel" }))
  if (action === "unmount") rendered.unmount()
  else if (action === "close") rendered.rerender(<WarehouseInventoryDialog warehouse={warehouse} open={false} canExport initialDateRange={range} onOpenChange={() => undefined} />)
  else await user.click(screen.getByRole("button", { name: "查询" }))
  expect(exportMock.mock.calls[0][2].aborted).toBe(true)
  await act(async () => resolveExport({ filename: "old.xlsx", size: 4 }))
  expect(screen.queryByText("期末库存文件已生成，已开始下载")).not.toBeInTheDocument()
})
