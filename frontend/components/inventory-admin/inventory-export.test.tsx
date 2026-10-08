import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react"
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

test("searches and exports by document number, then clears the filter", async () => {
  const user = userEvent.setup()
  render(<InventoryPage />)
  await screen.findByText("EXPORT-0001")

  await user.type(screen.getByPlaceholderText("输入单据编号"), "0001")
  await user.click(screen.getByRole("button", { name: "搜索" }))
  await waitFor(() => expect(mockListInventory).toHaveBeenLastCalledWith(expect.objectContaining({
    document_number: "0001", exclude_document_type: "进货订单",
  })))

  await user.click(screen.getByRole("button", { name: "导出Excel" }))
  expect(new URL(downloadUrls[0]).searchParams.get("document_number")).toBe("0001")

  await user.click(screen.getByRole("button", { name: "清空" }))
  expect(screen.getByPlaceholderText("输入单据编号")).toHaveValue("")
  await waitFor(() => expect(mockListInventory).toHaveBeenLastCalledWith(expect.objectContaining({
    document_number: undefined,
  })))
})

test.each(["应付款减少", "应付款增加", "应收款减少", "应收款增加"])(
  "allows exporting when %s is the selected document type",
  async (documentType) => {
    const user = userEvent.setup()
    render(<InventoryPage />)
    await screen.findByText("EXPORT-0001")
    await user.click(screen.getByPlaceholderText("选择单据类型"))
    await user.click(screen.getByRole("button", { name: documentType }))
    await user.click(screen.getByRole("button", { name: "搜索" }))
    await waitFor(() => expect(mockListInventory).toHaveBeenLastCalledWith(expect.objectContaining({
      document_types: [documentType],
    })))
    const exportButton = screen.getByRole("button", { name: "导出Excel" })
    await waitFor(() => expect(exportButton).toBeEnabled())
    await user.click(exportButton)

    expect(downloadUrls).toHaveLength(1)
    expect(new URL(downloadUrls[0]).searchParams.getAll("document_types")).toEqual([documentType])
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

test("aligns inventory totals with their table headers", async () => {
  mockListInventory.mockResolvedValueOnce({
    items: [{ id: 1, document_number: "ALIGN-0001", document_type: "进货单", date: "2026-09-03", total_count: "5", amount: "100" }],
    total: 1,
    totals: {
      current_page: { total_count: "5", amount: "100" },
      all: { total_count: "50", amount: "1000" },
    },
  })
  render(<InventoryPage />)
  await screen.findByText("ALIGN-0001")

  const table = screen.getByText("ALIGN-0001").closest("table")!
  const headers = Array.from(table.querySelectorAll("thead th"))
  const rows = Array.from(table.querySelectorAll("tfoot tr"))
  expect(rows).toHaveLength(2)
  for (const [rowIndex, values] of [["5", "100"], ["50", "1000"]].entries()) {
    const cells = Array.from(rows[rowIndex].querySelectorAll("td"))
    expect(cells).toHaveLength(headers.length)
    expect(cells[headers.findIndex((header) => header.textContent?.includes("总数"))]).toHaveTextContent(values[0])
    expect(cells[headers.findIndex((header) => header.textContent?.includes("金额"))]).toHaveTextContent(values[1])
  }
})

test("keeps totals under their headers after dragging amount and count", async () => {
  mockListInventory.mockResolvedValueOnce({
    items: [{ id: 1, document_number: "ALIGN-0002", document_type: "进货单", date: "2026-09-03", total_count: "5", amount: "100" }],
    total: 1,
    totals: {
      current_page: { total_count: "5", amount: "100" },
      all: { total_count: "50", amount: "1000" },
    },
  })
  render(<InventoryPage />)
  await screen.findByText("ALIGN-0002")

  const table = screen.getByText("ALIGN-0002").closest("table")!
  const dataTransfer = {
    effectAllowed: "move",
    dropEffect: "move",
    setData: vi.fn(),
    getData: vi.fn(() => "amount"),
  }
  fireEvent.dragStart(screen.getByRole("button", { name: "拖拽排序金额" }), { dataTransfer })
  fireEvent.dragOver(screen.getByRole("button", { name: "拖拽排序日期" }).closest("th")!, { dataTransfer })
  fireEvent.drop(screen.getByRole("button", { name: "拖拽排序日期" }).closest("th")!, { dataTransfer })

  const headers = Array.from(table.querySelectorAll("thead th"))
  const totalRows = Array.from(table.querySelectorAll("tfoot tr"))
  const bodyCells = Array.from(table.querySelector("tbody tr")!.querySelectorAll("td"))
  const amountIndex = headers.findIndex((header) => header.textContent?.includes("金额"))
  const countIndex = headers.findIndex((header) => header.textContent?.includes("总数"))
  expect(amountIndex).toBe(2)
  expect(bodyCells[amountIndex]).toHaveTextContent("100")
  expect(bodyCells[countIndex]).toHaveTextContent("5")
  for (const [rowIndex, values] of [["100", "5"], ["1000", "50"]].entries()) {
    const cells = Array.from(totalRows[rowIndex].querySelectorAll("td"))
    expect(cells).toHaveLength(headers.length)
    expect(cells[amountIndex]).toHaveTextContent(values[0])
    expect(cells[countIndex]).toHaveTextContent(values[1])
  }

  dataTransfer.getData.mockReturnValue("total_count")
  fireEvent.dragStart(screen.getByRole("button", { name: "拖拽排序总数" }), { dataTransfer })
  fireEvent.drop(screen.getByRole("button", { name: "拖拽排序单据编号" }).closest("th")!, { dataTransfer })

  const reorderedHeaders = Array.from(table.querySelectorAll("thead th"))
  const reorderedCountIndex = reorderedHeaders.findIndex((header) => header.textContent?.includes("总数"))
  const reorderedAmountIndex = reorderedHeaders.findIndex((header) => header.textContent?.includes("金额"))
  expect(reorderedCountIndex).toBe(1)
  for (const [rowIndex, values] of [["5", "100"], ["50", "1000"]].entries()) {
    const cells = Array.from(totalRows[rowIndex].querySelectorAll("td"))
    expect(cells[reorderedCountIndex]).toHaveTextContent(values[0])
    expect(cells[reorderedAmountIndex]).toHaveTextContent(values[1])
  }
})
