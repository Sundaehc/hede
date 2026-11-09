import { act, cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { afterEach, beforeEach, expect, test, vi } from "vitest"

import { InventoryPage } from "@/components/inventory-admin/inventory-page"
import type { InventoryRecord } from "@/lib/api"

const { listMock, updateMock, createMock } = vi.hoisted(() => ({
  listMock: vi.fn(), updateMock: vi.fn(), createMock: vi.fn(),
}))

vi.mock("@/components/auth/auth-provider", () => ({
  useAuth: () => ({ user: { id: 1, username: "test", display_name: "当前用户" } }),
}))
vi.mock("@/components/inventory-admin/inventory-detail-panel", () => ({
  InventoryDetailPanel: () => null,
}))
vi.mock("@/components/operation-log-dialog", () => ({
  OperationLogDialog: () => null,
}))
vi.mock("@/lib/api", async () => ({
  ...(await vi.importActual<typeof import("@/lib/api")>("@/lib/api")),
  listInventory: listMock,
  updateInventoryRecord: updateMock,
  createInventoryRecord: createMock,
  listInventoryBrands: async () => ({ items: [] }),
  listSuppliers: async () => ({ items: [] }),
  listWarehouseBrands: async () => ({ items: [] }),
  listWarehouses: async () => ({ items: [] }),
  listGeneralCustomerBrands: async () => ({ items: [] }),
  listGeneralCustomerShops: async () => ({ items: [] }),
  listGeneralCustomerUnits: async () => ({ items: [] }),
  listInventoryAccountSubjects: async () => ({ items: [] }),
}))

function order(id: number, summary: string): InventoryRecord {
  return {
    id, document_number: `PO-${id}`, document_type: "进货订单",
    date: "2026-11-01", supplier: "鞋厂", warehouse: "总仓",
    total_count: "30", amount: "999", handler: "原经手人", summary,
    additional_note: "原附加说明", extra_fields: { delivery_date: "2026-11-20" },
    source_workbook: "", source_sheet: "", source_row_number: "",
    deleted_at: null, created_at: null, updated_at: "2026-11-01T09:00:00+08:00",
  }
}

const initial = [order(20, "原摘要甲"), order(19, "原摘要乙"), order(18, "原摘要丙")]

beforeEach(() => {
  vi.clearAllMocks()
  window.localStorage.clear()
  window.sessionStorage.clear()
  listMock.mockResolvedValue({ items: initial, total: 25 })
  updateMock.mockImplementation(async (id: number, payload: Partial<InventoryRecord>) => ({
    item: { ...initial.find((item) => item.id === id), ...payload,
      summary: payload.summary?.trim(), handler: "服务端经手人", updated_at: "2026-11-08T15:00:00+08:00" },
    message: "更新成功",
  }))
  createMock.mockResolvedValue({ item: order(21, "新单"), message: "创建成功" })
})

afterEach(cleanup)

function rowOrder() {
  return Array.from(screen.getByText("PO-20").closest("tbody")!.querySelectorAll("tr"))
    .map((row) => row.querySelector("input")?.getAttribute("aria-label"))
}

async function editSummary(user: ReturnType<typeof userEvent.setup>, summary = " 修改后的摘要 ") {
  const row = screen.getByText("PO-19").closest("tr")!
  await user.click(within(row).getByTitle("编辑"))
  const dialog = screen.getByRole("dialog", { name: "编辑采购单" })
  await user.clear(within(dialog).getByRole("textbox", { name: "摘要" }))
  await user.type(within(dialog).getByRole("textbox", { name: "摘要" }), summary)
  await user.click(within(dialog).getByRole("button", { name: "保存" }))
}

test.each(["原经手人", "", null])("preserves purchase handler %s when another account edits the summary", async (handler) => {
  const existing = { ...initial[1], handler }
  listMock.mockResolvedValue({ items: [existing], total: 1 })
  updateMock.mockImplementation(async (_id: number, payload: Partial<InventoryRecord>) => ({
    item: { ...existing, ...payload }, message: "更新成功",
  }))
  const user = userEvent.setup()
  render(<InventoryPage mode="purchase-orders" />)
  await screen.findByText("PO-19")
  await user.click(within(screen.getByText("PO-19").closest("tr")!).getByTitle("编辑"))
  const dialog = within(screen.getByRole("dialog", { name: "编辑采购单" }))
  const handlerInput = dialog.getByRole("textbox", { name: "经手人" })
  expect(handlerInput).toHaveValue(handler || "")
  expect(handlerInput).not.toHaveAttribute("readonly")
  await user.type(dialog.getByRole("textbox", { name: "摘要" }), "补充")
  await user.click(dialog.getByRole("button", { name: "保存" }))
  await waitFor(() => expect(updateMock).toHaveBeenCalledWith(19, expect.objectContaining({ handler: handler || "" })))
  await waitFor(() => expect(screen.queryByRole("dialog", { name: "编辑采购单" })).not.toBeInTheDocument())
  await user.click(within(screen.getByText("PO-19").closest("tr")!).getByTitle("编辑"))
  expect(within(screen.getByRole("dialog", { name: "编辑采购单" })).getByRole("textbox", { name: "经手人" })).toHaveValue(handler || "")
})

test("allows manually changing a purchase handler", async () => {
  updateMock.mockImplementation(async (_id: number, payload: Partial<InventoryRecord>) => ({
    item: { ...initial[1], ...payload }, message: "更新成功",
  }))
  const user = userEvent.setup()
  render(<InventoryPage mode="purchase-orders" />)
  await screen.findByText("PO-19")
  await user.click(within(screen.getByText("PO-19").closest("tr")!).getByTitle("编辑"))
  const dialog = within(screen.getByRole("dialog", { name: "编辑采购单" }))
  const handler = dialog.getByRole("textbox", { name: "经手人" })
  await user.clear(handler)
  await user.type(handler, "指定经手人")
  await user.click(dialog.getByRole("button", { name: "保存" }))
  await waitFor(() => expect(updateMock).toHaveBeenCalledWith(19, expect.objectContaining({ handler: "指定经手人" })))
  await waitFor(() => expect(screen.queryByRole("dialog", { name: "编辑采购单" })).not.toBeInTheDocument())
  expect(within(screen.getByText("PO-19").closest("tr")!).getByText("指定经手人")).toBeInTheDocument()
})

test("continues to default new inventory handlers to the account", async () => {
  const user = userEvent.setup()
  render(<InventoryPage />)
  await screen.findByText("PO-19")
  await user.click(screen.getByRole("button", { name: "新增经营历程" }))
  const handler = within(screen.getByRole("dialog", { name: "新增经营历程" })).getByRole("textbox", { name: "经手人" })
  expect(handler).toHaveValue("当前用户")
  expect(handler).toHaveAttribute("readonly")
})

test("another tab refreshes the saved purchase page and keeps filters, pagination and drafts", async () => {
  const user = userEvent.setup()
  render(<InventoryPage mode="purchase-orders" />)
  await screen.findByText("PO-19")
  const filters = within(screen.getByRole("form", { name: "采购单筛选" }))
  await user.type(filters.getByRole("textbox", { name: "备注" }), "原摘要")
  await user.click(filters.getByRole("button", { name: "搜索" }))
  await user.click(screen.getByLabelText("Go to next page"))
  await waitFor(() => expect(listMock).toHaveBeenLastCalledWith(expect.objectContaining({ page: 2 })))
  await user.type(filters.getByRole("textbox", { name: "备注" }), "草稿")
  const before = listMock.mock.calls.length
  listMock.mockResolvedValue({ items: [initial[0], { ...initial[1], summary: "另一个网页更新" }, initial[2]], total: 25 })
  act(() => window.dispatchEvent(new StorageEvent("storage", {
    key: "hede:data-change:v1:inventory",
    newValue: JSON.stringify({ version: 1, id: "purchase-page-sync", source: "other-tab", resources: ["inventory"] }),
  })))
  await screen.findByText("另一个网页更新")
  expect(listMock).toHaveBeenCalledTimes(before + 1)
  expect(listMock).toHaveBeenLastCalledWith(expect.objectContaining({ page: 2, summary: "原摘要" }))
  expect(filters.getByRole("textbox", { name: "备注" })).toHaveValue("原摘要草稿")
})

test("another tab cannot overwrite an open purchase edit and refreshes after it closes", async () => {
  const user = userEvent.setup()
  render(<InventoryPage mode="purchase-orders" />)
  await screen.findByText("PO-19")
  await user.click(within(screen.getByText("PO-19").closest("tr")!).getByTitle("编辑"))
  const dialog = within(screen.getByRole("dialog", { name: "编辑采购单" }))
  await user.type(dialog.getByRole("textbox", { name: "摘要" }), "尚未保存")
  const before = listMock.mock.calls.length
  act(() => window.dispatchEvent(new StorageEvent("storage", {
    key: "hede:data-change:v1:inventory",
    newValue: JSON.stringify({ version: 1, id: "purchase-edit-sync", source: "other-tab", resources: ["inventory"] }),
  })))
  await new Promise((resolve) => setTimeout(resolve, 350))
  expect(listMock).toHaveBeenCalledTimes(before)
  expect(dialog.getByRole("textbox", { name: "摘要" })).toHaveValue("原摘要乙尚未保存")
  await user.click(dialog.getByRole("button", { name: "取消" }))
  await waitFor(() => expect(listMock).toHaveBeenCalledTimes(before + 1))
})

test.each(["最后修改时间", "摘要"])("keeps the edited purchase row and page under %s sorting", async (sortLabel) => {
  const user = userEvent.setup()
  render(<InventoryPage mode="purchase-orders" />)
  await screen.findByText("PO-19")
  await user.click(screen.getByRole("button", { name: (name) => name.startsWith(`${sortLabel}：`) }))
  await user.click(screen.getByLabelText("Go to next page"))
  await waitFor(() => expect(listMock).toHaveBeenLastCalledWith(expect.objectContaining({ page: 2 })))
  const beforeOrder = rowOrder()
  const beforeCount = listMock.mock.calls.length
  await user.click(screen.getByRole("checkbox", { name: "选择单据 PO-19" }))
  await editSummary(user)

  await waitFor(() => expect(screen.queryByRole("dialog", { name: "编辑采购单" })).not.toBeInTheDocument())
  expect(rowOrder()).toEqual(beforeOrder)
  const row = screen.getByText("PO-19").closest("tr")!
  expect(within(row).getByText("修改后的摘要")).toHaveAttribute("title", "修改后的摘要")
  expect(within(row).getByText("服务端经手人")).toBeInTheDocument()
  expect(row.querySelector('[title="2026-11-08T15:00:00+08:00"]')).toBeInTheDocument()
  expect(screen.getByRole("checkbox", { name: "选择单据 PO-19" })).toBeChecked()
  expect(listMock).toHaveBeenCalledTimes(beforeCount)
  expect(screen.getByText(/第 11-20 条/)).toBeInTheDocument()
  expect(updateMock).toHaveBeenCalledWith(19, expect.objectContaining({ summary: " 修改后的摘要 " }))

  // Explicit refresh continues to honor the user's server-side sorting.
  listMock.mockResolvedValue({ items: [initial[1], initial[0], initial[2]], total: 25 })
  await user.click(screen.getByRole("button", { name: "刷新列表" }))
  await waitFor(() => expect(rowOrder()).toEqual(["选择单据 PO-19", "选择单据 PO-20", "选择单据 PO-18"]))
  expect(listMock).toHaveBeenLastCalledWith(expect.objectContaining({ page: 2 }))
})

test("retains the visible row until an explicit search reapplies the summary filter", async () => {
  const user = userEvent.setup()
  render(<InventoryPage mode="purchase-orders" />)
  await screen.findByText("PO-19")
  const filters = within(screen.getByRole("form", { name: "采购单筛选" }))
  await user.type(filters.getByRole("textbox", { name: "备注" }), "原摘要")
  await user.click(filters.getByRole("button", { name: "搜索" }))
  await waitFor(() => expect(listMock).toHaveBeenLastCalledWith(expect.objectContaining({ summary: "原摘要" })))
  const beforeCount = listMock.mock.calls.length
  await editSummary(user, "已修改")
  await screen.findByText("已修改")
  expect(listMock).toHaveBeenCalledTimes(beforeCount)
  expect(screen.getByText("PO-19")).toBeInTheDocument()
  listMock.mockResolvedValue({ items: [initial[0], initial[2]], total: 2 })
  await user.click(filters.getByRole("button", { name: "搜索" }))
  await waitFor(() => expect(screen.queryByText("PO-19")).not.toBeInTheDocument())
})

test.each(["summary", "size_rows"] as const)("updates all visible headers without replacing %s product row amounts", async (mode) => {
  window.sessionStorage.setItem("hede:session-query:v1:anonymous:inventory:purchase-orders:submittedFilters", JSON.stringify({ product_code: "SKU" }))
  window.sessionStorage.setItem("hede:session-query:v1:anonymous:inventory:purchase-orders:purchaseDetailView", JSON.stringify(mode))
  const rows = [
    { ...initial[0], row_key: "20:1", purchase_detail_mode: mode, product_code: "SKU-1", quantity: "1", unit_price: "11", amount: "11" },
    { ...initial[1], row_key: "19:2", purchase_detail_mode: mode, product_code: "SKU-2", size_name: "230", quantity: "2", unit_price: "22", amount: "44" },
    { ...initial[1], row_key: "19:3", purchase_detail_mode: mode, product_code: "SKU-3", size_name: "235", quantity: "3", unit_price: "33", amount: "99" },
  ]
  listMock.mockResolvedValue({ items: rows, total: 3 })
  const user = userEvent.setup()
  render(<InventoryPage mode="purchase-orders" />)
  await screen.findByText("SKU-2")
  const editedRow = screen.getByText("SKU-2").closest("tr")!
  await user.click(within(editedRow).getByTitle("编辑"))
  const dialog = screen.getByRole("dialog", { name: "编辑采购单" })
  await user.type(within(dialog).getByRole("textbox", { name: "摘要" }), "更新")
  const beforeCount = listMock.mock.calls.length
  await user.click(within(dialog).getByRole("button", { name: "保存" }))
  await waitFor(() => expect(screen.queryByRole("dialog", { name: "编辑采购单" })).not.toBeInTheDocument())

  for (const [sku, amount] of [["SKU-2", "44"], ["SKU-3", "99"]]) {
    const row = screen.getByText(sku).closest("tr")!
    expect(within(row).getByText(amount)).toBeInTheDocument()
    expect(row.querySelector('[title="2026-11-08T15:00:00+08:00"]')).toBeInTheDocument()
    expect(within(row).queryByText("999")).not.toBeInTheDocument()
  }
  expect(screen.getByText("SKU-2").closest("tr")).toBe(editedRow)
  expect(listMock).toHaveBeenCalledTimes(beforeCount)
})

test("keeps original content and position when saving fails", async () => {
  updateMock.mockRejectedValue(new Error("保存服务暂时不可用"))
  const user = userEvent.setup()
  render(<InventoryPage mode="purchase-orders" />)
  await screen.findByText("PO-19")
  const beforeOrder = rowOrder()
  const beforeCount = listMock.mock.calls.length
  await editSummary(user)
  await screen.findByText("保存服务暂时不可用")
  expect(rowOrder()).toEqual(beforeOrder)
  expect(within(screen.getByText("PO-19").closest("tr")!).getByText("原摘要乙")).toBeInTheDocument()
  expect(listMock).toHaveBeenCalledTimes(beforeCount)
})

test("still reloads the inventory list after editing a non-purchase record", async () => {
  listMock.mockResolvedValue({ items: [{ ...initial[1], document_type: "进货单" }], total: 1 })
  const user = userEvent.setup()
  render(<InventoryPage />)
  await screen.findByText("PO-19")
  await user.click(within(screen.getByText("PO-19").closest("tr")!).getByTitle("编辑"))
  const dialog = screen.getByRole("dialog", { name: "编辑经营历程" })
  expect(within(dialog).getByRole("textbox", { name: "经手人" })).toHaveValue("当前用户")
  expect(within(dialog).getByRole("textbox", { name: "经手人" })).toHaveAttribute("readonly")
  const beforeCount = listMock.mock.calls.length
  await user.click(within(dialog).getByRole("button", { name: "保存" }))
  await waitFor(() => expect(listMock.mock.calls.length).toBeGreaterThan(beforeCount))
  expect(updateMock).toHaveBeenCalledWith(19, expect.objectContaining({ handler: "当前用户" }))
})

test("still reloads purchase orders after creating a new order", async () => {
  const user = userEvent.setup()
  render(<InventoryPage mode="purchase-orders" />)
  await screen.findByText("PO-19")
  await user.click(screen.getByRole("button", { name: "新增采购单" }))
  const dialog = screen.getByRole("dialog", { name: "新增采购单" })
  const handler = within(dialog).getByRole("textbox", { name: "经手人" })
  expect(handler).toHaveValue("")
  expect(handler).not.toHaveAttribute("readonly")
  await user.type(handler, "新单经手人")
  fireEvent.change(within(dialog).getByLabelText("交货日期"), { target: { value: "2026-11-20" } })
  const beforeCount = listMock.mock.calls.length
  await user.click(within(dialog).getByRole("button", { name: "保存" }))
  await waitFor(() => expect(createMock).toHaveBeenCalled())
  expect(createMock).toHaveBeenCalledWith(expect.objectContaining({ handler: "新单经手人" }))
  await waitFor(() => expect(listMock.mock.calls.length).toBeGreaterThan(beforeCount))
})
