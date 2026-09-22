import { cleanup, render, screen, waitFor, within } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { afterEach, beforeEach, expect, test, vi } from "vitest"

import { InventoryPage } from "@/components/inventory-admin/inventory-page"

const { mockListInventory } = vi.hoisted(() => ({ mockListInventory: vi.fn() }))

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
  listInventory: mockListInventory,
  listSuppliers: vi.fn().mockResolvedValue({ items: [] }),
  listWarehouseBrands: vi.fn().mockResolvedValue({ items: [] }),
  listWarehouses: vi.fn().mockResolvedValue({ items: [] }),
  listGeneralCustomerBrands: vi.fn().mockResolvedValue({ items: [] }),
  listGeneralCustomerShops: vi.fn().mockResolvedValue({ items: [] }),
  listGeneralCustomerUnits: vi.fn().mockResolvedValue({ items: [] }),
  listInventoryAccountSubjects: vi.fn().mockResolvedValue({ items: [] }),
}))

let downloadUrls: string[] = []

beforeEach(() => {
  vi.clearAllMocks()
  window.localStorage.clear()
  downloadUrls = []
  vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(function (this: HTMLAnchorElement) {
    downloadUrls.push(this.href)
  })
  mockListInventory.mockResolvedValue({
    items: [{
      id: 1,
      document_number: "EXPORT-0001",
      document_type: "应付款减少",
      date: "2026-09-03",
      supplier: "测试供应商",
      amount: "1000",
      summary: "质量罚款",
    }],
    total: 30,
  })
})

afterEach(() => {
  cleanup()
  vi.restoreAllMocks()
})

test("exports all filtered fine records rather than only the visible page", async () => {
  const user = userEvent.setup()
  render(<InventoryPage />)
  await screen.findByText("EXPORT-0001")
  await user.type(screen.getByPlaceholderText("摘要/备注"), "罚款")
  await user.click(screen.getByRole("button", { name: "搜索" }))
  await waitFor(() => expect(mockListInventory).toHaveBeenLastCalledWith(expect.objectContaining({
    summary: "罚款", completion_status: "completed", exclude_document_type: "进货订单",
  })))
  const exportButton = screen.getByRole("button", { name: "导出Excel" })
  await waitFor(() => expect(exportButton).toBeEnabled())
  await user.click(exportButton)

  expect(downloadUrls).toHaveLength(1)
  const params = new URL(downloadUrls[0]).searchParams
  expect(params.get("summary")).toBe("罚款")
  expect(params.get("completion_status")).toBe("completed")
  expect(params.get("exclude_document_type")).toBe("进货订单")
  expect(params.has("document_type")).toBe(false)
  expect(params.has("ids")).toBe(false)
  expect(params.has("page")).toBe(false)
})

test.each(["应付款减少", "应付款增加", "应收款减少", "应收款增加"])(
  "allows exporting when %s is the selected document type",
  async (documentType) => {
    const user = userEvent.setup()
    render(<InventoryPage />)
    await screen.findByText("EXPORT-0001")
    const typeOption = screen.getByRole("option", { name: documentType })
    await user.selectOptions(typeOption.closest("select")!, documentType)
    await user.click(screen.getByRole("button", { name: "搜索" }))
    await waitFor(() => expect(mockListInventory).toHaveBeenLastCalledWith(expect.objectContaining({
      document_type: documentType,
    })))
    const exportButton = screen.getByRole("button", { name: "导出Excel" })
    await waitFor(() => expect(exportButton).toBeEnabled())
    await user.click(exportButton)

    expect(downloadUrls).toHaveLength(1)
    expect(new URL(downloadUrls[0]).searchParams.get("document_type")).toBe(documentType)
    expect(screen.queryByText("暂不支持导出")).not.toBeInTheDocument()
  },
)

test("exports selected accounting documents by ID", async () => {
  const user = userEvent.setup()
  render(<InventoryPage />)
  const documentNumber = await screen.findByText("EXPORT-0001")
  const row = documentNumber.closest("tr")!
  await user.click(within(row).getByRole("checkbox"))
  await user.click(screen.getByRole("button", { name: "导出Excel" }))

  expect(downloadUrls).toHaveLength(1)
  expect(new URL(downloadUrls[0]).searchParams.get("ids")).toBe("1")
})
