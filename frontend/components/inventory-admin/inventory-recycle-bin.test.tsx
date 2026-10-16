import { act, cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { afterEach, beforeEach, expect, test, vi } from "vitest"

import { InventoryPage } from "@/components/inventory-admin/inventory-page"

const { mockListRecycleBin } = vi.hoisted(() => ({ mockListRecycleBin: vi.fn() }))

vi.mock("@/components/auth/auth-provider", () => ({
  useAuth: () => ({ user: { id: 1, username: "test" } }),
}))

vi.mock("@/components/inventory-admin/inventory-detail-panel", () => ({
  InventoryDetailPanel: () => null,
}))

vi.mock("@/components/operation-log-dialog", () => ({
  OperationLogDialog: () => null,
}))

vi.mock("@/lib/api", async () => ({
  ...(await vi.importActual<typeof import("@/lib/api")>("@/lib/api")),
  listInventory: async () => ({ items: [], total: 0 }),
  listInventoryRecycleBin: mockListRecycleBin,
  listInventoryBrands: async () => ({ items: [] }),
  listSuppliers: async () => ({ items: [] }),
  listWarehouseBrands: async () => ({ items: [] }),
  listWarehouses: async () => ({ items: [] }),
  listGeneralCustomerBrands: async () => ({ items: [] }),
  listGeneralCustomerShops: async () => ({ items: [] }),
  listGeneralCustomerUnits: async () => ({ items: [] }),
  listInventoryAccountSubjects: async () => ({ items: [] }),
}))

function recycleResponse(page: number) {
  return {
    items: [{
      id: page,
      document_number: "RECYCLE-" + page,
      document_type: "进货单",
      deleted_at: "2026-10-16T02:29:26Z",
    }],
    total: 3224,
  }
}

beforeEach(() => {
  vi.clearAllMocks()
  window.localStorage.clear()
  mockListRecycleBin.mockImplementation(async ({ page }) => recycleResponse(page))
})

afterEach(() => cleanup())

test.each([
  ["inventory", "button"],
  ["inventory", "enter"],
  ["purchase-orders", "button"],
  ["purchase-orders", "enter"],
] as const)("jumps %s recycle pages through %s and keeps navigation in sync", async (mode, submitMode) => {
  const user = userEvent.setup()
  render(<InventoryPage mode={mode} />)
  await user.click(screen.getByRole("button", { name: "回收站" }))
  const dialog = within(screen.getByRole("dialog"))
  await dialog.findByText("RECYCLE-1")
  expect(mockListRecycleBin).toHaveBeenLastCalledWith({
    page: 1,
    pageSize: 10,
    document_type: mode === "purchase-orders" ? "进货订单" : undefined,
    exclude_document_type: mode === "inventory" ? "进货订单" : undefined,
  })
  expect(dialog.getByText("1 / 323")).toBeInTheDocument()
  const input = dialog.getByRole("spinbutton", { name: "回收站跳转页码" })
  expect(input).toHaveAttribute("min", "1")
  expect(input).toHaveAttribute("max", "323")
  await user.click(dialog.getByRole("checkbox", { name: "选择回收站单据 RECYCLE-1" }))
  const callsBeforeTyping = mockListRecycleBin.mock.calls.length
  await user.clear(input)
  await user.type(input, "24")
  expect(mockListRecycleBin).toHaveBeenCalledTimes(callsBeforeTyping)
  if (submitMode === "button") {
    await user.click(dialog.getByRole("button", { name: "跳转" }))
  } else {
    await user.keyboard("{Enter}")
  }
  await dialog.findByText("RECYCLE-24")
  expect(mockListRecycleBin).toHaveBeenLastCalledWith(expect.objectContaining({ page: 24 }))
  expect(dialog.getByText("24 / 323")).toBeInTheDocument()
  expect(dialog.queryByText(/已选/)).not.toBeInTheDocument()
  expect(input).toHaveValue(24)

  await user.click(dialog.getByRole("button", { name: "下一页" }))
  await dialog.findByText("RECYCLE-25")
  expect(input).toHaveValue(25)
  await user.click(dialog.getByRole("button", { name: "上一页" }))
  await dialog.findByText("RECYCLE-24")
  expect(input).toHaveValue(24)

  await user.clear(input)
  await user.type(input, "323{Enter}")
  await dialog.findByText("RECYCLE-323")
  expect(dialog.getByRole("button", { name: "下一页" })).toBeDisabled()

  await user.click(dialog.getByRole("button", { name: mode === "inventory" ? "关闭进销存回收站" : "关闭采购单回收站" }))
  await user.click(screen.getByRole("button", { name: "回收站" }))
  const reopened = within(screen.getByRole("dialog"))
  await reopened.findByText("RECYCLE-1")
  expect(reopened.getByRole("spinbutton", { name: "回收站跳转页码" })).toHaveValue(1)
  expect(reopened.getByRole("button", { name: "上一页" })).toBeDisabled()
})

test.each(["", "0", "-2", "324", "1.5"])("rejects invalid recycle page %s without loading another page", async (value) => {
  const user = userEvent.setup()
  render(<InventoryPage />)
  await user.click(screen.getByRole("button", { name: "回收站" }))
  const dialog = within(screen.getByRole("dialog"))
  await dialog.findByText("RECYCLE-1")
  const callsBeforeInput = mockListRecycleBin.mock.calls.length
  fireEvent.change(dialog.getByRole("spinbutton", { name: "回收站跳转页码" }), { target: { value } })
  expect(dialog.getByRole("button", { name: "跳转" })).toBeDisabled()
  fireEvent.submit(dialog.getByRole("form", { name: "回收站页码跳转" }))
  expect(mockListRecycleBin).toHaveBeenCalledTimes(callsBeforeInput)
  expect(dialog.getByText("1 / 323")).toBeInTheDocument()
})

test("disables recycle page jumping while loading and when the recycle bin is empty", async () => {
  let finishLoading!: (response: { items: never[]; total: number }) => void
  mockListRecycleBin.mockImplementationOnce(() => new Promise((resolve) => { finishLoading = resolve }))
  const user = userEvent.setup()
  render(<InventoryPage />)
  await user.click(screen.getByRole("button", { name: "回收站" }))
  const dialog = within(screen.getByRole("dialog"))
  await waitFor(() => expect(mockListRecycleBin).toHaveBeenCalledOnce())
  expect(dialog.getByText("加载中...")).toBeInTheDocument()
  expect(dialog.getByRole("spinbutton", { name: "回收站跳转页码" })).toBeDisabled()
  expect(dialog.getByRole("button", { name: "跳转" })).toBeDisabled()
  await act(async () => finishLoading({ items: [], total: 0 }))
  expect(dialog.getByText("进销存回收站暂无单据")).toBeInTheDocument()
  expect(dialog.getByRole("spinbutton", { name: "回收站跳转页码" })).toBeDisabled()
  expect(dialog.getByRole("button", { name: "跳转" })).toBeDisabled()
  expect(dialog.getByRole("button", { name: "上一页" })).toBeDisabled()
  expect(dialog.getByRole("button", { name: "下一页" })).toBeDisabled()
})
