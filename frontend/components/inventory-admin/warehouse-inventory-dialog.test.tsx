import { act, cleanup, render, screen, waitFor } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { afterEach, beforeEach, expect, test, vi } from "vitest"

import { WarehouseInventoryDialog } from "@/components/inventory-admin/warehouse-inventory-dialog"
import type { WarehouseInventoryMovementResponse, WarehouseInventoryResponse, WarehouseItem } from "@/lib/api"

const { inventoryMock, movementsMock } = vi.hoisted(() => ({ inventoryMock: vi.fn(), movementsMock: vi.fn() }))
vi.mock("@/lib/api", async () => ({
  ...(await vi.importActual<typeof import("@/lib/api")>("@/lib/api")),
  getWarehouseInventory: inventoryMock,
  listWarehouseInventoryMovements: movementsMock,
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
