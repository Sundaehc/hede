import { act, cleanup, render, screen, waitFor } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { afterEach, beforeEach, expect, test, vi } from "vitest"

import { WarehouseInventoryDialog } from "@/components/inventory-admin/warehouse-inventory-dialog"
import type { WarehouseInventoryResponse, WarehouseItem } from "@/lib/api"

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
  movementsMock.mockResolvedValue({ items: [], total: 0, page: 1, page_size: 50 })
})
afterEach(cleanup)

test("opening and returning from movements reuses the already loaded inventory page", async () => {
  const user = userEvent.setup()
  render(<WarehouseInventoryDialog warehouse={warehouse} open initialDateRange={range} onOpenChange={() => undefined} />)
  await screen.findByText("P001")
  expect(inventoryMock).toHaveBeenCalledOnce()
  await user.click(screen.getByRole("button", { name: "查看库存明细" }))
  await waitFor(() => expect(movementsMock).toHaveBeenCalledOnce())
  await user.click(screen.getByRole("button", { name: "返回汇总" }))
  expect(screen.getByText("P001")).toBeInTheDocument()
  expect(inventoryMock).toHaveBeenCalledOnce()
  expect(movementsMock.mock.calls[0][2].aborted).toBe(true)
  await user.click(screen.getByRole("button", { name: "查询" }))
  await waitFor(() => expect(inventoryMock).toHaveBeenCalledTimes(2))
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
