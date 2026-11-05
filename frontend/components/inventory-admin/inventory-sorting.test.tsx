import {
  cleanup,
  render,
  screen,
  waitFor,
  within,
} from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { afterEach, beforeEach, expect, test, vi } from "vitest"

import { InventoryPage } from "@/components/inventory-admin/inventory-page"

const { listMock } = vi.hoisted(() => ({ listMock: vi.fn() }))

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
  vi.clearAllMocks()
  window.localStorage.clear()
  window.sessionStorage.clear()
  listMock.mockImplementation(async ({ page }) => ({
    items: [{ id: page, document_number: `SORT-${page}` }],
    total: 25,
  }))
})

afterEach(cleanup)

function getSortButton(label: string) {
  return screen.getByRole("button", {
    name: (name) => name.startsWith(`${label}：`),
  })
}

test.each([
  ["inventory", "日期"],
  ["purchase-orders", "订货日期"],
] as const)(
  "cycles descending, ascending and default sorting in %s and returns to page one",
  async (mode, dateLabel) => {
    const user = userEvent.setup()
    render(<InventoryPage mode={mode} />)
    await screen.findByText("SORT-1")
    await user.click(screen.getByLabelText("Go to next page"))
    await screen.findByText("SORT-2")

    const dateButton = getSortButton(dateLabel)
    const header = dateButton.closest("th")!
    expect(header).not.toHaveAttribute("aria-sort")

    await user.click(dateButton)
    await waitFor(() =>
      expect(listMock).toHaveBeenLastCalledWith(
        expect.objectContaining({
          page: 1,
          sortRules: [{ key: "date", direction: "desc" }],
        })
      )
    )
    expect(header).toHaveAttribute("aria-sort", "descending")
    expect(dateButton).toHaveAttribute("aria-pressed", "true")
    expect(within(dateButton).queryByText("1")).not.toBeInTheDocument()

    await user.click(dateButton)
    await waitFor(() =>
      expect(listMock).toHaveBeenLastCalledWith(
        expect.objectContaining({
          sortRules: [{ key: "date", direction: "asc" }],
        })
      )
    )
    expect(header).toHaveAttribute("aria-sort", "ascending")

    await user.click(dateButton)
    await waitFor(() =>
      expect(listMock).toHaveBeenLastCalledWith(
        expect.objectContaining({ sortRules: undefined })
      )
    )
    expect(header).not.toHaveAttribute("aria-sort")
    expect(dateButton).toHaveAttribute("aria-pressed", "false")
  }
)

test("keeps multiple-sort order and renumbers badges when a rule is removed", async () => {
  const user = userEvent.setup()
  render(<InventoryPage />)
  await screen.findByText("SORT-1")

  const dateButton = getSortButton("日期")
  const amountButton = getSortButton("金额")
  await user.click(dateButton)
  await user.keyboard("{Shift>}")
  await user.click(amountButton)
  await user.keyboard("{/Shift}")

  await waitFor(() =>
    expect(listMock).toHaveBeenLastCalledWith(
      expect.objectContaining({
        sortRules: [
          { key: "date", direction: "desc" },
          { key: "amount", direction: "desc" },
        ],
      })
    )
  )
  expect(within(dateButton).getByText("1")).toBeInTheDocument()
  expect(within(amountButton).getByText("2")).toBeInTheDocument()
  expect(dateButton.closest("th")).toHaveAttribute("aria-sort", "descending")
  expect(amountButton.closest("th")).not.toHaveAttribute("aria-sort")

  await user.keyboard("{Shift>}")
  await user.click(dateButton)
  await user.keyboard("{/Shift}")
  await waitFor(() =>
    expect(listMock).toHaveBeenLastCalledWith(
      expect.objectContaining({
        sortRules: [
          { key: "date", direction: "asc" },
          { key: "amount", direction: "desc" },
        ],
      })
    )
  )

  await user.keyboard("{Shift>}")
  await user.click(dateButton)
  await user.keyboard("{/Shift}")
  await waitFor(() =>
    expect(listMock).toHaveBeenLastCalledWith(
      expect.objectContaining({
        sortRules: [{ key: "amount", direction: "desc" }],
      })
    )
  )
  expect(dateButton.closest("th")).not.toHaveAttribute("aria-sort")
  expect(amountButton.closest("th")).toHaveAttribute("aria-sort", "descending")
  expect(within(dateButton).queryByText("1")).not.toBeInTheDocument()
  expect(within(amountButton).queryByText("2")).not.toBeInTheDocument()
  expect(within(amountButton).queryByText("1")).not.toBeInTheDocument()
})

