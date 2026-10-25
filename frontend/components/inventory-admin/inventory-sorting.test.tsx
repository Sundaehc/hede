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
