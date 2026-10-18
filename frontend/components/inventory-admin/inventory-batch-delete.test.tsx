import {
  act,
  cleanup,
  render,
  screen,
  waitFor,
  within,
} from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { afterEach, beforeEach, expect, test, vi } from "vitest"

import { InventoryPage } from "@/components/inventory-admin/inventory-page"

const { listMock, selectionMock, deleteMock } = vi.hoisted(() => ({
  listMock: vi.fn(),
  selectionMock: vi.fn(),
  deleteMock: vi.fn(),
}))

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
  listInventory: listMock,
  listInventorySelectionIds: selectionMock,
  batchDeleteInventory: deleteMock,
  listInventoryBrands: async () => ({ items: [] }),
  listSuppliers: async () => ({ items: [] }),
  listWarehouseBrands: async () => ({ items: [] }),
  listWarehouses: async () => ({ items: [] }),
  listGeneralCustomerBrands: async () => ({ items: [] }),
  listGeneralCustomerShops: async () => ({ items: [] }),
  listGeneralCustomerUnits: async () => ({ items: [] }),
  listInventoryAccountSubjects: async () => ({ items: [] }),
}))

beforeEach(() => {
  vi.resetAllMocks()
  window.localStorage.clear()
  window.sessionStorage.clear()
  listMock.mockImplementation(async ({ page }) => ({
    items: [
      { id: page, document_number: "DOC-" + page, document_type: "进货单" },
    ],
    total: 25,
  }))
  selectionMock.mockResolvedValue({ ids: [1, 2, 3, 4, 5], total: 5 })
  deleteMock.mockResolvedValue({ deleted: 2, message: "已移入回收站 2 条记录" })
})

afterEach(() => cleanup())

async function openPage(mode: "inventory" | "purchase-orders" = "inventory") {
  const user = userEvent.setup()
  render(<InventoryPage mode={mode} />)
  await screen.findByText("DOC-1")
  await waitFor(() =>
    expect(screen.getByRole("button", { name: "全选筛选结果" })).toBeEnabled()
  )
  return user
}

async function nextPage(user: ReturnType<typeof userEvent.setup>) {
  await user.click(screen.getByLabelText("Go to next page"))
  await screen.findByText("DOC-2")
  await waitFor(() =>
    expect(
      screen.getByRole("checkbox", { name: "全选当前页单据" })
    ).toBeEnabled()
  )
}

test.each(["inventory", "purchase-orders"] as const)(
  "preserves %s selections across pages and confirms the entire selection",
  async (mode) => {
    const user = await openPage(mode)
    await user.click(screen.getByRole("checkbox", { name: "选择单据 DOC-1" }))
    await nextPage(user)
    expect(
      screen.getByRole("button", { name: "批量删除 (1)" })
    ).toBeInTheDocument()
    await user.click(screen.getByRole("checkbox", { name: "选择单据 DOC-2" }))
    await user.click(screen.getByRole("button", { name: "批量删除 (2)" }))
    const confirmation = within(
      screen.getByRole("alertdialog", { name: "确认批量删除" })
    )
    expect(confirmation.getByText(/跨页选中的 2 张单据/)).toHaveTextContent(
      "不仅是当前页"
    )
    expect(deleteMock).not.toHaveBeenCalled()
    await user.click(confirmation.getByRole("button", { name: "移入回收站" }))
    await waitFor(() =>
      expect(deleteMock).toHaveBeenCalledExactlyOnceWith([1, 2])
    )
    await waitFor(() =>
      expect(listMock).toHaveBeenLastCalledWith(
        expect.objectContaining({ page: 1 })
      )
    )
  }
)

test("selecting and deselecting the current page does not discard another page", async () => {
  const user = await openPage()
  await user.click(screen.getByRole("checkbox", { name: "全选当前页单据" }))
  await nextPage(user)
  await user.click(screen.getByRole("checkbox", { name: "全选当前页单据" }))
  expect(
    screen.getByRole("button", { name: "批量删除 (2)" })
  ).toBeInTheDocument()
  await user.click(screen.getByRole("checkbox", { name: "全选当前页单据" }))
  expect(
    screen.getByRole("button", { name: "批量删除 (1)" })
  ).toBeInTheDocument()
  await user.click(screen.getByLabelText("Go to previous page"))
  await screen.findByText("DOC-1")
  expect(screen.getByRole("checkbox", { name: "选择单据 DOC-1" })).toBeChecked()
})

test("all matching selection uses committed filters, supports exclusions and sends a fixed ID snapshot", async () => {
  const user = await openPage()
  await user.type(screen.getByRole("textbox", { name: "备注" }), "已查询")
  await user.click(screen.getByRole("button", { name: "搜索" }))
  await waitFor(() =>
    expect(listMock).toHaveBeenLastCalledWith(
      expect.objectContaining({ summary: "已查询" })
    )
  )
  await user.type(screen.getByRole("textbox", { name: "备注" }), "未查询")
  await user.click(screen.getByRole("button", { name: "全选筛选结果" }))
  expect(selectionMock).toHaveBeenCalledExactlyOnceWith(
    expect.objectContaining({
      summary: "已查询",
      completion_status: "completed",
      exclude_document_type: "进货订单",
    })
  )
  expect(selectionMock.mock.calls[0][0]).not.toHaveProperty("page")
  expect(
    screen.getByRole("button", { name: "批量删除 (5)" })
  ).toBeInTheDocument()
  expect(screen.getByText(/全部筛选结果/)).toBeInTheDocument()
  await nextPage(user)
  expect(screen.getByRole("checkbox", { name: "选择单据 DOC-2" })).toBeChecked()
  await user.click(screen.getByRole("checkbox", { name: "选择单据 DOC-2" }))
  await user.click(screen.getByRole("button", { name: "批量删除 (4)" }))
  await user.click(
    within(screen.getByRole("alertdialog")).getByRole("button", {
      name: "移入回收站",
    })
  )
  expect(deleteMock).toHaveBeenCalledWith([1, 3, 4, 5])
})