test("an ordinary click replaces multiple sorting rules with a single column", async () => {
  const user = userEvent.setup()
  render(<InventoryPage />)
  await screen.findByText("SORT-1")

  await user.click(getSortButton("日期"))
  await user.keyboard("{Shift>}")
  await user.click(getSortButton("金额"))
  await user.keyboard("{/Shift}")

  const dateButton = getSortButton("日期")
  expect(dateButton).toHaveAttribute(
    "aria-label",
    "日期：当前降序，第 1 优先级；点击按此列降序"
  )
  await user.click(dateButton)

  await waitFor(() =>
    expect(listMock).toHaveBeenLastCalledWith(
      expect.objectContaining({
        sortRules: [{ key: "date", direction: "desc" }],
      })
    )
  )
  expect(getSortButton("金额")).toHaveAttribute("aria-pressed", "false")
  expect(within(dateButton).queryByText("1")).not.toBeInTheDocument()
})

test("shows transfer source in its own sortable warehouse column", async () => {
  listMock.mockResolvedValue({ items: [
    { id: 1, document_number: "TRANSFER-1", document_type: "同价调拨单", supplier: "出货甲仓", warehouse: "入货乙仓" },
    { id: 2, document_number: "PURCHASE-2", document_type: "进货单", supplier: "供应商甲", warehouse: "采购收货仓" },
  ], total: 2 })
  const user = userEvent.setup()
  render(<InventoryPage />)
  const document = await screen.findByText("TRANSFER-1")
  const table = document.closest("table")!
  const headers = Array.from(table.querySelectorAll("thead th"))
  const sourceIndex = headers.findIndex((header) => header.textContent?.includes("出货仓库"))
  const destinationIndex = headers.findIndex((header) => header.textContent?.includes("入货仓库"))
  const supplierIndex = headers.findIndex((header) => header.textContent?.includes("供应商/收货客户"))
  const transferCells = within(document.closest("tr")!).getAllByRole("cell")
  expect(sourceIndex).toBeGreaterThan(-1)
  expect(sourceIndex).not.toBe(supplierIndex)
  expect(transferCells[sourceIndex]).toHaveTextContent("出货甲仓")
  expect(transferCells[destinationIndex]).toHaveTextContent("入货乙仓")
  expect(transferCells[supplierIndex]).toHaveTextContent("-")
  const purchaseCells = within(screen.getByText("PURCHASE-2").closest("tr")!).getAllByRole("cell")
  expect(purchaseCells[sourceIndex]).toHaveTextContent("-")
  expect(purchaseCells[supplierIndex]).toHaveTextContent("供应商甲")
  for (const row of table.querySelectorAll("tfoot tr")) {
    expect(row.querySelectorAll("td")).toHaveLength(headers.length)
  }
  await user.click(getSortButton("出货仓库"))
  await waitFor(() => expect(listMock).toHaveBeenLastCalledWith(expect.objectContaining({
    sortRules: [{ key: "outbound_warehouse", direction: "desc" }],
  })))
})

test("adds the outbound warehouse column while preserving a saved column order", async () => {
  window.localStorage.setItem("hede.inventory-records.table-column-order.1", JSON.stringify([
    "amount", "document_number", "date", "document_type", "supplier", "total_count",
    "warehouse", "handler", "summary", "updated_at",
  ]))
  render(<InventoryPage />)
  await screen.findByText("SORT-1")
  const labels = screen.getAllByRole("columnheader").map((header) => header.textContent)
  expect(labels[1]).toContain("金额")
  const source = labels.findIndex((label) => label?.includes("出货仓库"))
  expect(labels[source + 1]).toContain("入货仓库")
  expect(screen.getByRole("button", { name: "拖拽排序出货仓库" })).toBeInTheDocument()
})
