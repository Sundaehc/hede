import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { afterEach, beforeEach, expect, test, vi } from "vitest"

import { InventoryDetailPanel } from "@/components/inventory-admin/inventory-detail-panel"
import type { InventoryRecord } from "@/lib/api"

const { listMock, optionsMock, replaceMock } = vi.hoisted(() => ({ listMock: vi.fn(), optionsMock: vi.fn(), replaceMock: vi.fn() }))
vi.mock("@/components/auth/auth-provider", () => ({
  useAuth: () => ({ user: { id: 1, role_code: "super_admin" }, hasPermission: () => true }),
}))
vi.mock("@/lib/api", async () => ({
  ...(await vi.importActual<typeof import("@/lib/api")>("@/lib/api")),
  listDetails: listMock,
  listInventoryDetailUnitPriceOptions: optionsMock,
  replaceDetailsFromExcel: replaceMock,
  listInventoryAccountSubjects: vi.fn().mockResolvedValue({ items: [] }),
  listSizeGroupOptions: vi.fn().mockResolvedValue({ items: [] }),
}))

beforeEach(() => {
  vi.clearAllMocks()
  listMock.mockResolvedValue({ items: [], total: 0, page: 1, page_size: 100 })
  optionsMock.mockResolvedValue({ items: ["268", "168", "99", null].map((value) => ({ value, count: 1 })), truncated: false })
})
afterEach(cleanup)

async function openFilter(documentType = "进货单") {
  const user = userEvent.setup()
  render(<InventoryDetailPanel record={{ id: 6787, document_number: "TEST", document_type: documentType } as InventoryRecord} suppliers={[]} onClose={vi.fn()} onTotalChanged={vi.fn()} />)
  await user.click(await screen.findByRole("button", { name: "筛选单价" }))
  const dialog = within(screen.getByRole("dialog", { name: "单价筛选" }))
  await waitFor(() => expect(dialog.getByRole("button", { name: "确定" })).toBeEnabled())
  return { user, dialog, search: dialog.getByRole("textbox", { name: "搜索单价" }) }
}

test.each(["进货单", "进货退货单"])("search and confirm filters matching prices for %s", async (documentType) => {
  const { user, dialog, search } = await openFilter(documentType)
  await user.type(search, "68")
  expect(dialog.getByText("已选 2 / 4")).toBeInTheDocument()
  await user.click(dialog.getByLabelText("选择168"))
  await user.click(dialog.getByRole("button", { name: "确定" }))
  await waitFor(() => expect(listMock).toHaveBeenLastCalledWith(6787, { page: 1, pageSize: 100, unitPriceValues: ["268"] }))
})

test("invert and select-all operate on matches and Enter excludes hidden prices", async () => {
  const { user, dialog, search } = await openFilter()
  await user.type(search, "68")
  await user.click(dialog.getByRole("button", { name: "反选" }))
  expect(dialog.getByText("已选 0 / 4")).toBeInTheDocument()
  await user.click(dialog.getByLabelText("全选"))
  await user.type(search, "{Enter}")
  await waitFor(() => expect(listMock).toHaveBeenLastCalledWith(6787, expect.objectContaining({ unitPriceValues: ["268", "168"] })))
})

test("unmatched searches require a choice rather than silently showing every price", async () => {
  const { user, dialog, search } = await openFilter()
  const initialCalls = listMock.mock.calls.length
  await user.type(search, "不存在")
  await user.click(dialog.getByRole("button", { name: "确定" }))
  expect(dialog.getByText("请至少选择一个单价")).toBeInTheDocument()
  expect(listMock).toHaveBeenCalledTimes(initialCalls)
})

test("blank prices remain selectable and IME Enter does not submit", async () => {
  const { user, dialog, search } = await openFilter()
  await user.type(search, "空白")
  fireEvent.keyDown(search, { key: "Enter", isComposing: true })
  expect(dialog.getByRole("button", { name: "确定" })).toBeInTheDocument()
  fireEvent.keyDown(search, { key: "Enter", isComposing: false })
  await waitFor(() => expect(listMock).toHaveBeenLastCalledWith(6787, expect.objectContaining({ unitPriceValues: ["__blank__"] })))
})

test("cancel and clear retain their existing behavior", async () => {
  const { user, dialog, search } = await openFilter()
  await user.type(search, "68")
  await user.click(dialog.getByRole("button", { name: "确定" }))
  await user.click(screen.getByRole("button", { name: "单价已筛选" }))
  const reopened = within(screen.getByRole("dialog", { name: "单价筛选" }))
  await waitFor(() => expect(reopened.getByRole("button", { name: "确定" })).toBeEnabled())
  await user.type(reopened.getByRole("textbox", { name: "搜索单价" }), "99")
  await user.click(reopened.getByRole("button", { name: "取消" }))
  expect(listMock).toHaveBeenLastCalledWith(6787, expect.objectContaining({ unitPriceValues: ["268", "168"] }))
  await user.click(screen.getByRole("button", { name: "单价已筛选" }))
  await user.click(within(screen.getByRole("dialog", { name: "单价筛选" })).getByRole("button", { name: "清除此列" }))
  await waitFor(() => expect(listMock).toHaveBeenLastCalledWith(6787, expect.objectContaining({ unitPriceValues: undefined })))
})

test("reimport resets detail pagination and price filters before querying the updated rows", async () => {
  let imported = false
  listMock.mockImplementation(async (_id, { page, unitPriceValues }) => ({
    items: imported && page === 1 && !unitPriceValues ? [{ id: 1, product_code: "IMPORTED-SKU", product_name: "导入新品" }] : [],
    total: imported ? 1 : 101, page, page_size: 100,
  }))
  replaceMock.mockImplementation(async () => { imported = true; return { message: "导入成功" } })
  const { user, dialog, search } = await openFilter()
  await user.type(search, "268")
  await user.click(dialog.getByRole("button", { name: "确定" }))
  await waitFor(() => expect(listMock).toHaveBeenLastCalledWith(6787, expect.objectContaining({ unitPriceValues: ["268"] })))
  await user.click(screen.getByRole("button", { name: "下一页" }))
  await waitFor(() => expect(listMock).toHaveBeenLastCalledWith(6787, expect.objectContaining({ page: 2 })))
  await user.upload(document.querySelector<HTMLInputElement>('input[type="file"]')!, new File(["excel"], "更新.xlsx"))
  await user.click(within(await screen.findByRole("alertdialog", { name: "确认重新导入明细" })).getByRole("button", { name: "确认导入" }))
  expect(await screen.findByText("IMPORTED-SKU")).toBeInTheDocument()
  expect(listMock).toHaveBeenLastCalledWith(6787, { page: 1, pageSize: 100, unitPriceValues: undefined })
  await user.click(within(screen.getByRole("alertdialog", { name: "导入完成" })).getByRole("button", { name: "确定" }))
  expect(screen.getByRole("button", { name: "筛选单价" })).toBeInTheDocument()
})