test("purchase all matching selection is limited to purchase documents", async () => {
  const user = await openPage("purchase-orders")
  await user.click(screen.getByRole("button", { name: "全选筛选结果" }))
  expect(selectionMock).toHaveBeenCalledWith(
    expect.objectContaining({
      document_type: "进货订单",
      exclude_document_type: undefined,
      completion_status: undefined,
    })
  )
})

test("searching again clears cross-page selection and ignores a late select-all response", async () => {
  let finish!: (result: { ids: number[]; total: number }) => void
  selectionMock.mockImplementationOnce(
    () =>
      new Promise((resolve) => {
        finish = resolve
      })
  )
  const user = await openPage()
  await user.click(screen.getByRole("checkbox", { name: "选择单据 DOC-1" }))
  await user.click(screen.getByRole("button", { name: "全选筛选结果" }))
  expect(screen.getByRole("button", { name: "正在全选..." })).toBeDisabled()
  await user.type(screen.getByRole("textbox", { name: "备注" }), "新范围")
  await user.click(screen.getByRole("button", { name: "搜索" }))
  await waitFor(() =>
    expect(listMock).toHaveBeenLastCalledWith(
      expect.objectContaining({ summary: "新范围" })
    )
  )
  await act(async () => finish({ ids: [1, 2, 3], total: 3 }))
  expect(
    screen.queryByRole("button", { name: /批量删除/ })
  ).not.toBeInTheDocument()
  expect(
    screen.getByRole("checkbox", { name: "选择单据 DOC-1" })
  ).not.toBeChecked()
})

test("changing completion tabs clears the selection", async () => {
  const user = await openPage()
  await user.click(screen.getByRole("checkbox", { name: "选择单据 DOC-1" }))
  await user.click(screen.getByRole("tab", { name: "未完成单据" }))
  await waitFor(() =>
    expect(listMock).toHaveBeenLastCalledWith(
      expect.objectContaining({ completion_status: "incomplete" })
    )
  )
  expect(
    screen.queryByRole("button", { name: /批量删除/ })
  ).not.toBeInTheDocument()
})

test("canceling deletion sends no mutation and preserves selection", async () => {
  const user = await openPage()
  await user.click(screen.getByRole("checkbox", { name: "选择单据 DOC-1" }))
  await user.click(screen.getByRole("button", { name: "批量删除 (1)" }))
  await user.click(
    within(screen.getByRole("alertdialog")).getByRole("button", {
      name: "取消",
    })
  )
  expect(deleteMock).not.toHaveBeenCalled()
  expect(
    screen.getByRole("button", { name: "批量删除 (1)" })
  ).toBeInTheDocument()
  await user.click(screen.getByRole("button", { name: "取消选择" }))
  expect(
    screen.queryByRole("button", { name: /批量删除/ })
  ).not.toBeInTheDocument()
})

test("select-all errors preserve explicit selections and do not delete anything", async () => {
  selectionMock.mockRejectedValueOnce(new Error("查询失败"))
  const user = await openPage()
  await user.click(screen.getByRole("checkbox", { name: "选择单据 DOC-1" }))
  await user.click(screen.getByRole("button", { name: "全选筛选结果" }))
  expect(
    await screen.findByRole("alertdialog", { name: "全选失败" })
  ).toHaveTextContent("查询失败")
  expect(deleteMock).not.toHaveBeenCalled()
  await user.click(screen.getByRole("button", { name: "确定" }))
  expect(
    screen.getByRole("button", { name: "批量删除 (1)" })
  ).toBeInTheDocument()
})

test("failed deletion retains the selection and does not show a success message", async () => {
  deleteMock.mockRejectedValueOnce(new Error("数据库暂不可用"))
  const user = await openPage()
  await user.click(screen.getByRole("checkbox", { name: "选择单据 DOC-1" }))
  await user.click(screen.getByRole("button", { name: "批量删除 (1)" }))
  await user.click(
    within(screen.getByRole("alertdialog")).getByRole("button", {
      name: "移入回收站",
    })
  )
  expect(
    await screen.findByRole("alertdialog", { name: "批量删除失败" })
  ).toHaveTextContent("数据库暂不可用")
  await user.click(screen.getByRole("button", { name: "确定" }))
  expect(screen.getByRole("checkbox", { name: "选择单据 DOC-1" })).toBeChecked()
})

test("page size changes preserve selected documents", async () => {
  const user = await openPage()
  await user.click(screen.getByRole("checkbox", { name: "选择单据 DOC-1" }))
  const pageSize = screen
    .getAllByRole("combobox")
    .find((element) =>
      within(element).queryByRole("option", { name: "50 条" })
    )!
  await user.selectOptions(pageSize, "50")
  await waitFor(() =>
    expect(listMock).toHaveBeenLastCalledWith(
      expect.objectContaining({ pageSize: 50 })
    )
  )
  expect(screen.getByRole("checkbox", { name: "选择单据 DOC-1" })).toBeChecked()
})
